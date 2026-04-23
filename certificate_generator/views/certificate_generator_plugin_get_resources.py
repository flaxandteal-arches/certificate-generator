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
        """List available resources"""

        try:
            data_loader = DataLoader()
            resource_svc = resource_service.ResourceService(data_loader)
            data_loader.load_resources()
            logger = logging.getLogger(__name__)
            resource_list = resource_svc.list_resources()
            logger.error("Got the data")
            logger.error("Got the data")
            logger.error("Got the data")
            logger.error("Got the data")
            logger.error("Got the data")
            logger.error("Got the data")
            return JsonResponse({"resources": resource_list}, status=200)


        except Exception as e:
            logging.error(f"Error listing resources: {e}")
            return JsonResponse(
                {"error": str(e)},
                safe=False,
                status=500
            )