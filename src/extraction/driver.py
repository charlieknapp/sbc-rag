import json
import re

from .extractor import (
    clean_text,
    parse_flat_single_value,
    parse_flat_tier_only,
    parse_scope_outer_colon,
    parse_tier_outer_bcbsil,
    parse_scope_outer_trailing_clause,
    parse_scope_outer_trailing_label,
    parse_highmark_oop_max,
    parse_category_outer_colon,
    parse_kaiser_oop_max,
    parse_referral_required,
)
from .schema import PlanFacts

QUESTION_MARKERS = {
    "deductible": "what is the overall deductible",
    "oop_max": "out-of-pocket limit for this plan",
    "referral": "you need a referral",
}

# Both patterns find the same "Answer: ... Why this matters:" span; the raw
# variant additionally captures the actual trailing punctuation (one or two
# periods) so the stored raw text reflects what was really there, rather
# than a forced convention.
ANSWER_PATTERN_CLEANED = r"Answer:\s*(.*?)\.\.?\s*Why this matters:"
ANSWER_PATTERN_RAW = r"Answer:\s*(.*?)(\.\.?)\s*Why this matters:"

EXTRACTOR_REGISTRY = {
    ("aetna_md_bronze_ppo_2019.pdf", "deductible"): parse_scope_outer_colon,
    ("aetna_md_bronze_ppo_2019.pdf", "oop_max"): parse_scope_outer_colon,

    ("anthem_ppo_hsa_2022.pdf", "deductible"): parse_scope_outer_trailing_clause,
    ("anthem_ppo_hsa_2022.pdf", "oop_max"): parse_scope_outer_trailing_clause,

    ("bcbsil_bluechoice_bronze_ppo_2024.pdf", "deductible"): parse_tier_outer_bcbsil,
    ("bcbsil_bluechoice_bronze_ppo_2024.pdf", "oop_max"): parse_tier_outer_bcbsil,

    ("blueshield_ca_calpers_access_hmo_2025.pdf", "deductible"): parse_flat_single_value,
    ("blueshield_ca_calpers_access_hmo_2025.pdf", "oop_max"): parse_category_outer_colon,

    ("cigna_nc_connect_bronze_hmo_2024.pdf", "deductible"): parse_flat_tier_only,
    ("cigna_nc_connect_bronze_hmo_2024.pdf", "oop_max"): parse_flat_tier_only,

    ("highmark_hdhp_ppoblue_2026.pdf", "deductible"):
        lambda t: parse_scope_outer_trailing_label(t, scope_labels=["out-of-network", "network"]),
    ("highmark_hdhp_ppoblue_2026.pdf", "oop_max"): parse_highmark_oop_max,

    ("kaiser_ca_traditional_hmo_2026.pdf", "deductible"): parse_flat_single_value,
    ("kaiser_ca_traditional_hmo_2026.pdf", "oop_max"): parse_kaiser_oop_max,

    ("uhc_stancounty_hdhp_2025.pdf", "deductible"): parse_flat_tier_only,
    ("uhc_stancounty_hdhp_2025.pdf", "oop_max"):
        lambda t: parse_scope_outer_trailing_label(t, scope_labels=["out-of-network", "in-network"]),
}


def load_chunks(chunks_path: str = "data/processed/chunks.json") -> list[dict]:
    with open(chunks_path) as f:
        return json.load(f)


def find_answer_text(chunks: list[dict], source_filename: str, field: str) -> tuple[str, str] | None:
    """
    Finds the "important_questions" chunk for a given plan and field
    (deductible / oop_max / referral). Returns a (cleaned_text, raw_text)
    tuple:
      - cleaned_text: artifact-normalized via clean_text() (dash variants,
        stray post-hyphen spaces) — what the parser functions should
        consume, since they were built and tested against this form.
      - raw_text: the true original answer text straight from the chunk,
        untouched — what PlanFacts' raw_*_text fields should store, so
        "raw" actually means raw rather than "raw-ish."
    Returns None — not a guess — if no matching chunk is found, so a
    plan/field combination we haven't seen the real wording for surfaces
    as a loud gap rather than a silently missing value.
    """
    marker = QUESTION_MARKERS[field]
    for chunk in chunks:
        if chunk.get("source_filename") != source_filename:
            continue
        if chunk.get("section") != "important_questions":
            continue

        raw_chunk_text = chunk.get("text", "")
        cleaned_chunk_text = clean_text(raw_chunk_text)

        if marker not in cleaned_chunk_text.lower():
            continue

        cleaned_match = re.search(ANSWER_PATTERN_CLEANED, cleaned_chunk_text, flags=re.IGNORECASE | re.DOTALL)
        raw_match = re.search(ANSWER_PATTERN_RAW, raw_chunk_text, flags=re.IGNORECASE | re.DOTALL)
        if cleaned_match and raw_match:
            cleaned_text = cleaned_match.group(1).strip() + ".."
            raw_text = raw_match.group(1).strip() + raw_match.group(2)
            return cleaned_text, raw_text
    return None


def get_plan_metadata(chunks: list[dict], source_filename: str) -> dict:
    for chunk in chunks:
        if chunk.get("source_filename") == source_filename and chunk.get("section") == "header_metadata":
            text = clean_text(chunk.get("text", ""))
            plan_type_match = re.search(r"Plan Type:\s*(.+)", text)
            return {
                "insurer": chunk.get("insurer"),
                "plan_name": chunk.get("plan_name"),
                "plan_type": plan_type_match.group(1).strip() if plan_type_match else None,
            }
    return {}


def build_plan_facts(chunks: list[dict], source_filename: str) -> PlanFacts:
    metadata = get_plan_metadata(chunks, source_filename)

    deductible_result = find_answer_text(chunks, source_filename, "deductible")
    oop_result = find_answer_text(chunks, source_filename, "oop_max")
    referral_result = find_answer_text(chunks, source_filename, "referral")

    # fail loud: don't silently build a PlanFacts on missing source text
    missing = [name for name, val in [("deductible", deductible_result), ("oop_max", oop_result), ("referral", referral_result)] if val is None]
    if missing:
        raise ValueError(f"{source_filename}: could not find answer text for: {missing}")

    deductible_cleaned, deductible_raw = deductible_result
    oop_cleaned, oop_raw = oop_result
    referral_cleaned, referral_raw = referral_result

    deductible_parser = EXTRACTOR_REGISTRY[(source_filename, "deductible")]
    oop_parser = EXTRACTOR_REGISTRY[(source_filename, "oop_max")]

    return PlanFacts(
        source_filename=source_filename,
        insurer=metadata["insurer"],
        plan_name=metadata["plan_name"],
        plan_type=metadata["plan_type"],
        deductibles=deductible_parser(deductible_cleaned),
        out_of_pocket_maxes=oop_parser(oop_cleaned),
        referral_required=parse_referral_required(referral_cleaned),
        raw_referral_text=referral_raw,
        raw_deductible_text=deductible_raw,
        raw_oop_max_text=oop_raw,
    )


def build_all_plan_facts(
    chunks_path: str = "data/processed/chunks.json",
    output_path: str = "data/processed/plan_facts.json",
) -> list[PlanFacts]:
    chunks = load_chunks(chunks_path)
    source_filenames = sorted(set(c["source_filename"] for c in chunks))

    all_facts = [build_plan_facts(chunks, fn) for fn in source_filenames]

    with open(output_path, "w") as f:
        json.dump([pf.model_dump() for pf in all_facts], f, indent=2)

    return all_facts


if __name__ == "__main__":
    facts = build_all_plan_facts()
    print(f"Wrote {len(facts)} plans to data/processed/plan_facts.json")