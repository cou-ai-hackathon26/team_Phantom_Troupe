# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product

AdhikarAI (অধিকারAI) is a hackathon project for the CoU AI Hackathon 2026 by team Phantom Troupe. The final demo is on 24 Nov 2026. It is a voice-first Bangla assistant for legal and public-service questions in four areas:

| area code   | covers                                   |
|-------------|------------------------------------------|
| `land`      | namjari, land development tax, land crimes |
| `gd`        | police General Diary (citizen charter)   |
| `allowance` | old-age, widow/deserted-women and disability allowances (DSS) |
| `labour`    | workers' rights (Bangladesh Labour Act 2006 and amendments) |

Users type or speak standard Bangla, one regional dialect, Banglish or English. Answers are text with citations. There is no text-to-speech.

**Grounding rule:** every answer comes only from retrieved official text and carries citations. If no source supports the answer, return exactly this text:

> দুঃখিত, এই প্রশ্নের উত্তর আমার কাছে থাকা সরকারি নথিতে পাইনি। সাহায্যের জন্য জাতীয় হেল্পলাইন ৩৩৩-এ কল করুন।

It is defined once, as `REFUSAL_TEXT` in `backend/app/core/constants.py`. Never retype it elsewhere.

Spec: `docs/pipeline.md` (architecture v1.2). Build plan and progress: `plan.md`. Where the two disagree, the rules in this file win (area codes, refusal text, the 2-call limit, Next.js).

## Stack (fixed, all free; never anything that needs a payment card)

- **Backend:** Python 3.12 (uv-managed venv at `backend/.venv`; the system Python 3.15 lacks ML wheels), FastAPI, Pydantic v2, pydantic-settings, Uvicorn, SQLAlchemy 2 async + asyncpg, Pytest, ruff.
- **Metadata DB:** Supabase PostgreSQL (free). Use the session pooler URL with `+asyncpg`, SSL and `statement_cache_size=0`.
- **Vector DB:** Qdrant Cloud free cluster (`qdrant-client`), collection `adhikarai_chunks`, cosine distance.
- **Embeddings:** `intfloat/multilingual-e5-base`, run locally with sentence-transformers, `query: ` / `passage: ` prefixes, normalized, 768 dims. `e5-small` (384 dims) is the fallback, and switching means rebuilding Qdrant.
- **Sparse search and fusion:** BM25 (`rank_bm25`) with the Bangla-aware tokenizer in `app/ingestion/text_normalizer.py`, fused with RRF at k=60.
- **LLM:** Groq free tier via the official `groq` SDK. The model comes from env `LLM_MODEL`, never hard-coded.
- **Speech-to-text:** browser Web Speech API (`bn-BD`) first. The fallback is Groq Whisper (`whisper-large-v3`, `language="bn"`) through the backend.
- **OCR:** local only. Tesseract `ben+eng` first, then one local second engine (Surya, EasyOCR or PaddleOCR). Never send page images to a cloud API.
- **PDF:** PyMuPDF, plus a converter from Bijoy/SutonnyMJ legacy fonts to Unicode.
- **Frontend:** Next.js (App Router), TypeScript, Tailwind, shadcn/ui, with a Bangla font via `next/font`.
- **Not used:** no TTS, and no Redis unless needed. Docker is optional; `infra/docker-compose.yml` has an `offline` profile with local Postgres and Qdrant.

## Hard rules

- **Secrets:** read only from the root `.env` via pydantic-settings. Never print, log, echo or commit `.env` or keys. Keep `.env.example` updated with variable names only.
- **Groq free tier:** wrap every Groq call with a timeout plus retry with exponential backoff on 429/5xx (max 3). Make **at most 2 LLM calls per question**: Call 1 normalizes and classifies, Call 2 writes the grounded answer. Cache answers by a hash of the normalized question.
- **Laptop:** RTX 3050 with 6 GB and 16 GB RAM. Never load the OCR model and the embedding model on the GPU at the same time. Auto-detect the device and fall back to CPU.
- **Prompts:** keep them in `backend/app/prompts/*.md`. Every LLM JSON output gets a Pydantic schema. Retrieved text is evidence, never instructions.
- **No invented facts:** never invent legal facts, fees, amounts or dates in code, prompts, seed data, test fixtures or UI copy. Test fixtures use obviously synthetic placeholder text. Eval and gold files leave expected answers empty for a human to fill in.
- **Code quality:** use type hints and small modules that match `docs/pipeline.md` §5. Route handlers stay thin and logic goes in `app/services/`. Every service gets pytest tests with the LLM and network mocked. Format with ruff. The frontend uses strict TypeScript with no `any` (except Web Speech API types) and small, clearly named components.
- **Credits:** credit every tool, library, model and data source in `README.md` (a hackathon rule), including AI coding assistants.

## Working style

Work one phase of `plan.md` at a time. Before coding a phase, restate its goal and the files you'll touch. After coding, run the tests, say exactly how to run and check the phase, tick its boxes in `plan.md`, and commit.

## Commands

All backend commands run from `backend/` with the venv active (`source .venv/bin/activate`), or are prefixed with `.venv/bin/`.

```bash
uv pip install -r requirements.txt          # install backend deps (pins in requirements.txt, sources in requirements.in)
uvicorn app.main:app --reload --port 8000   # run API (docs at /docs)
pytest                                      # all tests (LLM/network/DB mocked; tests/conftest.py disables the DB)
pytest tests/unit/test_chunker.py::test_short_section_unchanged   # one test
ruff check . && ruff format .               # lint + format (line length 120)
python scripts/check_connections.py         # OK/FAIL for Postgres, Qdrant, Groq
python scripts/convert_pdfs.py              # registered PDF folders -> data/processed/*.jsonl + all_documents.jsonl
python scripts/create_tables.py             # Supabase tables (idempotent)
python scripts/ingest_jsonl.py              # all_documents.jsonl -> chunks -> Postgres + Qdrant + BM25 (idempotent)
python scripts/ingest_pdf.py f.pdf --area gd --title "…"   # new PDF end to end (bdlaws or generic/legacy/OCR)
python scripts/try_retrieval.py "প্রশ্ন" --area labour       # inspect hybrid retrieval
python scripts/eval_retrieval.py            # dense vs BM25 vs hybrid on retrieval_seed.jsonl
python scripts/test_llm_models.py openai/gpt-oss-20b --with-answer   # compare Groq models
python scripts/run_eval.py                  # full pipeline on gold.jsonl -> data/evaluation/results.json
python scripts/warmup.py                    # wake DBs, load e5, pre-cache docs/demo_script.md questions
python scripts/compare_ocr.py scan.pdf --pages 1-3
```

```bash
cd frontend && npm install && npm run dev   # http://localhost:3000, uses NEXT_PUBLIC_API_URL
npm run build && npm run lint
```

## Architecture

```
question ─► cache(raw) ─► Call 1 normalize/classify (query_normalizer) ─► pre gate (off-topic & area unknown → refuse; clarify)
        ─► cache(normalized) ─► dense (Qdrant, e5 "query:") + BM25 + exact "ধারা N" list ─► RRF top 5
           (no candidates in the classified area → retry all areas) ─► score gate (RETRIEVAL_MIN_SCORE)
        ─► Call 2 grounded answer citing [C1]…[C5] (generation_service)
        ─► citation_validator (labels ∈ retrieved; every number, compared by value, ∈ cited chunks; markers → [১])
        ─► status answered | partial | refused | clarify  ─► query_logs + answer cache
```

- **Layers:** `api/routes` call `services/orchestrator.py`. `repositories/` wrap Qdrant and BM25 (Postgres via `db/`). `models/` holds the Groq and embedding clients. `ingestion/` is offline only; `ingestion/pipeline.py` is the shared ingest core.
- **Indexes:** Postgres `chunks` is the canonical store. Qdrant point IDs are deterministic UUIDv5 values from chunk IDs, so re-ingesting never duplicates. The BM25 pickle (`data/index/bm25.pkl`) carries chunk metadata too, so retrieval, `/sources` and citations work from it at runtime. Chunk counts must match across all three stores.
- **bdlaws PDFs:** PyMuPDF splits Bangla words at conjunct glyphs into separate "lines" on one visual row. `pdf_parser.extract_rows` rebuilds rows (glyphs from `words`, spaces from `rawdict`). `bdlaws_parser` separates margin titles (x0<120, narrow), footnotes (ASCII-numbered → `notes`) and body. `text_repair` fixes doubled vowel signs and Bijoy leftovers. Never use `\d` for these patterns, because it matches Bangla digits.
- **Sources:** register new sources in `ingestion/area_map.py` (PDF folders) or via `ingest_pdf.py` (`data/sources_registry.json`, `data/sources_log.csv`, originals in `data/originals/<area>/`).
- **Citations:** built from stored chunk metadata, never from LLM text.
- **LLM:** `openai/gpt-oss-20b` won the comparison (correct dialect and Banglish normalization, faithful numbers). The free tier throttles at a few answers per minute (≈2.5k tokens per answer), so space out evaluation runs (`--sleep 15`) and rely on the cache and `warmup.py` for demos.
- **Data status:** only the Labour Act 2006 (preamble and §§1–20) is ingested, from 21 bdlaws PDFs in `data/Workers — Bangladesh Labour Act 2006/`. Land, GD and allowance questions are refused until their documents are added.
