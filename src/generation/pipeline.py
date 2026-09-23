from dataclasses import dataclass

from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever

from .direct_lookup import build_direct_answer, detect_direct_lookup
from .evidence import gather_evidence
from .generation import CitationIssue, GenerationMetrics, generate_answer, verify_citations
from .schema import Citation, GeneratedAnswer


@dataclass
class PipelineResult:
    question: str
    result: GeneratedAnswer
    verification_issues: list[CitationIssue]
    metrics: GenerationMetrics


def answer_question(
    question: str,
    bm25: BM25Retriever,
    embedding: EmbeddingRetriever,
) -> PipelineResult:
    bundle = gather_evidence(question, bm25, embedding)

    direct_match = detect_direct_lookup(question, bundle.plan_facts)
    if direct_match is not None:
        source_filename, field = direct_match
        direct = build_direct_answer(source_filename, field, bundle.plan_facts)
        if direct is not None:
            result = GeneratedAnswer(
                answer=direct["answer"],
                confident=True,
                citations=[
                    Citation(
                        insurer=direct["insurer"],
                        plan_name=direct["plan_name"],
                        source_filename=direct["source_filename"],
                        section=direct["section"],
                        source_type="verified_plan_data",
                    )
                ],
            )
            metrics = GenerationMetrics(
                latency_seconds=0.0,
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0.0,
            )
            return PipelineResult(
                question=question,
                result=result,
                verification_issues=[],
                metrics=metrics,
            )
        # direct_match detected but this plan/field combo has no usable data
        # (e.g. field never extracted for this plan) — fall through rather
        # than dead-ending the question.

    result, metrics = generate_answer(question, bundle)
    issues = verify_citations(result, bundle)

    return PipelineResult(
        question=question,
        result=result,
        verification_issues=issues,
        metrics=metrics,
    )