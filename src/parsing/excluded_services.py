"""
Excluded Services / Other Covered Services extraction: pulls the two
short bulleted-list sections near the end of each SBC (real, directly-
answerable "does this plan cover X" content) into a flat list of item
strings per section.

Both sections are laid out as 2-3 column bullet grids with no vertical
ruling lines and, on several documents (Aetna confirmed directly), no
enclosing rectangle around the bullet content at all -- so
camelot/pdfplumber's table-cell extraction can't detect column
boundaries here and collapses everything into one cell, in whatever
order the underlying text stream happens to store it (not necessarily
left-to-right, top-to-bottom -- see notebooks/excluded_services_explore.py
for the investigation that ruled out both a rectangle-based and a plain
delimiter-splitting approach). This module bypasses table extraction
entirely for this content and reconstructs it directly from word-level
(x0, top) positions instead, the same fundamental technique already used
to diagnose UHC's duplicate text and Anthem's header layout -- applied
here to actually rebuild reading order, not just detect a defect.

Section boundaries are found via three ordered marker phrases, located
document-wide rather than assumed to fit on one page (Aetna splits
Excluded Services and Other Covered Services across two different
pages):
  1. EXCLUDED_MARKER ("Does NOT Cover") -- start of Excluded Services.
  2. OTHER_COVERED_MARKER ("Other Covered Services") -- end of Excluded
     Services, start of Other Covered Services.
  3. STOP_MARKER ("Your Rights to Continue Coverage") -- end of Other
     Covered Services. Not itself extracted; it exists only because
     nothing else marks where the last of the two sections ends.
     Confirmed present on all 8 known documents, on the same page as
     Other Covered Services every time.

A section's content can span a page break (Aetna again), which risks
sweeping a page footer (e.g. "080600-110020-011807 5 of 8") into a
section's bullet content -- filtered out via _FOOTER_PATTERN before any
words are collected.

Column reconstruction: bullet characters ("•" and the private-use glyph
"\uf0b7" seen on BCBS IL/Anthem) mark the left edge of each column, so
their x0 positions are clustered into column anchors first. Every word is
then grouped into a physical line (by y-position) and each LINE -- never
an individual word -- is assigned to its nearest column anchor; this
matters because a long bullet's later words can drift in x-position
closer to a different column's anchor than its own, and assigning
word-by-word would wrongly split one line's text across two columns.
Within a column, a bullet-prefixed line starts a new item and a line
without one is treated as a wrapped continuation of the previous item
(the same "trust the source PDF's own visual signal" idea as the
lowercase-continuation heuristic used elsewhere in this project, but
using the bullet character directly rather than inferring from
capitalization). Items are returned column by column, left to right,
matching the actual reading order shown on the page.
"""

import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pdfplumber

from .camelot_extract import extract_camelot_tables
from .document_registry import DocumentConfig
from .strip_invisible import strip_invisible_text_from_pdf

OTHER_COVERED_MARKER = "Other Covered Services (Limitations"
STOP_MARKER = "Your Rights to Continue Coverage"

_BULLET_CHARS = {"•", "\uf0b7"}
_LEADING_BULLET_PATTERN = re.compile(r"^[•\uf0b7]\s*")
_FOOTER_PATTERN = re.compile(r"\d+\s+of\s+\d+")
EXCLUDED_TITLE_END_MARKER = "excluded services.)"

@dataclass
class ServiceLists:
    """The two extracted service lists for one document.

    excluded_services: items under "Services Your Plan Generally Does NOT
        Cover" (wording varies slightly by document).
    other_covered_services: items under "Other Covered Services".
    """

    excluded_services: List[str] = field(default_factory=list)
    other_covered_services: List[str] = field(default_factory=list)


def _find_marker_position(pdf, marker: str) -> Optional[Tuple[int, float, float]]:
    """Return (page_idx, top, bottom) of the first text line containing
    marker (whitespace-normalized, case-insensitive substring) anywhere
    in the document, or None if never found. Searched document-wide,
    not page-by-page in isolation, since section boundaries aren't
    assumed to land on any particular page.
    """
    marker_norm = marker.lower()
    for page_idx, page in enumerate(pdf.pages):
        for line in page.extract_text_lines():
            text_norm = " ".join(line["text"].split()).lower()
            if marker_norm in text_norm:
                return (page_idx, line["top"], line["bottom"])
    return None


def _page_words_in_range(page, top_bound: float, bottom_bound: float) -> List[dict]:
    """Return every word on this page whose top position falls within
    [top_bound, bottom_bound), skipping any word that belongs to a
    footer line (matched via _FOOTER_PATTERN, e.g. "5 of 8"). Footer
    filtering matters here specifically because a section's content can
    span a page break, which would otherwise sweep the source page's own
    footer into that section's bullet content.
    """
    footer_ranges = [
        (line["top"], line["bottom"])
        for line in page.extract_text_lines()
        if _FOOTER_PATTERN.search(line["text"])
    ]

    words = []
    for word in page.extract_words():
        if not (top_bound <= word["top"] < bottom_bound):
            continue
        if any(f_top <= word["top"] <= f_bottom for f_top, f_bottom in footer_ranges):
            continue
        words.append(word)
    return words


def _gather_words(pdf, start: Tuple[int, float], end: Tuple[int, float]) -> List[dict]:
    """Gather every content word between a start boundary (page_idx,
    top_y) and an end boundary (page_idx, top_y), including every full
    page in between when start and end fall on different pages -- a
    section's content isn't assumed to fit on one page (see module
    docstring: Aetna splits Excluded Services and Other Covered Services
    across two pages).
    """
    start_page, start_y = start
    end_page, end_y = end
    words: List[dict] = []

    if start_page == end_page:
        page = pdf.pages[start_page]
        words.extend(_page_words_in_range(page, start_y, end_y))
        return words

    first_page = pdf.pages[start_page]
    words.extend(_page_words_in_range(first_page, start_y, first_page.height))

    for page_idx in range(start_page + 1, end_page):
        page = pdf.pages[page_idx]
        words.extend(_page_words_in_range(page, 0, page.height))

    last_page = pdf.pages[end_page]
    words.extend(_page_words_in_range(last_page, 0, end_y))

    return words


def _bullet_x0_positions(words: List[dict]) -> List[float]:
    """Return the x0 of every word that is (or starts with) a bullet
    character -- these mark the left edge of each column, and their x0
    positions are what column anchors get clustered from.
    """
    return [w["x0"] for w in words if w["text"] and w["text"][0] in _BULLET_CHARS]


def _cluster_column_anchors(bullet_x0s: List[float], gap_threshold: float = 30.0) -> List[float]:
    """Cluster bullet x0 positions into column anchor x-positions: sort
    the values and start a new column whenever the gap to the previous
    value exceeds gap_threshold. Returns one representative x0 per
    column (the minimum x0 in that cluster), sorted left to right.
    """
    if not bullet_x0s:
        return []
    sorted_x0s = sorted(bullet_x0s)
    clusters: List[List[float]] = [[sorted_x0s[0]]]
    for x0 in sorted_x0s[1:]:
        if x0 - clusters[-1][-1] > gap_threshold:
            clusters.append([x0])
        else:
            clusters[-1].append(x0)
    return [min(cluster) for cluster in clusters]


def _group_words_into_lines(words: List[dict], y_tolerance: float = 2.0) -> List[dict]:
    """Group words into physical lines by vertical position: words whose
    top values are within y_tolerance of each other belong to the same
    line. Returns one dict per line: {"top", "x0" (leftmost word's x0),
    "text" (words joined left to right), "words"}. Lines -- never
    individual words -- are what get assigned to a column next (see
    _assign_lines_to_columns), since one physical line always belongs to
    exactly one column's paragraph flow even when its later words drift
    closer in x-position to a different column's anchor.
    """
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: List[dict] = []
    for word in sorted_words:
        if lines and abs(word["top"] - lines[-1]["top"]) <= y_tolerance:
            lines[-1]["words"].append(word)
        else:
            lines.append({"top": word["top"], "words": [word]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
        line["x0"] = line["words"][0]["x0"]
        line["text"] = " ".join(w["text"] for w in line["words"])
    return lines


def _split_row_into_segments(row_words: List[dict], gap_threshold: float = 15.0) -> List[List[dict]]:
    """Split one row's words (already sorted left to right) into
    segments: start a new segment whenever the horizontal gap between
    the previous word's right edge and the current word's left edge
    exceeds gap_threshold, OR whenever the current word is itself a
    bullet character. The gap check alone isn't reliable on every
    document -- on BCBS IL and Cigna specifically, a bullet can sit
    close enough to the preceding column's text that the gap falls
    under threshold, silently merging two columns' items together. A
    bullet is a direct, unambiguous signal from the source PDF that a
    new item starts there, so it always forces a new segment
    regardless of spacing.
    """
    if not row_words:
        return []
    segments: List[List[dict]] = [[row_words[0]]]
    for word in row_words[1:]:
        gap = word["x0"] - segments[-1][-1]["x1"]
        is_bullet = bool(word["text"]) and word["text"][0] in _BULLET_CHARS
        if gap > gap_threshold or is_bullet:
            segments.append([word])
        else:
            segments[-1].append(word)
    return segments


def _assign_segment_to_column(segment: List[dict], anchors: List[float]) -> int:
    """Return the column index whose anchor is nearest to this segment's
    own leading word's x0 -- checked once per segment, not per word,
    since a segment's leading position sits right at its column's true
    boundary even when later words in a long segment drift closer to a
    different column's anchor.
    """
    x0 = segment[0]["x0"]
    return min(range(len(anchors)), key=lambda i: abs(x0 - anchors[i]))

def _strip_leading_bullet(text: str) -> str:
    """Remove a single leading bullet character (and any following
    whitespace) from text, if present; returns text unchanged otherwise.
    The return value differing from the input is what _build_items_from_column
    uses to detect "this line starts a new item".
    """
    match = _LEADING_BULLET_PATTERN.match(text)
    if match:
        return text[match.end():]
    return text


def _build_items_from_column(lines: List[dict]) -> List[str]:
    """Walk one column's lines top to bottom, starting a new item at
    each bullet-prefixed line and merging any line without a bullet onto
    the current item as a wrapped continuation.
    """
    items: List[str] = []
    for line in lines:
        text = line["text"]
        stripped = _strip_leading_bullet(text)
        if stripped != text:
            items.append(stripped.strip())
        elif items:
            items[-1] = f"{items[-1]} {text.strip()}"
        else:
            items.append(text.strip())
    return items


def _extract_section_items(pdf, start: Tuple[int, float], end: Tuple[int, float]) -> List[str]:
    """Extract one section's bullet items from the word-level content
    between start and end boundaries: cluster bullet x0 positions into
    column anchors, group all words into physical rows, split each row
    into segments wherever a large horizontal gap marks a jump between
    columns, assign each segment to its nearest column by its own
    leading position, then within each column walk its segments top to
    bottom building items. Returns items column by column, left to
    right. Returns an empty list if no bullet characters are found in
    the range (nothing to anchor columns on).
    """
    words = _gather_words(pdf, start, end)
    anchors = _cluster_column_anchors(_bullet_x0_positions(words))
    if not anchors:
        return []

    rows = _group_words_into_lines(words)

    column_lines: List[List[dict]] = [[] for _ in anchors]
    for row in rows:
        for segment in _split_row_into_segments(row["words"]):
            col_idx = _assign_segment_to_column(segment, anchors)
            column_lines[col_idx].append({
                "top": row["top"],
                "text": " ".join(w["text"] for w in segment),
            })

    items: List[str] = []
    for lines in column_lines:
        lines.sort(key=lambda l: l["top"])
        items.extend(_build_items_from_column(lines))
    return items

def _extract_service_lists_from_path(path: str) -> ServiceLists:
    """Open path, locate the boundary markers document-wide, and extract
    both sections' items. Returns empty lists (not an error) for a
    section whose markers can't all be located -- a document genuinely
    missing a section, or an unexpected structural difference, is a real
    possibility that shouldn't silently produce garbage.

    Excluded Services' start boundary uses EXCLUDED_TITLE_END_MARKER
    ("excluded services.)") rather than EXCLUDED_MARKER's own line,
    since the title text can wrap across multiple physical lines (seen
    on Anthem) -- EXCLUDED_TITLE_END_MARKER is the literal, consistent
    phrase the title always ends on regardless of how many lines it
    wraps across, so it correctly finds the true end of the title even
    when EXCLUDED_MARKER's own line is only the title's first line. On
    every other document the title fits on one line, so both markers
    land on the same line and this changes nothing there.
    """
    with pdfplumber.open(path) as pdf:
        excluded_title_end_pos = _find_marker_position(pdf, EXCLUDED_TITLE_END_MARKER)
        other_covered_pos = _find_marker_position(pdf, OTHER_COVERED_MARKER)
        stop_pos = _find_marker_position(pdf, STOP_MARKER)

        result = ServiceLists()

        if excluded_title_end_pos is not None and other_covered_pos is not None:
            start = (excluded_title_end_pos[0], excluded_title_end_pos[2])
            end = (other_covered_pos[0], other_covered_pos[1])
            result.excluded_services = _extract_section_items(pdf, start, end)

        if other_covered_pos is not None and stop_pos is not None:
            start = (other_covered_pos[0], other_covered_pos[2])
            end = (stop_pos[0], stop_pos[1])
            result.other_covered_services = _extract_section_items(pdf, start, end)

        return result

def extract_service_lists(pdf_path: str, config: DocumentConfig) -> ServiceLists:
    """Extract the Excluded Services and Other Covered Services lists
    from a document, using column-aware word-position reconstruction
    (see module docstring for why table-cell extraction can't be used
    for this content).

    Routes through the same invisible-text stripping table/header
    extraction already applies for camelot-routed documents, since
    word-level extraction is just as vulnerable to UHC-style duplicate
    text as any other text-based extraction.
    """
    if config.extract_fn is extract_camelot_tables:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            cleaned_path = tmp.name
        try:
            strip_invisible_text_from_pdf(pdf_path, cleaned_path)
            return _extract_service_lists_from_path(cleaned_path)
        finally:
            os.remove(cleaned_path)
    else:
        return _extract_service_lists_from_path(pdf_path)