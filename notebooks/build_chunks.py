"""
Runs the chunk builder (src/chunking/chunker.py) against every document in
data/processed/ and writes the combined result to data/processed/chunks.json
-- one flat list of chunk objects across all 8 documents, ready for
retrieval to index.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.chunking.chunker import build_document_chunks

PROCESSED_DIR = Path("data/processed")
OUTPUT_PATH = PROCESSED_DIR / "chunks.json"


def main():
    all_chunks = []

    for path in sorted(PROCESSED_DIR.glob("*.json")):
        if path.name == "chunks.json":
            continue
        with open(path) as f:
            doc = json.load(f)
        chunks = build_document_chunks(doc)
        all_chunks.extend(asdict(c) for c in chunks)
        print(f"{path.name}: {len(chunks)} chunks")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_chunks, f, indent=2)

    print(f"\nWrote {len(all_chunks)} total chunks to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()