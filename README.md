# sbc-rag
RAG-based Q&amp;A tool for health benefit plans — parses real SBC (Summary of Benefits and Coverage) forms, retrieves and extracts plan data, and answers questions like "what's my deductible for an ER visit" with cited sources. Built to explore retrieval, structured extraction, and grounded generation on table-heavy insurance documents.

## Status

In progress — built over ~4 weeks. See phase notes below for what's done vs. in progress as of the review date.

## Project Structure

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

## Setup

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt


*(TODO: add any API keys / .env instructions once we get to the generation step)*

## Data — SBC Sources

*(TODO: list the 5-8 SBCs used — insurer, plan name, plan type (HMO/PPO/HDHP), link to source)*

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