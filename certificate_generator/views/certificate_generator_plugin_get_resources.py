from arches.app.models.models import ResourceInstance
import json
import logging
from django.http import JsonResponse
from django.views import View
from pathlib import Path
from certificate_generator.views import resource_service
from certificate_generator.views.loaders.data_loader import DataLoader
from certificate_generator.views.template_registry import TemplateRegistry

class CertificateGeneratorPluginGetResources(View):

    def get(self, request):
        """List available document templates with version info"""
        logging.info('Listing available templates')

        try:
            base_dir = Path(__file__).parent
            data_loader = DataLoader(
                resource_file=base_dir / "t_output_df_only_1.json",
                graphs_dir=base_dir / "pkg" / "graphs" / "resource_models",
            )
            resource_svc = resource_service.ResourceService(data_loader)
            list_resources = data_loader.load_resources()
            resource_list = resource_svc.list_resources()
            return JsonResponse({"resources": resource_list}, status=200)


        except Exception as e:
            logging.error(f"Error listing resources: {e}")
            return JsonResponse(
                {"error": str(e)},
                safe=False,
                status=500
            )