import logging
import math
import re
from pathlib import Path
from typing import Dict, Any

from django.conf import settings

from certificate_generator.views.utils.image_utils import (
    download_images_batch,
    load_image,
    iiif_identifier_from_url,
    iiif_image_size,
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

_A4_ASPECT_TOLERANCE = 0.06  # how far a sheet may stray from A4 portrait

# Fail-safe name/caption terms. Classification is driven by RDM visibility tags
# ('Boundary Map' / 'Site Plan'), but legacy resources predate the tagging and
# carry none, so they'd fall through to illustrations. When the relevant tag is
# absent we fall back to the pre-tag behaviour: word-match the filename/caption.
_SITE_PLAN_TERMS = ['site plan', 'siteplan', 'site_plan', 'floor plan', 'plan']
_BOUNDARY_MAP_TERMS = ['boundary map', 'boundary_map', 'boundarymap', 'map', 'boundary']
_SQUARE_TERMS = ['square', 'sq']


def _name_matches(text: str, terms) -> bool:
    """True if any term appears as a whole word in text (case-insensitive)."""
    text = text.lower()
    return any(re.search(rf'\b{re.escape(term)}\b', text) for term in terms)


def _is_a4_portrait(width: int, height: int) -> bool:
    """True if a pixel size is ~A4 portrait (taller than wide, aspect near _PAGE_ASPECT)."""
    if not width or not height or width >= height:
        return False
    return abs((width / height) - _PAGE_ASPECT) <= _A4_ASPECT_TOLERANCE


def _i18n_value(node: Dict[str, Any]) -> str:
    """Collapse an Arches i18n node {lang: {value, direction}} to the settings language, else en, else any."""
    for lang in (getattr(settings, 'LANGUAGE_CODE', None), 'en'):
        if lang and node.get(lang, {}).get('value'):
            return node[lang]['value']
    for leaf in node.values():
        if leaf.get('value'):
            return leaf['value']
    return ''


def _caption(image: Dict[str, Any]) -> str:
    """The image caption, read from the images nodegroup's captions.caption node."""
    caption = image.get('captions', {}).get('caption', '')
    return caption if isinstance(caption, str) else ''


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
                # Arches multilingual node {lang: {value, direction}}: collapse to one language now.
                if data and all(
                    isinstance(v, dict) and 'value' in v and 'direction' in v
                    for v in data.values()
                ):
                    return _i18n_value(data)
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
            # Caption node; fall back to the file's own altText/alt_text.
            alt_text = (
                _caption(image)
                or meta.get('altText') or meta.get('alt_text') or ''
            )
            type = meta.get('type', '')
            if type and type.startswith('video/'):
                continue  # Skip videos
            entry = {'alt_text': alt_text, 'url': url, 'filename': filename}

            if 'Available' not in visibility:
                continue

            is_main = 'Main Image for All Reports' in visibility
            
            is_main_boundary = 'Main Image for Maps' in visibility
            is_boundary = 'Boundary Map' in visibility
            is_site_plan = 'Site Plan' in visibility
            is_report = 'Report' in visibility
            name_or_alt = f"{filename} {alt_text}"

            # Fail-safe for legacy resources never tagged: if neither map/plan
            # tag is present, fall back to word-matching the filename/caption.
            if not is_boundary and not is_site_plan:
                is_boundary = _name_matches(name_or_alt, _BOUNDARY_MAP_TERMS)
                is_site_plan = _name_matches(name_or_alt, _SITE_PLAN_TERMS)

            is_square = (
                'Square' in visibility
                or 'Square Shot' in visibility
                or _name_matches(name_or_alt.replace('_', ' '), _SQUARE_TERMS)
            )
            # Slots are non-exclusive: one image may carry several visibility
            # tags (e.g. both "Main Image for All Reports" and "Boundary Map")
            # and must then appear in every slot it's tagged for. Each slot gets
            # its own copy because _attach_iiif_images mutates an entry's `image`
            # in place per crop region, so a shared dict would have its first
            # crop clobbered by the second.
            matched = False
            if is_main and not resource.get('main_image'):
                resource['main_image'] = dict(entry)
                matched = True
            if is_main_boundary and not resource.get('main_boundary'):
                resource['main_boundary'] = dict(entry)
                matched = True
            if is_boundary and not is_square:
                resource['boundary_map'].append({**entry, 'type': ['main', 'square']})
                matched = True
            if is_site_plan and not is_square:
                resource['site_plan'].append(dict(entry))
                matched = True
            if is_report and not is_square:
                resource['illustrations'].append(dict(entry))

        # if no main image, fall back to the first illustration
        if 'main_image' not in resource and len(resource['illustrations']) > 0:
            resource['main_image'] = dict(resource['illustrations'][0])
        else:
            resource['main_image'] = resource.get('main_image', {'alt_text': '', 'url': ''})

        square_entries = [resource['main_image']]

        # main_boundary falls back to the first Boundary Map; a copy so it can be cropped independently.
        if not resource.get('main_boundary') and resource['boundary_map']:
            resource['main_boundary'] = dict(resource['boundary_map'][0])
            
        full_entries = resource['boundary_map'] + resource['site_plan'] + resource['illustrations']
        self._attach_iiif_images(square_entries, region='square')
        self._attach_iiif_images(full_entries, region='full')

        # Front-page main map: chrome-trim crop only for A4-portrait sheets, else centred square.
        main_boundary = resource.get('main_boundary')
        if main_boundary:
            identifier = (
                main_boundary.get('filename')
                or iiif_identifier_from_url(main_boundary.get('url', ''))
            )
            size = iiif_image_size(identifier) if identifier else None
            region = BOUNDARY_MAP_REGION if size and _is_a4_portrait(*size) else 'square'
            self._attach_iiif_images([main_boundary], region=region)

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
        empty_address = {'street': '', 'town': '', 'county': '', 'postcode': ''}
        addresses = resource.get('location_data', {}).get('addresses', [])
        if not addresses:
            resource['address'] = empty_address
            return resource

        resource['address'] = dict(empty_address)
        for addr in addresses:
            street = addr.get('street', {}).get('street_value', '')
            lga = (addr.get('lga') or [''])[0]
            town = (addr.get('suburbs') or [''])[0]
            if street:
                resource['address'] = {
                    'street': street,
                    'town': town,
                    'county': resource['address'].get('county', ''),
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
        lot_on_plan_entries = resource.get('location_data', {}).get('lot_on_plan', [])
        if isinstance(lot_on_plan_entries, dict):  # single tile collapses to a dict
            lot_on_plan_entries = [lot_on_plan_entries]
        if not lot_on_plan_entries:
            resource['mapped_lot_on_plan'] = None
            return resource

        lot_on_plans = []
        for lop in lot_on_plan_entries:
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