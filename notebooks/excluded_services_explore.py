"""
Checks whether "Your Rights to Continue Coverage" -- the section that
immediately follows Other Covered Services on Aetna's actual PDF -- is a
reliable, universally-present stop marker across all 8 documents, before
relying on it to bound the end of Other Covered Services' content. Needed
because the rectangle-based approach to bounding these sections turned
out not to generalize (see excluded_services_explore.py's rects dump:
Aetna's content area isn't enclosed by any rectangle at all, and
Highmark's borders are drawn as dozens of small, inconsistent
line-segment rects rather than one clean box), so bounding by text-line
position (this section's own title line down to the next boundary's
title line) is the fallback -- and that fallback needs its own stop
marker verified the same way every other marker in this project has
been, not assumed from one document.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pdfplumber

from src.parsing.document_registry import DOCUMENT_REGISTRY
from src.parsing.camelot_extract import extract_camelot_tables
from src.parsing.strip_invisible import strip_invisible_text_from_pdf

STOP_MARKER = "Your Rights to Continue Coverage"


def _find_marker_page(path: str) -> int:
    """Return the 0-indexed page number containing STOP_MARKER, or -1 if
    not found anywhere in the document.
    """
    with pdfplumber.open(path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if STOP_MARKER in text:
                return page_idx
    return -1


for filename, config in DOCUMENT_REGISTRY.items():
    path = f"data/raw/{filename}"

    if config.extract_fn is extract_camelot_tables:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            cleaned_path = tmp.name
        try:
            strip_invisible_text_from_pdf(path, cleaned_path)
            page_idx = _find_marker_page(cleaned_path)
        finally:
            os.remove(cleaned_path)
    else:
        page_idx = _find_marker_page(path)

    status = f"found on page {page_idx}" if page_idx != -1 else "NOT FOUND"
    print(f"{filename} ({config.insurer}): {status}")