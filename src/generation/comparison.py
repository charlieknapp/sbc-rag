from dataclasses import dataclass
from typing import Literal

ComparisonField = Literal["deductible", "oop_max"]
Direction = Literal["lowest", "highest"]

FIELD_TO_JSON_KEY: dict[ComparisonField, str] = {
    "deductible": "deductibles",
    "oop_max": "out_of_pocket_maxes",
}

# Canonical "individual, in-network" (or closest equivalent) label per plan,
# confirmed against plan_facts.json and, for Anthem, cross-checked against
# the source PDF. Pharmacy-specific OOP maxes (Blue Shield CA, Kaiser) are
# intentionally excluded — "out-of-pocket limit" means the medical OOP max
# in common usage, and only 2 of 8 plans report pharmacy separately.
COMPARISON_LABEL_MAP: dict[str, dict[ComparisonField, str]] = {
    "aetna_md_bronze_ppo_2019.pdf": {
        "deductible": "individual, in-network",
        "oop_max": "individual, in-network",
    },
    "anthem_ppo_hsa_2022.pdf": {
        "deductible": "person, in-network",
        "oop_max": "person, in-network",
    },
    "bcbsil_bluechoice_bronze_ppo_2024.pdf": {
        "deductible": "individual, in-network",
        "oop_max": "individual, in-network",
    },
    "blueshield_ca_calpers_access_hmo_2025.pdf": {
        "deductible": "all",
        "oop_max": "medical_individual",
    },
    "cigna_nc_connect_bronze_hmo_2024.pdf": {
        "deductible": "person",
        "oop_max": "person",
    },
    "highmark_hdhp_ppoblue_2026.pdf": {
        "deductible": "in-network_individual",
        "oop_max": "network_individual",
    },
    "kaiser_ca_traditional_hmo_2026.pdf": {
        "deductible": "all",
        "oop_max": "medical_individual",
    },
    "uhc_stancounty_hdhp_2025.pdf": {
        "deductible": "person",
        "oop_max": "in-network_person",
    },
}


@dataclass
class ComparisonEntry:
    insurer: str
    plan_name: str
    amount: float


@dataclass
class ComparisonResult:
    field: ComparisonField
    direction: Direction
    winners: list[ComparisonEntry]
    all_entries: list[ComparisonEntry]
    unlimited_plans: list[str]


def _get_canonical_entry(plan: dict, field: ComparisonField) -> dict | None:
    label_map = COMPARISON_LABEL_MAP.get(plan["source_filename"])
    if label_map is None:
        return None
    target_label = label_map[field]
    for entry in plan[FIELD_TO_JSON_KEY[field]]:
        if entry["label"] == target_label:
            return entry
    return None


def _has_unlimited_entry(plan: dict, field: ComparisonField) -> bool:
    return any(entry["is_unlimited"] for entry in plan[FIELD_TO_JSON_KEY[field]])


def compute_comparison(
    field: ComparisonField,
    direction: Direction,
    all_plan_facts: list[dict],
) -> ComparisonResult:
    entries: list[ComparisonEntry] = []
    unlimited_plans: list[str] = []

    for plan in all_plan_facts:
        canonical = _get_canonical_entry(plan, field)
        if canonical is not None and not canonical["is_unlimited"]:
            entries.append(ComparisonEntry(
                insurer=plan["insurer"],
                plan_name=plan["plan_name"],
                amount=canonical["amount"],
            ))
        if _has_unlimited_entry(plan, field):
            unlimited_plans.append(f"{plan['insurer']} - {plan['plan_name']}")

    target = min(e.amount for e in entries) if direction == "lowest" else max(e.amount for e in entries)
    winners = [e for e in entries if e.amount == target]
    all_entries_sorted = sorted(entries, key=lambda e: e.amount, reverse=(direction == "highest"))

    return ComparisonResult(
        field=field,
        direction=direction,
        winners=winners,
        all_entries=all_entries_sorted,
        unlimited_plans=unlimited_plans,
    )


COMPARISON_TRIGGERS: list[tuple[ComparisonField, Direction, list[str]]] = [
    ("deductible", "lowest", ["lowest deductible", "smallest deductible", "cheapest deductible"]),
    ("deductible", "highest", ["highest deductible", "largest deductible", "biggest deductible"]),
    ("oop_max", "lowest", ["lowest out-of-pocket", "lowest out of pocket", "smallest out-of-pocket"]),
    ("oop_max", "highest", ["highest out-of-pocket", "highest out of pocket", "largest out-of-pocket", "highest out-of- pocket"]),
]


def detect_comparison_question(question: str) -> tuple[ComparisonField, Direction] | None:
    q = question.lower()
    for field, direction, phrases in COMPARISON_TRIGGERS:
        if any(p in q for p in phrases):
            return field, direction
    return None