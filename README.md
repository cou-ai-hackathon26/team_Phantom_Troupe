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

## Run it

**One-time setup:**

```bash
cp .env.example .env            # fill in DATABASE_URL, QDRANT_URL/KEY, GROQ_API_KEY, LLM_MODEL, APP_SECRET_KEY
cd backend
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python scripts/check_connections.py    # expect OK for postgres, qdrant and groq
.venv/bin/python scripts/convert_pdfs.py         # data/<folder>/*.pdf -> data/processed/*.jsonl
.venv/bin/python scripts/create_tables.py        # Supabase tables (idempotent)
.venv/bin/python scripts/ingest_jsonl.py         # Postgres + Qdrant + BM25 (idempotent)
.venv/bin/python scripts/create_admin.py you@example.com   # admin account (asks for the password)
cd ../frontend && npm install
```

**Every time, in two terminals:**

```bash
# terminal 1: API on :8000 (docs at http://localhost:8000/docs)
cd backend && .venv/bin/uvicorn app.main:app --port 8000

# terminal 2: UI on :3000 (open in Chrome for voice)
cd frontend && npm run dev               # or for the demo: npm run build && npx next start -p 3000
```

Then open:
- <http://localhost:3000> to ask questions by voice or text, and attach your own document with 📎
- <http://localhost:3000/admin> to manage the knowledge base (log in with an admin email and password)
- <http://localhost:3000/sources> and <http://localhost:3000/about> for browsing documents and the evaluation results

The frontend talks to `http://localhost:8000` by default. Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` if the API runs elsewhere, and add the UI's origin to `CORS_ORIGINS` in `.env`.

Requirements: Python 3.12 via [uv](https://docs.astral.sh/uv/), Node.js 22, ffmpeg. For OCR: Tesseract with Bengali (`sudo dnf install tesseract tesseract-langpack-ben`); EasyOCR is installed from `requirements.txt` as the second engine.

## Admin panel (`/admin`)

- **See the knowledge** the AI answers from: every document per area, with section and chunk counts, issuer and source link, and the full text of each section.
- **Upload** an official PDF (text, old Bijoy font or scanned) or an image, with its area, official title, issuer and source URL. Ingestion runs in the background with live steps: original preserved with sha256, text extraction and OCR, chunking, local embedding, Qdrant, Postgres, then the BM25 index is swapped into the running API. The document is answerable immediately, and re-uploading the same document ID replaces the old version.
- **Delete** a document: it's removed from Qdrant, Postgres, BM25 and the processed data. Built-in documents (registered in `area_map.py`) can't be deleted here.
- Every change clears the answer cache, so earlier answers and refusals are recomputed.
- **Login:** admin accounts live in the `admin_users` table. Passwords are stored only as salted scrypt hashes, and there's no plain-text copy anywhere. Create an account or reset a password with `scripts/create_admin.py <email>`. Login returns a session token signed with `APP_SECRET_KEY`, valid for `ADMIN_SESSION_HOURS` (12 by default). If `APP_SECRET_KEY` is unset, sessions end whenever the API restarts. `ADMIN_TOKEN` is an optional static key for scripts.

## Personal documents (users)

On the chat screen, 📎 attaches a PDF or photo (deed, appointment letter, notice…). The text is extracted, using local OCR for scans and photos, and then:

- it is **never embedded or added to the knowledge base**, never written to disk or a database, never cached, and never logged
- it lives in server memory for `USER_DOC_TTL_MINUTES` (default 60), or until the user removes it
- for each question, the most relevant passages of the document go to the answer step next to the official sources, and the answer cites them separately as **আপনার নথি**, never as law

## Environment variables (`.env`, names only — see `.env.example`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Supabase **session pooler** string (`postgresql://…`; the asyncpg driver and password escaping are handled automatically) |
| `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` | Qdrant Cloud free cluster |
| `GROQ_API_KEY`, `LLM_MODEL`, `STT_MODEL` | Groq free tier; `LLM_MODEL=openai/gpt-oss-20b` was best in our comparison (`scripts/test_llm_models.py`) |
| `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `EMBEDDING_DEVICE` | local `intfloat/multilingual-e5-base`, 768 dims |
| `RETRIEVAL_MIN_SCORE` | score gate (tune with `scripts/run_eval.py`) |
| `OCR_PROVIDER`, `OCR_SECOND_ENGINE`, `OCR_DEVICE`, `OCR_MIN_CONFIDENCE` | local OCR only |
| `APP_SECRET_KEY`, `ADMIN_SESSION_HOURS` | signs admin login sessions (long random string); session length |
| `ADMIN_TOKEN`, `MAX_UPLOAD_MB` | optional static admin key for scripts; upload size limit |
| `USER_DOC_TTL_MINUTES` | how long a user's personal document stays in memory |
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
| POST | `/api/v1/user-docs` | personal PDF or image → `{doc_id, filename, pages, methods, preview, expires_at}` (in memory only); pass `user_doc_id` to `/chat` |
| DELETE | `/api/v1/user-docs/{doc_id}` | remove a personal document now |
| POST | `/api/v1/admin/login` | `{email, password}` → `{token, email, expires_at}` |
| GET/POST/DELETE | `/api/v1/admin/documents[/{id}]`, `/admin/jobs[/{id}]`, `/admin/check` | knowledge-base management (Bearer session token) |
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

**Models and services:** [intfloat/multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base) (embeddings, run locally) · [Tavily](https://tavily.com) search API, free tier (web fallback limited to official government sites) · [Groq](https://groq.com) free tier: `openai/gpt-oss-20b` (OpenAI open-weight model) for answers, `whisper-large-v3` (OpenAI Whisper) for speech-to-text fallback · [Supabase](https://supabase.com) (PostgreSQL) · [Qdrant Cloud](https://qdrant.tech) (vector database) · browser Web Speech API (Chrome speech recognition)

**Backend libraries:** FastAPI · Pydantic / pydantic-settings · Uvicorn · SQLAlchemy · asyncpg · qdrant-client · groq SDK · httpx · sentence-transformers · Hugging Face Transformers · PyTorch · rank-bm25 · PyMuPDF · pytesseract / Tesseract OCR · EasyOCR · Pillow · NumPy · ffmpeg · pytest · ruff · uv

**Frontend libraries:** Next.js · React · TypeScript · Tailwind CSS · shadcn/ui · Radix UI · lucide-react · tw-animate-css · Hind Siliguri font (Google Fonts)

**Development tools:** Playwright with headless Chromium (UI screenshots and voice-flow checks during development) · Docker Compose (offline profile)

**AI coding assistant:** [Claude Code](https://claude.com/claude-code) (Anthropic) helped write code and documentation.
