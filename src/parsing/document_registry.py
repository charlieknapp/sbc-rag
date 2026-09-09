"""
Per-document extraction registry: maps each of the 8 fixed SBC PDFs to the
extraction recipe it actually needs, so a pipeline script can process all
8 documents automatically instead of needing hand-written per-document
notebook variants.

What varies per document, at the code level, is deliberately narrow --
just two things: which extraction function to call (pdfplumber vs
camelot), and which grid-table TableSpec to use (plain GRID_TABLE_SPEC vs
CIGNA_GRID_TABLE_SPEC). Important Questions never needed a
document-specific spec, so every document uses IMPORTANT_QUESTIONS_SPEC.
strip_invisible_text_from_pdf is NOT a per-document toggle here -- it
already runs unconditionally inside extract_camelot_tables for every
camelot-routed document, and is a verified no-op on documents that don't
actually have invisible text.

This is deliberately hardcoded per filename rather than any kind of
auto-detection system -- right-sized for this assignment's fixed, known
8-document set, not a general "figure out the right extractor for any
SBC" tool, which would be real, out-of-scope engineering.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional

from .camelot_extract import extract_camelot_tables
from .pdfplumber_extract import extract_pdfplumber_tables
from .normalize import (
    TableSpec,
    GRID_TABLE_SPEC,
    IMPORTANT_QUESTIONS_SPEC,
    CIGNA_GRID_TABLE_SPEC,
)

# Both extraction functions take a single pdf_path argument and return the
# same pages[table][row][cell] shape, so they're interchangeable here.
ExtractFn = Callable[[str], List]


@dataclass
class DocumentConfig:
    """Everything the parsing pipeline needs to know about one document.

    extract_fn: which extraction function to call for this document.
    grid_spec: which TableSpec to use for the Common Medical Event table.
    iq_spec: which TableSpec to use for the Important Questions table
        (always IMPORTANT_QUESTIONS_SPEC currently, but kept as an
        explicit field rather than hardcoded, in case a document-specific
        variant is ever needed the way CIGNA_GRID_TABLE_SPEC was).
    notes: document-level facts worth carrying forward into later phases
        (e.g. structured extraction) that aren't used by parsing itself,
        so they don't get lost in prose again.
    """

    filename: str
    insurer: str
    extract_fn: ExtractFn
    grid_spec: TableSpec
    iq_spec: TableSpec
    notes: Optional[str] = None


DOCUMENT_REGISTRY: dict = {
    "highmark_hdhp_ppoblue_2026.pdf": DocumentConfig(
        filename="highmark_hdhp_ppoblue_2026.pdf",
        insurer="Highmark BCBS",
        extract_fn=extract_pdfplumber_tables,
        grid_spec=GRID_TABLE_SPEC,
        iq_spec=IMPORTANT_QUESTIONS_SPEC,
        notes="Generic template with unfilled blank fields (literal "
        "'call ___' placeholders) -- extraction must tolerate genuinely "
        "missing values, not assume every field is populated.",
    ),
    "aetna_md_bronze_ppo_2019.pdf": DocumentConfig(
        filename="aetna_md_bronze_ppo_2019.pdf",
        insurer="Aetna",
        extract_fn=extract_pdfplumber_tables,
        grid_spec=GRID_TABLE_SPEC,
        iq_spec=IMPORTANT_QUESTIONS_SPEC,
    ),
    "bcbsil_bluechoice_bronze_ppo_2024.pdf": DocumentConfig(
        filename="bcbsil_bluechoice_bronze_ppo_2024.pdf",
        insurer="Blue Cross Blue Shield of IL",
        extract_fn=extract_pdfplumber_tables,
        grid_spec=GRID_TABLE_SPEC,
        iq_spec=IMPORTANT_QUESTIONS_SPEC,
    ),
    "kaiser_ca_traditional_hmo_2026.pdf": DocumentConfig(
        filename="kaiser_ca_traditional_hmo_2026.pdf",
        insurer="Kaiser Permanente",
        extract_fn=extract_pdfplumber_tables,
        grid_spec=GRID_TABLE_SPEC,
        iq_spec=IMPORTANT_QUESTIONS_SPEC,
        notes="$0 deductible, flat copays, zero coinsurance anywhere.",
    ),
    "uhc_stancounty_hdhp_2025.pdf": DocumentConfig(
        filename="uhc_stancounty_hdhp_2025.pdf",
        insurer="UnitedHealthcare",
        extract_fn=extract_camelot_tables,
        grid_spec=GRID_TABLE_SPEC,
        iq_spec=IMPORTANT_QUESTIONS_SPEC,
        notes="Source PDF carries a hidden, invisible-render-mode "
        "duplicate text layer; extract_camelot_tables strips it "
        "automatically via strip_invisible_text_from_pdf.",
    ),
    "cigna_nc_connect_bronze_hmo_2024.pdf": DocumentConfig(
        filename="cigna_nc_connect_bronze_hmo_2024.pdf",
        insurer="Cigna",
        extract_fn=extract_camelot_tables,
        grid_spec=CIGNA_GRID_TABLE_SPEC,
        iq_spec=IMPORTANT_QUESTIONS_SPEC,
        notes="Deductible equals OOP max ($9,450 = $9,450); "
        "grid table needs CIGNA_GRID_TABLE_SPEC (split_camelot_merged_rows) "
        "because the source PDF draws one shared bounding box around "
        "multiple distinct services in places.",
    ),
    "blueshield_ca_calpers_access_hmo_2025.pdf": DocumentConfig(
        filename="blueshield_ca_calpers_access_hmo_2025.pdf",
        insurer="Blue Shield of CA",
        extract_fn=extract_camelot_tables,
        grid_spec=GRID_TABLE_SPEC,
        iq_spec=IMPORTANT_QUESTIONS_SPEC,
        notes="Two separate OOP maximums on one plan: Medical "
        "$1,500/$3,000 plus a separate Pharmacy $7,700/$15,400 -- "
        "extraction schema cannot assume one OOP max number per plan.",
    ),
    "anthem_ppo_hsa_2022.pdf": DocumentConfig(
        filename="anthem_ppo_hsa_2022.pdf",
        insurer="Anthem",
        extract_fn=extract_camelot_tables,
        grid_spec=GRID_TABLE_SPEC,
        iq_spec=IMPORTANT_QUESTIONS_SPEC,
        notes="Deductible splits into three numbers in one answer cell "
        "($1,500/person, $2,800/member, $3,000/family) rather than the "
        "usual individual/family pair.",
    ),
}


def get_document_config(filename: str) -> DocumentConfig:
    """Look up the extraction recipe for one of the 8 known documents by
    filename. Raises KeyError with the list of known filenames if the
    given filename isn't registered -- deliberately loud, since a typo'd
    or unregistered filename silently falling through to some default
    extractor would be exactly the kind of hidden-assumption bug this
    project has repeatedly had to root-cause.
    """
    if filename not in DOCUMENT_REGISTRY:
        raise KeyError(
            f"'{filename}' is not in the document registry. "
            f"Known filenames: {sorted(DOCUMENT_REGISTRY.keys())}"
        )
    return DOCUMENT_REGISTRY[filename]