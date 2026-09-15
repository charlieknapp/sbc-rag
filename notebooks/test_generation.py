import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever
from src.generation.evidence import gather_evidence
from src.generation.generation import generate_answer

bm25 = BM25Retriever()
embedding = EmbeddingRetriever()

questions = [
    "Which plan has the lowest deductible?",
    "Which plan has the highest out-of-pocket limit?",
]

for q in questions:
    bundle = gather_evidence(q, bm25, embedding)
    result = generate_answer(q, bundle)
    print(f"Q: {q}")
    print(f"  confident={result.confident}")
    print(f"  answer: {result.answer}")
    for c in result.citations:
        print(f"    - {c.insurer} | {c.section} | {c.source_type}")
    print()