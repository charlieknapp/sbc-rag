import json
import sys
sys.path.append("src")

from retrieval.bm25_retriever import BM25Retriever
from retrieval.embedding_retriever import EmbeddingRetriever

K = 5

def load_questions(path="eval/questions.jsonl"):
    questions = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions

def score(retriever, question, expected_ids):
    results = retriever.retrieve(question["question"], k=K)
    result_ids = [r.chunk_id for r in results]
    found = [eid for eid in expected_ids if eid in result_ids]
    hit = len(found) > 0
    # rank of the first expected id that was found, if any (1-indexed)
    rank = next((i + 1 for i, rid in enumerate(result_ids) if rid in expected_ids), None)
    return hit, rank, len(found), len(expected_ids)

def main():
    questions = load_questions()
    bm25 = BM25Retriever()
    embed = EmbeddingRetriever()

    by_category = {}

    for q in questions:
        expected_ids = q["expected_chunk_ids"]

        if q["category"] == "unanswerable":
            bm25_top = bm25.retrieve(q["question"], k=K)[0]
            embed_top = embed.retrieve(q["question"], k=K)[0]
            print(f"[UNANSWERABLE] id={q['id']}  BM25 top score={bm25_top.score:.3f}  Embeddings top score={embed_top.score:.3f}")
            continue

        bm25_hit, bm25_rank, bm25_found, total = score(bm25, q, expected_ids)
        embed_hit, embed_rank, embed_found, _ = score(embed, q, expected_ids)

        cat = by_category.setdefault(q["category"], {"bm25_hits": 0, "embed_hits": 0, "total": 0})
        cat["bm25_hits"] += int(bm25_hit)
        cat["embed_hits"] += int(embed_hit)
        cat["total"] += 1

        print(f"id={q['id']:2d} [{q['category']}]  BM25: hit={bm25_hit} rank={bm25_rank} found={bm25_found}/{total}  |  Embeddings: hit={embed_hit} rank={embed_rank} found={embed_found}/{total}")

    print("\n=== Summary by category ===")
    for cat, stats in by_category.items():
        bm25_pct = 100 * stats["bm25_hits"] / stats["total"]
        embed_pct = 100 * stats["embed_hits"] / stats["total"]
        print(f"{cat:25s}  BM25: {stats['bm25_hits']}/{stats['total']} ({bm25_pct:.0f}%)   Embeddings: {stats['embed_hits']}/{stats['total']} ({embed_pct:.0f}%)")

if __name__ == "__main__":
    main()