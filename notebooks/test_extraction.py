import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extraction.extractor import parse_scope_outer_trailing_label, parse_referral_required

# --- Highmark deductible (regression check after generalizing the function) ---

highmark_deductible_text = (
    "$2,000 individual/$4,000 family network. "
    "$4,000 individual/$8,000 family out-of-network.."
)
print("Highmark deductible:")
for e in parse_scope_outer_trailing_label(highmark_deductible_text, scope_labels=["out-of-network", "network"]):
    print(" ", e)

# --- UHC OOP max (new shape: same as Highmark's, but no trailing punctuation) ---

uhc_oop_text = (
    "$3,000 person / $6,000 family In-network "
    "$5,000 person / $10,000 family Out-of-network."
)
print("UHC OOP max:")
for e in parse_scope_outer_trailing_label(uhc_oop_text, scope_labels=["out-of-network", "in-network"]):
    print(" ", e)
    
    # --- Referral required ---

referral_cases = {
    "Aetna":   "No..",
    "Highmark": "o No..",
    "Blue Shield CA": "Yes..",
    "Kaiser":  "Yes, but you may self-refer to certain specialists..",
}
print("Referral required:")
for name, text in referral_cases.items():
    print(f"  {name}: {parse_referral_required(text)}")