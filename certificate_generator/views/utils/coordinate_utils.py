"""
Utility functions for converting geographic coordinates (WGS84 longitude/latitude)
to projected coordinates (MGA easting/northing).

Supports automatic zone detection for MGA2020 (GDA2020) and MGA94 (GDA94).
"""

import logging
import math
from typing import Dict, Any, Optional

from pyproj import Transformer


# EPSG base codes for each datum
_EPSG_BASE = {
    "GDA2020": 7800,
    "GDA94": 28300,
}


def get_mga_zone(longitude: float) -> int:
    """
    Calculate the MGA/UTM zone number from a longitude value.

    Args:
        longitude: Longitude in decimal degrees.

    Returns:
        The MGA zone number (e.g. 55 or 56).
    """
    return math.floor((longitude + 180) / 6) + 1


def get_epsg_code(longitude: float, datum: str) -> Optional[int]:
    """
    Get the EPSG code for the appropriate MGA zone and datum.

    Args:
        longitude: Longitude in decimal degrees.
        datum: The geodetic datum, either "GDA2020" or "GDA94".

    Returns:
        The EPSG code (e.g. 7856 for GDA2020 Zone 56).

    Returns None if the datum is not supported.
    """
    base = _EPSG_BASE.get(datum)
    if base is None:
        logging.warning(f"Unsupported datum '{datum}'. Supported: {list(_EPSG_BASE.keys())}")
        return None
    zone = get_mga_zone(longitude)
    return base + zone


def convert_to_mga(
    longitude: float,
    latitude: float,
    datum: str,
) -> Optional[Dict[str, Any]]:
    """
    Convert WGS84 longitude/latitude to MGA easting/northing.

    Automatically determines the correct MGA zone from the longitude.

    Args:
        longitude: Longitude in decimal degrees (WGS84).
        latitude: Latitude in decimal degrees (WGS84).
        datum: The target geodetic datum, either "GDA2020" or "GDA94".

    Returns:
        Dictionary with easting, northing, zone, datum, and epsg keys.
    """
    zone = get_mga_zone(longitude)
    epsg = get_epsg_code(longitude, datum)
    
    if epsg is None:
        return None

    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    easting, northing = transformer.transform(longitude, latitude)

    logging.info(
        "Converted (%.6f, %.6f) to MGA Zone %d (%s): E %.2f, N %.2f",
        longitude, latitude, zone, datum, easting, northing,
    )

    return {
        "easting": round(easting, 2),
        "northing": round(northing, 2),
        "zone": zone,
        "datum": datum,
        "epsg": epsg,
    }


def convert_geometry_from_resource(resource: Dict[str, Any]) -> list:
    """
    Extract coordinates and datum from a mapped resource's location_data
    and convert to MGA easting/northing.

    Expects the resource structure:
        location_data.geometry.geospatial_coordinates.features[].geometry.coordinates
        location_data.geometry.current_base_map.current_base_map_names.current_base_map_name

    Args:
        resource: The mapped resource dictionary.

    Returns:
        List of dicts with easting, northing, zone, datum, and epsg keys.
        Geometries that fail conversion (bad datum, missing coords) are skipped.
    """
    geometry_list = resource.get("location_data", {}).get("geometry", [])

    converted_geometries = []

    # Extract coordinates from GeoJSON
    for geometry in geometry_list:
        geospatial = geometry.get("geospatial_coordinates", {})
        features = geospatial.get("features", [])
        if not features:
            logging.warning("No features found in geospatial_coordinates")
            continue

        coords = features[0].get("geometry", {}).get("coordinates")
        if not coords or len(coords) < 2:
            logging.warning("No valid coordinates found in first feature")
            continue

        longitude, latitude = coords[0], coords[1]

        # Extract datum from the resource data
        base_map = geometry.get("current_base_map", {})
        base_map_names = base_map.get("current_base_map_names", {})
        datum = base_map_names.get("current_base_map_name")

        if not datum:
            logging.warning("No datum (current_base_map_name) found in resource geometry data; skipping")
            continue

        mga_value = convert_to_mga(longitude, latitude, datum)
        if mga_value:
            converted_geometries.append(mga_value)
        
    return converted_geometries
