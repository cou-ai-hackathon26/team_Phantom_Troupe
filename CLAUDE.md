# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

AdhikarAI is a hackathon project (Team Phantom Troupe, CoU AI Hackathon 2026, final demo 24 Nov 2026). It is a voice-first Bangla assistant that answers questions in four domains (`workers`, `land`, `police`, `allowances`) using hybrid RAG over official government documents. Answers are shown as text with verified citations, and the system abstains when the evidence is insufficient.

**Right now the repo holds only the plan:** `AdhikarAI_AI_Engineering_Pipeline_Free_Stack.md` (v1.2). It is the spec. Read the relevant section before building a module. Section numbers are given below. Once real code and commands exist, replace the "planned" parts of this file with verified ones. The plan's §5 tree is rooted at `adhikarai/`, which maps to this repo's root.

Out of date: an earlier plan (`AdhikarAI_Solution_Architecture.md`, with ChromaDB, gTTS, a 2-call limit, a fixed refusal string and a demo cache) has been replaced. Don't reintroduce those pieces. In particular, **text-to-speech was removed** in v1.2. Voice is input only.

## Planned commands (unverified; update once the code exists)

- Backend: Python + FastAPI on Uvicorn, port 8000, app at `backend/app/main.py` (`uvicorn app.main:app --reload` from `backend/`). Deps are in `backend/requirements.txt`.
- Tests: Pytest under `backend/tests/{unit,integration,evaluation}`. Run one test with `pytest tests/unit/test_x.py::test_name`.
- Ingestion: `backend/scripts/ingest_documents.py`. Rebuild vectors with `backend/scripts/rebuild_qdrant.py`.
- Benchmark: `backend/scripts/run_benchmark.py` (wraps `app/evaluation/run_eval.py`).
- Docker: `infra/docker-compose.yml` runs only the API by default. `docker compose --profile offline up` adds local Postgres and Qdrant as a fallback if the venue network is weak. Point `DATABASE_URL` and `QDRANT_URL` at them.
- Config: copy `.env.example` to `.env`. The variables are listed in plan §17.2 (`GROQ_API_KEY`, `LLM_MODEL`, `STT_MODEL`, `DATABASE_URL`, `QDRANT_*`, `EMBEDDING_*`, `OCR_*`).
- Frontend: React + TypeScript in `frontend/`.

## Architecture (big picture)

The backend is a single FastAPI app with layered modules (§3.1, §5). Routes stay thin: `api/routes/*` call `services/orchestrator.py`. Services hold the logic. `repositories/` wrap Postgres, Qdrant and BM25. `models/` holds swappable adapters for the LLM (Groq) and embeddings (local e5), selected via `.env`. Prompts are markdown files in `app/prompts/`.

**Offline ingestion (§6–7, `app/ingestion/`):** official PDF/HTML originals, kept byte-for-byte in `data/originals/<NN_domain>/` and recorded in the source registry `data/sources_log.csv` (URL, issuer, dates, sha256, version status) → PyMuPDF page-by-page extraction → detect Bijoy/SutonnyMJ legacy-font gibberish and convert it to Unicode → local OCR for scanned pages (Tesseract `ben+eng` first, then a second local engine when confidence is low; never cloud OCR) → cleaning (never strip provisos, footnotes, table headers or section numbers) → structure-aware chunking (one section, clause, table or FAQ per chunk; long sections split at subsections with parent metadata) → embed locally and upsert to Qdrant, build BM25, write metadata to Supabase Postgres. Each chunk carries document_id, domain, section and page range (§7.6), and every chunk must map to a real source page (§7.7 quality gates). The team's existing 442-entry section-level JSONL is loaded as derived sources linked to the original URLs (§6.5).

**Embeddings (§9):** `intfloat/multilingual-e5-base` (768-dim) via sentence-transformers, with `query: ` and `passage: ` prefixes and normalized vectors. `-small` (384-dim) is the fallback. The Qdrant collection size must match the model, so changing the model means rebuilding the collection. Don't load OCR and embedding models on the GPU at the same time (RTX 3050 laptop).

**Query pipeline (§10, §13.5 `orchestrator.run`):** normalize (keep names, numbers and section refs) → classify domain + intent (LLM structured output; `uncertain` means search broadly or ask a clarifying question) → rewrite into search variants (must not add facts) → dense retrieval from Qdrant + BM25 → RRF fusion (keep raw ranks in the trace) → optional cross-encoder rerank, kept only if measured to help → evidence assembly (if insufficient, abstain) → Groq answer generation (structured: `answer, claims[], citations[], limitations[], needs_human_review`) → atomic claim extraction → **deterministic citation validation in code** (IDs exist, chunk belongs to document, page range valid, URL from registry, numbers and dates match evidence) → trust policy maps the result to one of `SUPPORTED | PARTIALLY_SUPPORTED | INSUFFICIENT_EVIDENCE | SOURCE_CONFLICT | OUTDATED_SOURCE | NEEDS_HUMAN_REVIEW`. Regeneration attempts are bounded, with no infinite generate→verify loop.

Core rule (§21): code verifies anything exactly checkable. The LLM only interprets language and explains. Citation objects are built from the source registry, never from LLM text. Similarity score never decides legal precedence (§12.3).

**Voice (§10 Step 0, §13.4a):** the default is browser `webkitSpeechRecognition` (`bn-BD`, Chrome, HTTPS or localhost). The recognized text is shown for the user to edit before sending. The fallback is `MediaRecorder` → `POST /api/v1/chat/voice` → ffmpeg to 16 kHz mono WAV → Groq Whisper (`language="bn"`, `temperature=0`, domain-word `prompt`) → the transcript enters the same pipeline as typed text. Don't keep audio after transcription.

**API (§13):** `POST /api/v1/chat` takes `{message, language_preference, conversation_id?}` and returns `{answer, domain, status, citations[{document_id, chunk_id, title, section, page_start, page_end, source_url}], limitations, needs_human_review, request_id}`. `/chat/voice` returns the same plus `transcript`. Also `/feedback`, `/sources/{document_id}` and `/health`. The `/admin/*` routes (documents, ingestion, evaluation) require auth.

**Evaluation (§15):** a human-reviewed gold set (20–30 per domain; includes Banglish, dialect, out-of-scope, outdated-source and conflict traps). It reports Recall@K, MRR, nDCG, citation precision and coverage, and correct-abstention rate, plus the A–D ablation (dense → hybrid → reranked → trust-enhanced). Report only measured numbers.

## Groq (LLM + STT)

- Use the official `groq` SDK. Keep model IDs in config/`.env` (`LLM_MODEL`, `STT_MODEL`), never hard-coded. Hosted models change, so check the console Models page first and choose the chat model by Bangla eval results.
- Free tier only: no payment card on any service, including Supabase and Qdrant. Limits are per organization and per model. HTTP 429 means wait for the reset, so handle it gracefully and never fabricate an answer.
- Validate every structured output with Pydantic. Retrieved text is evidence, never instructions.
- Supabase and Qdrant free projects pause when idle. Wake both the day before the demo.

## Project rules

- Keep source originals unchanged. Never use blogs or mirrors as evidence. Mark superseded or unverified documents, and don't present an old fiscal-year amount as current. An unofficial translation must be labeled as such.
- Don't collect NID, phone numbers or addresses. Redact personal data from logs.
- Keep the credits list in `README.md` up to date (required by the hackathon rules), including AI coding assistants.
