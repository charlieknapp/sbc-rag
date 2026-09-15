import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever
from src.generation.pipeline import answer_question

bm25 = BM25Retriever()
embedding = EmbeddingRetriever()

with open("eval/questions.jsonl") as f:
    questions = [json.loads(line) for line in f if line.strip()]

for q in questions:
    pipeline_result = answer_question(q["question"], bm25, embedding)
    result = pipeline_result.result

    print(f"[{q['id']}] {q['question']}")
    print(f"  expected: {q['expected_answer']}")
    print(f"  got:      {result.answer[:200]}")
    print(f"  confident={result.confident}  citations={len(result.citations)}  issues={len(pipeline_result.verification_issues)}")
    for c in result.citations:
        print(f"    - {c.insurer} | {c.section} | {c.source_type}")
    print()