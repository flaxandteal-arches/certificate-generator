"""
Template version registry.
Loads templates.json and provides version resolution for the template system.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional


class TemplateRegistry:
    """
    Manages template metadata from the templates.json manifest.
    Provides lookup, filtering, and version resolution.
    """

    VALID_STATUSES = {"draft", "published", "archived"}

    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir
        self.manifest_path = templates_dir / "templates.json"
        self._manifest: Dict[str, Any] = {}
        self._load_manifest()

    def _load_manifest(self) -> None:
        if not self.manifest_path.exists():
            logging.warning("templates.json not found at %s", self.manifest_path)
            self._manifest = {"templates": {}}
            return

        with open(self.manifest_path, "r", encoding="utf-8") as f:
            self._manifest = json.load(f)

        self._validate_manifest()

    def _validate_manifest(self) -> None:
        templates = self._manifest.get("templates", {})
        for slug, template in templates.items():
            published_count = 0
            for ver in template.get("versions", []):
                status = ver.get("status")
                if status not in self.VALID_STATUSES:
                    logging.error(
                        "Template %s v%s has invalid status: %s",
                        slug, ver.get("version"), status,
                    )
                if status == "published":
                    published_count += 1
                filepath = self.templates_dir / ver["filename"]
                if not filepath.exists():
                    logging.error("Template file missing: %s", filepath)
            if published_count > 1:
                logging.error(
                    "Template %s has %d published versions (expected 0 or 1)",
                    slug, published_count,
                )

    def reload(self) -> None:
        self._load_manifest()

    def list_templates(
        self,
        include_drafts: bool = False,
        include_archived: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        List all template groups with their available versions.
        By default returns only published versions.
        """
        result = []
        templates = self._manifest.get("templates", {})

        for slug, template in templates.items():
            published_version = None
            all_versions = []

            for ver in template.get("versions", []):
                status = ver["status"]
                include = (
                    status == "published"
                    or (status == "draft" and include_drafts)
                    or (status == "archived" and include_archived)
                )
                if not include:
                    continue

                filepath = self.templates_dir / ver["filename"]
                version_info = {
                    "version": ver["version"],
                    "status": status,
                    "filename": ver["filename"],
                    "size": filepath.stat().st_size if filepath.exists() else 0,
                    "created_at": ver["created_at"],
                    "created_by": ver["created_by"],
                    "changelog": ver["changelog"],
                }
                all_versions.append(version_info)

                if status == "published":
                    published_version = version_info

            if not all_versions:
                continue

            result.append({
                "id": slug,
                "name": template["display_name"],
                "description": template.get("description", ""),
                "category": template.get("category", ""),
                "published_version": published_version,
                "versions": all_versions,
            })

        result.sort(key=lambda x: x["name"])
        return result

    def resolve_template_path(
        self,
        template_id: str,
        version: Optional[int] = None,
    ) -> Optional[Path]:
        """
        Resolve a template_id (and optional version) to a filesystem path.

        If version is None, resolves to the current published version.
        If version is given, resolves to that exact version (any status).
        Falls back to legacy_ids if the primary slug lookup fails.
        """
        template = self._find_template(template_id)
        if template is None:
            return None

        versions = template.get("versions", [])

        if version is not None:
            for ver in versions:
                if ver["version"] == version:
                    return self.templates_dir / ver["filename"]
            return None

        for ver in versions:
            if ver["status"] == "published":
                return self.templates_dir / ver["filename"]

        return None

    def get_template_info(
        self,
        template_id: str,
        version: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        template = self._find_template(template_id)
        if template is None:
            return None

        if version is not None:
            for ver in template["versions"]:
                if ver["version"] == version:
                    return {**template, "resolved_version": ver}
            return None

        for ver in template["versions"]:
            if ver["status"] == "published":
                return {**template, "resolved_version": ver}

        return None

    def _find_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Look up a template by slug, falling back to legacy_ids."""
        templates = self._manifest.get("templates", {})

        if template_id in templates:
            return templates[template_id]

        for _slug, template in templates.items():
            if template_id in template.get("legacy_ids", []):
                return template

        return None

    def resolve_slug(self, template_id: str) -> Optional[str]:
        """Return the canonical template slug for a template_id, resolving
        legacy_ids. Returns None if the template is unknown."""
        templates = self._manifest.get("templates", {})

        if template_id in templates:
            return template_id

        for slug, template in templates.items():
            if template_id in template.get("legacy_ids", []):
                return slug

        return None
