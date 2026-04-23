from pathlib import Path
from typing import Dict, Any
import json
import logging
import alizarin
from django.core import serializers
from arches.app.models.models import ResourceInstance, TileModel
from arches.app.models.graph import Graph
from itertools import groupby
from operator import itemgetter

class DataLoader:
    """Utility class for loading resource data"""

    def __init__(self):
        self._resources: Dict[str, Dict[str, Any]] | None = None

    def _register_graphs(self):
        """Register all graphs that are marked as resources and build the resource list"""
        resource_list = []
        graphs_processed = {}

        for r in ResourceInstance.objects.filter(graph__isresource=True):
            graph_id = str(r.graph_id)
            
            # Register graph once per graph_id
            if graph_id not in graphs_processed:
                graph = Graph.objects.get(pk=r.graph_id)
                serialized = graph.serialize()
                graph_json = json.dumps({"graph": [serialized]})
                static_graph = alizarin.register_graph(graph_json)
                graphs_processed[graph_id] = static_graph

            tiles = list(
                TileModel.objects.filter(resourceinstance=r).values(
                    'tileid',
                    'data',
                    'nodegroup_id',
                    'parenttile_id',
                    'resourceinstance_id',
                )
            )

            for tile in tiles:
                tile['tileid'] = str(tile['tileid'])
                tile['nodegroup_id'] = str(tile['nodegroup_id'])
                tile['resourceinstance_id'] = str(tile['resourceinstance_id'])
                if tile['parenttile_id']:
                    tile['parenttile_id'] = str(tile['parenttile_id'])

            resource_list.append({
                "resourceinstanceid": str(r.resourceinstanceid),
                "graph_id": graph_id,
                "tiles": tiles,
            })
        

        return resource_list
    
    def load_resources(self):
        resource_list = self._register_graphs()
        sorted_resources = sorted(resource_list, key=itemgetter('graph_id'))
        all_results = []

        for graph_id, group in groupby(sorted_resources, key=itemgetter('graph_id')):
            group_list = list(group)
            result = alizarin.batch_tiles_to_trees(
                json.dumps(group_list),
            )

            if result.get('success') or result.get('results'):
                all_results.extend(result['results'])

        mapped_resources = {r["resourceinstanceid"]: r for r in all_results}
        self._resources = mapped_resources
        logging.info("Loaded %d resources", len(mapped_resources))
        return mapped_resources

    
    def get_resource(self, resource_id: str) -> Dict[str, Any]:
        """Get a single resource by its resourceinstanceid"""
        if self._resources is None:
            raise ValueError("Resources not loaded. Call load_resources() first.")
        
        return self._resources.get(resource_id, {})
    
    def get_all_resources(self) -> Dict[str, Dict[str, Any]]:
        """Get all loaded resources"""
        if self._resources is None:
            raise ValueError("Resources not loaded. Call load_resources() first.")
        
        return self._resources

    def resolve_related_resources(self, resource_data, all_resources):
        """
        Resolve related resource UUIDs to full resource data
        
        Args:
            resource_data: The main resource dict
            all_resources: Dict of all resources keyed by resourceinstanceid
            config: Configuration dict with 'expand' list
            
        Returns:
            Resource data with related_resources expanded to full objects
        """
        resolved = resource_data.copy()
        related_resources = resource_data.get("related_resources", [])
        
        if not related_resources:
            resolved["related_resources"] = []
            return resolved
    
        resolved_related = []
        for related_ref in related_resources:
            alias = related_ref.get("alias")
            resource_id = related_ref.get("resourceinstanceid")
            
            # Look up the related resource
            related_resource = all_resources.get(resource_id)
            
            if related_resource:
                # Create the expanded related resource structure
                resolved_related.append({
                    "alias": alias,
                    "name": related_resource.get("name", ""),
                    "resource_id": resource_id,
                    "resource_type": related_resource.get("graph_name", ""),
                    "graph_name": related_resource.get("graph_name", ""),
                    "fields": related_resource.get("fields", {})
                })
            else:
                logging.warning(f"Related resource not found: {resource_id}")
        
        resolved["related_resources"] = resolved_related
        return resolved
