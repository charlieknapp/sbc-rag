import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever
from src.generation.evidence import gather_evidence
from src.generation.generation import generate_answer, verify_citations
from src.generation.schema import Citation, GeneratedAnswer

bm25 = BM25Retriever()
embedding = EmbeddingRetriever()

# --- Valid case: a real generated answer, should pass with zero issues ---

question = "What is the deductible for the Aetna plan?"
bundle = gather_evidence(question, bm25, embedding)
result = generate_answer(question, bundle)

issues = verify_citations(result, bundle)
print(f"Real answer, issue count: {len(issues)}")
for issue in issues:
    print(f"  UNEXPECTED ISSUE: {issue.reason}")

# --- Invalid case: a deliberately fabricated citation for a plan never in this bundle ---

fake_result = GeneratedAnswer(
    answer="The Kaiser plan has a $0 deductible.",
    citations=[
        Citation(
            insurer="Kaiser Permanente",
            plan_name="CalPERS TRADITIONAL HMO",
            section="deductible",
            source_type="verified_plan_data",
        )
    ],
    confident=True,
)

fake_issues = verify_citations(fake_result, bundle)
print(f"\nFabricated citation, issue count: {len(fake_issues)}")
for issue in fake_issues:
    print(f"  Correctly caught: {issue.reason}")