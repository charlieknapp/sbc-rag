"""
Builds data/processed/<filename_stem>.json for each of the 8 documents,
running every Phase 2 extraction function (normalize_document for both
table specs, extract_header_metadata, extract_service_lists) via the
document registry, and writing the result to disk.

This is the Phase 2 -> Phase 3 boundary: chunking (and everything after
it) reads from data/processed/, not data/raw/, so a chunking-strategy
iteration doesn't have to re-run PDF extraction (slow, especially for the
camelot-routed documents) every time, and a parsing bug and a chunking
bug can't get confused with each other since they now run in separate
passes.

Deliberately NOT resolving named fields here (e.g. "network_cost" vs.
"out_of_network_cost") -- that's schema/labeling work that belongs to
Phase 5 (Structured Extraction), not this driver. What this script does
capture, that normalize_document previously discarded, is each table's
actual resolved header text per column -- so labeling later is a mapping
step against text already saved here, not a re-parse of the PDF.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parsing.document_registry import DOCUMENT_REGISTRY
from src.parsing.normalize import normalize_document
from src.parsing.header_metadata import extract_header_metadata
from src.parsing.excluded_services import extract_service_lists

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")


def build_table_section(rows: list, columns) -> dict:
    """Package one table's normalize_document() output into the on-disk
    shape: resolved column labels alongside the still-positional rows.
    columns is None when this document's header for this table was never
    resolved from real header text (only the positional fallback ran) --
    kept as None rather than guessed at, so downstream code can tell the
    difference between "no columns" and "columns not derivable" instead
    of silently treating both the same way.
    """
    return {"columns": columns, "rows": rows}


def build_document(filename: str) -> dict:
    """Run every Phase 2 extraction function for one document and return
    the combined, still-positional result ready to write to disk.
    """
    config = DOCUMENT_REGISTRY[filename]
    pdf_path = str(RAW_DIR / filename)

    pages = config.extract_fn(pdf_path)
    grid_rows, grid_columns = normalize_document(pages, config.grid_spec)
    iq_rows, iq_columns = normalize_document(pages, config.iq_spec)

    header_metadata = extract_header_metadata(pdf_path, config)
    service_lists = extract_service_lists(pdf_path, config)

    return {
        "source_filename": filename,
        "insurer": config.insurer,
        "notes": config.notes,
        "header_metadata": asdict(header_metadata),
        "grid_table": build_table_section(grid_rows, grid_columns),
        "important_questions": build_table_section(iq_rows, iq_columns),
        "excluded_services": service_lists.excluded_services,
        "other_covered_services": service_lists.other_covered_services,
    }


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    for filename in DOCUMENT_REGISTRY:
        print(f"Processing {filename}...")
        document_data = build_document(filename)

        output_path = PROCESSED_DIR / f"{Path(filename).stem}.json"
        with open(output_path, "w") as f:
            json.dump(document_data, f, indent=2)

        print(
            f"  -> wrote {output_path} "
            f"({len(document_data['grid_table']['rows'])} grid rows, "
            f"{len(document_data['important_questions']['rows'])} IQ rows, "
            f"{len(document_data['excluded_services'])} excluded, "
            f"{len(document_data['other_covered_services'])} other covered)"
        )


if __name__ == "__main__":
    main()