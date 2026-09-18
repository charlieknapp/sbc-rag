"""
Deterministic per-plan service-coverage lookup.

Same motivation as comparison.py's COMPARISON_LABEL_MAP: rather than asking
the model to read 8 plans' other_covered_services/excluded_services chunks
out of whatever retrieval happened to surface and correctly enumerate all
8, compute the real answer once, in code, and hand the model a table it
just has to report rather than reconstruct.

CANONICAL_SERVICES was verified against the real chunks.json for all 8
plans before being trusted here (see planning-and-decisions.md, "Pre-emptive
check" entry) -- every term below is confirmed to have zero false-positive
substring matches against real SBC list text for the current 8-plan corpus.
If a term is added later, or a 9th plan is added, rerun that same check
before trusting it here -- this list is not self-validating.
"""

from dataclasses import dataclass
from typing import Literal

CANONICAL_SERVICES: list[str] = [
    "acupuncture",
    "bariatric surgery",
    "chiropractic care",
    "cosmetic surgery",
    "dental care",
    "hearing aids",
    "infertility treatment",
    "long-term care",
    "private-duty nursing",
    "routine eye care",
    "routine foot care",
    "weight loss programs",
    "abortion",
    "non-emergency care when traveling outside the U.S",
]

CoverageStatus = Literal["covered", "excluded", "not_mentioned"]

_LIST_SECTIONS = ("other_covered_services", "excluded_services")

SECTION_MARKERS = {
    "other_covered_services": "other covered services",
    "excluded_services": "not covered",
}



@dataclass
class ServiceCoverageEntry:
    insurer: str
    plan_name: str
    source_filename: str
    service: str
    status: CoverageStatus
    detail: str | None  # full item text (with limitations), None if not_mentioned
    section: str | None  # which chunk this came from, None if not_mentioned


def _split_list_chunk_items(text: str, section: str) -> list[str]:
    """
    Split a other_covered_services/excluded_services chunk's dense
    semicolon-joined text into individual items, stripping the leading
    "Insurer - Plan. Other covered services:" preamble and trailing
    punctuation on each item.

    Splits on the known section marker ("other covered services" /
    "not covered", via SECTION_MARKERS) rather than the first colon in
    the text. A first-colon split breaks on 3 of 8 plans (Anthem, Cigna,
    Highmark), whose own insurer/plan-name text contains an earlier colon
    ("...Inc.: Custom Anthem...", "...University: PPO Blue...") -- that
    split point lands on the plan-name colon instead of the real marker,
    gluing the whole preamble onto the first item. Confirmed via real
    build_context_block() output before this fix (see planning-and-decisions.md).

    Same splitting logic used to build and verify CANONICAL_SERVICES
    against real data -- keep these in sync if either changes.
    """
    marker = SECTION_MARKERS.get(section)
    if marker:
        idx = text.lower().find(marker)
        if idx != -1:
            colon_idx = text.find(":", idx)
            if colon_idx != -1:
                text = text[colon_idx + 1:]
    elif ":" in text:
        # Fallback for an unrecognized section -- old behavior, unchanged.
        text = text.split(":", 1)[1]
    return [item.strip().rstrip(".").strip() for item in text.split(";") if item.strip()]


def _find_matching_item(service: str, items: list[str]) -> str | None:
    """Return the first item containing `service` as a substring (case-insensitive), or None."""
    service_lower = service.lower()
    for item in items:
        if service_lower in item.lower():
            return item
    return None


def build_service_coverage_index(all_chunks: list[dict]) -> list[ServiceCoverageEntry]:
    """
    For every distinct plan present in all_chunks and every canonical
    service, determine covered / excluded / not_mentioned by scanning that
    plan's other_covered_services and excluded_services chunks.

    Deliberately includes not_mentioned entries rather than omitting them --
    #25's bug was silently presenting an incomplete list as complete, and
    the fix for that is disclosing absence-of-evidence honestly, not just
    getting the present cases right.
    """
    list_chunks = [c for c in all_chunks if c.get("section") in _LIST_SECTIONS]

    # group list chunks by plan (source_filename is the stable key, per Fix #4)
    plans: dict[str, dict] = {}
    for chunk in list_chunks:
        key = chunk["source_filename"]
        plans.setdefault(key, {"insurer": chunk["insurer"], "plan_name": chunk["plan_name"]})
        plans[key][chunk["section"]] = chunk["text"]

    entries: list[ServiceCoverageEntry] = []
    for source_filename, plan in plans.items():
        covered_items = _split_list_chunk_items(plan.get("other_covered_services", ""), "other_covered_services")
        excluded_items = _split_list_chunk_items(plan.get("excluded_services", ""), "excluded_services")

        for service in CANONICAL_SERVICES:
            covered_match = _find_matching_item(service, covered_items)
            excluded_match = _find_matching_item(service, excluded_items)

            if covered_match is not None:
                status: CoverageStatus = "covered"
                detail, section = covered_match, "other_covered_services"
            elif excluded_match is not None:
                status = "excluded"
                detail, section = excluded_match, "excluded_services"
            else:
                status = "not_mentioned"
                detail, section = None, None

            entries.append(
                ServiceCoverageEntry(
                    insurer=plan["insurer"],
                    plan_name=plan["plan_name"],
                    source_filename=source_filename,
                    service=service,
                    status=status,
                    detail=detail,
                    section=section,
                )
            )
    return entries


def detect_service_coverage_question(question: str) -> str | None:
    """
    Lightweight keyword match, same shape as comparison.py's
    detect_comparison_question(): if the question names one of the 14
    canonical services, return that service string; otherwise None.

    Note: this can false-positive the same way any keyword trigger can
    (e.g. a question mentioning "eye" in an unrelated context won't match
    since we match the full "routine eye care" phrase, but a question that
    happens to use one of these exact phrases in an unrelated sense would).
    Flagged as a known risk, not yet hardened -- check against the full
    eval set before trusting broadly.
    """
    question_lower = question.lower()
    for service in CANONICAL_SERVICES:
        if service.lower() in question_lower:
            return service
    return None


def format_service_coverage_section(service: str, entries: list[ServiceCoverageEntry]) -> str:
    """
    Render the 8-plan coverage table for one service as an explicit,
    bulleted block -- same "explicit list, not dense prose" formatting
    choice that fixed the #15 list-bleed bug, deliberately reused here
    since this feature reintroduces the same crowding risk (8 plans'
    worth of list data in one block) that caused #14's original bug.
    """
    relevant = [e for e in entries if e.service == service]
    if not relevant:
        return ""

    lines = [f"=== VERIFIED SERVICE COVERAGE: {service} ==="]
    for e in relevant:
        if e.status == "covered":
            lines.append(f"- {e.insurer} | {e.plan_name} | {e.source_filename}: COVERED -- {e.detail}")
        elif e.status == "excluded":
            lines.append(f"- {e.insurer} | {e.plan_name} | {e.source_filename}: NOT COVERED -- {e.detail}")
        else:
            lines.append(
                f"- {e.insurer} | {e.plan_name} | {e.source_filename}: "
                f"not mentioned in either list for this plan"
            )
    return "\n".join(lines)