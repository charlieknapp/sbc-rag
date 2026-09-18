import json
from dataclasses import dataclass

from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever
from src.extraction.driver import load_chunks

from .comparison import ComparisonResult, compute_comparison, detect_comparison_question
from .service_coverage import ServiceCoverageEntry, build_service_coverage_index, detect_service_coverage_question


@dataclass
class EvidenceBundle:
    chunks: list
    plan_facts: list[dict]
    comparison_result: ComparisonResult | None = None
    service_coverage_entries: list[ServiceCoverageEntry] | None = None
    service_coverage_service: str | None = None
    


def gather_evidence(
    question: str,
    bm25: BM25Retriever,
    embedding: EmbeddingRetriever,
    plan_facts_path: str = "data/processed/plan_facts.json",
    k: int = 10,
) -> EvidenceBundle:
    bm25_results = bm25.retrieve(question, k=k)
    embedding_results = embedding.retrieve(question, k=k)

    seen_ids = set()
    combined_chunks = []
    for result in bm25_results + embedding_results:
        if result.chunk_id not in seen_ids:
            seen_ids.add(result.chunk_id)
            combined_chunks.append(result)

    with open(plan_facts_path) as f:
        all_plan_facts = json.load(f)

    all_chunks = load_chunks()
    comparison_result = None
    detected = detect_comparison_question(question)
    if detected is not None:
        field, direction = detected
        comparison_result = compute_comparison(field, direction, all_plan_facts)
    service_coverage_entries = None
    service_coverage_service = detect_service_coverage_question(question)
    if service_coverage_service is not None:
        service_coverage_entries = build_service_coverage_index(all_chunks)

    return EvidenceBundle(
        chunks=combined_chunks,
        plan_facts=all_plan_facts,
        comparison_result=comparison_result,
        service_coverage_entries=service_coverage_entries,
        service_coverage_service=service_coverage_service,
    )