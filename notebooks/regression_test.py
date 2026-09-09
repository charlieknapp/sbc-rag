"""
Regression check for the four documents validated early in Phase 2
(Highmark, Aetna, BCBS IL, Kaiser), re-run against the current codebase
after all the UHC/Cigna/Blue Shield CA/Anthem work. Every fix made during
that work either lives in a new file these four never import
(strip_invisible.py, camelot_extract.py) or is gated behind a flag that
defaults off for them (split_camelot_merged_rows). This script is the
actual verification of that claim, rather than continuing to rely on
reasoning-through-the-code-paths alone.

Expected baselines, from when each document was originally validated:
- Highmark: 7 Important Questions rows, 28 grid rows
- Aetna:    7 Important Questions rows, 30 grid rows
- BCBS IL:  7 Important Questions rows, 32 grid rows
- Kaiser:   7 Important Questions rows, 30 grid rows

A mismatch doesn't necessarily mean something broke -- skim the printed
rows themselves, not just the counts, before concluding that.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parsing.pdfplumber_extract import extract_pdfplumber_tables
from src.parsing.normalize import (
    normalize_document,
    GRID_TABLE_SPEC,
    IMPORTANT_QUESTIONS_SPEC,
)

DOCUMENTS = {
    "Highmark": ("data/raw/highmark_hdhp_ppoblue_2026.pdf", 7, 28),
    "Aetna": ("data/raw/aetna_md_bronze_ppo_2019.pdf", 7, 30),
    "BCBS IL": ("data/raw/bcbsil_bluechoice_bronze_ppo_2024.pdf", 7, 32),
    "Kaiser": ("data/raw/kaiser_ca_traditional_hmo_2026.pdf", 7, 30),
}

for name, (path, expected_iq, expected_grid) in DOCUMENTS.items():
    print(f"=== {name} ===")
    pages = extract_pdfplumber_tables(path)

    iq_rows = normalize_document(pages, IMPORTANT_QUESTIONS_SPEC)
    status = "OK" if len(iq_rows) == expected_iq else "MISMATCH"
    print(f"Important Questions: {len(iq_rows)} rows (expected {expected_iq}) [{status}]")

    grid_rows = normalize_document(pages, GRID_TABLE_SPEC)
    status = "OK" if len(grid_rows) == expected_grid else "MISMATCH"
    print(f"Grid table: {len(grid_rows)} rows (expected {expected_grid}) [{status}]")
    print()