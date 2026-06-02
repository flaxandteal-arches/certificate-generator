"""
Version-aware resource loading for certificates.

Composes the single-resource ResourceLoader + ResourceMapper into the data a
template needs. For the "existing vs updated" flow, the user-selected version
provides the normal (updated) data and the finalised (Active) version of the
same group provides the "existing" data, merged in under ``existing_*`` keys.

ResourceLoader and ResourceMapper stay version-agnostic; all versioning concern
(and the only dependency on arches_resource_version_manager) lives here.
"""

import logging
from typing import Any, Dict

from arches_resource_version_manager.models import VersionedResource

from certificate_generator.views.loaders import ResourceLoader
from certificate_generator.views.mappers import ResourceMapper

logger = logging.getLogger(__name__)

# Keys copied from the finalised (Active) version into the selected version's
# data under an ``existing_`` prefix. Whitelisted (not blind-prefixed) so we
# only carry what the templates reference and don't drag unused image bytes.
_EXISTING_KEYS = (
    "boundary_map",
    "main_boundary",
    "descriptions",
    "mapped_lot_on_plan",
)


def _map(resource_id: str) -> Dict[str, Any]:
    return ResourceMapper(ResourceLoader().load(resource_id)).load_resource()


def merge_existing(updated: Dict[str, Any], existing: Dict[str, Any]) -> Dict[str, Any]:
    """Copy the whitelisted keys from ``existing`` into ``updated`` as
    ``existing_<key>``. Mutates and returns ``updated``."""
    for key in _EXISTING_KEYS:
        if key in existing:
            updated[f"existing_{key}"] = existing[key]
    return updated


def build_template_data(selected_resource_id: str, *, include_existing: bool) -> Dict[str, Any]:
    """
    Map the selected resource version. When ``include_existing`` and the group
    has a finalised (Active) version distinct from the selection, also map that
    Active version and merge it in under ``existing_*`` keys.

    Degrades to the plain single-resource mapping when the resource isn't
    versioned or has no (distinct) Active version.
    """
    updated = _map(selected_resource_id)
    if not include_existing:
        return updated

    try:
        group_id = VersionedResource.objects.values_list(
            "resource_group_id", flat=True
        ).get(pk=selected_resource_id)
    except VersionedResource.DoesNotExist:
        return updated  # not versioned

    active = VersionedResource.objects.get_current_final(group_id)
    if active is None or str(active.pk) == str(selected_resource_id):
        return updated  # no finalised version, or the selection is the final one

    existing = _map(str(active.pk))
    return merge_existing(updated, existing)
