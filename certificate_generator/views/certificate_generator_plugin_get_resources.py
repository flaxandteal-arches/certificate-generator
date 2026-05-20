"""
Resource picker list endpoint.

Returns Heritage Item resources for the certificate-generator dropdown.
Backed by a single ORM query against ResourceInstance + TileModel:
no tile→tree conversion, no alizarin, no in-memory full-table walk.

Display name comes from ResourceInstance.descriptors (the Arches-indexed
name field). The system reference number ("place_id") is pulled directly
out of the system_reference_numbers tile's JSONB data column.
"""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import OuterRef, Subquery
from django.db.models.fields.json import KT
from django.http import JsonResponse
from django.views import View

from arches.app.models.models import ResourceInstance, TileModel

logger = logging.getLogger(__name__)


# Heritage Item graph
HERITAGE_ITEM_GRAPH_ID = "076f9381-7b00-11e9-8d6b-80000b44d1d9"

# system_reference_numbers nodegroup → primary_reference_number node
# (number datatype). TileModel.data is keyed by node UUID; the number is
# stored as the bare JSON value, not wrapped in an i18n object.
SYSTEM_REF_NODEGROUP_ID = "325a2f2f-efe4-11eb-9b0c-a87eeabdefba"
PRIMARY_REF_NUMBER_NODE_ID = "325a2f33-efe4-11eb-b0bb-a87eeabdefba"


class CertificateGeneratorPluginGetResources(LoginRequiredMixin, View):
    def get(self, request):
        try:
            place_id_sq = (
                TileModel.objects
                .filter(
                    resourceinstance_id=OuterRef("pk"),
                    nodegroup_id=SYSTEM_REF_NODEGROUP_ID,
                )
                .annotate(place_id=KT(f"data__{PRIMARY_REF_NUMBER_NODE_ID}"))
                .values("place_id")[:1]
            )

            qs = (
                ResourceInstance.objects
                .filter(graph_id=HERITAGE_ITEM_GRAPH_ID)
                .annotate(
                    display_name=KT("descriptors__en__name"),
                    place_id=Subquery(place_id_sq),
                )
                .values("resourceinstanceid", "display_name", "place_id")
                .order_by("place_id", "display_name")
            )

            resources = [
                {
                    "resource_id": str(row["resourceinstanceid"]),
                    "name": row["display_name"] or "",
                    "place_id": row["place_id"] or "",
                }
                for row in qs
            ]
            return JsonResponse({"resources": resources}, status=200)

        except Exception:
            logger.exception("Error listing resources")
            return JsonResponse({"error": "Internal server error"}, status=500)
