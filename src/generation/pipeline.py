from dataclasses import dataclass

from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever

from .evidence import gather_evidence
from .generation import CitationIssue, GenerationMetrics, generate_answer, verify_citations
from .schema import GeneratedAnswer


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
    result, metrics = generate_answer(question, bundle)
    issues = verify_citations(result, bundle)

    return PipelineResult(
        question=question,
        result=result,
        verification_issues=issues,
        metrics=metrics,
    )