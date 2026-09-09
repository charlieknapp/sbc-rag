import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parsing.camelot_extract import extract_camelot_tables
from src.parsing.normalize import normalize_document, IMPORTANT_QUESTIONS_SPEC

PDF_PATH = "data/raw/anthem_ppo_hsa_2022.pdf"

pages = extract_camelot_tables(PDF_PATH, flavor="lattice")
cleaned_rows = normalize_document(pages, IMPORTANT_QUESTIONS_SPEC)

print(f"Normalized into {len(cleaned_rows)} clean row(s):\n")
for row in cleaned_rows:
    print(row)
    print()