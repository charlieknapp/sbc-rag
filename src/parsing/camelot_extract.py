"""
Camelot-based extraction, used only for documents where pdfplumber's
output is too unreliable to work with (currently: UHC, whose source PDF
carries a hidden, invisible-render-mode duplicate text layer -- see
planning doc, PDF #5, and strip_invisible.py for the root-cause writeup).

Converts camelot's tables into the same plain nested-list format
pdfplumber's extract_tables() produces (List[page][table][row][cell]),
so normalize.py's functions can consume either source unchanged.

Text-level cleanup used to happen here (a string-similarity heuristic that
tried to detect and collapse duplicated text inside each cell), but that
approach is gone: it couldn't reliably handle every shape the duplication
took (truncated copies, a trailing bleed of the next row's label) without
risking real data loss. It's replaced by strip_invisible_text_from_pdf,
which removes the duplicate content at its actual source -- the PDF's
content stream -- before camelot ever sees the file, so camelot's raw
output is already correct and this module no longer needs to touch cell
text at all.
"""

import os
import tempfile
from typing import List, Optional

import camelot

from .strip_invisible import strip_invisible_text_from_pdf


def extract_camelot_tables(
    pdf_path: str, flavor: str = "lattice"
) -> List[List[List[List[Optional[str]]]]]:
    """Extract every table in the PDF via camelot, first stripping any
    invisible-render-mode text from a temporary copy of the PDF so camelot
    never sees the duplicate content that copy would otherwise contribute.
    Returns the pages[table][row][cell] shape pdfplumber's extract_tables()
    produces -- so normalize.py's normalize_document() can be called
    identically regardless of which extraction path produced the data.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        cleaned_path = tmp.name
    try:
        strip_invisible_text_from_pdf(pdf_path, cleaned_path)
        camelot_tables = camelot.read_pdf(cleaned_path, pages="all", flavor=flavor)
    finally:
        os.remove(cleaned_path)

    tables_by_page: dict = {}
    for t in camelot_tables:
        page_num = int(t.page) - 1  # camelot pages are 1-indexed
        tables_by_page.setdefault(page_num, []).append(t.data)

    if not tables_by_page:
        return []
    last_page = max(tables_by_page)
    return [tables_by_page.get(i, []) for i in range(last_page + 1)]