import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parsing.pdfplumber_extract import extract_pdfplumber_tables
from src.parsing.normalize import find_table_and_header

PDF_PATH = "data/raw/kaiser_ca_traditional_hmo_2026.pdf"  # adjust if needed

pages = extract_pdfplumber_tables(PDF_PATH)
for page_num, page_tables in enumerate(pages):
    for table in page_tables:
        for row in table:
            row_text = " | ".join(str(c) for c in row)
            if "urgent" in row_text.lower() or "immediate" in row_text.lower() or "emergency" in row_text.lower():
                print(f"page {page_num}: {row}")