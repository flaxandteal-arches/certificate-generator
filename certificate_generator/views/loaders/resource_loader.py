"""
Single-resource loader.

Fetches one resource through the Arches ORM and converts it to a tree via
alizarin.tiles_to_json_tree.
"""

import json
import logging
from typing import Any, Dict

import alizarin

from arches.app.models.graph import Graph
from arches.app.models.models import ResourceInstance, TileModel


# Process-wide cache of graphs already registered with alizarin. The Rust
# side de-dupes registrations, but reserialising the graph for every request
# is wasted work.
_REGISTERED_GRAPHS: Dict[str, str] = {}


def _ensure_graph_registered(graph_id: str) -> str:
    """Register the graph with alizarin if it hasn't been yet, return the handle."""
    handle = _REGISTERED_GRAPHS.get(graph_id)
    if handle is not None:
        return handle
    graph = Graph.objects.get(pk=graph_id)
    graph_json = json.dumps({"graph": [graph.serialize()]})
    handle = alizarin.register_graph(graph_json)
    _REGISTERED_GRAPHS[graph_id] = handle
    return handle


def _serialise_tiles(tiles):
    """Stringify UUID fields on tile rows in place."""
    for tile in tiles:
        tile['tileid'] = str(tile['tileid'])
        tile['nodegroup_id'] = str(tile['nodegroup_id'])
        tile['resourceinstance_id'] = str(tile['resourceinstance_id'])
        if tile['parenttile_id']:
            tile['parenttile_id'] = str(tile['parenttile_id'])
    return tiles


class ResourceLoader:
    """Per-request loader for a single resource."""

    def load(self, resource_id: str) -> Dict[str, Any]:
        """
        Fetch a single resource via the Arches ORM and convert it to a tree
        using alizarin.tiles_to_json_tree.

        Raises:
            KeyError: if the resource_id is not found.
        """
        try:
            instance = ResourceInstance.objects.get(pk=resource_id)
        except ResourceInstance.DoesNotExist as e:
            raise KeyError(f"Resource not found: {resource_id}") from e

        graph_id = str(instance.graph_id)
        _ensure_graph_registered(graph_id)

        tiles = _serialise_tiles(list(
            TileModel.objects.filter(resourceinstance_id=resource_id).values(
                'tileid', 'data', 'nodegroup_id', 'parenttile_id', 'resourceinstance_id',
            )
        ))

        payload = {
            "resourceinstanceid": str(instance.resourceinstanceid),
            "graph_id": graph_id,
            "tiles": tiles,
        }
        tree = alizarin.tiles_to_json_tree(json.dumps(payload))
        logging.info("Loaded resource %s (graph %s, %d tiles)", resource_id, graph_id, len(tiles))
        return tree
