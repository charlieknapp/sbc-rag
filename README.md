# sbc-rag
RAG-based Q&amp;A tool for health benefit plans — parses real SBC (Summary of Benefits and Coverage) forms, retrieves and extracts plan data, and answers questions like "what's my deductible for an ER visit" with cited sources. Built to explore retrieval, structured extraction, and grounded generation on table-heavy insurance documents.

## Status

In progress — built over ~4 weeks. Phases 0-2 (environment, data acquisition, parsing) are complete. Phase 3 (chunking) is next. See phase notes below for what's done vs. in progress as of the review date.


## Project Structure

 ```
sbc-rag/
├── data/
│ ├── raw/ # original SBC PDFs, untouched
│ └── processed/ # extracted text/tables, chunks
├── src/
│ ├── parsing/ # PDF -> structured text/tables
│ ├── chunking/
│ ├── retrieval/ # BM25 + embeddings
│ ├── extraction/ # structured schema extraction
│ ├── generation/ # LLM synthesis step
│ └── evaluation/
├── notebooks/ # exploratory work
├── tests/
└── eval/
└── questions.jsonl # eval question set + correct answers
```

## Setup

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

*(TODO: add any API keys / .env instructions once we get to the generation step)*

## Data — SBC Sources

| Insurer | Plan | Type | Deductible (indiv/family) | OOP Max (indiv/family) | Source | Year |
|---|---|---|---|---|---|---|
| Kaiser Permanente | CalPERS Traditional HMO | HMO | $0 | $1,500 / $3,000 | [kaiserpermanente.org](https://choose.kaiserpermanente.org/content/dam/kp/secondsales/microsites/contents/pdf/calpers/2026/CalPERS_Summary%20of%20Benefits%20and%20Coverage%20(SBC)%20(PDF)_CA_Basic_ADA_2026.pdf) | 2026 |
| Aetna | MD Bronze PPO 6000 80/60 HSA | PPO | $6,000 / $12,000 | $6,550 / $13,300 | [aetna.com](https://www.aetna.com/plan-documents/SBC-2019-SHOP-MD-739938.pdf) | 2019 |
| UnitedHealthcare | Stanislaus County HDHP | HDHP | $1,650 / $3,300 | $3,000 / $6,000 | [stancounty.com](https://www.stancounty.com/riskmgmt/docs/eb-forms/uhc-ppo-hdhp-hsa-sbc.pdf) (employer-hosted mirror) | 2025 |
| Cigna | NC Connect Bronze 9450 | HMO | $9,450 / $18,900 | $9,450 / $18,900 | [cigna.com](https://www.cigna.com/static/www-cigna-com/docs/ifp/m-24-sbc-nc-944655-b-connect9450.pdf) | 2024 |
| Blue Shield of CA | CalPERS Access+ HMO | HMO | $0 | $1,500 / $3,000 | [blueshieldca.com](https://www.blueshieldca.com/content/dam/bsca/en/premier-accounts/docs/calpers/Public_Employees_Benefit_Retirement_System_CalPERS_Access_HMO__M0037791_01-25_SBC.pdf) | 2025 |
| Blue Cross Blue Shield of IL | Blue Choice Preferred Bronze PPO | PPO | $7,000 / $14,000 | $9,450 / $18,900 | [bcbsil.com](https://www.bcbsil.com/sbc/ind/sbc-bpsh31bceiilo-il-2024.pdf) | 2024 |
| Anthem | PPO+ / Prudent Buyer (HSA-qualified) | PPO | $1,500 / $2,800 / $3,000 | $6,450 / $12,900 | [anthem.com](https://www.anthem.com/docs/inline/PPO-HSA_Summary.PDF) | 2022 |
| Highmark BCBS | PPO Blue (HDHP, via Carnegie Mellon) | HDHP | $2,000 / $4,000 | $4,000 / $8,000 | [cmu.edu](https://www.cmu.edu/hr/assets/benefits/2026-highmark-hdhp-sbc.pdf) (employer-hosted mirror) | 2026 |

Note: coverage years span 2019-2026 intentionally. The SBC has been a federally standardized template since 2012, so structure is consistent across years — this range actually helps confirm our parsing isn't overfit to one year's minor formatting.

## How It Works

### 1. Parsing
Every SBC is federally templated, but that consistency turned out to hold at the section level, not the extraction level — no two documents rendered their tables the same way underneath, and several looked visually identical while breaking differently on inspection.

**Grid table and Important Questions table.** Both use `pdfplumber`'s table extraction (tuned tolerances — `snap_tolerance`/`join_tolerance`/`intersection_tolerance`/`edge_min_length` all set to `5`, found through a controlled default-vs-tuned comparison after a wrong first guess of `8` caused real cross-row text bleed) as the default path, with `camelot` (lattice mode, reading actual ruling lines instead of clustering text positions) substituted in for four documents whose specific defects pdfplumber couldn't handle: UnitedHealthcare (a duplicate invisible text layer — a legitimate PDF accessibility feature that confused every text-based extractor equally, fixed by stripping render-mode-3 text directly from the content stream), Cigna (decorative shading rectangles that pdfplumber's line-detection mistook for real row boundaries), Blue Shield CA and Anthem (a stray footnote and a mid-page table split, respectively, that camelot's ruling-line-based extraction simply didn't trip over). Which library and which table spec each document needs is captured once in `src/parsing/document_registry.py`, not re-decided per script.

Raw table output — from either library — still isn't usable directly: merged cells, blank continuation rows, and wrapped multi-line labels all needed a shared normalization pass (`src/parsing/normalize.py`) that forward-fills blank category labels, merges orphaned overflow text onto the correct row, and tracks state across page breaks. The same normalization logic, generalized around a `TableSpec` dataclass, handles both the "Common Medical Events" grid table and the "Important Questions" table (different column shapes and merge semantics, same underlying blank-continuation pattern).

**Non-table content.** Header metadata (insurer, plan name, coverage period, plan type) and the Excluded Services / Other Covered Services bulleted lists are extracted separately, since neither is a ruled table. Header metadata is pulled line-by-line with marker-based field detection, falling back to the document registry (not PDF text) for insurer name on the several documents where it's rendered as a logo image rather than text. Excluded/Other Covered Services required a different technique entirely — both lists are laid out as multi-column bullet grids with no ruling lines and, on at least one document, no enclosing rectangle at all — so they're reconstructed directly from word-level `(x0, top)` positions: bullet characters anchor column positions, rows are split into segments by horizontal gap, and each segment is assigned to its nearest column by its own leading position.

**Deferred, on purpose:** the three standardized coverage examples (having a baby / managing diabetes / simple fracture) are structurally more involved than the other content and aren't needed until evaluation — every document prints the same three scenarios with fixed totals, so they'll serve as a built-in ground-truth check in Phase 7 rather than being built now. Language-access boilerplate and legal disclaimers are excluded outright — no answerable content.

**Validation.** All 8 documents were checked by hand against their actual rendered PDFs (not just row/item counts), and a full 8-document regression pass was run against the final codebase after every document was individually validated — this caught one real bug (a fix made for one document silently dropping a valid row on another) before it could ship. A few small, low-severity artifacts remain and are documented in code rather than fixed: isolated single-character word splits on 2-3 documents, and one cosmetic field-boundary issue on Anthem's header (a value that lands split across two fields instead of one, nothing lost).

### 2. Chunking
*(TODO: fixed-size vs. semantic — what we chose and why, how we handled tables)*

### 3. Retrieval
*(TODO: BM25 vs. semantic search — how each performed, on which question types, and why)*

### 4. Structured Extraction
*(TODO: schema design, extraction accuracy against ground truth)*

### 5. Generation
*(TODO: how the final LLM step works, citation approach, low-confidence handling)*

## Evaluation

*(TODO: accuracy / latency / token-usage results against the eval set)*

## What I'd Do Differently With a Real Budget

*(TODO)*

## Example Queries

*(TODO: a few sample Q&A outputs once the tool works end-to-end)*