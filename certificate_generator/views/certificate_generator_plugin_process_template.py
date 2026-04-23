import json
import logging
import base64
import datetime
from django.http import HttpResponse, JsonResponse
from django.views import View
from pathlib import Path
from docx import settings

from certificate_generator.views.services import document_service, resource_service
from certificate_generator.views.loaders.data_loader import DataLoader
from certificate_generator.views.registry.template_registry import TemplateRegistry

class CertificateGeneratorPluginProcessTemplate(View):
    def post(self, req):
        """Process a document template with resource data"""
        logging.info('Processing document template')

        try:
            if req.body:
                req_body = json.loads(req.body)
                resource_id = req_body.get('resource_id')
                resource_name = req_body.get('resource_name')
                template_id = req_body.get('template_id')
                template_version = req_body.get('template_version')

            if not resource_id or not template_id:
                return JsonResponse(
                    json.dumps({"error": "Missing required fields: resource_id and template_id"}),
                    mimetype="application/json",
                    status_code=400
                )

            data_loader = DataLoader()
            resource_svc = resource_service.ResourceService(data_loader)
            BASE_DIR = Path(__file__).parent.parent
            TEMPLATES_DIR = BASE_DIR / "report_templates"
            document_service_svc = document_service.DocumentService(TemplateRegistry(TEMPLATES_DIR))
            # Business logic delegated to services
            data_loader.load_resources()
            data = resource_svc.get_mapped_resource(resource_id)
            template_path = document_service_svc.resolve_template(template_id, template_version)
            document_bytes = document_service_svc.generate_document(template_path, data)

            # Build response filename
            version = int(template_version) if template_version is not None else None
            version_suffix = f"_v{version}" if version else ""
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{resource_name}_{template_id}_{version_suffix}_{timestamp}.docx"

            response = HttpResponse(
                document_bytes,
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        except KeyError as e:
            return JsonResponse(
                {"error": str(e)},
                status=404
            )

        except FileNotFoundError as e:
            return JsonResponse(
                {"error": str(e)},
                status=404
            )

        except ValueError as e:
            logging.error(f"Invalid JSON in request body: {e}")
            return JsonResponse(
                {"error": "Invalid JSON in request body", "details": str(e)},
                status=400
            )

        except Exception as e:
            logging.error(f"Error processing template: {e}", exc_info=True)
            return JsonResponse(
                {"error": "Internal server error", "details": str(e)},
                status=500
            )