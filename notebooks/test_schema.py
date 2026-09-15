import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generation.schema import Citation, GeneratedAnswer
from pydantic import ValidationError

# --- Valid case: a normal answer with both citation types ---

answer = GeneratedAnswer(
    answer="Your deductible on the Highmark plan is $2,000 individual / $4,000 family in-network.",
    citations=[
        Citation(
            insurer="Highmark BCBS",
            plan_name="Carnegie Mellon University: PPO Blue",
            section="deductible",
            source_type="verified_plan_data",
        ),
        Citation(
            insurer="Highmark BCBS",
            plan_name="Carnegie Mellon University: PPO Blue",
            section="important_questions",
            source_type="sbc_text",
        ),
    ],
    confident=True,
)
print("Valid answer built successfully:", answer.answer[:50], "...")

# --- Valid case: the low-confidence/refusal shape (no citations) ---

refusal = GeneratedAnswer(
    answer="I don't have enough information to answer that confidently.",
    citations=[],
    confident=False,
)
print("Refusal case built successfully:", refusal.confident, refusal.citations)

# --- Invalid case: source_type isn't one of the two allowed literals ---

try:
    Citation(
        insurer="Highmark BCBS",
        plan_name="Carnegie Mellon University: PPO Blue",
        section="deductible",
        source_type="made_up_type",
    )
    print("ERROR: should have raised a validation error and did not")
except ValidationError as e:
    print("Validator correctly rejected bad source_type:")
    print(e)