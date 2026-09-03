"""
Utility functions for handling images in document templates.
Supports downloading images from URLs and preparing them for docxtpl InlineImage.
"""

import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Union, Optional, Tuple, List, Dict
from urllib.parse import urlparse, quote

from django.conf import settings
from PIL import Image, ImageOps


def download_image(url: str, timeout: int = 30) -> Optional[BytesIO]:
    """
    Download an image from a URL and return it as a BytesIO object.

    Args:
        url: The URL of the image to download
        timeout: Request timeout in seconds

    Returns:
        BytesIO object containing the image data, or None if download failed
    """
    try:
        logging.info("downloading image from url: %s", url)
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        logging.info("image downloaded successfully")
        return BytesIO(response.content)
    except requests.RequestException as e:
        logging.warning(f"Failed to download image from URL: {url} - {e}")
        return None


def normalise_image_bytes(raw: bytes) -> Optional[Tuple[bytes, int, int]]:
    """
    Fully decode image bytes and re-encode them as a clean RGB JPEG.

    Returns ``(jpeg_bytes, width, height)``, or ``None`` if the bytes can't be
    decoded. Unlike a header-only dimension read, this forces a complete pixel
    decode (``load()``), so a partially-corrupt download — valid header but bad
    body — is rejected rather than embedded (which would make Word open the
    document read-only). The re-encode also normalises whatever the IIIF server
    returned into bytes Word reliably reads.
    """
    try:
        with Image.open(BytesIO(raw)) as im:
            im.load()
            im = ImageOps.exif_transpose(im)
            rgb = im.convert("RGB")
        buf = BytesIO()
        rgb.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), rgb.width, rgb.height
    except Exception as e:
        logging.warning("normalise_image_bytes: undecodable image (%d bytes): %s", len(raw or b""), e)
        return None


def get_image_dimensions(img_data: Union[BytesIO, Path, str]) -> Tuple[int, int]:
    """
    Get the dimensions of an image.

    Args:
        img_data: BytesIO, Path object, or file path string

    Returns:
        Tuple of (width, height)
    """
    if isinstance(img_data, BytesIO):
        img_data.seek(0)

    with Image.open(img_data) as pil_img:
        return pil_img.size


def load_image(img: str, images_dir: Optional[Path] = None) -> Optional[BytesIO]:
    """
    Load an image from either a URL or local file path.

    Args:
        img: URL or filename of the image
        images_dir: Directory for local images (required if img is a filename)

    Returns:
        BytesIO object containing the image data, or None if loading failed
    """
    if not img:
        return None

    # Check if img is a URL
    if img.startswith(('http://', 'https://')):
        return download_image(img)

    # Otherwise treat as local file
    if images_dir is None:
        logging.warning(f"images_dir not provided for local image: {img}")
        return None

    img_path = images_dir / img
    if not img_path.exists():
        logging.warning(f"Image not found: {img_path}")
        return None

    # Read file into BytesIO for consistent handling
    with open(img_path, 'rb') as f:
        return BytesIO(f.read())


def download_images_batch(urls: List[str], max_workers: int = 10, timeout: int = 30) -> Dict[str, Optional[BytesIO]]:
    """
    Download multiple images concurrently using a thread pool.

    Args:
        urls: List of image URLs to download
        max_workers: Maximum number of concurrent downloads
        timeout: Request timeout in seconds per download

    Returns:
        Dictionary mapping each URL to its BytesIO data (or None if failed)
    """
    results: Dict[str, Optional[BytesIO]] = {}
    if not urls:
        return results

    def _download(url: str) -> Tuple[str, Optional[BytesIO]]:
        return url, download_image(url, timeout=timeout)

    logging.info("downloading %d images concurrently (max_workers=%d)", len(urls), max_workers)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_download, url) for url in urls]
        for future in as_completed(futures):
            url, data = future.result()
            results[url] = data
    logging.info("batch download complete: %d/%d succeeded", sum(1 for v in results.values() if v), len(urls))
    return results


def is_url(value: str) -> bool:
    """Check if a string is a URL."""
    return isinstance(value, str) and value.startswith(('http://', 'https://'))


def iiif_identifier_from_url(url: str) -> str:
    """
    Derive the IIIF image identifier from an image's stored blob/preview URL.

    Cantaloupe is configured against the same blob storage and addresses images
    by filename, so the identifier is the last path segment of the URL (any
    folders and query string stripped).

    Returns '' if no filename can be derived.
    """
    if not url:
        return ''
    path = urlparse(url).path
    return path.rsplit('/', 1)[-1]


def iiif_image_size(identifier: str, timeout: int = 5) -> Optional[Tuple[int, int]]:
    """Read (width, height) from an image's IIIF info.json, or None if unavailable."""
    base = getattr(settings, 'PUBLIC_SERVER_ADDRESS', None)
    if not identifier or not base:
        return None
    url = f"{base.rstrip('/')}/iiifserver/iiif/2/{quote(identifier)}/info.json"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        info = resp.json()
        return int(info['width']), int(info['height'])
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        logging.warning("Failed to read IIIF info.json for %s: %s", identifier, e)
        return None


def build_iiif_url(identifier: str, region: str = 'full', size: str = 'full') -> str:
    """
    Build a IIIF Image API 2.x URL for the given identifier, served through the
    public Arches /iiifserver proxy.

    URL grammar: {base}/iiifserver/iiif/2/{identifier}/{region}/{size}/{rotation}/{quality}.{format}
    e.g. https://host/iiifserver/iiif/2/stock_01.jpeg/square/full/0/default.jpg

    The proxy is used (rather than the internal Cantaloupe endpoint) because the
    certificate generator only has egress to public addresses, not to the
    internal cantaloupe service. settings.PUBLIC_SERVER_ADDRESS is the public
    ingress URL and is set per-environment. Output is always JPEG.

    Args:
        identifier: the image filename (see iiif_identifier_from_url)
        region: IIIF region — 'square' to crop to a centred square, or 'full'
        size: IIIF size — defaults to 'full'

    Returns '' if there is no identifier or no configured public server address.
    """
    base = getattr(settings, 'PUBLIC_SERVER_ADDRESS', None)
    if not identifier or not base:
        return ''
    # Always request JPEG output. The doc has a white background (no transparency
    # needed), and Cantaloupe's full-size PNG render of large maps can produce
    # bytes PIL can't decode, whereas its JPEG render is reliable.
    return f"{base.rstrip('/')}/iiifserver/iiif/2/{quote(identifier)}/{region}/{size}/0/default.jpg"
