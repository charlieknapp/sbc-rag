"""
Fixed-size chunking baseline test: flattens one document's already-clean
data/processed/*.json into a single text blob, applies naive fixed-size
(character-window) chunking to it, and measures whether any chunk boundary
falls strictly inside a row/item's character range -- i.e. actually splits
it mid-chunk.

The point isn't to build a chunker we'll keep -- we already expect to land
on row-level structured chunking (see planning doc). The point is to get
real, measurable evidence of *why* fixed-size chunking fails the "never
split a row mid-chunk" requirement, even against text that's already clean
and correctly extracted (not garbled raw PDF text) -- so the failure is
attributable to fixed-size chunking's blindness to structure, not to bad
upstream parsing.
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROCESSED_DIR = Path("data/processed")


def flatten_document(doc: dict) -> Tuple[str, List[Tuple[int, int, str]]]:
    """Flatten one processed document into a single text blob, and return
    the (start, end, label) character span of every row/item we consider
    an indivisible unit (grid table rows, Important Questions rows,
    Excluded/Other Covered list items) -- these are exactly the units the
    assignment's "never split a row mid-chunk" rule is about, so we need
    their exact boundaries to check violations precisely rather than by
    eye.
    """
    parts: List[str] = []
    spans: List[Tuple[int, int, str]] = []
    pos = 0

    def add(text: str, label: str) -> None:
        nonlocal pos
        parts.append(text)
        start = pos
        pos += len(text)
        spans.append((start, pos, label))
        parts.append("\n")
        pos += 1

    hm = doc["header_metadata"]
    add(
        f"Insurer: {hm['insurer']} | Plan: {hm['plan_name']} | "
        f"Coverage Period: {hm['coverage_period']} | Plan Type: {hm['plan_type']}",
        "header",
    )

    for row in doc["grid_table"]["rows"]:
        row_text = " | ".join(str(c) for c in row if c is not None)
        add(row_text, "grid_row")

    for row in doc["important_questions"]["rows"]:
        row_text = " | ".join(str(c) for c in row if c is not None)
        add(row_text, "iq_row")

    for item in doc["excluded_services"]:
        add(item, "excluded_item")

    for item in doc["other_covered_services"]:
        add(item, "other_covered_item")

    return "".join(parts), spans


def fixed_size_chunks(text: str, chunk_size: int, overlap: int) -> List[Tuple[int, int]]:
    """Textbook naive fixed-size chunking: fixed-length character windows
    with a fixed overlap between consecutive windows, with zero awareness
    of the text's content -- the baseline we're testing specifically to
    see whether it violates "never split a row mid-chunk," even on text
    that's already clean.
    """
    chunks: List[Tuple[int, int]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append((start, end))
        if end == n:
            break
        start = end - overlap
    return chunks


def find_row_splits(
    chunk_bounds: List[Tuple[int, int]], row_spans: List[Tuple[int, int, str]]
) -> List[Tuple[int, int, str]]:
    """Return every row/item span that a chunk boundary cuts through the
    MIDDLE of -- i.e. a chunk starts or ends strictly inside that row's
    character range, not at its edge. This is the actual, countable
    violation of "never split a row mid-chunk," not an eyeballed guess.
    """
    violations: List[Tuple[int, int, str]] = []
    for row_start, row_end, label in row_spans:
        for start, end in chunk_bounds:
            if row_start < start < row_end or row_start < end < row_end:
                violations.append((row_start, row_end, label))
                break
    return violations


def run_test(filename: str, chunk_size: int, overlap: int) -> None:
    with open(PROCESSED_DIR / filename) as f:
        doc = json.load(f)

    text, spans = flatten_document(doc)
    chunk_bounds = fixed_size_chunks(text, chunk_size, overlap)
    violations = find_row_splits(chunk_bounds, spans)

    print(f"=== {filename} | chunk_size={chunk_size}, overlap={overlap} ===")
    print(f"{len(chunk_bounds)} chunks produced, {len(spans)} rows/items total")
    print(f"{len(violations)} row(s)/item(s) split mid-chunk:\n")

    for row_start, row_end, label in violations[:5]:  # show a handful, not all
        original = text[row_start:row_end]
        print(f"  [{label}] full text: {original!r}")
        for start, end in chunk_bounds:
            if start > row_start and start < row_end:
                print(f"    -> chunk cuts it starting at offset {start - row_start}: "
                      f"{text[row_start:start]!r} | {text[start:row_end]!r}")
        print()


if __name__ == "__main__":
    for chunk_size, overlap in [(300, 30), (500, 50), (800, 80)]:
        run_test("bcbsil_bluechoice_bronze_ppo_2024.json", chunk_size, overlap)
        run_test("highmark_hdhp_ppoblue_2026.json", chunk_size, overlap)