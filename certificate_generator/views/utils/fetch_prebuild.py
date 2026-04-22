#!/usr/bin/env python3
"""
Fetch prebuild files from blob storage.

Downloads and extracts prebuild.tgz from blob storage,
overwriting the local prebuild/ directory.

Usage: python utils/fetch_prebuild.py

Environment variables:
  BLOB_BASE_URL     - Base URL for blob storage (required)
  SKIP_BLOB_FETCH   - Set to 'true' to skip fetching (keep local files)
"""

import os
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root
if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")

BLOB_BASE_URL = os.environ.get("BLOB_BASE_URL")
SKIP_BLOB_FETCH = os.environ.get("SKIP_BLOB_FETCH", "").lower() == "true"


def fetch_prebuild(filename: str) -> None:
    blob_url = f"{BLOB_BASE_URL}/content/prebuild/{filename}"

    print(f"\nProcessing: {filename}")
    print(f"  Fetching from: {blob_url}")
    print(f"  Destination: {PROJECT_ROOT}")

    try:
        with urlopen(blob_url) as response:
            data = response.read()
    except HTTPError as e:
        if e.code == 404:
            print("  - Not found in blob, no prebuild downloaded")
            return
        print(f"  Warning: HTTP {e.code} for {blob_url}")
        return
    except URLError as e:
        print(f"  Warning: Failed to fetch {blob_url}: {e.reason}")
        return

    with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        with tarfile.open(tmp_path, "r:gz") as tar:
            tar.extractall(path=PROJECT_ROOT)
        print("  ✓ Downloaded and extracted")
    finally:
        os.unlink(tmp_path)


def main() -> None:
    print("=== Fetch Prebuild ===")

    if SKIP_BLOB_FETCH:
        print("\nSKIP_BLOB_FETCH is set - prebuild folder not being fetched")
        return

    if not BLOB_BASE_URL:
        print("\nBLOB_BASE_URL not set - prebuild folder not being fetched")
        return

    fetch_prebuild("prebuild-certs.tgz")

    print("\n=== Prebuild fetch complete ===")


if __name__ == "__main__":
    main()
