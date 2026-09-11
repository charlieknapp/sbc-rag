# notebooks/test_embedding.py
import sys
sys.path.append("src")

from retrieval.embedding_retriever import EmbeddingRetriever

retriever = EmbeddingRetriever()

queries = [
    "what is the deductible for Kaiser",
    "what do I pay to see a specialist",
]

for query in queries:
    print(f"\n=== Query: {query!r} ===")
    results = retriever.retrieve(query, k=5)
    for rank, r in enumerate(results, start=1):
        print(f"{rank}. score={r.score:.3f}  {r.text}")