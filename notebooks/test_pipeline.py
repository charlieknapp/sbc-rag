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

total_latency = 0.0
total_input = 0
total_output = 0
total_cost = 0.0

for q in questions:
    pipeline_result = answer_question(q["question"], bm25, embedding)
    result = pipeline_result.result
    print(f"[{q['id']}] {q['question']}")
    print(f"  expected: {q['expected_answer']}")
    print(f"  got:      {result.answer}")
    print(f"  confident={result.confident}  citations={len(result.citations)}  issues={len(pipeline_result.verification_issues)}")
    for c in result.citations:
        print(f"    - {c.insurer} | {c.plan_name} | {c.source_filename} | {c.section} | {c.source_type}")
    if pipeline_result.verification_issues:
        print(f"  ISSUES: {pipeline_result.verification_issues}")
    print()
    total_latency += pipeline_result.metrics.latency_seconds
    total_input += pipeline_result.metrics.input_tokens
    total_output += pipeline_result.metrics.output_tokens
    total_cost += pipeline_result.metrics.estimated_cost_usd

n = len(questions)
print("=" * 100)
print(f"TOTALS ({n} questions): latency={total_latency:.2f}s (avg {total_latency/n:.2f}s)  "
      f"input={total_input} (avg {total_input/n:.1f})  output={total_output} (avg {total_output/n:.1f})  "
      f"cost=${total_cost:.4f} (avg ${total_cost/n:.6f})")