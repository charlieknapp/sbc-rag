"""
Validates extract_service_lists against all 8 documents via the registry,
in one run -- the underlying column-reconstruction mechanism is now
confirmed against both extraction paths (pdfplumber and camelot) and both
a simple bare-term list (Highmark) and a qualifier-heavy one (Aetna), so
this switches from one-document-at-a-time debugging to a single batched
comparison pass for the remaining documents.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parsing.document_registry import DOCUMENT_REGISTRY, get_document_config
from src.parsing.excluded_services import extract_service_lists

for filename, config in DOCUMENT_REGISTRY.items():
    path = f"data/raw/{filename}"
    service_lists = extract_service_lists(path, config)

    print(f"=== {filename} ({config.insurer}) ===")
    print(f"Excluded Services ({len(service_lists.excluded_services)} items):")
    for item in service_lists.excluded_services:
        print(f"  - {item}")
    print(f"Other Covered Services ({len(service_lists.other_covered_services)} items):")
    for item in service_lists.other_covered_services:
        print(f"  - {item}")
    print()