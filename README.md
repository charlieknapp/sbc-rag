# sbc-rag
RAG-based Q&amp;A tool for health benefit plans — parses real SBC (Summary of Benefits and Coverage) forms, retrieves and extracts plan data, and answers questions like "what's my deductible for an ER visit" with cited sources. Built to explore retrieval, structured extraction, and grounded generation on table-heavy insurance documents.

## Status

In progress — built over ~4 weeks. See phase notes below for what's done vs. in progress as of the review date.

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
*(TODO: pdfplumber vs. camelot — what we chose and why)*

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