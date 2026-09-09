"""
Header metadata extraction: pulls Coverage Period, Coverage for, Plan
Type, and plan name off page 1 of each SBC, above the Important Questions
table.

Insurer name is deliberately NOT extracted from the PDF text -- on
several documents (Aetna, BCBS IL, Kaiser confirmed so far) the insurer
name is rendered as a logo image, not text, leaving a bare ": " artifact
where the name should be (nothing before the colon that separates it
from the plan name). Re-deriving something we already know correctly
would be pointless risk; DocumentConfig.insurer (document_registry.py)
supplies it directly instead.

Marker-based fields (Coverage Period, Coverage for, Plan Type) are
reliably worded the same way across all 8 documents -- same federal-
template consistency as "Important Questions"/"Why This Matters" in the
table extraction. Plan name has no marker at all and its position
relative to the marker line isn't consistent (sometimes before it,
sometimes on a separate line before it, sometimes split across a prefix
on the marker line AND a following line) -- so, like content columns in
normalize.py, it's derived by taking everything else in the header block
rather than guessed at positionally.

Like table extraction, this must route through the same invisible-text
handling as the rest of the pipeline for camelot-routed documents (UHC
etc.), or duplicate render-mode-3 text corrupts the header block the same
way it corrupted the tables.
"""

import os
import tempfile
from dataclasses import dataclass
from typing import List, Optional

import pdfplumber

from .camelot_extract import extract_camelot_tables
from .document_registry import DocumentConfig
from .strip_invisible import strip_invisible_text_from_pdf

COVERAGE_PERIOD_MARKER = "Coverage Period:"
COVERAGE_FOR_MARKER = "Coverage for:"
PLAN_TYPE_MARKER = "Plan Type:"
BOILERPLATE_START_MARKER = "The Summary of Benefits and Coverage (SBC) document"
TITLE_MARKER = "Summary of Benefits and Coverage: What this Plan Covers"

@dataclass
class HeaderMetadata:
    """Header-block fields for one document. insurer comes from the
    registry (see module docstring); everything else is extracted from
    the PDF's own first-page text.
    """

    insurer: str
    plan_name: Optional[str]
    coverage_period: Optional[str]
    coverage_for: Optional[str]
    plan_type: Optional[str]


def _get_first_page_text(pdf_path: str, config: DocumentConfig) -> str:
    """Return page 1's text, routed through the same invisible-text
    stripping camelot-routed documents already get for table extraction
    (see strip_invisible.py) -- without it, a document like UHC comes
    back with every header line duplicated.
    """
    if config.extract_fn is extract_camelot_tables:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            cleaned_path = tmp.name
        try:
            strip_invisible_text_from_pdf(pdf_path, cleaned_path)
            with pdfplumber.open(cleaned_path) as pdf:
                return pdf.pages[0].extract_text() or ""
        finally:
            os.remove(cleaned_path)
    else:
        with pdfplumber.open(pdf_path) as pdf:
            return pdf.pages[0].extract_text() or ""


def _extract_marker_line_values(line: str) -> tuple:
    """Split one "Coverage for: X | Plan Type: Y" line into
    (prefix_before_markers, coverage_for_value, plan_type_value).
    Bounded to this single line deliberately -- see module docstring on
    why Plan Type must not be allowed to spill onto the next line.
    """
    cf_idx = line.find(COVERAGE_FOR_MARKER)
    prefix = line[:cf_idx].strip() if cf_idx != -1 else ""
    rest = line[cf_idx + len(COVERAGE_FOR_MARKER):] if cf_idx != -1 else line

    pt_idx = rest.find(PLAN_TYPE_MARKER)
    if pt_idx != -1:
        coverage_for = rest[:pt_idx].strip(" |")
        plan_type = rest[pt_idx + len(PLAN_TYPE_MARKER):].strip()
    else:
        coverage_for = rest.strip(" |")
        plan_type = None

    return prefix, coverage_for or None, plan_type or None


def extract_header_metadata(pdf_path: str, config: DocumentConfig) -> HeaderMetadata:
    """Extract Coverage Period, Coverage for, Plan Type, and plan name
    from page 1 of the given document.
    """
    text = _get_first_page_text(pdf_path, config)
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    coverage_period: Optional[str] = None
    marker_line_index: Optional[int] = None
    coverage_for: Optional[str] = None
    plan_type: Optional[str] = None
    marker_line_prefix = ""

    boilerplate_index = len(lines)
    for i, line in enumerate(lines):
        if BOILERPLATE_START_MARKER in line:
            boilerplate_index = i
            break

    for i, line in enumerate(lines[:boilerplate_index]):
        if COVERAGE_PERIOD_MARKER in line and coverage_period is None:
            coverage_period = line.split(COVERAGE_PERIOD_MARKER, 1)[1].strip() or None
        elif COVERAGE_FOR_MARKER in line and marker_line_index is None:
            marker_line_index = i
            marker_line_prefix, coverage_for, plan_type = _extract_marker_line_values(line)

    plan_name_parts: List[str] = []
    for i, line in enumerate(lines[:boilerplate_index]):
        if COVERAGE_PERIOD_MARKER in line or TITLE_MARKER in line:
            continue
        if i == marker_line_index:
            if marker_line_prefix:
                plan_name_parts.append(marker_line_prefix)
            continue
        plan_name_parts.append(line)

    plan_name = " ".join(plan_name_parts).strip()
    plan_name = plan_name.lstrip(":").strip()  # strip the logo-gap artifact
    plan_name = plan_name or None

    return HeaderMetadata(
        insurer=config.insurer,
        plan_name=plan_name,
        coverage_period=coverage_period,
        coverage_for=coverage_for,
        plan_type=plan_type,
    )