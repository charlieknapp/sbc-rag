from typing import Literal

from .comparison import _get_canonical_entry

Field = Literal["deductible", "oop_max", "referral"]

INSURER_KEYWORDS: dict[str, list[str]] = {
    "kaiser_ca_traditional_hmo_2026.pdf": ["kaiser"],
    "aetna_md_bronze_ppo_2019.pdf": ["aetna"],
    "uhc_stancounty_hdhp_2025.pdf": ["unitedhealthcare", "united healthcare", "uhc"],
    "cigna_nc_connect_bronze_hmo_2024.pdf": ["cigna"],
    "blueshield_ca_calpers_access_hmo_2025.pdf": ["blue shield of ca", "blue shield california", "blue shield of california"],
    "bcbsil_bluechoice_bronze_ppo_2024.pdf": ["blue cross blue shield of il", "bcbs il", "bcbs of illinois", "blue cross blue shield of illinois"],
    "anthem_ppo_hsa_2022.pdf": ["anthem"],
    "highmark_hdhp_ppoblue_2026.pdf": ["highmark"],
}

FIELD_KEYWORDS: dict[Field, list[str]] = {
    "deductible": ["deductible"],
    # NOTE: bare "out-of-pocket"/"out of pocket" deliberately excluded — it's
    # used colloquially ("how much would I owe out of pocket for...") to mean
    # "what do I pay", not the technical out-of-pocket-maximum field. Requiring
    # a max/limit qualifier avoids that collision (confirmed bug: eval #7).
    "oop_max": [
        "out-of-pocket max", "out-of-pocket maximum", "out-of-pocket limit",
        "out of pocket max", "out of pocket maximum", "out of pocket limit",
        "oop max", "oop limit",
    ],
    "referral": ["referral"],
}

# ACA metal tiers. Used only as a plan-identity guard: INSURER_KEYWORDS matches
# on insurer name alone, which isn't enough to confirm the question is asking
# about the actual plan on file rather than a differently-tiered (possibly
# nonexistent) plan from the same insurer (confirmed bug: eval #27, "Cigna
# Platinum PPO" silently resolved to the real Cigna Bronze plan).
METAL_TIERS = ("bronze", "silver", "gold", "platinum", "catastrophic")

# Tier/network qualifiers the canonical entry can't distinguish (it's always
# "individual, in-network"). If the question names one explicitly, direct
# lookup can't safely answer it — decline and let the LLM path read the real
# tiered figures from SBC text instead.
SCOPE_QUALIFIERS = ("family", "out-of-network", "out of network", "non-participating")

def detect_direct_lookup(question: str, all_plan_facts: list[dict]) -> tuple[str, Field] | None:
    q = question.lower()

    if any(s in q for s in SCOPE_QUALIFIERS):
        return None
    
    matched_plans = [fn for fn, keywords in INSURER_KEYWORDS.items() if any(k in q for k in keywords)]
    if len(matched_plans) != 1:
        return None

    matched_fields = [f for f, keywords in FIELD_KEYWORDS.items() if any(k in q for k in keywords)]
    if len(matched_fields) != 1:
        return None

    source_filename = matched_plans[0]

    # Plan-identity guard: if the question names a metal tier that doesn't
    # match this plan's own tier, this isn't actually the plan being asked
    # about — decline rather than silently substituting the wrong plan.
    mentioned_tiers = [t for t in METAL_TIERS if t in q]
    if mentioned_tiers:
        plan = next((p for p in all_plan_facts if p["source_filename"] == source_filename), None)
        if plan is None:
            return None
        plan_name_lower = plan["plan_name"].lower()
        if any(t not in plan_name_lower for t in mentioned_tiers):
            return None

    return source_filename, matched_fields[0]

def build_direct_answer(source_filename: str, field: Field, all_plan_facts: list[dict]) -> dict | None:
    plan = next((p for p in all_plan_facts if p["source_filename"] == source_filename), None)
    if plan is None:
        return None

    if field == "referral":
        required = plan.get("referral_required")
        if required is None:
            return None
        answer = (
            f"{'Yes' if required else 'No'}, you {'do' if required else 'do not'} need a referral "
            f"to see a specialist on the {plan['insurer']} - {plan['plan_name']} plan."
        )
        # raw_referral_text is sometimes just a bare "Yes."/"No." restating the
        # boolean with no added information (e.g. Blue Shield CA) — appending
        # it verbatim in that case produces a redundant "Yes... Yes.." sentence
        # (confirmed bug: eval #3). Only append when it says something new.
        extra = (plan.get("raw_referral_text") or "").strip()
        if extra.rstrip(".").lower() not in ("", "yes", "no"):
            answer += f" {extra}"
        section = "referral requirement"
    else:
        canonical = _get_canonical_entry(plan, field)
        if canonical is None:
            return None
        field_label = "deductible" if field == "deductible" else "out-of-pocket maximum"
        amount_text = "unlimited" if canonical["is_unlimited"] else f"${canonical['amount']:,.0f}"
        answer = (
            f"The {field_label} for the {plan['insurer']} - {plan['plan_name']} plan is "
            f"{amount_text} ({canonical['label']})."
        )
        section = field_label

    return {
        "answer": answer,
        "insurer": plan["insurer"],
        "plan_name": plan["plan_name"],
        "source_filename": plan["source_filename"],
        "section": section,
    }