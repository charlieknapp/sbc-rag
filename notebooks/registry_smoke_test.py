"""
Smoke test for document_registry.py: confirms every registered document
resolves to a config that actually produces the previously-validated row
counts, via the registry's own routing (not by importing extractors
directly the way the earlier per-document scripts did). This isn't
re-validating the documents themselves -- that's already done -- it's
validating that the registry's wiring (filenames, extract_fn, spec
choice) is correct.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parsing.document_registry import DOCUMENT_REGISTRY, get_document_config
from src.parsing.normalize import normalize_document

# (expected Important Questions rows, expected grid rows), from every
# document's own validated baseline earlier in the project.
EXPECTED = {
    "highmark_hdhp_ppoblue_2026.pdf": (7, 28),
    "aetna_md_bronze_ppo_2019.pdf": (7, 30),
    "bcbsil_bluechoice_bronze_ppo_2024.pdf": (7, 32),
    "kaiser_ca_traditional_hmo_2026.pdf": (7, 30),
    "uhc_stancounty_hdhp_2025.pdf": (7, 30),
    "cigna_nc_connect_bronze_hmo_2024.pdf": (7, 30),
    "blueshield_ca_calpers_access_hmo_2025.pdf": (7, 30),
    "anthem_ppo_hsa_2022.pdf": (7, 30),
}

for filename in DOCUMENT_REGISTRY:
    config = get_document_config(filename)
    path = f"data/raw/{filename}"
    expected_iq, expected_grid = EXPECTED[filename]

    pages = config.extract_fn(path)

    iq_rows = normalize_document(pages, config.iq_spec)
    grid_rows = normalize_document(pages, config.grid_spec)

    iq_status = "OK" if len(iq_rows) == expected_iq else "MISMATCH"
    grid_status = "OK" if len(grid_rows) == expected_grid else "MISMATCH"

    print(f"{config.insurer} ({filename})")
    print(f"  Important Questions: {len(iq_rows)} (expected {expected_iq}) [{iq_status}]")
    print(f"  Grid table: {len(grid_rows)} (expected {expected_grid}) [{grid_status}]")