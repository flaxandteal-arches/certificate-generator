import math
from pathlib import Path
import re
import resource
from typing import Dict, Any
import json

from quartz.views.utils.image_utils import download_images_batch, load_image
from quartz.views.utils.coordinate_utils import convert_geometry_from_resource

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
                if 'en' in data and len(data) == 1:
                    return data['en']
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

        print("Mapped data after initial extraction:", self.mapped_data)

        # Additional mappings
        self._map_images(self.mapped_data)
        self._map_address(self.mapped_data)
        self._map_geometry(self.mapped_data)
        self._map_lot_on_plan(self.mapped_data)

        with open('mapped_resource.json', 'w', encoding='utf-8') as f:
            json.dump(self.mapped_data, f, ensure_ascii=False, indent=4, default=lambda o: f"<{type(o).__name__}>")

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

        site_plan_terms = ['site plan', 'siteplan', 'site_plan', 'floor plan', 'plan']
        boundary_map_terms = ['boundary map', 'boundary_map', 'boundarymap', 'map', 'boundary']
        
        # Collect all image URLs and batch-download them concurrently
        urls = []
        for image in images:
            url = image.get('preview', [{}])[0].get('url', '')
            if url:
                urls.append(url)
        image_cache = download_images_batch(urls)

        for image in images:
            meta = image.get('_', [{}])[0]
            visibility = image.get('visibility', [])
            name = meta.get('name', '').lower()
            url = image.get('preview', [{}])[0].get('url', '')
            alt_text = meta.get('alt_text', '')
            type = meta.get('type', '')
            if type and type.startswith('video/'):
                continue  # Skip videos
            entry = {'image': image_cache.get(url), 'alt_text': alt_text, 'url': url}

            if not alt_text:
                continue

            if 'Available' not in visibility and 'Public' not in visibility: 
                continue

            is_main = (
                ('Main Image for All Reports' in visibility
                 or 'Main Image for Public Website' in visibility)
                and 'Square Shot' in visibility
            )
            is_main_boundary = (
                'Main Image for Maps' in visibility
                and 'Square Shot' in visibility
            )
            name_or_alt = f"{name} {alt_text.lower()}"
            is_boundary = any(re.search(rf'\b{term}\b', name_or_alt) for term in boundary_map_terms)
            is_site_plan = any(re.search(rf'\b{term}\b', name_or_alt) for term in site_plan_terms)

            if is_main and not resource.get('main_image'):
                resource['main_image'] = entry
            elif is_main_boundary and not resource.get('main_boundary'):
                resource['main_boundary'] = entry
                print("FOUND SQUARE MAP", resource['main_boundary'])
            elif is_boundary:
                resource['boundary_map'].append({**entry, 'type': ['main', 'square']})
            elif is_site_plan:
                resource['site_plan'].append(entry)
            else:
                resource['illustrations'].append(entry)
        
        # if no main image set as the first image
        if 'main_image' not in resource and len(resource['illustrations']) > 0:
            first_url = resource['illustrations'][0]['url']
            alt_text = resource['illustrations'][0]['alt_text']
            resource['main_image'] = {'image': image_cache.get(first_url), 'alt_text': alt_text, 'url': first_url}
        else:
            resource['main_image'] = resource.get('main_image', {'image': None, 'alt_text': '', 'url': ''})

        # set the main boundary image
        if 'main_boundary' not in resource:
            no_map = load_image('no_boundary_map.jpg', Path('static/images'))
            resource['main_boundary'] = {'image': no_map, 'alt_text': 'No boundary map', 'url': ''}

        # check if the main image and boundary image are the same and remove the boundary image if so
        if not resource['main_image']['url'] and resource['main_boundary']['url']:
            resource['main_image'] = resource['main_boundary']
            print("Entered image delete")
            resource['main_boundary'] = {}
            print("Deleted main boundary image as it is the same as the main image", resource['main_boundary'])

    def _map_geometry(self, resource: Dict[str, Any]) -> None:
        """
        Convert geographic coordinates to MGA easting/northing
        and store as a geometry entry on the resource.

        Args:
            resource: The resource dictionary with location_data.
        """
        result = convert_geometry_from_resource(resource)
        if result:
            resource['mapped_geometry'] = result[0]  # Assuming we take the first geometry for simplicity
        else:
            resource['mapped_geometry'] = None

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
            county = addr.get('county', {}).get('county_value', '')
            if street:
                resource['address'] = {
                    'street': street,
                    'town': addr.get('town_or_city', {}).get('town_or_city_value', ''),
                    'postcode': addr.get('postcode', {}).get('postcode_value', ''),
                }
            if county:
                resource['address']['county'] = county
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

        print("Mapped lot on plans:", lot_on_plans)

        resource['mapped_lot_on_plan'] = {
            'column_1': col1,
            'column_2': col2,
            'column_3': col3,
        }

        return resource