import datetime
import json
import logging
import re

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.views import View
from pathlib import Path
from certificate_generator.views.services import document_service
from certificate_generator.views.loaders import ResourceLoader
from certificate_generator.views.mappers import ResourceMapper
from certificate_generator.views.registry.template_registry import TemplateRegistry

logger = logging.getLogger(__name__)


class CertificateGeneratorPluginProcessTemplate(LoginRequiredMixin, View):
    def post(self, req):
        """Process a document template with resource data"""
        logger.info('Processing document template')

        try:
            if not req.body:
                return JsonResponse(
                    {"error": "Missing request body"},
                    status=400,
                )

            req_body = json.loads(req.body)
            resource_id = req_body.get('resource_id')
            resource_name = req_body.get('resource_name')
            template_id = req_body.get('template_id')
            template_version = req_body.get('template_version')

            if not resource_id or not template_id:
                return JsonResponse(
                    {"error": "Missing required fields: resource_id and template_id"},
                    status=400,
                )

            version = None
            if template_version is not None and template_version != "":
                try:
                    version = int(template_version)
                except (TypeError, ValueError):
                    return JsonResponse(
                        {"error": "template_version must be an integer"},
                        status=400,
                    )

            BASE_DIR = Path(__file__).parent.parent
            TEMPLATES_DIR = BASE_DIR / "report_templates"
            document_service_svc = document_service.DocumentService(TemplateRegistry(TEMPLATES_DIR))

            # Fetch + convert only the selected resource via the Arches ORM
            # and alizarin.tiles_to_json_tree, instead of batch-converting the
            # whole DB.
            resource_tree = ResourceLoader().load(resource_id)
            data = ResourceMapper(resource_tree).load_resource()
            # Resolve concept leaves to their labels (language already handled in ResourceMapper).
            mapped_data = resolve_concepts(data)

            template_path = document_service_svc.resolve_template(template_id, version)
            document_bytes = document_service_svc.generate_document(template_path, mapped_data)

            # Build response filename. Sanitize the client-supplied resource
            # name so it can't inject Content-Disposition headers or path
            # separators.
            safe_name = re.sub(r'[^\w\-. ]+', '_', (resource_name or '')).strip() or 'document'
            version_suffix = f"_v{version}" if version is not None else ""
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_name}_{template_id}{version_suffix}_{timestamp}.docx"

            response = HttpResponse(
                document_bytes,
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        except KeyError as e:
            return JsonResponse({"error": str(e)}, status=404)

        except FileNotFoundError as e:
            return JsonResponse({"error": str(e)}, status=404)

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in request body: %s", e)
            return JsonResponse(
                {"error": "Invalid JSON in request body"},
                status=400,
            )

        except Exception:
            logger.exception("Error processing template")
            return JsonResponse(
                {"error": "Internal server error"},
                status=500,
            )


def resolve_concepts(data):
    """Collapse concept leaves ({'_': [[id, label], ...]}) to their label and recurse."""
    if isinstance(data, dict):
        if '_' in data:
            raw = data['_']
            if isinstance(raw, list) and raw:
                first = raw[0]
                if isinstance(first, list) and len(first) == 2:
                    return first[1]
                if isinstance(first, str):
                    return first
            return raw

        return {k: resolve_concepts(v) for k, v in data.items()}

    if isinstance(data, list):
        return [resolve_concepts(item) for item in data]

    return data
