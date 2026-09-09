"""
Removes PDF-invisible-render-mode (Tr 3) text directly from a page's content
stream, rather than via rectangle-based redaction.

Why not redaction: PyMuPDF's add_redact_annot/apply_redactions erases
everything whose BOUNDING BOX intersects a rectangle, regardless of what put
it there. On UHC's SBC PDF, the invisible text layer isn't laid out like
real lines -- get_texttrace() shows its "spans" have essentially zero gap
between consecutive characters even when they'd visually wrap, producing a
handful of giant single-line spans up to ~3800pt wide (page width is ~612pt)
that stack many logical lines into one reported bbox. A rectangle redaction
built from that bbox blankets a whole horizontal band of the page and wipes
out real, VISIBLE text sharing that band -- confirmed by testing (page 0's
visible-text char count dropped from 4745 to 2558, and mid-word text like
"Health Plan" was corrupted to "ealth Plan").

This module avoids that failure mode entirely by operating on the content
stream's actual operators instead of on-page geometry: it tracks the current
text render mode (the operand of the Tr operator, honoring the q/Q graphics
state stack the mode is saved/restored on) as it walks the stream, and drops
only the text-SHOWING operators (Tj, TJ, ', ") that execute while the mode
is 3 (invisible). Every other operator -- positioning, font selection, Tr
itself, non-text graphics -- passes through unchanged, so nothing at any
bounding-box position can be collaterally damaged.
"""

import re
from typing import List, Optional

import pymupdf as fitz


_TOKEN_RE = re.compile(
    rb"""
    (?P<ws>\s+)
    | (?P<comment>%[^\r\n]*)
    | (?P<dict_open><<)
    | (?P<dict_close>>>)
    | (?P<hexstring><[0-9A-Fa-f\s]*>)
    | (?P<name>/[^\s()<>\[\]{}/%]*)
    | (?P<array_open>\[)
    | (?P<array_close>\])
    | (?P<string>\((?:[^\\()]|\\.|\((?:[^\\()]|\\.)*\))*\))
    | (?P<other>[^\s()<>\[\]{}/%]+)
    """,
    re.VERBOSE | re.DOTALL,
)


def _tokenize(stream: bytes) -> List[tuple]:
    """Split a content stream into (kind, raw_bytes) tokens, skipping
    whitespace/comments. `raw_bytes` preserves the token's exact original
    bytes so reassembly is byte-for-byte identical apart from removed spans.
    """
    tokens = []
    pos = 0
    length = len(stream)
    while pos < length:
        match = _TOKEN_RE.match(stream, pos)
        if not match:
            # Shouldn't happen for well-formed content streams, but don't
            # hang or crash on the unexpected -- pass the byte through.
            tokens.append(("other", stream[pos : pos + 1]))
            pos += 1
            continue
        pos = match.end()
        kind = match.lastgroup
        if kind in ("ws", "comment"):
            continue
        tokens.append((kind, match.group()))
    return tokens


def strip_invisible_text(stream: bytes) -> bytes:
    """Return `stream` with every Tj/TJ/'/" operator dropped while the
    active text render mode (per the most recent Tr operand, honoring q/Q
    save/restore) is 3 (invisible). All other content is byte-identical.
    """
    tokens = _tokenize(stream)

    output: List[bytes] = []
    operand_buffer: List[tuple] = []
    mode_stack: List[int] = []
    current_mode = 0

    def flush_operands():
        for _, raw in operand_buffer:
            output.append(raw)
            output.append(b" ")
        operand_buffer.clear()

    for kind, raw in tokens:
        if kind in ("name", "hexstring", "array_open", "array_close", "string", "dict_open", "dict_close"):
            operand_buffer.append((kind, raw))
            continue
        if kind == "other" and not _looks_like_operator(raw):
            operand_buffer.append((kind, raw))
            continue

        operator = raw

        if operator == b"q":
            mode_stack.append(current_mode)
            flush_operands()
            output.append(operator)
        elif operator == b"Q":
            if mode_stack:
                current_mode = mode_stack.pop()
            flush_operands()
            output.append(operator)
        elif operator == b"Tr":
            if operand_buffer:
                try:
                    current_mode = int(operand_buffer[-1][1])
                except ValueError:
                    pass
            flush_operands()
            output.append(operator)
        elif operator in (b"Tj", b"'", b'"'):
            if current_mode == 3:
                operand_buffer.clear()
            else:
                flush_operands()
                output.append(operator)
        elif operator == b"TJ":
            if current_mode == 3:
                operand_buffer.clear()
            else:
                flush_operands()
                output.append(operator)
        else:
            flush_operands()
            output.append(operator)

        if kind != "other" or _looks_like_operator(raw):
            output.append(b" ")

    flush_operands()
    return b"".join(output)


_OPERATOR_RE = re.compile(rb"^[A-Za-z'\"*]+$")


def _looks_like_operator(raw: bytes) -> bool:
    """PDF numbers are the other thing that can show up as an 'other'
    token; operators are always alphabetic (plus the special ' and "
    text-show operators, and BX/EX/etc.), so this is a safe split.
    """
    return bool(_OPERATOR_RE.match(raw))


def strip_invisible_text_from_pdf(input_path: str, output_path: str) -> None:
    """Write a copy of the PDF at `input_path` to `output_path` with every
    invisible-render-mode (Tr 3) text-showing operator removed from every
    page's content stream.
    """
    doc = fitz.open(input_path)
    for page in doc:
        xref = page.get_contents()
        if not xref:
            continue
        # Concatenate multi-stream pages into one, since operator state
        # (current Tr mode, the q/Q stack) can legitimately carry across
        # stream boundaries and splitting them back up isn't necessary --
        # PyMuPDF's get_contents() already lets us write a single merged
        # stream back to the first xref and drop the rest.
        combined = b"\n".join(doc.xref_stream(x) for x in xref)
        cleaned = strip_invisible_text(combined)
        doc.update_stream(xref[0], cleaned)
        for extra_xref in xref[1:]:
            doc.update_stream(extra_xref, b"")
    doc.save(output_path)
    doc.close()