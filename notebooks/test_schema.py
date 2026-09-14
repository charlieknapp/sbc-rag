# notebooks/test_schema.py
import sys
sys.path.append("src")

from extraction.schema import AmountEntry, PlanFacts

# should succeed
kaiser = PlanFacts(
    source_filename="kaiser_ca_traditional_hmo_2026.pdf",
    insurer="Kaiser Permanente",
    plan_name="CalPERS TRADITIONAL HMO",
    plan_type="HMO",
    deductibles=[AmountEntry(label="individual", amount=0.0)],
    out_of_pocket_maxes=[
        AmountEntry(label="individual, medical", amount=1500.0),
        AmountEntry(label="family, medical", amount=3000.0),
    ],
    referral_required=False,
    raw_referral_text="Yes, but you may self-refer to certain specialists.",
    raw_deductible_text="$0",
    raw_oop_max_text="$1,500 Individual / $3,000 Family.",
)
print("Kaiser built successfully:", kaiser.insurer)

# should raise — Aetna's out-of-network OOP max is "Unlimited," this represents it wrong
# (both amount and is_unlimited set) to confirm the validator actually rejects it
try:
    bad = AmountEntry(label="family, out-of-network", amount=27000.0, is_unlimited=True)
    print("BUG: this should have raised but didn't")
except ValueError as e:
    print("Validator correctly rejected bad entry:", e)