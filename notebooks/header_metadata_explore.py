"""
Exploration script: dumps each document's first-page text (routed through
the same invisible-text-stripping the table extraction already uses for
camelot documents, so UHC-style duplicate text doesn't show up here too)
to look at how header metadata (Coverage Period, Coverage for, Plan Type,
plan name) is actually laid out before designing extraction logic.
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

for filename, config in DOCUMENT_REGISTRY.items():
    path = f"data/raw/{filename}"
    print(f"=== {filename} ({config.insurer}) ===")

    if config.extract_fn is extract_camelot_tables:
        # This document's tables are routed through camelot, which strips
        # invisible-render-mode text first. Do the same here, or a
        # document like UHC comes back with duplicated header text.
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            cleaned_path = tmp.name
        try:
            strip_invisible_text_from_pdf(path, cleaned_path)
            with pdfplumber.open(cleaned_path) as pdf:
                text = pdf.pages[0].extract_text()
        finally:
            os.remove(cleaned_path)
    else:
        with pdfplumber.open(path) as pdf:
            text = pdf.pages[0].extract_text()

    print(text[:1200])
    print()