"""
Normalization pass for raw table rows extracted by pdfplumber.

Table extraction libraries return a flat grid of rows, but the SBC template's
actual layout has labels (category names, question text) and "overflow" text
(Limitations, Why This Matters) that visually merge across multiple rows.
pdfplumber doesn't understand merged cells, so it forces that content into
the wrong place -- this module cleans that back up into rows that actually
make sense.

Generalized to work across different SBC table types (the Common Medical
Event grid, the Important Questions table, and potentially others) by
describing each table's shape as a TableSpec rather than hardcoding column
positions. Content columns (payment columns, Answers) are derived
positionally -- everything between the label column and the overflow column
-- since their own header text isn't stable across insurers (e.g. "Network
Provider" vs. "Participating Provider"), while the label and overflow
headers are fixed SBC template text and stay consistent.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class TableSpec:
    """Describes how to locate and interpret one type of SBC table.

    marker_text: text that identifies both the table and its header row
        (e.g. "Common Medical Event", "Important Questions").
    label_header: header text for the column holding the wrapping label
        that can fragment across rows (e.g. "Common Medical Event",
        "Important Questions").
    overflow_header: header text for the column that receives merged
        orphan text (e.g. "Limitations", "Why This Matters").
    extra_boilerplate_markers: additional phrases to skip as boilerplate
        rows that appear AFTER the header row (e.g. "What You Will Pay").
        Content before the header row is skipped automatically, based on
        header_row_index -- no marker list needed for that, since that
        preceding content (insurer name, plan name, coverage period) is
        document-specific text we can't match against a fixed phrase.
    stop_marker: text that marks the start of the NEXT section (e.g.
        "Common Medical Event" for the Important Questions table). When
        set, a page that has no table matching THIS spec's own marker_text
        is still treated as continuation content -- as long as it also
        doesn't contain stop_marker -- since a continuation page doesn't
        always repeat its own table's header. Leave as None for a table
        we haven't verified this is safe for (falls back to the stricter
        "only process pages with our own marker" behavior).
    single_row_per_label: True when this table's label always identifies
        exactly one logical row (e.g. the Important Questions table: one
        question = one row, always), so a blank OR continuation-fragment
        label never means "genuine new row sharing the previous label" --
        it always means "this raw row is more of the same answer that
        happened to wrap onto another line," even when that raw row
        carries its own new content/overflow text. Contrast with the grid
        table (default False), where a blank/forward-filled category
        label legitimately introduces a new, distinct row (e.g. multiple
        services under one "If you have a hospital stay" category) -- so
        there, only a row with ALL content columns blank gets merged.
    """
    marker_text: str
    label_header: str
    overflow_header: str
    extra_boilerplate_markers: List[str] = field(default_factory=list)
    stop_marker: Optional[str] = None
    single_row_per_label: bool = False
    split_camelot_merged_rows: bool = False

# The Common Medical Event / drug grid table: category label wraps across
# rows, an arbitrary number of payment columns sit between the category and
# Limitations columns, and a stray "(you will pay the least)/(you will pay
# the most)" sub-header row can follow the main header row. Its header has
# repeated on every page we've tested so far, so no stop_marker needed yet
# -- revisit if a document turns up where it doesn't repeat.
GRID_TABLE_SPEC = TableSpec(
    marker_text="Common Medical Event",
    label_header="Common Medical Event",
    overflow_header="Limitations",
    extra_boilerplate_markers=["What You Will Pay", "You will pay the"],
)

# The Important Questions table: question text wraps across rows the same
# way category labels do, with a single Answers column and a Why This
# Matters overflow column. Its continuation content (the referral question)
# landed in a headerless box on the next page -- stop_marker tells us when
# that continuation content has ended and the grid table has begun.
IMPORTANT_QUESTIONS_SPEC = TableSpec(
    marker_text="Important Questions",
    label_header="Important Questions",
    overflow_header="Why This Matters",
    stop_marker="Common Medical Event",
    extra_boilerplate_markers=["All copayment and coinsurance costs"],
    single_row_per_label=True,
)

# Cigna-only variant of GRID_TABLE_SPEC: camelot merges several distinct
# services into one row on this document (see split_merged_rows), a
# pattern that turned out to also produce false-positive splits on other
# documents (confirmed on UHC -- a single wrapped service name got cut
# into two fake rows) when applied unconditionally. Scoped as an opt-in
# flag on the spec rather than a global default so it only runs against
# the one document it's known to be needed -- and known safe -- for.
CIGNA_GRID_TABLE_SPEC = TableSpec(
    marker_text=GRID_TABLE_SPEC.marker_text,
    label_header=GRID_TABLE_SPEC.label_header,
    overflow_header=GRID_TABLE_SPEC.overflow_header,
    extra_boilerplate_markers=GRID_TABLE_SPEC.extra_boilerplate_markers,
    stop_marker=GRID_TABLE_SPEC.stop_marker,
    single_row_per_label=GRID_TABLE_SPEC.single_row_per_label,
    split_camelot_merged_rows=True,
)

def is_blank(cell: Optional[str]) -> bool:
    """True if a cell is None, empty, or whitespace-only."""
    return cell is None or cell.strip() == ""


def _normalize_whitespace(text: str) -> str:
    """Collapse any run of whitespace (spaces, tabs, newlines) to a single
    space. pdfplumber preserves the PDF's own line-wrapping inside cell
    text (e.g. "Common Medical\\nEvent"), so marker-text comparisons need
    to go through this first or they'll silently never match.
    """
    return " ".join(text.split())


def is_category_continuation(label: Optional[str]) -> bool:
    """True if `label` looks like the tail end of a wrapped label (e.g.
    "stay", "surgery") rather than a genuine new label.

    Heuristic: every real label in this dataset starts a fresh sentence
    with a capital letter (the SBC template's fixed phrasing), so a
    non-blank label cell that starts with a lowercase letter is almost
    certainly a continuation fragment, not a new label boundary. Revisit
    if a real document ever has a genuine label that starts lowercase.
    """
    if is_blank(label):
        return False
    return label.strip()[0].islower()


def is_boilerplate_row(row: list, markers: List[str]) -> bool:
    """True if this row contains any of `markers` (whitespace-normalized,
    case-insensitive) -- a stray header/sub-header row that appears after the
    main header row and isn't real data (e.g. the "(you will pay the least)"
    row in the grid table). Content BEFORE the header row is handled
    separately, by slicing on header_row_index, since it's document-specific
    text with no fixed phrase to match against.
    """
    for cell in row:
        if any(_text_contains(cell, marker) for marker in markers):
            return True
    return False

def _text_contains(cell: Optional[str], marker: str) -> bool:
    """True if `marker` appears in `cell` (whitespace-normalized, case-insensitive).

    Case-insensitivity matters because even fixed federal-template phrasing isn't
    guaranteed to match capitalization exactly across insurers -- Kaiser's SBC
    uses "Why this Matters:" (lowercase "this") where every other insurer seen so
    far uses "Why This Matters:". Without this, resolve_column_index silently
    fails to find the overflow column, which cascades into every content column
    failing too (they're derived positionally between label and overflow), which
    in turn meant every row came through blank and got silently dropped instead
    of raising any visible error.
    """
    if cell is None:
        return False
    return marker.lower() in _normalize_whitespace(cell).lower()

def _text_contains_row(row: list, marker: str) -> bool:
    """True if `marker` (whitespace-normalized, case-insensitive) appears in
    any cell of `row`, regardless of which column it landed in -- row-level
    counterpart to _text_contains, used to check whether a header fragment
    (label_header/overflow_header) showed up anywhere in a given raw row.
    """
    return any(_text_contains(cell, marker) for cell in row)

def resolve_header_block(
    table: List[List[Optional[str]]],
    header_row_index: int,
    spec: TableSpec,
    max_window: int = 8,
) -> Tuple[list, int]:
    """Merge the raw rows starting at header_row_index into a single
    combined header row, and report how far that header band extends.

    A table's header isn't always one raw row -- pdfplumber can split a
    single visual header band into several raw rows (e.g. "Common Medical
    Event / Services You May Need / What You Will Pay" on one row, then
    "Limitations, Exceptions, & Other" wrapping onto a later row, with a
    payment-column sub-header like "Plan Provider"/"Non-Plan Provider"
    sandwiched in between). Scans forward row by row, capped at
    max_window, merging cells positionally into merged_row -- first
    non-blank value per column wins, same rule resolve_column_index
    already applies within a single row -- until both spec.label_header
    and spec.overflow_header have appeared somewhere in the rows scanned
    so far.

    Returns (merged_header_row, header_end_index), where header_end_index
    is the last raw row absorbed into the header band; real data starts at
    header_end_index + 1. Every row inside the window is treated as
    header rather than data, which is what keeps a payment-column
    sub-header row (blank label, blank overflow, real content in the
    content columns -- otherwise indistinguishable from a legitimate
    forward-filled-category data row) from leaking through as a spurious
    row.

    Raises ValueError if max_window rows aren't enough to find both
    headers, rather than silently falling back to a single-row header --
    an unresolved overflow column doesn't fail loudly on its own (every
    row on the page just quietly ends up with zero content columns and
    gets dropped as "no content"), which is exactly the bug this function
    exists to catch, so staying silent here would defeat the point.
    """
    merged_row: list = []
    found_label = False
    found_overflow = False

    window_end = min(header_row_index + max_window, len(table))
    for i in range(header_row_index, window_end):
        row = table[i]
        if len(row) > len(merged_row):
            merged_row.extend([None] * (len(row) - len(merged_row)))
        for col_idx, cell in enumerate(row):
            if merged_row[col_idx] is None and not is_blank(cell):
                merged_row[col_idx] = cell

        if _text_contains_row(row, spec.label_header):
            found_label = True
        if _text_contains_row(row, spec.overflow_header):
            found_overflow = True

        if found_label and found_overflow:
            return merged_row, i

    raise ValueError(
        f"Could not resolve a full header block for marker "
        f"'{spec.marker_text}' within {max_window} rows starting at row "
        f"{header_row_index} (found label_header={found_label}, "
        f"overflow_header={found_overflow}). The header band may be "
        f"longer than max_window, or this document's phrasing doesn't "
        f"match label_header/overflow_header."
    )
    
def find_table_and_header(
    tables: List[List[List[Optional[str]]]], spec: TableSpec
) -> Tuple[Optional[List[List[Optional[str]]]], Optional[int]]:
    """Find the table matching spec.marker_text on this page, and the index
    of its header row within that table.

    A page can mention marker_text without actually containing the table --
    e.g. an Important Questions answer that says "See the Common Medical
    Events chart below for your costs," which contains the grid table's
    marker text as ordinary prose, not a header. To avoid mistaking that
    for a real header, each candidate row where marker_text appears is
    validated with resolve_header_block (does a real header block -- one
    that also contains spec.overflow_header within the window -- resolve
    starting there?) before being accepted; a candidate that fails
    validation is skipped in favor of the next occurrence, rather than
    accepted outright.

    Returns (None, None) if no candidate on this page validates -- either
    because this table type isn't on this page at all, or because it's a
    continuation page that doesn't repeat its own header (see
    normalize_document's use of TableSpec.stop_marker for that case).
    """
    for table in tables:
        for i, row in enumerate(table):
            for cell in row:
                if _text_contains(cell, spec.marker_text):
                    try:
                        resolve_header_block(table, i, spec)
                    except ValueError:
                        break  # this occurrence isn't a real header; keep scanning
                    return table, i
    return None, None

def _table_contains_marker(table: List[List[Optional[str]]], marker_text: str) -> bool:
    """True if `marker_text` (whitespace-normalized, case-insensitive) appears
    anywhere in this single table.
    """
    for row in table:
        for cell in row:
            if _text_contains(cell, marker_text):
                return True
    return False



def resolve_column_index(header_row: list, header_text: str) -> Optional[int]:
    """Find which column index in `header_row` contains `header_text`
    (whitespace-normalized, case-insensitive). Returns None if not found on
    this page (e.g. if pdfplumber's column detection shifted for this
    particular table).
    """
    for idx, cell in enumerate(header_row):
        if _text_contains(cell, header_text):
            return idx
    return None



def resolve_columns(header_row: list, spec: TableSpec) -> Tuple[Optional[int], List[int], Optional[int]]:
    """Resolve (label_idx, content_idxs, overflow_idx) from a table's
    header row. Content columns are derived positionally as everything
    between the label and overflow columns, since their own header text
    (payment column names especially) isn't stable across insurers.

    If label_header and overflow_header both resolve to the SAME column
    (e.g. camelot merged multiple header labels into one cell -- seen on
    UHC's Important Questions table, where "Important Questions", "Answers",
    and "Why this Matters:" all landed in column 0 together), that isn't a
    real resolution -- report overflow_idx as None (the same signal used
    for "not found at all") so the caller can fall back to deriving columns
    from the table's actual row shape instead of trusting a collapsed header.
    """
    label_idx = resolve_column_index(header_row, spec.label_header)
    overflow_idx = resolve_column_index(header_row, spec.overflow_header)
    if label_idx is not None and overflow_idx is not None and overflow_idx <= label_idx:
        overflow_idx = None
    content_idxs: List[int] = []
    if label_idx is not None and overflow_idx is not None and overflow_idx > label_idx:
        content_idxs = list(range(label_idx + 1, overflow_idx))
    return label_idx, content_idxs, overflow_idx


def _get(row: list, idx: Optional[int]) -> Optional[str]:
    """Safe positional lookup: returns None if `idx` is None or out of
    range for this row, rather than raising, since raw row lengths can
    vary slightly across pages/documents.
    """
    return row[idx] if idx is not None and idx < len(row) else None

def derive_positional_columns(table: List[List[Optional[str]]]) -> Tuple[Optional[int], List[int], Optional[int]]:
    """For a headerless table (continuation content with no header row of
    its own to resolve column roles from), derive them purely from shape:
    first column = label, last column = overflow, everything between =
    content. This is what lets a small box like the referral question
    (3 raw columns) get parsed correctly even though the indices resolved
    from the main table's header (6 raw columns) don't apply to it.
    """
    if not table:
        return None, [], None
    num_cols = max((len(row) for row in table), default=0)
    if num_cols < 2:
        return (0 if num_cols else None), [], None
    label_idx = 0
    overflow_idx = num_cols - 1
    content_idxs = list(range(1, overflow_idx))
    return label_idx, content_idxs, overflow_idx

def split_merged_rows(
    rows: List[List[Optional[str]]],
    column_indices: Tuple[Optional[int], List[int], Optional[int]],
) -> List[List[Optional[str]]]:
    """Undo a camelot artifact (seen on Cigna): when the source PDF draws
    one bounding box around several distinct services, camelot reports
    them as a single row whose content cells (e.g. Service, Network
    payment, Out-of-Network payment) each hold N newline-joined values
    instead of N separate rows.

    Deliberately only looks at the CONTENT columns (`content_idxs`) to
    decide whether a row should split -- never the label or overflow
    column. Ordinary multi-line label/overflow text routinely wraps onto
    the same number of lines as some unrelated column purely by
    coincidence (e.g. a 3-line question label next to a 3-line answer
    paragraph); splitting on that would fragment a single real value into
    nonsense pieces (an earlier version of this function did exactly
    that, catching it via testing). The content columns are the actual
    per-service data, so only agreement among *them* is real evidence of
    a multi-row merge -- and content columns always outnumber 1 wherever
    this artifact has actually been observed (Important Questions tables
    have only 1 content column, so this is naturally a no-op there).

    A row splits only when at least 2 content cells share the same
    newline-split count (> 1). The label and overflow cells (and any
    content cell that didn't share that count) are duplicated in full
    onto every resulting row rather than guessed at -- duplicating a
    label is harmless (a repeated, non-blank label just reads as another
    fresh row start), and duplicating an explanatory note avoids
    attaching it to the wrong half.

    Known limitation, not yet solved: if a content column's own text
    happens to wrap onto an extra line beyond the real number of items
    (e.g. one service name is long enough to word-wrap), its line count
    won't match the other content columns' and it's excluded from the
    split -- so it comes through duplicated, unsplit, on every resulting
    row instead of being separated. This doesn't lose or misattach any
    dollar data (payment columns still split correctly), it just leaves
    a couple of service-name cells combined instead of separated.
    """
    label_idx, content_idxs, overflow_idx = column_indices
    if len(content_idxs) < 2:
        return rows

    def line_count(cell: Optional[str]) -> int:
        return len(cell.split("\n")) if cell else 1

    result: List[List[Optional[str]]] = []
    for row in rows:
        content_counts = [line_count(_get(row, idx)) for idx in content_idxs]
        multiline_counts = [c for c in content_counts if c > 1]
        if len(multiline_counts) < 2:
            result.append(row)
            continue

        from collections import Counter

        majority_count, _ = Counter(multiline_counts).most_common(1)[0]
        matching_idxs = [
            idx for idx, c in zip(content_idxs, content_counts) if c == majority_count
        ]
        if len(matching_idxs) < 2:
            result.append(row)
            continue

        split_cells = {idx: _get(row, idx).split("\n") for idx in matching_idxs}
        for k in range(majority_count):
            new_row = list(row)
            for idx in matching_idxs:
                new_row[idx] = split_cells[idx][k].strip()
            result.append(new_row)

    return result

def normalize_rows(
    rows: List[List[Optional[str]]],
    spec: TableSpec,
    column_indices: Tuple[Optional[int], List[int], Optional[int]],
    start_category: Optional[str] = None,
    start_last_row: Optional[list] = None,
    start_pending_rows: Optional[List[list]] = None,
) -> Tuple[List[list], Optional[str], Optional[list], List[list]]:
    """Clean a list of raw rows (already positioned past any header row)
    into real rows: [label, *content_values, overflow_value].

    Takes already-resolved `column_indices` rather than a header row,
    since a continuation page may have no header of its own to resolve
    indices from -- the caller (normalize_document) carries the indices
    resolved from wherever the real header was found.

    When spec.single_row_per_label is True, any row without a genuinely
    fresh (non-blank, non-continuation) label is treated as a wrapped
    continuation of the CURRENT row -- its content and overflow text (if
    any) gets appended onto the last real row's matching cells -- rather
    than being evaluated by the row_has_content/Case A/B rules below,
    which assume a blank label can legitimately start a new sibling row
    (true for the grid table's forward-filled categories, not true here).
    This branch is a no-op for specs where single_row_per_label is False
    (the default), so grid-table behavior is unchanged.

    Returns (cleaned_rows, last_category, last_real_row, rows_pending_category)
    so the caller can carry all three pieces of state into the next page's
    call (fixes both the page-break label gap and multi-line labels that
    keep wrapping across a page boundary).
    """
    label_idx, content_idxs, overflow_idx = column_indices

    cleaned_rows: List[list] = []
    last_category = start_category
    last_real_row = start_last_row
    rows_pending_category: List[list] = list(start_pending_rows) if start_pending_rows else []

    for row in rows:
        if is_boilerplate_row(row, spec.extra_boilerplate_markers):
            continue

        raw_label = _get(row, label_idx)
        content_values = [_get(row, idx) for idx in content_idxs]
        overflow_value = _get(row, overflow_idx)

        was_continuation = is_category_continuation(raw_label)
        is_fresh_label = not is_blank(raw_label) and not was_continuation

        if spec.single_row_per_label and not is_fresh_label:
            if was_continuation:
                last_category = f"{last_category} {raw_label.strip()}".strip()
                for pending_row in rows_pending_category:
                    pending_row[0] = last_category
            if last_real_row is not None:
                for i, value in enumerate(content_values):
                    if not is_blank(value):
                        existing = last_real_row[1 + i] or ""
                        last_real_row[1 + i] = f"{existing} {value.strip()}".strip()
                if not is_blank(overflow_value):
                    existing = last_real_row[-1] or ""
                    last_real_row[-1] = f"{existing} {overflow_value.strip()}".strip()
            continue

        if was_continuation and last_category is not None:
            last_category = f"{last_category} {raw_label.strip()}".strip()
            for pending_row in rows_pending_category:
                pending_row[0] = last_category
            label = last_category
        else:
            label = raw_label

        row_has_content = any(not is_blank(v) for v in content_values)

        if not row_has_content:
            if is_blank(overflow_value):
                continue
            if last_real_row is not None:
                existing = last_real_row[-1] or ""
                last_real_row[-1] = f"{existing} {overflow_value.strip()}".strip()
            continue

        if is_blank(label):
            label = last_category
        elif not was_continuation:
            last_category = label.strip()
            rows_pending_category = []

        new_row = [label] + content_values + [overflow_value]
        cleaned_rows.append(new_row)
        last_real_row = new_row
        rows_pending_category.append(new_row)

    return cleaned_rows, last_category, last_real_row, rows_pending_category


def clean_whitespace(rows: List[list]) -> List[list]:
    """Normalize whitespace in every cell of every row -- collapses embedded
    newlines and repeated spaces down to single spaces, uniformly, so a
    cell's formatting doesn't depend on whether it happened to pass through
    the orphan-merge logic or arrived pre-assembled from pdfplumber intact.

    Purely cosmetic: does not change which row any text is attached to.
    """
    cleaned: List[list] = []
    for row in rows:
        cleaned_row = [
            _normalize_whitespace(cell) if isinstance(cell, str) else cell
            for cell in row
        ]
        cleaned.append(cleaned_row)
    return cleaned


def normalize_document(
    pages: List[List[List[List[Optional[str]]]]], spec: TableSpec
) -> List[list]:
    """Run normalization across every page of a document for the table type
    described by `spec`, carrying label, last-row, and pending-row state
    forward across page boundaries.

    A page with our own header (spec.marker_text found) is processed using
    column roles resolved from that page's header BLOCK -- see
    resolve_header_block, which merges however many raw rows that block
    actually spans (pdfplumber can split one visual header into several
    raw rows) into a single combined row before resolve_columns runs on
    it, and reports where real data starts. A continuation page with no
    header of our own is processed table-by-table: each table before the
    first one containing spec.stop_marker gets its own positionally
    -derived column roles (see derive_positional_columns), rather than
    reusing the indices resolved from a different, differently-shaped
    table -- fixes real corruption seen when a small headerless box (e.g.
    the referral question) doesn't share the main table's column layout.
    Boilerplate rows (e.g. the "All copayment and coinsurance costs..."
    disclaimer, which sits between these tables on every document) are
    filtered per-row via spec.extra_boilerplate_markers, same as always.
    If spec has no stop_marker set, the continuation fallback never
    triggers, preserving the stricter "only process pages with our own
    marker" behavior.
    """
    all_cleaned_rows: List[list] = []
    carried_category: Optional[str] = None
    carried_last_row: Optional[list] = None
    carried_pending_rows: List[list] = []
    column_indices: Optional[Tuple[Optional[int], List[int], Optional[int]]] = None

    for page_tables in pages:
        table, header_row_index = find_table_and_header(page_tables, spec)

        if table is not None:
            header_row, header_end_index = resolve_header_block(table, header_row_index, spec)
            column_indices = resolve_columns(header_row, spec)
            if column_indices[2] is None:
                # Header row's own layout didn't resolve cleanly (e.g. its
                # cells collapsed together) -- fall back to deriving column
                # roles from the table's actual row shape instead, the same
                # fallback already used for headerless continuation tables.
                column_indices = derive_positional_columns(table)
            cleaned, carried_category, carried_last_row, carried_pending_rows = normalize_rows(
                table[header_end_index + 1:],
                spec,
                column_indices,
                start_category=carried_category,
                start_last_row=carried_last_row,
                start_pending_rows=carried_pending_rows,
            )
            all_cleaned_rows.extend(cleaned)
            continue

        if column_indices is None or spec.stop_marker is None:
            # Haven't started this table yet on this document, or no
            # stop_marker is defined for it -- nothing here belongs to it.
            continue

        stop_idx = None
        for i, t in enumerate(page_tables):
            if _table_contains_marker(t, spec.stop_marker):
                stop_idx = i
                break

        tables_before_stop = page_tables[:stop_idx] if stop_idx is not None else page_tables

        for t in tables_before_stop:
            table_column_indices = derive_positional_columns(t)
            cleaned, carried_category, carried_last_row, carried_pending_rows = normalize_rows(
                t,
                spec,
                table_column_indices,
                start_category=carried_category,
                start_last_row=carried_last_row,
                start_pending_rows=carried_pending_rows,
            )
            all_cleaned_rows.extend(cleaned)

        if stop_idx is not None:
            break

    return clean_whitespace(all_cleaned_rows)