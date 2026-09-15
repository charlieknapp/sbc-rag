import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever
from src.generation.evidence import gather_evidence
from src.generation.generation import build_context_block

bm25 = BM25Retriever()
embedding = EmbeddingRetriever()

bundle = gather_evidence("Which plan has the highest out-of-pocket limit?", bm25, embedding)
print(build_context_block(bundle))