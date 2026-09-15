import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.embedding_retriever import EmbeddingRetriever

retriever = EmbeddingRetriever()

question = "Does the Highmark BCBS plan cover getting my eyes checked as a kid?"  

results = retriever.retrieve(question, k=5)

for r in results:
    print(f"score={r.score:.4f}  chunk_id={r.chunk_id}")
    print(f"  metadata={r.metadata}")
    print(f"  text={r.text[:150]}...")
    print()