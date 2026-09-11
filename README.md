# sbc-rag
RAG-based Q&amp;A tool for health benefit plans — parses real SBC (Summary of Benefits and Coverage) forms, retrieves and extracts plan data, and answers questions like "what's my deductible for an ER visit" with cited sources. Built to explore retrieval, structured extraction, and grounded generation on table-heavy insurance documents.

## Status

In progress — built over ~4 weeks. Phases 0-4 (environment, data acquisition, parsing, chunking, retrieval) are complete. Phase 5 (structured extraction) is next. See phase notes below for what's done vs. in progress as of the review date.


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

**Output.** Validated extraction results are persisted to `data/processed/` as one JSON file per document (`notebooks/build_processed_data.py`), rather than re-running PDF extraction on every downstream iteration — chunking and every phase after it reads from this stable artifact, which also keeps a parsing bug and a downstream bug from being confused with each other.

### 2. Chunking

Because the source PDFs are already reduced to clean, structured JSON in `data/processed/` before chunking runs (see Parsing above), the fixed-size vs. semantic comparison this project calls for could be tested directly against real data rather than argued from first principles.

**Fixed-size chunking was tested and measurably fails the "never split a row mid-chunk" requirement.** A naive character-window chunker (with overlap) was run against the flattened text of two documents at three window sizes (300/500/800 characters), tracking each row's exact character span so violations could be counted rather than eyeballed. Result: 28-62% of rows were split mid-chunk depending on window size, and the violation rate never approached zero even at the largest size tested — row lengths vary enormously (a ~110-character row sits next to a ~1,500-character prescription drug row), and a fixed-size window has no way to know where a row's boundary actually is. No window size is simultaneously small enough to keep chunks focused and large enough to never cut a row on this data.

**Semantic (embedding-based) chunking was tested and found to be a real but imperfect signal.** Using local embeddings (`sentence-transformers`, `all-MiniLM-L6-v2` — the same model reused for the retrieval phase) consecutive-row cosine similarity was computed across all 8 documents and compared against the grid table's own real category boundaries — already known with certainty, since they're extracted directly during parsing — using precision/recall/F1 across a threshold sweep. The best single threshold (0.65) recovered the true category structure with F1 = 0.840 (precision 0.863, recall 0.833): a real, well-above-random signal, but not perfect, and no threshold cleanly separates every case (two rows in the *same* category scored a lower similarity, 0.627, than two rows in genuinely *different* categories at 0.786).

**Decision: structured, row-level chunking — not fixed-size or similarity-threshold chunking.** Since the real category/row boundaries are already known with zero error from parsing, using a noisy ~84%-accurate embedding proxy to rediscover them would be strictly worse than simply using the boundary already extracted. Chunks are built directly from `data/processed/*.json`'s row structure (`src/chunking/chunker.py`): one chunk per grid table row and one per Important Questions row, with category, service/question text, and plan identity folded explicitly into each chunk's text (a retriever hands back isolated chunks with no surrounding context, so each one has to be self-describing); one chunk per whole Excluded Services / Other Covered Services list (list items showed no meaningful internal similarity signal worth grouping by); and one small chunk per document for header-level facts (deductible, plan type, coverage period). This satisfies "never split a row mid-chunk" exactly, by construction — a chunk *is* a row — rather than by tuning a threshold and hoping.

320 chunks were produced across all 8 documents (`data/processed/chunks.json`), with per-document counts cross-checked against the already-validated parsing row/item counts for every document.

### 3. Retrieval

With 320 chunks in hand, retrieval's job is narrowing that down to a handful of chunks actually relevant to a given question — the assignment calls for both a keyword method and a semantic method, tested against real questions rather than assumed to behave a certain way.

**BM25 (keyword search)** (`src/retrieval/bm25_retriever.py`, via `rank-bm25`) scores chunks by word overlap with the query, weighted by term rarity and adjusted for chunk length — no understanding of meaning, purely lexical matching. Custom tokenization strips punctuation and a hand-curated stopword list; a real bug was caught and fixed here via a failing test query, not assumed away — the initial tokenizer left bare single-character fragments like `'s'` (from splitting contractions such as "What's") untouched, which measurably diluted real signal on short queries. Fixing it (filtering tokens of length 1) took BM25 on one previously-failing test question from 0/8 relevant chunks found to 6/8.

**Semantic search (embeddings)** (`src/retrieval/embedding_retriever.py`, via `sentence-transformers`'s `all-MiniLM-L6-v2` — the same model used for the Phase 2 chunking-boundary evaluation — and FAISS's `IndexFlatIP` over L2-normalized vectors, i.e. exact cosine similarity) embeds both the query and every chunk, retrieving by vector closeness rather than literal word match. FAISS was chosen over Chroma as the vector store specifically because it's a tooling decision, not a second method to compare — 320 chunks rebuilt fresh from `chunks.json` on every run don't need Chroma's persistence or metadata-filtering layer.

**Evaluation.** A 27-question eval set (`eval/questions.jsonl`) was built directly from the real chunk data, with ground-truth `chunk_id`s and expected answers — not approximated from summary values — spanning five deliberate categories: exact-SBC-vocabulary lookups, paraphrased questions, questions using rare/distinctive terms, questions naming no specific plan (genuinely ambiguous across all 8), cross-plan comparison questions, and one deliberately unanswerable question (a plan that doesn't exist in the corpus, to probe fabrication risk ahead of Phase 6). `eval/run_retrieval_eval.py` runs both retrievers at k=5 (matching the top-k that will actually reach the LLM at generation time) and reports hit-rate by category:

| Category | BM25 | Embeddings |
|---|---|---|
| Exact vocabulary | 100% | 100% |
| Paraphrased | 50% | 67% |
| Rare/distinctive terms | 100% | 75% |
| No plan named (ambiguous) | 80% | 80% |
| Cross-plan comparison | 60% | 60% |

**This is the core, measured result the phase was built to test:** BM25 and embeddings do win on different, predictable question types — BM25 on distinctive vocabulary, embeddings on paraphrased wording — confirming the hypothesis with real numbers instead of assuming it. Both tie on easy exact-match lookups, as expected.

**Real failure modes found and root-caused, not just observed:**
- *Confusable adjacent rows*: a query like "what do I pay to see a specialist" can outrank the true cost row with a topically-adjacent "do you need a referral to see a specialist" row, since both share real vocabulary/meaning around paying for specialist care despite answering different questions. Embeddings are less confidently wrong here (near-tied scores) than BM25 (a 3x score gap favoring the wrong row), but neither method is immune.
- *Uniform boilerplate crowding*: on plans with unusually flat cost structures (e.g. Cigna's plan, where deductible = out-of-pocket max, so nearly every service reads "0% coinsurance"), embeddings can fail to distinguish between many near-identical chunks and miss the specific one asked about entirely.
- *Genuine SBC-vocabulary gaps*: some real-world phrasing (e.g. "therapy visit") has no literal match anywhere in the source document's own text (which says "outpatient services," never "therapy") — a gap in the source data's vocabulary, not a retrieval bug, that keyword matching structurally cannot bridge and embeddings can only partially close.
- *Term-frequency bias toward complex answers*: BM25 can underrank the simplest, most favorable answers (e.g. a $0 deductible, explained in one short sentence) relative to more complex ones that repeat the query term more often purely because they require more explanatory text — a structural property of frequency-based scoring, not a bug.

**Known, documented architectural limitation:** cross-plan comparison questions ("which plan has the lowest deductible") cannot be reliably answered by a single top-k retrieval call from either method — nothing guarantees one comparable row gets returned per plan. Included in the eval set specifically to demonstrate and quantify this gap (both methods score only 60%, and even a "hit" often means finding just one relevant plan's chunk, not enough to actually answer a comparison) rather than to pretend it's solved; Phase 5/6 will need to account for this rather than be surprised by it.

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