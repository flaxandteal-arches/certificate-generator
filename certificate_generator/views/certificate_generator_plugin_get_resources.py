from arches.app.models.models import ResourceInstance
import json
import logging
from django.http import JsonResponse
from django.views import View
from pathlib import Path
from certificate_generator.views.services import resource_service
from certificate_generator.views.loaders.data_loader import DataLoader

class CertificateGeneratorPluginGetResources(View):

    def get(self, request):
        """List available resources"""

        try:
            data_loader = DataLoader()
            resource_svc = resource_service.ResourceService(data_loader)
            data_loader.load_resources()
            resource_list = resource_svc.list_resources()
            return JsonResponse({"resources": resource_list}, status=200)


        except Exception as e:
            logging.error(f"Error listing resources: {e}")
            return JsonResponse(
                {"error": str(e)},
                safe=False,
                status=500
            )