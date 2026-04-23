"""
Resource service - business logic for loading and listing resources.
"""

import logging
from typing import Any, Dict, List

from certificate_generator.views.loaders import DataLoader
from certificate_generator.views.mappers import ResourceMapper
class ResourceService:

    def __init__(self, data_loader: DataLoader):
        self.data_loader = data_loader

    def list_resources(self) -> List[Dict[str, Any]]:
        """Return a summary list of all available resources."""
        all_resources = self.data_loader.get_all_resources()
        resources = []
        for resource_id, resource_data in all_resources.items():
            resources.append({
                "resource_id": resource_id,
                "place_id": resource_data.get("system_reference_numbers", {}).get("uuid", {}).get("resourceid", {}).get("en", ""),
                "name": resource_data.get("_name", resource_id),
                "resourceinstanceid": resource_data.get("resourceinstance", {}).get("resourceinstanceid", ""),
                "graph_id": resource_data.get("graph_id", ""),
                "graph_name": resource_data.get("graph_id", ""),
                "fields_count": len(resource_data.keys()),
            })

        return resources

    def get_mapped_resource(self, resource_id: str) -> Dict[str, Any]:
        """
        Load a resource, resolve its related resources, and run it through
        the mapper to produce a flat context dict ready for template rendering.

        Raises:
            KeyError: If the resource_id is not found.
        """
        resource_data = self.data_loader.get_resource(resource_id)
        if not resource_data:
            raise KeyError(f"Resource not found: {resource_id}")

        resolved_data = self.data_loader.resolve_related_resources(
            resource_data,
            self.data_loader.get_all_resources(),
        )

        mapper = ResourceMapper(resolved_data)
        return mapper.load_resource()