import logging
import math
from pathlib import Path
from typing import Dict, Any

from certificate_generator.views.utils.image_utils import (
    download_images_batch,
    load_image,
    iiif_identifier_from_url,
    build_iiif_url,
)
from certificate_generator.views.utils.coordinate_utils import convert_geometry_from_resource

logger = logging.getLogger(__name__)

# Square IIIF crop framing the parcel on A4-portrait boundary-map sheets,
# trimming the title/legend chrome. Set the left/right edges and the top edge
# (all % of page); the square's side is (right - left) and the height auto-
# derives from the page aspect so the crop is always square.
_BOUNDARY_LEFT = 8.5    # left edge, % across (↑ pulls the left side in)
_BOUNDARY_RIGHT = 86.0  # right edge, % across (↓ pulls the right side in)
_BOUNDARY_TOP = 12.0    # top edge, % down  (↑ moves the square down the page)
_PAGE_ASPECT = 2481 / 3506
_BOUNDARY_WIDTH = _BOUNDARY_RIGHT - _BOUNDARY_LEFT
BOUNDARY_MAP_REGION = (
    f"pct:{_BOUNDARY_LEFT},{_BOUNDARY_TOP},"
    f"{_BOUNDARY_WIDTH},{round(_BOUNDARY_WIDTH * _PAGE_ASPECT, 2)}"
)


class ResourceMapper:
    def __init__(self, resource_data: Dict[str, Any]):
        self.resource_data = resource_data
        self.mapped_data = {}

    def load_resource(self) -> Dict[str, Any]:
        """Load the resource data"""
        self._get_value_data_json()
        return self.mapped_data

    def _get_value_data_json(self) -> Dict[str, Any]:
        """
        Extracts and returns the value data from the resource JSON structure.
        """
        def extract_values(data: Any) -> Any:
            if isinstance(data, dict):
                # Arches i18n string leaf: {"value": "...", "direction": "ltr"}
                if 'value' in data and 'direction' in data:
                    return data['value']
                # Language map: {"en": {"value": ..., "direction": ...}, ...}
                if 'en' in data and len(data) == 1:
                    return extract_values(data['en'])
                elif 'labels' in data:
                    labels = data.get('labels', [])
                    labels_list = [label.get('value') for label in labels]
                    return labels_list[0] if len(labels_list) == 1 else labels_list
                else:
                    # Process ALL keys, not just one
                    return {key: extract_values(value) for key, value in data.items()}
            elif isinstance(data, list):
                return [extract_values(item) for item in data]
            else:
                return data

        self.mapped_data = extract_values(self.resource_data)

        # Additional mappings
        self._map_images(self.mapped_data)
        self._map_address(self.mapped_data)
        self._map_geometry(self.mapped_data)
        self._map_lot_on_plan(self.mapped_data)

    def _map_images(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """
        Identify image fields in the context and map them appropriately.

        Args:
            context: The context dictionary with potential image fields.
        """
        images = resource.get('images', [])
        if not images:
            return resource

        resource['boundary_map'] = []
        resource['site_plan'] = []
        resource['illustrations'] = []
        # Classify each image into a slot by its RDM visibility tags. `url` is
        # the stored download URL; `name`/`path` is the filename IIIF addresses by.
        for image in images:
            meta = image.get('_', [{}])[0]
            visibility = image.get('visibility', [])
            url = meta.get('url', '')
            filename = meta.get('path') or meta.get('name') or ''
            alt_text = meta.get('altText') or meta.get('alt_text') or ''
            type = meta.get('type', '')
            if type and type.startswith('video/'):
                continue  # Skip videos
            entry = {'alt_text': alt_text, 'url': url, 'filename': filename}

            if 'Available' not in visibility and 'Public' not in visibility:
                continue

            is_main = (
                'Main Image for All Reports' in visibility
                or 'Main Image for Public Website' in visibility
            )
            is_main_boundary = 'Main Image for Maps' in visibility
            is_boundary = 'Boundary Map' in visibility
            is_site_plan = 'Site Plan' in visibility

            if is_main and not resource.get('main_image'):
                resource['main_image'] = entry
            elif is_main_boundary and not resource.get('main_boundary'):
                resource['main_boundary'] = entry
            elif is_boundary:
                resource['boundary_map'].append({**entry, 'type': ['main', 'square']})
            elif is_site_plan:
                resource['site_plan'].append(entry)
            else:
                resource['illustrations'].append(entry)

        # if no main image, fall back to the first illustration
        if 'main_image' not in resource and len(resource['illustrations']) > 0:
            resource['main_image'] = dict(resource['illustrations'][0])
        else:
            resource['main_image'] = resource.get('main_image', {'alt_text': '', 'url': ''})

        # Fetch image bytes from IIIF, cropping per kind: main photo -> centred
        # square; boundary maps -> framed square; everything else -> uncropped.
        square_entries = [resource['main_image']]
        boundary_entries = []
        if resource.get('main_boundary'):
            boundary_entries.append(resource['main_boundary'])
        boundary_entries += resource['boundary_map']
        full_entries = resource['site_plan'] + resource['illustrations']
        self._attach_iiif_images(square_entries, region='square')
        self._attach_iiif_images(boundary_entries, region=BOUNDARY_MAP_REGION)
        self._attach_iiif_images(full_entries, region='full')

        # set the main boundary placeholder if there isn't one
        if 'main_boundary' not in resource:
            no_map = load_image('no_boundary_map.jpg', Path('static/images'))
            resource['main_boundary'] = {'image': no_map, 'alt_text': 'No boundary map', 'url': ''}

        # if there's no main image but there is a boundary, use the boundary as the main image
        if not resource['main_image'].get('url') and resource['main_boundary'].get('url'):
            resource['main_image'] = resource['main_boundary']
            resource['main_boundary'] = {}

    def _attach_iiif_images(self, entries, region):
        """
        Populate each entry's ``image`` (BytesIO) from the IIIF image server,
        cropping per ``region``. IIIF is the single source of truth: an image
        IIIF can't serve gets ``image=None`` and is skipped at render time.
        Mutates the entries in place.
        """
        if not entries:
            return

        # Filename-based IIIF URLs via the public /iiifserver proxy. Prefer the
        # explicit filename; fall back to the last path segment of the stored
        # URL (handles blob URLs whose segment is the filename).
        for entry in entries:
            identifier = entry.get('filename') or iiif_identifier_from_url(entry.get('url', ''))
            entry['_iiif_url'] = build_iiif_url(identifier, region=region)
        iiif_cache = download_images_batch([e['_iiif_url'] for e in entries if e.get('_iiif_url')])

        for entry in entries:
            entry['image'] = iiif_cache.get(entry.pop('_iiif_url', ''))

    def _map_geometry(self, resource: Dict[str, Any]) -> None:
        """
        Convert geographic coordinates to MGA easting/northing
        and store as a geometry entry on the resource.

        Args:
            resource: The resource dictionary with location_data.
        """
        result = convert_geometry_from_resource(resource)
        # Templates currently render a single point; if multiple geometries are
        # present we only surface the first. Expose the full list if templates
        # ever need them.
        resource['mapped_geometry'] = result[0] if result else None

    def _map_address(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map address fields from the resource data.

        Args:
            resource: The resource dictionary with potential address fields.
        """
        addresses = resource.get('location_data', {}).get('addresses', [])
        if not addresses:
            resource['address'] = None
            return resource

        resource['address'] = {'street': '', 'town': '', 'county': '', 'postcode': ''}
        for addr in addresses:
            street = addr.get('street', {}).get('street_value', '')
            lga = (addr.get('lga') or [''])[0]
            town = (addr.get('suburbs') or [''])[0]
            if street:
                resource['address'] = {
                    'street': street,
                    'town': town,
                    'postcode': addr.get('postcode', {}).get('postcode_value', ''),
                }
            if lga:
                resource['address']['county'] = lga
        return resource 
    
    def _map_lot_on_plan(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map lot on plan fields from the resource data.

        Args:
            resource: The resource dictionary with potential lot on plan fields.
        """
        area_assignments = resource.get('location_data', {}).get('area_assignments', {}).get('area_assignment', [])
        if not area_assignments:
            resource['mapped_lot_on_plan'] = None
            return resource
        
        lot_on_plans = []
        for assignment in area_assignments:
            for lop in assignment.get('lot_on_plan', []):
                lot = lop.get('lot', '')
                plan = lop.get('plan', '')
                if lot and plan:
                    lot_on_plans.append(f'{lot} {plan}')
        
        third = math.ceil(len(lot_on_plans) / 3)
        col1 = lot_on_plans[:third]
        col2 = lot_on_plans[third:2*third]
        col3 = lot_on_plans[2*third:]

        resource['mapped_lot_on_plan'] = {
            'column_1': col1,
            'column_2': col2,
            'column_3': col3,
        }

        return resource