"""
Builds the final chunk objects that retrieval will index: reads Phase 2/3
boundary data/processed/*.json (untouched, never modified here) and
renders each document's rows/items into human-readable chunk text plus
citation metadata, entirely at build time -- nothing gets written back
into data/processed/.

Chunking granularity, decided and validated in Phase 3 (see planning
doc): row-level for the grid table and Important Questions table (chosen
over category-level/table-level for retrieval precision, and confirmed
via the fixed-size/semantic chunking comparison to be both exact -- a
chunk IS a row, so "never split a row mid-chunk" holds by construction --
and more accurate than the best embedding-threshold approach tested,
which only reached 84% F1 against real ground truth); one chunk per
whole list for Excluded/Other Covered Services (list items don't have a
meaningful internal grouping signal -- confirmed during the semantic
chunking exploration); one small chunk per document for header metadata.

Grid table rows apply the CONFIRMED (not guessed -- validated by hand
across all 8 documents during the Phase 2/3 boundary work) column
resolution rule when there are exactly two content values: Network cost,
then Out-of-Network cost, in that order. This labeling is scoped
narrowly to that one confirmed case; Important Questions' content columns
vary too much in count and meaning across documents to safely label the
same way, so those stay as a neutral join.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Chunk:
    """One retrievable unit. text is what gets indexed/embedded; every
    other field is citation/filter metadata, never searched directly.
    """

    chunk_id: str
    text: str
    source_filename: str
    insurer: str
    plan_name: Optional[str]
    section: str
    category: Optional[str] = None
    row_index: Optional[int] = None


def _document_prefix(doc: dict) -> str:
    """Shared "which plan is this" prefix every chunk's text starts with,
    so a chunk is self-describing on its own -- a retriever hands back
    isolated chunks, not whole documents, so each one needs to carry its
    own source identity rather than relying on surrounding context that
    won't be there at query time.
    """
    hm = doc["header_metadata"]
    return f"{hm['insurer']} - {hm['plan_name']}"


def _join_values(values: List[Optional[str]]) -> str:
    """Join non-None values with '. ', for building readable chunk text
    from a row's positional cells without asserting what each one means.
    """
    return ". ".join(v for v in values if v)


def build_grid_table_chunks(doc: dict) -> List[Chunk]:
    """One chunk per grid table row. Splits the row's middle span into
    the service name (always the first element) and the payment values
    (everything after it) -- a grid row is [category, service, network,
    out_of_network, limitations], so the payment span is 2 elements when
    everything resolved normally. Only when payment_values has exactly 2
    elements are they labeled Network cost / Out-of-Network cost -- the
    confirmed column-order rule from the Phase 2/3 boundary work. Any
    other count falls back to an unlabeled join rather than guessing.
    """
    prefix = _document_prefix(doc)
    chunks: List[Chunk] = []

    for i, row in enumerate(doc["grid_table"]["rows"]):
        category = row[0] or "Unknown category"
        middle = row[1:-1]
        overflow = row[-1]

        service = middle[0] if middle else None
        payment_values = middle[1:] if len(middle) > 1 else []

        if len(payment_values) == 2:
            network, out_of_network = payment_values
            cost_text = _join_values(
                [
                    f"Network cost: {network}" if network else None,
                    f"Out-of-Network cost: {out_of_network}" if out_of_network else None,
                ]
            )
        else:
            cost_text = _join_values(payment_values)

        parts = [
            prefix,
            f"Category: {category}",
            f"Service: {service}" if service else None,
            f"Cost: {cost_text}" if cost_text else None,
            f"Limitations: {overflow}" if overflow else None,
        ]
        text = ". ".join(p for p in parts if p)

        chunks.append(
            Chunk(
                chunk_id=f"{doc['source_filename']}::grid_table::{i}",
                text=text,
                source_filename=doc["source_filename"],
                insurer=doc["insurer"],
                plan_name=doc["header_metadata"]["plan_name"],
                section="grid_table",
                category=category,
                row_index=i,
            )
        )

    return chunks


def build_important_questions_chunks(doc: dict) -> List[Chunk]:
    """One chunk per Important Questions row. Content-column count and
    meaning vary too much across documents (sometimes a blank spacer
    column, sometimes a single Answer column, sometimes a shorter
    continuation-table row with no overflow at all) to safely apply
    fixed labels the way the grid table's Network/Out-of-Network rule
    does -- stays a neutral join instead.
    """
    prefix = _document_prefix(doc)
    chunks: List[Chunk] = []

    for i, row in enumerate(doc["important_questions"]["rows"]):
        question = row[0] or "Unknown question"
        content_values = row[1:-1] if len(row) > 2 else []
        overflow = row[-1] if len(row) > 1 else None

        answer_text = _join_values(content_values)
        parts = [
            prefix,
            f"Question: {question}",
            f"Answer: {answer_text}" if answer_text else None,
            f"Why this matters: {overflow}" if overflow else None,
        ]
        text = ". ".join(p for p in parts if p)

        chunks.append(
            Chunk(
                chunk_id=f"{doc['source_filename']}::important_questions::{i}",
                text=text,
                source_filename=doc["source_filename"],
                insurer=doc["insurer"],
                plan_name=doc["header_metadata"]["plan_name"],
                section="important_questions",
                row_index=i,
            )
        )

    return chunks


def build_service_list_chunk(doc: dict, key: str, section: str, label: str) -> Optional[Chunk]:
    """One chunk for a whole service list (Excluded Services or Other
    Covered Services) -- not one chunk per item, since consecutive-item
    embedding similarity showed no meaningful internal grouping signal
    for this content (see Phase 3 semantic chunking exploration), and a
    query like "is X excluded" benefits from seeing the whole list rather
    than one item in isolation. Returns None if the list is empty rather
    than emitting a useless empty chunk.
    """
    items = doc[key]
    if not items:
        return None

    prefix = _document_prefix(doc)
    text = f"{prefix}. {label}: " + "; ".join(items) + "."

    return Chunk(
        chunk_id=f"{doc['source_filename']}::{section}",
        text=text,
        source_filename=doc["source_filename"],
        insurer=doc["insurer"],
        plan_name=doc["header_metadata"]["plan_name"],
        section=section,
    )


def build_header_chunk(doc: dict) -> Chunk:
    """One small chunk per document carrying the top-line facts (plan
    type, coverage period, coverage for) that get asked about constantly
    and are cheap to include in full every time.
    """
    hm = doc["header_metadata"]
    prefix = _document_prefix(doc)
    parts = [
        prefix,
        f"Coverage Period: {hm['coverage_period']}" if hm["coverage_period"] else None,
        f"Coverage for: {hm['coverage_for']}" if hm["coverage_for"] else None,
        f"Plan Type: {hm['plan_type']}" if hm["plan_type"] else None,
    ]
    text = ". ".join(p for p in parts if p)

    return Chunk(
        chunk_id=f"{doc['source_filename']}::header_metadata",
        text=text,
        source_filename=doc["source_filename"],
        insurer=doc["insurer"],
        plan_name=hm["plan_name"],
        section="header_metadata",
    )


def build_document_chunks(doc: dict) -> List[Chunk]:
    """Build every chunk for one document, across all sections."""
    chunks: List[Chunk] = []
    chunks.append(build_header_chunk(doc))
    chunks.extend(build_grid_table_chunks(doc))
    chunks.extend(build_important_questions_chunks(doc))

    excluded_chunk = build_service_list_chunk(
        doc, "excluded_services", "excluded_services", "Services generally NOT covered"
    )
    if excluded_chunk:
        chunks.append(excluded_chunk)

    other_covered_chunk = build_service_list_chunk(
        doc, "other_covered_services", "other_covered_services", "Other covered services"
    )
    if other_covered_chunk:
        chunks.append(other_covered_chunk)

    return chunks