"""
Measures how well similarity-based boundary detection recovers the grid
table's REAL category boundaries (already known -- wherever row[0], the
category label, changes) across all 8 documents, for a range of
thresholds -- rather than picking a threshold by eye off one document's
similarity distribution (semantic_chunking_explore.py), this scores each
threshold's actual accuracy against ground truth we already have as data.

A "boundary" is the gap between row i and row i+1. True boundary set:
every gap where the category label changes. Predicted boundary set, for
a given threshold: every gap where consecutive-row cosine similarity
falls below that threshold. Precision = of the boundaries we predicted,
how many were real; recall = of the real boundaries, how many we caught;
F1 = their harmonic mean, balancing both into one comparable number.
"""

import json
import sys
from pathlib import Path
from typing import List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentence_transformers import SentenceTransformer
import numpy as np

PROCESSED_DIR = Path("data/processed")
MODEL_NAME = "all-MiniLM-L6-v2"


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def true_boundaries(rows: List[list]) -> Set[int]:
    """Real category boundaries: every gap index i where row[i][0] !=
    row[i+1][0] -- ground truth already present in the data.
    """
    return {i for i in range(len(rows) - 1) if rows[i][0] != rows[i + 1][0]}


def predicted_boundaries(embeddings: np.ndarray, threshold: float) -> Set[int]:
    """Every gap index where consecutive-row similarity falls below
    `threshold` -- where this threshold would place a chunk boundary.
    """
    return {
        i for i in range(len(embeddings) - 1)
        if cosine_similarity(embeddings[i], embeddings[i + 1]) < threshold
    }


def precision_recall_f1(predicted: Set[int], true: Set[int]) -> Tuple[float, float, float]:
    """Standard precision/recall/F1 between two boundary-position sets.
    Both empty is a trivial perfect match; either empty with the other
    non-empty scores 0 across the board, avoiding a misleading divide-by-
    zero "precision=1.0" when nothing was actually predicted.
    """
    if not predicted and not true:
        return 1.0, 1.0, 1.0
    if not predicted or not true:
        return 0.0, 0.0, 0.0

    true_positives = len(predicted & true)
    precision = true_positives / len(predicted)
    recall = true_positives / len(true)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def main():
    print("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME)

    processed_files = sorted(PROCESSED_DIR.glob("*.json"))
    thresholds = [round(t, 2) for t in np.arange(0.30, 0.85, 0.05)]

    documents = []
    for path in processed_files:
        with open(path) as f:
            doc = json.load(f)
        rows = doc["grid_table"]["rows"]
        texts = [" | ".join(str(c) for c in row if c is not None) for row in rows]
        embeddings = model.encode(texts)
        documents.append((path.stem, rows, embeddings))

    print(f"\nLoaded {len(documents)} documents.\n")
    print(f"{'threshold':>9} | {'precision':>9} | {'recall':>7} | {'f1':>6} | avg chunks/doc")
    print("-" * 65)

    results_by_threshold = {}
    for threshold in thresholds:
        precisions, recalls, f1s, chunk_counts = [], [], [], []
        for name, rows, embeddings in documents:
            true = true_boundaries(rows)
            predicted = predicted_boundaries(embeddings, threshold)
            p, r, f1 = precision_recall_f1(predicted, true)
            precisions.append(p)
            recalls.append(r)
            f1s.append(f1)
            chunk_counts.append(len(predicted) + 1)

        results_by_threshold[threshold] = (np.mean(precisions), np.mean(recalls), np.mean(f1s))
        print(f"{threshold:>9} | {np.mean(precisions):>9.3f} | {np.mean(recalls):>7.3f} | "
              f"{np.mean(f1s):>6.3f} | {np.mean(chunk_counts):>6.1f}")

    best_threshold = max(results_by_threshold, key=lambda t: results_by_threshold[t][2])
    p, r, f1 = results_by_threshold[best_threshold]
    print(f"\nBest F1 threshold: {best_threshold} (precision={p:.3f}, recall={r:.3f}, f1={f1:.3f})\n")

    for name, rows, embeddings in documents:
        true = true_boundaries(rows)
        predicted = predicted_boundaries(embeddings, best_threshold)
        p, r, f1 = precision_recall_f1(predicted, true)
        print(f"  {name}: {len(rows)} rows, {len(true)} true boundaries, "
              f"{len(predicted)} predicted, precision={p:.2f} recall={r:.2f} f1={f1:.2f}")


if __name__ == "__main__":
    main()