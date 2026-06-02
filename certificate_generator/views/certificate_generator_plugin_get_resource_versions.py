"""
Resource version list endpoint.

Given a resource instance id, returns the sibling versions in its version
group (Draft / Active / Retired) so the certificate-generator plugin can offer
a version picker. Resources that aren't under version management (no
VersionedResource row) return is_versioned=false and the caller falls back to
using the resource as-is.
"""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from arches_resource_version_manager.models import VersionedResource

logger = logging.getLogger(__name__)

ACTIVE_STATE = "Active"


class CertificateGeneratorPluginGetResourceVersions(LoginRequiredMixin, View):
    def get(self, request):
        resource_id = request.GET.get("resource_id")
        if not resource_id:
            return JsonResponse({"error": "Missing resource_id"}, status=400)

        try:
            group_id = VersionedResource.objects.values_list(
                "resource_group_id", flat=True
            ).get(pk=resource_id)
        except VersionedResource.DoesNotExist:
            # Not onboarded into version management — caller uses resource as-is.
            return JsonResponse({"is_versioned": False, "versions": []}, status=200)
        except Exception:
            logger.exception("Error resolving version group for %s", resource_id)
            return JsonResponse({"error": "Internal server error"}, status=500)

        siblings = (
            VersionedResource.objects.filter(resource_group_id=group_id)
            .select_related("resourceinstance__resource_instance_lifecycle_state")
            .order_by("created_at")
        )

        versions = []
        active_resource_id = None
        for v in siblings:
            state = str(v.resourceinstance.resource_instance_lifecycle_state.name)
            vid = str(v.pk)
            if state == ACTIVE_STATE:
                active_resource_id = vid
            versions.append({
                "resource_id": vid,
                "version_label": f"{v.major_version}.{v.minor_version}",
                "lifecycle_state": state,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            })

        return JsonResponse({
            "is_versioned": True,
            "has_active": active_resource_id is not None,
            "active_resource_id": active_resource_id,
            "versions": versions,
        }, status=200)
