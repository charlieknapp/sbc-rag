import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generation.comparison import compute_comparison, detect_comparison_question

with open("data/processed/plan_facts.json") as f:
    all_plan_facts = json.load(f)

print("=== compute_comparison: deductible, lowest ===")
result = compute_comparison("deductible", "lowest", all_plan_facts)
print(f"winners: {[(e.insurer, e.plan_name, e.amount) for e in result.winners]}")
print(f"all entries (sorted): {[(e.insurer, e.amount) for e in result.all_entries]}")
print(f"unlimited flags: {result.unlimited_plans}")
print()

print("=== compute_comparison: oop_max, highest ===")
result = compute_comparison("oop_max", "highest", all_plan_facts)
print(f"winners: {[(e.insurer, e.plan_name, e.amount) for e in result.winners]}")
print(f"all entries (sorted): {[(e.insurer, e.amount) for e in result.all_entries]}")
print(f"unlimited flags: {result.unlimited_plans}")
print()

print("=== compute_comparison: oop_max, lowest ===")
result = compute_comparison("oop_max", "lowest", all_plan_facts)
print(f"winners: {[(e.insurer, e.plan_name, e.amount) for e in result.winners]}")
print()

print("=== detect_comparison_question ===")
test_questions = [
    "Which plan has the lowest deductible?",
    "Which plan has the highest out-of-pocket limit?",
    "Which plan has the highest out-of- pocket limit?",  # real SBC-style artifact
    "What is the deductible for the Aetna plan?",  # should NOT trigger
    "Does this plan cover acupuncture?",  # should NOT trigger
]
for q in test_questions:
    print(f"{q!r} -> {detect_comparison_question(q)}")