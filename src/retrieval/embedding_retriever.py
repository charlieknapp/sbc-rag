import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from .base import RetrievalResult

class EmbeddingRetriever:
    def __init__(self, chunks_path: str = "data/processed/chunks.json", model_name: str = "all-MiniLM-L6-v2"):
        with open(chunks_path) as f:
            self.chunks = json.load(f)

        self.model = SentenceTransformer(model_name)

        texts = [c["text"] for c in self.chunks]
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
        faiss.normalize_L2(embeddings)  # in-place L2 normalization -> inner product == cosine similarity

        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings)

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        query_vec = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_vec)

        scores, indices = self.index.search(query_vec, k)

        return [
            RetrievalResult(
                chunk_id=self.chunks[i]["chunk_id"],
                text=self.chunks[i]["text"],
                score=float(score),
                metadata={k2: v for k2, v in self.chunks[i].items() if k2 not in ("chunk_id", "text")},
            )
            for score, i in zip(scores[0], indices[0])
        ]