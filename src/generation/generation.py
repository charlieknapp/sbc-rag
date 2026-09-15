import os

import anthropic
from dotenv import load_dotenv

from .evidence import EvidenceBundle
from .schema import Citation, GeneratedAnswer

from dataclasses import dataclass

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are answering questions about health insurance plans using ONLY the context provided below. Never use outside knowledge about health insurance or any specific plan, even if you believe you know the answer.

Rules:
1. Only state facts directly supported by the provided context.
2. VERIFIED PLAN DATA is validated, authoritative data. You MUST cite source_type "verified_plan_data" for any fact that VERIFIED PLAN DATA covers, even when RETRIEVED SBC TEXT also contains matching or overlapping information. Never cite "sbc_text" for a fact that VERIFIED PLAN DATA already covers. Use "sbc_text" only for facts VERIFIED PLAN DATA does not cover.
3. If a COMPUTED COMPARISON section is present, it is a definitive, already-verified answer to a highest/lowest comparison question. Use its winner(s) exactly as given — including ties and the unlimited-exposure note, if present — and cite source_type "verified_plan_data" for each winning plan, with section set to a short descriptive label such as "out-of-pocket max comparison" or "deductible comparison". Never repeat the source_type value as the section value. Do not attempt to independently re-derive the highest/lowest value from the plan data yourself.
4. If context for more than one plan is provided, first identify which specific plan (or plans, for a comparison question) the question is actually asking about — usually named directly in the question — and ignore data belonging to any other plan present in the context.
5. If nothing in the provided context actually answers the question, do not guess or fall back on outside knowledge. Set confident to false, write an answer explaining you don't have enough information to answer confidently, and leave citations empty.
6. Every citation must correspond to real context you were actually given — never invent a citation, an insurer, or a plan name not present in the context below.

Respond by calling the submit_answer tool."""

ANSWER_TOOL = {
    "name": "submit_answer",
    "description": "Submit the final answer with citations and a confidence flag.",
    "input_schema": GeneratedAnswer.model_json_schema(),
}


def format_amount_entries(entries: list[dict]) -> str:
    parts = []
    for e in entries:
        if e["is_unlimited"]:
            parts.append(f"{e['label']}: Unlimited")
        else:
            parts.append(f"{e['label']}: ${e['amount']:,.0f}")
    return "; ".join(parts)


def format_comparison_section(result) -> str:
    field_label = "deductible" if result.field == "deductible" else "out-of-pocket max"
    winner_names = "; ".join(f"{e.insurer} - {e.plan_name}" for e in result.winners)
    tie_note = " (tied)" if len(result.winners) > 1 else ""

    lines = [
        f"=== COMPUTED COMPARISON: {result.direction} {field_label} "
        f"(authoritative — this has already been computed correctly; do not recompute it) ===",
        f"{result.direction.capitalize()} {field_label}: {winner_names} at "
        f"${result.winners[0].amount:,.0f}{tie_note}",
        "All plans, sorted:",
    ]
    for e in result.all_entries:
        lines.append(f"  {e.insurer} - {e.plan_name}: ${e.amount:,.0f}")

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
                f"\nPlan: {pf['insurer']} - {pf['plan_name']}\n"
                f"  Deductible: {format_amount_entries(pf['deductibles'])}\n"
                f"  Out-of-pocket max: {format_amount_entries(pf['out_of_pocket_maxes'])}\n"
                f"  Referral required: {pf['referral_required']} "
                f"(details: {pf['raw_referral_text']})"
            )

    if bundle.comparison_result:
        parts.append("\n" + format_comparison_section(bundle.comparison_result))

    parts.append("\n=== RETRIEVED SBC TEXT ===")
    for c in bundle.chunks:
        category = c.metadata.get("category")
        section_label = c.metadata["section"] + (f" ({category})" if category else "")
        parts.append(
            f"\nPlan: {c.metadata['insurer']} - {c.metadata['plan_name']}\n"
            f"Section: {section_label}\n"
            f"Text: {c.text}"
        )

    return "\n".join(parts)


def generate_answer(question: str, bundle: EvidenceBundle) -> GeneratedAnswer:
    context_block = build_context_block(bundle)
    user_message = f"Context:\n{context_block}\n\nQuestion: {question}"

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[ANSWER_TOOL],
        tool_choice={"type": "tool", "name": "submit_answer"},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_use_block = next(b for b in response.content if b.type == "tool_use")
    return GeneratedAnswer.model_validate(tool_use_block.input)


@dataclass
class CitationIssue:
    citation: Citation
    reason: str


def verify_citations(result: GeneratedAnswer, bundle: EvidenceBundle) -> list[CitationIssue]:
    issues = []

    verified_plans = {(pf["insurer"], pf["plan_name"]) for pf in bundle.plan_facts}
    chunk_plans = {(c.metadata["insurer"], c.metadata["plan_name"]) for c in bundle.chunks}

    for citation in result.citations:
        plan_key = (citation.insurer, citation.plan_name)
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