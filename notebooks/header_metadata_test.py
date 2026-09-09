"""
Validates extract_header_metadata against all 8 documents via the
registry, so we can eyeball every field before treating this as done.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parsing.document_registry import DOCUMENT_REGISTRY
from src.parsing.header_metadata import extract_header_metadata

for filename, config in DOCUMENT_REGISTRY.items():
    path = f"data/raw/{filename}"
    metadata = extract_header_metadata(path, config)
    print(f"=== {filename} ===")
    print(metadata)
    print()