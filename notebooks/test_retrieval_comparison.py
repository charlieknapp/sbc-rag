# notebooks/test_retrieval_comparison.py
import sys
import json
sys.path.append("src")

from retrieval.bm25_retriever import BM25Retriever, tokenize
from retrieval.embedding_retriever import EmbeddingRetriever

TARGET_IDS = {21}

def load_questions(path="eval/questions.jsonl"):
    questions = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions

bm25 = BM25Retriever()
embed = EmbeddingRetriever()

questions = [q for q in load_questions() if q["id"] in TARGET_IDS]

for q in questions:
    print(f"\n{'='*80}")
    print(f"id={q['id']}  category={q['category']}")
    print(f"Query: {q['question']!r}")
    print(f"Expected chunk_ids: {q['expected_chunk_ids']}")

    print("\n  [BM25 top 10]")
    for rank, r in enumerate(bm25.retrieve(q["question"], k=10), start=1):
        overlap = set(tokenize(q["question"])) & set(tokenize(r.text))
        marker = " <-- EXPECTED" if r.chunk_id in q["expected_chunk_ids"] else ""
        print(f"    {rank:2d}. score={r.score:.3f}  overlap={overlap}{marker}")
        print(f"        {r.chunk_id}")
        print(f"        {r.text}")

    print("\n  [Embeddings top 10]")
    for rank, r in enumerate(embed.retrieve(q["question"], k=10), start=1):
        marker = " <-- EXPECTED" if r.chunk_id in q["expected_chunk_ids"] else ""
        print(f"    {rank:2d}. score={r.score:.3f}{marker}")
        print(f"        {r.chunk_id}")
        print(f"        {r.text}")