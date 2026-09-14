import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extraction.driver import load_chunks, find_answer_text

chunks = load_chunks()

plans = sorted(set(c["source_filename"] for c in chunks))

for plan in plans:
    print(plan)
    for field in ("deductible", "oop_max", "referral"):
        answer = find_answer_text(chunks, plan, field)
        print(f"  {field}: {answer}")
    print()