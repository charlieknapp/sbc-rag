"""
Diagnostic: computes and prints embedding similarity between every
consecutive pair of rows/items in one document (in original document
order), so we can look at the real distribution before picking a
similarity threshold for grouping -- rather than guessing at threshold
values blindly.
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentence_transformers import SentenceTransformer
import numpy as np

PROCESSED_DIR = Path("data/processed")
MODEL_NAME = "all-MiniLM-L6-v2"


def get_document_units(doc: dict) -> List[Tuple[str, str]]:
    """Return the document's rows/items in original order as (label, text)
    pairs -- the atomic units chunk boundaries fall between, never inside.
    """
    units: List[Tuple[str, str]] = []

    for row in doc["grid_table"]["rows"]:
        text = " | ".join(str(c) for c in row if c is not None)
        units.append(("grid_row", text))

    for row in doc["important_questions"]["rows"]:
        text = " | ".join(str(c) for c in row if c is not None)
        units.append(("iq_row", text))

    for item in doc["excluded_services"]:
        units.append(("excluded_item", item))

    for item in doc["other_covered_services"]:
        units.append(("other_covered_item", item))

    return units


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


if __name__ == "__main__":
    print("Loading embedding model (first run downloads weights)...")
    model = SentenceTransformer(MODEL_NAME)

    with open(PROCESSED_DIR / "highmark_hdhp_ppoblue_2026.json") as f:
        doc = json.load(f)

    units = get_document_units(doc)
    texts = [text for _, text in units]
    embeddings = model.encode(texts)

    sims = []
    print(f"{len(units)} rows/items, {len(units) - 1} consecutive pairs:\n")
    for i in range(1, len(units)):
        sim = cosine_similarity(embeddings[i - 1], embeddings[i])
        sims.append(sim)
        label_prev, text_prev = units[i - 1]
        label_curr, text_curr = units[i]
        print(f"  {sim:.3f}  [{label_prev}]->[{label_curr}]  "
              f"{text_prev[:50]!r} -> {text_curr[:50]!r}")

    sims = np.array(sims)
    print(f"\nmin={sims.min():.3f}  max={sims.max():.3f}  "
          f"mean={sims.mean():.3f}  median={np.median(sims):.3f}  std={sims.std():.3f}")