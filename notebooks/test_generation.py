import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever
from src.generation.evidence import gather_evidence
from src.generation.generation import generate_answer

bm25 = BM25Retriever()
embedding = EmbeddingRetriever()

question = "What is the deductible for the Aetna plan?"
bundle = gather_evidence(question, bm25, embedding)
result, metrics = generate_answer(question, bundle)

print(f"Q: {question}")
print(f"  confident={result.confident}")
print(f"  answer: {result.answer}")
for c in result.citations:
    print(f"    - {c.insurer} | {c.section} | {c.source_type}")
print()
print(f"  latency: {metrics.latency_seconds:.2f}s")
print(f"  input tokens: {metrics.input_tokens}")
print(f"  output tokens: {metrics.output_tokens}")
print(f"  estimated cost: ${metrics.estimated_cost_usd:.6f}")