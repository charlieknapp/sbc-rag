# notebooks/test_bm25.py
import sys
sys.path.append("src")

from retrieval.bm25_retriever import BM25Retriever, tokenize

retriever = BM25Retriever()

queries = [
    "what is the deductible for Kaiser",
    "what do I pay to see a specialist",
]

for query in queries:
    print(f"\n=== Query: {query!r} ===")
    results = retriever.retrieve(query, k=10)
    for rank, r in enumerate(results, start=1):
        overlap = set(tokenize(query)) & set(tokenize(r.text))
        print(f"{rank}. score={r.score:.3f}  overlap={overlap}  {r.text[:120]}...")