import os
import time

import anthropic
from dotenv import load_dotenv

from .evidence import EvidenceBundle
from .schema import Citation, GeneratedAnswer
from .service_coverage import format_service_coverage_section, SECTION_MARKERS

from dataclasses import dataclass

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL = "claude-haiku-4-5-20251001"
INPUT_COST_PER_MTOK = 1.0
OUTPUT_COST_PER_MTOK = 5.0

SYSTEM_PROMPT = """You are answering questions about health insurance plans using ONLY the context provided below. Never use outside knowledge about health insurance or any specific plan, even if you believe you know the answer.

Rules:
1. Only state facts directly supported by the provided context.
2. VERIFIED PLAN DATA is validated, authoritative data. You MUST cite source_type "verified_plan_data" for any fact that VERIFIED PLAN DATA covers, even when RETRIEVED SBC TEXT also contains matching or overlapping information. Never cite "sbc_text" for a fact that VERIFIED PLAN DATA already covers. Use "sbc_text" only for facts VERIFIED PLAN DATA does not cover.
3. If a COMPUTED COMPARISON section is present, it is a definitive, already-verified answer to a highest/lowest comparison question. Use its winner(s) exactly as given — including ties and the unlimited-exposure note, if present — and cite source_type "verified_plan_data" for each winning plan, with section set to a short descriptive label such as "out-of-pocket max comparison" or "deductible comparison". Never repeat the source_type value as the section value. Do not attempt to independently re-derive the highest/lowest value from the plan data yourself.
4. For any question about a specific plan's covered-services or excluded-services list — whether the service is covered or excluded, or what its specific limitations or details are — carefully read that exact plan's own list entry directly, in full, before answering. The same service name can appear across multiple plans with different limitation details, or no limitation stated at all; never infer an answer from how other plans phrase the same service line, and never let one plan's list entry influence your answer about a different plan. If a limitation or detail is stated in that plan's own entry, report it exactly as written, even if most of the other plans listed for that same service state no limitation.
5. If context for more than one plan is provided, first identify which specific plan (or plans, for a comparison question) the question is actually asking about — usually named directly in the question — and ignore data belonging to any other plan present in the context.
6. If nothing in the provided context actually answers the question, do not guess or fall back on outside knowledge. Set confident to false, write an answer explaining you don't have enough information to answer confidently, and leave citations empty.
7. Every citation must correspond to real context you were actually given — never invent a citation, an insurer, or a plan name not present in the context below.
8. Every citation must include source_filename, copied exactly as shown in the context (e.g. "kaiser_ca_traditional_hmo_2026.pdf") — never abbreviated, reworded, or omitted, even if the plan's full name is long.
9. If a VERIFIED SERVICE COVERAGE section is present, it is a definitive, already-computed answer for that specific service across all 8 plans — including plans where the service is not mentioned in either list at all. Report every plan's status from this section, not just the plans whose SBC text chunks happen to appear below in RETRIEVED SBC TEXT. Cite source_type "verified_plan_data" for each plan referenced from this section, with section set to a short descriptive label such as "service coverage: acupuncture" (never repeat source_type as the section value, per rule 3).
10. When a question asks which plan is "cheapest," "most expensive," or otherwise compares the cost of a specific service (e.g. a visit type, procedure, or benefit) across plans using retrieved SBC text rather than a COMPUTED COMPARISON section, check whether every plan being compared uses the same kind of cost structure for that service (e.g. all flat copays, or all coinsurance percentages with the same deductible status). If the cost structures differ — for example, one plan uses a flat copay and another uses coinsurance that only applies after the deductible is met — do not declare a single cheapest or most expensive plan. Instead, state plainly that the plans use different cost structures that aren't directly comparable without knowing the person's deductible status, and describe what each plan actually charges.


Respond by calling the submit_answer tool."""

ANSWER_TOOL = {
    "name": "submit_answer",
    "description": "Submit the final answer with citations and a confidence flag.",
    "input_schema": GeneratedAnswer.model_json_schema(),
}

LIST_SECTIONS = {"other_covered_services", "excluded_services"}


def format_amount_entries(entries: list[dict]) -> str:
    parts = []
    for e in entries:
        if e["is_unlimited"]:
            parts.append(f"{e['label']}: Unlimited")
        else:
            parts.append(f"{e['label']}: ${e['amount']:,.0f}")
    return "; ".join(parts)


def format_list_chunk_text(text: str, section: str) -> str:
    """Reformat a dense semicolon-joined services-list chunk into an explicit
    bulleted list, purely for prompt readability. Does not touch stored chunk data.

    Splits on the known section marker (SECTION_MARKERS, shared with
    service_coverage.py's _split_list_chunk_items()) rather than the first
    colon in the text -- 3 of 8 plans (Anthem, Cigna, Highmark) have their
    own insurer/plan-name colon earlier in the string ("...Inc.: Custom
    Anthem..."), which a first-colon split mistakes for the real marker,
    gluing the whole preamble onto the first bulleted item instead of
    keeping it in the header line above the bullets.
    """
    marker = SECTION_MARKERS.get(section)
    if marker:
        idx = text.lower().find(marker)
        if idx == -1:
            return text
        colon_idx = text.find(":", idx)
        if colon_idx == -1:
            return text
        prefix, items_part = text[:colon_idx], text[colon_idx + 1:]
    elif ":" in text:
        prefix, _, items_part = text.partition(":")
    else:
        return text

    items = [item.strip() for item in items_part.strip().rstrip(".").split(";") if item.strip()]
    if not items:
        return text
    bullet_lines = "\n".join(f"  - {item}" for item in items)
    return f"{prefix}:\n{bullet_lines}"


def format_comparison_section(result) -> str:
    field_label = "deductible" if result.field == "deductible" else "out-of-pocket max"
    winner_names = "; ".join(
        f"{e.insurer} - {e.plan_name} (source_filename: {e.source_filename})" for e in result.winners
    )
    tie_note = " (tied)" if len(result.winners) > 1 else ""

    lines = [
        f"=== COMPUTED COMPARISON: {result.direction} {field_label} "
        f"(authoritative — this has already been computed correctly; do not recompute it) ===",
        f"{result.direction.capitalize()} {field_label}: {winner_names} at "
        f"${result.winners[0].amount:,.0f}{tie_note}",
        "All plans, sorted:",
    ]
    for e in result.all_entries:
        lines.append(f"  {e.insurer} - {e.plan_name} (source_filename: {e.source_filename}): ${e.amount:,.0f}")

    if result.unlimited_plans:
        lines.append(
            "Note: the following plans have an Unlimited value in this category "
            "(typically out-of-network) not reflected in the numeric comparison above: "
            + ", ".join(result.unlimited_plans)
        )

    return "\n".join(lines)


def build_context_block(bundle: EvidenceBundle) -> str:
    parts = []

    if bundle.plan_facts:
        parts.append("=== VERIFIED PLAN DATA (authoritative — prefer over SBC text below) ===")
        for pf in bundle.plan_facts:
            parts.append(
                f"\nPlan: {pf['insurer']} - {pf['plan_name']} (source_filename: {pf['source_filename']})\n"
                f"  Deductible: {format_amount_entries(pf['deductibles'])}\n"
                f"  Out-of-pocket max: {format_amount_entries(pf['out_of_pocket_maxes'])}\n"
                f"  Referral required: {pf['referral_required']} "
                f"(details: {pf['raw_referral_text']})"
            )

    if bundle.comparison_result:
        parts.append("\n" + format_comparison_section(bundle.comparison_result))
        
    if bundle.service_coverage_entries:
        parts.append(
            "\n" + format_service_coverage_section(bundle.service_coverage_service, bundle.service_coverage_entries)
        )

    parts.append("\n=== RETRIEVED SBC TEXT ===")
    for c in bundle.chunks:
        section = c.metadata["section"]
        category = c.metadata.get("category")
        section_label = section + (f" ({category})" if category else "")
        text = format_list_chunk_text(c.text, section) if section in LIST_SECTIONS else c.text
        parts.append(
            f"\nPlan: {c.metadata['insurer']} - {c.metadata['plan_name']}\n"
            f"(source_filename: {c.metadata['source_filename']})\n"
            f"Section: {section_label}\n"
            f"Text: {text}"
        )

    return "\n".join(parts)


@dataclass
class GenerationMetrics:
    latency_seconds: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


def generate_answer(question: str, bundle: EvidenceBundle) -> tuple[GeneratedAnswer, GenerationMetrics]:
    context_block = build_context_block(bundle)
    user_message = f"Context:\n{context_block}\n\nQuestion: {question}"

    start = time.perf_counter()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1536,
        system=SYSTEM_PROMPT,
        tools=[ANSWER_TOOL],
        tool_choice={"type": "tool", "name": "submit_answer"},
        messages=[{"role": "user", "content": user_message}],
    )
    latency_seconds = time.perf_counter() - start

    tool_use_block = next(b for b in response.content if b.type == "tool_use")
    result = GeneratedAnswer.model_validate(tool_use_block.input)

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    estimated_cost_usd = (
        input_tokens / 1_000_000 * INPUT_COST_PER_MTOK
        + output_tokens / 1_000_000 * OUTPUT_COST_PER_MTOK
    )

    metrics = GenerationMetrics(
        latency_seconds=latency_seconds,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
    )

    return result, metrics


@dataclass
class CitationIssue:
    citation: Citation
    reason: str


def verify_citations(result: GeneratedAnswer, bundle: EvidenceBundle) -> list[CitationIssue]:
    issues = []

    verified_plans = {(pf["insurer"], pf["source_filename"]) for pf in bundle.plan_facts}
    chunk_plans = {(c.metadata["insurer"], c.metadata["source_filename"]) for c in bundle.chunks}

    for citation in result.citations:
        plan_key = (citation.insurer, citation.source_filename)
        if citation.source_type == "verified_plan_data" and plan_key not in verified_plans:
            issues.append(CitationIssue(
                citation=citation,
                reason=f"cites verified_plan_data for {plan_key}, but no PlanFacts for this plan was in the evidence bundle",
            ))
        elif citation.source_type == "sbc_text" and plan_key not in chunk_plans:
            issues.append(CitationIssue(
                citation=citation,
                reason=f"cites sbc_text for {plan_key}, but no retrieved chunk for this plan was in the evidence bundle",
            ))

    return issues