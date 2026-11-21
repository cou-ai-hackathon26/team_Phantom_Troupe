# অধিকারAI (AdhikarAI)

**সরকারি নথি থেকে আপনার অধিকারের উত্তর** — a voice-first Bangla assistant for land services, police GD, social allowances and workers' rights. Users speak or type in standard Bangla, a regional dialect, Banglish or English. Answers come **only** from official government documents and carry a citation for every claim. When no source supports an answer, the assistant says so and points to the national helpline 333.

Team **Phantom Troupe** · CoU AI Hackathon 2026. Build plan and progress are in [`plan.md`](plan.md); the architecture spec is [`docs/pipeline.md`](docs/pipeline.md); the demo is in [`docs/demo_script.md`](docs/demo_script.md).

> **Corpus today:** the Bangladesh Labour Act 2006 (preamble and §§ 1–20 with amendment notes). Land, GD and allowance documents plug into the same pipeline (`scripts/ingest_pdf.py`). Until they're added, questions in those areas are refused rather than guessed.

## How it works

```
question (voice/text) ─► Call 1: normalize dialect/Banglish → standard Bangla, classify area   [Groq LLM]
   ─► gate: off-topic? too vague? ─► hybrid retrieval: e5 dense (Qdrant) + BM25 (+ exact "ধারা N"), RRF k=60, top 5
   ─► gate: evidence too weak? ─► Call 2: grounded answer citing [C1]…[C5] only                   [Groq LLM]
   ─► validation in code: cited ids ∈ retrieved, every number appears in the cited source
   ─► answered | partial (warning) | refused (fixed text + ৩৩৩) | clarify
```

- At most **2 LLM calls** per question; answers are cached by question hash.
- Citations are built from stored metadata (title, section, page, official URL, amendment notes), never from model text.
- Offline ingestion: bdlaws PDF parsing (rebuilds Bangla words PyMuPDF splits, margin titles, footnotes), text repair, Bijoy → Unicode, local OCR, section-aware chunking, then Postgres + Qdrant + BM25.

## Setup (≈10 commands)

Requirements: Python 3.12 via [uv](https://docs.astral.sh/uv/), Node.js 22, ffmpeg. For scanned PDFs only, also Tesseract with Bengali data (`sudo dnf install tesseract tesseract-langpack-ben`).

```bash
cp .env.example .env                                  # fill in the values (free tiers, no card)
cd backend
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python scripts/check_connections.py         # OK for postgres, qdrant, groq
.venv/bin/python scripts/convert_pdfs.py              # data/<folder>/*.pdf -> data/processed/*.jsonl
.venv/bin/python scripts/create_tables.py             # Supabase tables (idempotent)
.venv/bin/python scripts/ingest_jsonl.py              # chunks -> Postgres + Qdrant + BM25 (idempotent)
.venv/bin/uvicorn app.main:app --port 8000            # API; docs at http://localhost:8000/docs
cd ../frontend && npm install && npm run dev          # UI at http://localhost:3000 (use Chrome for voice)
```

### Environment variables (`.env`, names only — see `.env.example`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Supabase **session pooler** string (`postgresql://…`; the asyncpg driver and password escaping are handled automatically) |
| `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` | Qdrant Cloud free cluster |
| `GROQ_API_KEY`, `LLM_MODEL`, `STT_MODEL` | Groq free tier; `LLM_MODEL=openai/gpt-oss-20b` was best in our comparison (`scripts/test_llm_models.py`) |
| `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `EMBEDDING_DEVICE` | local `intfloat/multilingual-e5-base`, 768 dims |
| `RETRIEVAL_MIN_SCORE` | score gate (tune with `scripts/run_eval.py`) |
| `OCR_PROVIDER`, `OCR_SECOND_ENGINE`, `OCR_DEVICE`, `OCR_MIN_CONFIDENCE` | local OCR only |
| `NEXT_PUBLIC_API_URL` | in `frontend/.env.local`, default `http://localhost:8000` |

## Adding documents

```bash
# a registered bdlaws folder (see backend/app/ingestion/area_map.py), then re-index
.venv/bin/python scripts/convert_pdfs.py && .venv/bin/python scripts/ingest_jsonl.py

# any new PDF: originals preserved with sha256 in data/originals/, provenance in data/sources_log.csv
.venv/bin/python scripts/ingest_pdf.py path/to/file.pdf --area allowance \
    --title "<official title>" --issuer "<issuing office>" --source-url "<official URL>"

.venv/bin/python scripts/compare_ocr.py scan.pdf --pages 1-3   # choose OCR_SECOND_ENGINE on real scans
```

## Tests and evaluation

```bash
cd backend
.venv/bin/python -m pytest                                  # unit tests; LLM/network mocked, no external calls
.venv/bin/python -m pytest tests/unit/test_chunker.py::test_short_section_unchanged
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python scripts/try_retrieval.py "লে-অফ হলে শ্রমিক কি ক্ষতিপূরণ পায়?" --area labour
.venv/bin/python scripts/eval_retrieval.py                  # dense vs BM25 vs hybrid on retrieval_seed.jsonl
.venv/bin/python scripts/run_eval.py                        # full pipeline on data/evaluation/gold.jsonl -> results.json
cd ../frontend && npm run lint && npm run build
```

`data/evaluation/gold.jsonl` holds the test questions. **`expected_chunk_ids`, `must_include` and `must_not_include` must be filled in by a human reviewer** before Recall@5, MRR and answer coverage can be measured. The latest results are shown on `/about`, and only measured numbers are reported.

## API

| Method | Path | |
|---|---|---|
| POST | `/api/v1/chat` | `{"message", "area"?, "debug"?}` → `{status, answer, citations[], normalized_question, area, warnings[], trace?, latency_ms, cached, request_id}` |
| POST | `/api/v1/chat/voice/transcribe` | audio (≤10 MB, ≤30 s) → `{transcript}` (Groq Whisper fallback; silence and prompt echoes rejected) |
| POST | `/api/v1/chat/voice` | audio → chat response + `transcript` |
| GET | `/api/v1/sources`, `/sources/documents/{id}`, `/sources/{chunk_id}` | browse documents, sections, full text with amendment notes |
| POST | `/api/v1/feedback` | `{query_log_id, rating: up\|down}` |
| GET | `/api/v1/health`, `/api/v1/eval/latest` | service status; latest evaluation |

```bash
curl -s localhost:8000/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"message": "চাকরি থেকে ছাঁটাই করলে কী কী পাওনা পাব?"}'      # answered, with citations
curl -s localhost:8000/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"message": "আজকে ঢাকার আবহাওয়া কেমন থাকবে?"}'               # refused with the fixed text
```

Statuses: `answered`, `partial` (a number couldn't be matched to the source, so a warning is shown), `refused` (fixed text and helpline 333), and `clarify`. On a Groq rate limit the API returns HTTP 503 `{"detail": {"code": "rate_limited", "message": "কিছুক্ষণ পর আবার চেষ্টা করুন।"}}`.

## Demo day

- `scripts/warmup.py` wakes Supabase and Qdrant (free projects pause when idle), loads the embedding model and pre-caches the demo questions from `docs/demo_script.md`. Run it the day before and the morning of the demo.
- **Offline fallback (weak venue internet):**
  ```bash
  docker compose -f infra/docker-compose.yml --profile offline up -d postgres qdrant
  # in .env:  DATABASE_URL=postgresql://adhikarai:adhikarai_local@localhost:5432/adhikarai
  #           QDRANT_URL=http://localhost:6333   and leave QDRANT_API_KEY empty
  cd backend && .venv/bin/python scripts/create_tables.py && .venv/bin/python scripts/ingest_jsonl.py
  ```
  Groq (the LLM) and Chrome speech recognition still need internet, so keep a phone hotspot ready. BM25 and citations also work from the local index file.

## Credits

The hackathon rules require crediting every tool, library, model and data source.

**Data sources (official):**
- Bangladesh Labour Act 2006 (বাংলাদেশ শ্রম আইন, ২০০৬), as amended. Legislative and Parliamentary Affairs Division, Ministry of Law, Justice and Parliamentary Affairs: <https://bdlaws.minlaw.gov.bd/act-952.html>. Section pages `https://bdlaws.minlaw.gov.bd/act-print-952/section-print-<id>.html` were saved as PDF on 21 Nov 2026; each citation links to its exact section page.

**Models and services:** [intfloat/multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base) (embeddings, run locally) · [Groq](https://groq.com) free tier: `openai/gpt-oss-20b` (OpenAI open-weight model) for answers, `whisper-large-v3` (OpenAI Whisper) for speech-to-text fallback · [Supabase](https://supabase.com) (PostgreSQL) · [Qdrant Cloud](https://qdrant.tech) (vector database) · browser Web Speech API (Chrome speech recognition)

**Backend libraries:** FastAPI · Pydantic / pydantic-settings · Uvicorn · SQLAlchemy · asyncpg · qdrant-client · groq SDK · httpx · sentence-transformers · Hugging Face Transformers · PyTorch · rank-bm25 · PyMuPDF · pytesseract / Tesseract OCR · EasyOCR (optional) · Pillow · NumPy · ffmpeg · pytest · ruff · uv

**Frontend libraries:** Next.js · React · TypeScript · Tailwind CSS · shadcn/ui · Radix UI · lucide-react · tw-animate-css · Hind Siliguri font (Google Fonts)

**Development tools:** Playwright with headless Chromium (UI screenshots and voice-flow checks during development) · Docker Compose (offline profile)

**AI coding assistant:** [Claude Code](https://claude.com/claude-code) (Anthropic) helped write code and documentation.
