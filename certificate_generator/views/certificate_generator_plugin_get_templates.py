import json
import logging
from django.http import JsonResponse
from django.views import View
from pathlib import Path

from certificate_generator.views.registry.template_registry import TemplateRegistry

class CertificateGeneratorPluginGetTemplates(View):

    def get(self, request):
        """List available document templates with version info"""
        logging.info('Listing available templates')

        try:
            print('Listing available templates')
            include_drafts = request.GET.get("include_drafts", "false").lower() == "true"
            include_archived = request.GET.get("include_archived", "false").lower() == "true"
            BASE_DIR = Path(__file__).parent.parent
            TEMPLATES_DIR = BASE_DIR / "report_templates"
            template_registry = TemplateRegistry(TEMPLATES_DIR)
            templates = template_registry.list_templates(
                include_drafts=include_drafts,
                include_archived=include_archived,
            )

            return JsonResponse(
                {"templates": templates},
                safe=False
            )

        except Exception as e:
            logging.error(f"Error listing templates: {e}")
            return JsonResponse(
                {"error": str(e)},
                safe=False,
                status=500
            )