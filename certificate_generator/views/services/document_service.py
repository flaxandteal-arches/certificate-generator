"""
Document service - business logic for generating documents from templates.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from certificate_generator.views.processors import document_template_processor
from certificate_generator.views.registry import TemplateRegistry

class DocumentService:

    def __init__(self, template_registry: TemplateRegistry):
        self.template_registry = template_registry

    def resolve_template(
        self,
        template_id: str,
        template_version: Optional[int] = None,
    ) -> Path:
        """
        Resolve a template ID and optional version to a file path.

        Raises:
            FileNotFoundError: If the template or version does not exist.
        """
        version = int(template_version) if template_version is not None else None
        template_path = self.template_registry.resolve_template_path(template_id, version=version)

        if template_path is None or not template_path.exists():
            version_label = f" v{version}" if version else " (no published version)"
            raise FileNotFoundError(f"Template not found: {template_id}{version_label}")

        return template_path

    def generate_document(
        self,
        template_path: Path,
        data: Dict[str, Any],
    ) -> bytes:
        """
        Process a template with mapped resource data and return the document bytes.

        Args:
            template_path: Resolved path to the .docx template.
            data: Mapped resource data (output of ResourceMapper.load_resource).

        Returns:
            Raw bytes of the generated .docx file.
        """
        document_template_processor_svc = document_template_processor.DocumentTemplateProcessor(str(template_path)) 
        processor = document_template_processor_svc
        processor.process_template(data)

        with tempfile.NamedTemporaryFile(mode='wb', suffix='.docx', delete=False) as tmp:
            output_path = tmp.name

        try:
            processor.save(output_path)
            with open(output_path, 'rb') as f:
                return f.read()
        finally:
            os.unlink(output_path)
