import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever
from src.generation.evidence import gather_evidence

bm25 = BM25Retriever()
embedding = EmbeddingRetriever()

questions = [
    "Which plan has the lowest deductible?",
    "Which plan has the highest out-of-pocket limit?",
    "What is the deductible for the Aetna plan?",
]

for q in questions:
    bundle = gather_evidence(q, bm25, embedding)
    print(f"Q: {q}")
    print(f"  chunks: {len(bundle.chunks)}  plan_facts: {len(bundle.plan_facts)}")
    if bundle.comparison_result:
        r = bundle.comparison_result
        print(f"  comparison: {r.field} {r.direction}")
        print(f"    winners: {[(e.insurer, e.amount) for e in r.winners]}")
        print(f"    unlimited: {r.unlimited_plans}")
    else:
        print("  comparison: None")
    print()