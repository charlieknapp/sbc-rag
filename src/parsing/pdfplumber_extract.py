"""
pdfplumber-based extraction, used for the four documents that never needed
camelot: Highmark, Aetna, BCBS IL, Kaiser. These were the original
documents used to validate the normalization pass (see normalize.py) and
have no known structural defects that pdfplumber can't handle.

TUNED_SETTINGS started at snap/join/intersection_tolerance=8,
edge_min_length=10 (Test 4, to fix Highmark's spurious table
fragmentation), then had the three tolerance values dropped to 5 after the
BCBS IL cross-row text bleed investigation showed 8 was loose enough to
misjudge closely-spaced row boundaries on cleaner documents. 5 is the
current, validated value -- loose enough to still fix Highmark's original
problem, tight enough not to reintroduce the bleed on BCBS IL/Aetna.

This was previously duplicated inline in each notebook test script rather
than living in one place -- pulled out here so there's a single source of
truth for what "the pdfplumber extraction path" actually does, mirroring
camelot_extract.py's role for the camelot-routed documents.
"""

from typing import List, Optional

import pdfplumber

TUNED_SETTINGS = {
    "snap_tolerance": 5,
    "join_tolerance": 5,
    "intersection_tolerance": 5,
    "edge_min_length": 10,
}


def extract_pdfplumber_tables(
    pdf_path: str, table_settings: Optional[dict] = None
) -> List[List[List[List[Optional[str]]]]]:
    """Extract every table in the PDF via pdfplumber, using TUNED_SETTINGS
    by default. Returns the same pages[table][row][cell] shape
    camelot_extract.extract_camelot_tables() produces, so
    normalize.py's normalize_document() can be called identically
    regardless of which extraction path produced the data.
    """
    settings = table_settings if table_settings is not None else TUNED_SETTINGS
    pages_out: List[List[List[List[Optional[str]]]]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages_out.append(page.extract_tables(table_settings=settings))
    return pages_out