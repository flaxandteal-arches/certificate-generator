import logging
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from pathlib import Path

from certificate_generator.views.registry.template_registry import TemplateRegistry

logger = logging.getLogger(__name__)


class CertificateGeneratorPluginGetTemplates(LoginRequiredMixin, View):

    def get(self, request):
        """List available document templates with version info"""
        logger.info('Listing available templates')

        try:
            include_drafts = request.GET.get("include_drafts", "false").lower() == "true"
            include_archived = request.GET.get("include_archived", "false").lower() == "true"
            BASE_DIR = Path(__file__).parent.parent
            TEMPLATES_DIR = BASE_DIR / "report_templates"
            template_registry = TemplateRegistry(TEMPLATES_DIR)
            templates = template_registry.list_templates(
                include_drafts=include_drafts,
                include_archived=include_archived,
            )

            return JsonResponse({"templates": templates}, safe=False)

        except Exception:
            logger.exception("Error listing templates")
            return JsonResponse(
                {"error": "Internal server error"},
                safe=False,
                status=500,
            )
