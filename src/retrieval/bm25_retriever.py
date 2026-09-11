# src/retrieval/bm25_retriever.py
import json
import re
from rank_bm25 import BM25Okapi
from .base import RetrievalResult

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "if", "of", "to", "in", "on", "at", "and", "or", "for", "what",
    "how", "you", "your", "my", "i", "me", "we", "us", "this", "that",
    "it", "be", "been", "being", "has", "have", "had", "will", "would",
    "can", "could", "should", "not", "so", "than", "then", "there",
    "here", "with", "from", "by", "as", "when", "where", "who", "which",
}

def tokenize(text: str) -> list[str]:
    # lowercase, strip punctuation, split on whitespace.
    # No stemming yet — SBC vocabulary ("deductible", "coinsurance", "copay")
    # is plain enough that it may not be needed; revisit if we see recall
    # problems from simple plural/tense mismatches once we have real queries.
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]

class BM25Retriever:
    def __init__(self, chunks_path: str = "data/processed/chunks.json"):
        with open(chunks_path) as f:
            self.chunks = json.load(f)
        tokenized_corpus = [tokenize(c["text"]) for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        scores = self.bm25.get_scores(tokenize(query))
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [
            RetrievalResult(
                chunk_id=self.chunks[i]["chunk_id"],
                text=self.chunks[i]["text"],
                score=float(scores[i]),
                metadata={k2: v for k2, v in self.chunks[i].items() if k2 not in ("chunk_id", "text")},
            )
            for i in ranked_indices
        ]