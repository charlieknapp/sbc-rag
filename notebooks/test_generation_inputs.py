import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# notebooks/test_generation_inputs.py (extend with this block, or run standalone)

# 1. See the exact context block the model receives for this question
from src.generation.evidence import gather_evidence
from src.generation.generation import build_context_block
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever

bm25 = BM25Retriever()
emb = EmbeddingRetriever()

QUESTION = "What are the limitations on chiropractic care under the Kaiser plan?"

# 2. Run the real question through the full pipeline 3x, same discipline as #15
from src.generation.pipeline import answer_question

for i in range(3):
    pr = answer_question(QUESTION, bm25, emb)
    print(f"--- Run {i+1} ---")
    print("confident:", pr.result.confident)
    print("answer:", pr.result.answer)
    print("citations:", pr.result.citations)
    print("verification_issues:", pr.verification_issues)
    print()