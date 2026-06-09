# coding: utf-8
"""
Refactored document template system that works with JSON data
using docxtpl (python-docx-template) for Jinja2 templating.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import jinja2

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from io import BytesIO
from certificate_generator.views.processors.richtext import mark2html, apply_list_indentation, apply_heading_spacing, fix_invalid_tables
from certificate_generator.views.utils.image_utils import load_image, normalise_image_bytes


class DocumentTemplateProcessor:
    """Main class for processing document templates with JSON data using docxtpl"""

    def __init__(self, template_path: str):
        """
        Initialize the processor with a document template

        Args:
            template_path: Path to the .docx template file
        """
        self.doc = DocxTemplate(template_path)
        self.template_path = template_path
        self.images_dir = Path(__file__).parent / "images"

    def process_template(self, data: Dict[str, Any]) -> None:
        """
        Process the template with the provided data and mapping

        Args:
            data: The raw JSON data structure
        """
        # Prepare context for text placeholders
        context = self._prepare_context(data)
        env = jinja2.Environment(undefined=jinja2.ChainableUndefined)
        env.filters["mark2html"] = mark2html
        def to_image(img, width=None, height=None, max_width=155, max_height=180, anchor=None):
            # Resolve the source to raw bytes. Anything that doesn't yield real,
            # decodable image bytes must render as "" — emitting an InlineImage
            # for missing/empty bytes leaves a dangling image relationship, which
            # makes Word Online / Google Docs open the document read-only.
            if isinstance(img, BytesIO):
                img.seek(0)
                raw = img.read()
            elif isinstance(img, str):
                if not img:
                    return ""
                loaded = load_image(img, self.images_dir)
                raw = loaded.read() if loaded is not None else b""
            else:
                return ""
            if not raw:
                return ""

            # Fully decode and re-encode to clean JPEG bytes before embedding.
            # A header-only check would pass a valid-header/corrupt-body download
            # and embed it (making Word open the doc read-only); a full decode +
            # re-encode rejects bad images and normalises good ones.
            normalised = normalise_image_bytes(raw)
            if normalised is None:
                return ""
            raw, img_width, img_height = normalised

            # Each InlineImage gets its own fresh stream so a shared/exhausted
            # BytesIO can't serialise as an empty media part.
            if width or height:
                w = Mm(width) if width else None
                h = Mm(height) if height else None
                return InlineImage(self.doc, BytesIO(raw), width=w, height=h, anchor=anchor)

            # Constrain by height; square/landscape and portrait differ only in
            # the cap so captions still fit.
            h = Mm(105) if img_width >= img_height else Mm(max_height)
            return InlineImage(self.doc, BytesIO(raw), width=None, height=h, anchor=anchor)
        env.filters["to_image"] = to_image
        def enumeratep1(itbl):
            for n, i in enumerate(itbl):
                yield (n + 1), i
        env.filters["enumeratep1"] = enumeratep1
        def to_written_date(isodate):
            if not isinstance(isodate, str) or not isodate:
                return ""
            try:
                return datetime.fromisoformat(isodate).strftime("%d %B %Y")
            except ValueError:
                return ""
        env.filters["to_written_date"] = to_written_date
        def format_key(text):
            if not isinstance(text, str):
                return ""
            return text.replace("_", " ")
        env.filters["format_key"] = format_key
        # Render the template with Jinja2 (text replacements)
        def capitalise(s):
            if not isinstance(s, str) or not s:
                return ""
            return s.lower().capitalize()
        env.filters["capitalise"] = capitalise
        self.doc.render(context, env, autoescape=True)
        apply_list_indentation(self.doc)
        apply_heading_spacing(self.doc)
        # Repair tables left empty by missing data — an empty <w:tbl> makes
        # Word Online open the document read-only.
        fix_invalid_tables(self.doc)

    def _prepare_context(self, mapping: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare the context for docxtpl rendering.
        Handles text placeholders. 

        Args:
            mapping: Dictionary of placeholder keys to replacement values

        Returns:
            Context dictionary ready for docxtpl rendering
        """
        context = {}
        for key, value in mapping.items():
            # Handle None values
            if value is None:
                context[key] = ""
                continue

            # Convert booleans to strings
            if isinstance(value, bool):
                context[key] = str(value)
                continue

            if key == 'criteria' and 'saved_criteria' not in context:
                context['saved_criteria'] = [c["criterion"].split('_')[1] for c in value if c is not None]
                context[key] = value
                continue

            if isinstance(value, list):
                context[key] = value
                continue

            if isinstance(value, dict):
                context[key] = value
                continue

            # Default: convert primitives to string
            text = str(value) if value is not None else ""
            context[key] = text

            # Convert date_today to written date format
            if key == 'date_today':
                context['date_today'] = datetime.now().strftime("%d %B %Y")

        return context

    def save(self, output_path: str) -> None:
        """
        Save the processed document

        Args:
            output_path: Path where the document should be saved
        """
        self.doc.save(output_path)


def process_document_template(template_path: str, data_path: str,
                              output_path: str, config: Optional[Dict[str, Any]] = None) -> str:
    """
    Main function to process a document template with JSON data

    Args:
        template_path: Path to the .docx template
        data_path: Path to the JSON data file
        output_path: Path for the output document
        config: Optional configuration dictionary

    Returns:
        Path to the generated document
    """
    # Load JSON data
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Process template
    processor = DocumentTemplateProcessor(template_path)
    processor.process_template(data)

    # Save output
    processor.save(output_path)

    return output_path


if __name__ == "__main__":
    # Example usage
    import sys

    if len(sys.argv) < 4:
        print("Usage: python file_template.py <template.docx> <data.json> <output.docx>")
        sys.exit(1)

    template_path = sys.argv[1]
    data_path = sys.argv[2]
    output_path = sys.argv[3]

    # Optional: pass config as JSON file or dict
    config = {}
    if len(sys.argv) > 4:
        with open(sys.argv[4], 'r') as f:
            config = json.load(f)

    result = process_document_template(template_path, data_path, output_path, config)
    print(f"Document generated successfully: {result}")
