import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever
from src.generation.evidence import gather_evidence

bm25 = BM25Retriever()
embedding = EmbeddingRetriever()

QUESTIONS = {
    8: "What do I pay to see a specialist on the Cigna Connect Bronze plan?",
    12: "What's my share of the cost for a mental health therapy visit on the BCBS IL plan?",
}

for qnum, question in QUESTIONS.items():
    print(f"\n=== Question {qnum} ===")
    print(question)
    bundle = gather_evidence(question, bm25, embedding)
    print(f"Chunks returned: {len(bundle.chunks)}")
    for c in bundle.chunks:
        section = c.metadata["section"]
        category = c.metadata.get("category", "")
        insurer = c.metadata["insurer"]
        plan = c.metadata["plan_name"]
        print(f"  [{insurer} - {plan}] {section} / {category}:")
        print(f"    {c.text}")