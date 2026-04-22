# coding: utf-8
"""
Refactored document template system that works with JSON data
using docxtpl (python-docx-template) for Jinja2 templating.
"""

import html as html_module
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from datetime import datetime
import jinja2

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from io import BytesIO
from certificate_generator.views.processors.richtext import mark2html, apply_list_indentation, apply_heading_spacing
from certificate_generator.views.utils.image_utils import load_image, get_image_dimensions


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
        env = jinja2.Environment()
        env.filters["mark2html"] = mark2html
        def to_image(img, width=None, height=None, max_width=155, max_height=180, anchor=None):
            if img is None:
                return ""

            # If img is already a BytesIO (pre-downloaded), use it directly
            if isinstance(img, BytesIO):
                img.seek(0)
                img_data = img
            elif isinstance(img, str):
                if not img:
                    return ""
                img_data = load_image(img, self.images_dir)
            else:
                return ""
            if img_data is None:
                return None

            # If explicit width/height provided, use those
            if width or height:
                w = Mm(width) if width else None
                h = Mm(height) if height else None
                return InlineImage(self.doc, img_data, width=w, height=h, anchor=anchor)

            # Otherwise, check image dimensions and constrain by the larger dimension
            img_width, img_height = get_image_dimensions(img_data)
            img_data.seek(0)  # Reset position after reading dimensions

            # Calculate aspect ratio and determine which dimension to constrain
            if img_width >= img_height:
                # Landscape or square - constrain by height to fit caption
                w = None
                h = Mm(105)
            else:
                # Portrait - constrain by height
                w = None
                h = Mm(max_height)

            return InlineImage(self.doc, img_data, width=w, height=h, anchor=anchor)
        env.filters["to_image"] = to_image
        def enumeratep1(itbl):
            for n, i in enumerate(itbl):
                yield (n + 1), i
        env.filters["enumeratep1"] = enumeratep1
        def to_written_date(isodate):
            return datetime.fromisoformat(isodate).strftime("%d %B %Y")
        env.filters["to_written_date"] = to_written_date
        def format_key(text):
            return text.replace("_", " ")
        env.filters["format_key"] = format_key
        # Render the template with Jinja2 (text replacements)
        env.filters["capitalise"] = lambda s: s.lower().capitalize()
        self.doc.render(context, env, autoescape=True)
        apply_list_indentation(self.doc)
        apply_heading_spacing(self.doc)

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

    def _is_valid_image_filename(self, value: str) -> bool:
        """Check if a string looks like a valid image filename"""
        if not isinstance(value, str):
            return False
        # Must be short enough to be a filename (not a description/paragraph)
        if len(value) > 255:
            return False
        # Must have an image extension
        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')
        return value.lower().endswith(image_extensions)

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
