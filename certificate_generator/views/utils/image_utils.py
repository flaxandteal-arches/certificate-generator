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

from PIL import Image


def download_image(url: str, timeout: int = 5) -> Optional[BytesIO]:
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


def download_images_batch(urls: List[str], max_workers: int = 10, timeout: int = 5) -> Dict[str, Optional[BytesIO]]:
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
