# অধিকারAI (AdhikarAI)

**সরকারি নথি থেকে আপনার অধিকারের উত্তর** — a voice-first Bangla assistant that answers questions about land services, police GD, social allowances and workers' rights. It answers only from official government documents and shows a citation with every answer. When no source supports an answer, it says so and points to the national helpline 333.

Team **Phantom Troupe**, CoU AI Hackathon 2026.

> Status: under active development. See [`plan.md`](plan.md) for progress and [`docs/pipeline.md`](docs/pipeline.md) for the architecture.

## Quick start

Requirements: Python 3.12 (managed by [uv](https://docs.astral.sh/uv/)), Node.js 22 LTS, ffmpeg, and Tesseract with Bengali data (for PDF OCR only).

```bash
cp .env.example .env            # fill in Supabase, Qdrant Cloud and Groq values (all free tiers)

# backend
cd backend
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python scripts/check_connections.py     # OK/FAIL per service
.venv/bin/uvicorn app.main:app --reload --port 8000   # API docs: http://localhost:8000/docs
.venv/bin/python -m pytest

# frontend (new terminal)
cd frontend && npm install && npm run dev        # http://localhost:3000
```

## Data and ingestion

Source documents live in `data/<folder>/` (registered in `backend/app/ingestion/area_map.py`). Right now that's the Bangladesh Labour Act 2006 (21 section PDFs from bdlaws.minlaw.gov.bd).

```bash
cd backend
.venv/bin/python scripts/convert_pdfs.py      # PDFs -> data/processed/*.jsonl + all_documents.jsonl
.venv/bin/python scripts/create_tables.py     # Supabase tables (idempotent)
.venv/bin/python scripts/ingest_jsonl.py      # chunks -> Postgres + Qdrant + BM25 (idempotent)
.venv/bin/python scripts/try_retrieval.py "লে-অফ হলে শ্রমিক কি ক্ষতিপূরণ পায়?" --area labour
.venv/bin/python scripts/test_llm_models.py openai/gpt-oss-20b --with-answer   # compare LLM_MODEL candidates
```

## API examples

With the API running (`uvicorn app.main:app --port 8000`) and `LLM_MODEL` set in `.env`:

```bash
# answered, with citations (add "debug": true to get the retrieval trace)
curl -s localhost:8000/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"message": "চাকরি থেকে ছাঁটাই করলে কী কী পাওনা পাব?"}'

# off-topic -> the fixed refusal text, status "refused", no citations
curl -s localhost:8000/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"message": "আজকে ঢাকার আবহাওয়া কেমন থাকবে?"}'

curl -s localhost:8000/api/v1/sources                       # indexed documents
curl -s localhost:8000/api/v1/sources/labour-act-2006-s6    # one chunk with full text and amendment notes
```

Response statuses: `answered`, `partial` (a number in the answer couldn't be matched to the source, so a warning is attached), `refused` (the fixed text with helpline 333), and `clarify` (the system asks a follow-up question). On a Groq rate limit, the API returns HTTP 503 `{"detail": {"code": "rate_limited", "message": "কিছুক্ষণ পর আবার চেষ্টা করুন।"}}`.

## Credits

The hackathon rules require crediting every tool, library, model and data source.

**Models and services:** [intfloat/multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base) (embeddings, run locally) · [Groq](https://groq.com) free tier (LLM inference and Whisper speech-to-text) · [Supabase](https://supabase.com) (PostgreSQL) · [Qdrant Cloud](https://qdrant.tech) (vector database) · Web Speech API (browser speech recognition)

**Backend libraries:** FastAPI · Pydantic / pydantic-settings · Uvicorn · SQLAlchemy · asyncpg · qdrant-client · groq SDK · httpx · sentence-transformers · PyTorch · rank-bm25 · PyMuPDF · pytesseract / Tesseract OCR · Pillow · NumPy · pytest · ruff · uv

**Frontend libraries:** Next.js · React · TypeScript · Tailwind CSS · shadcn/ui · Radix UI · lucide-react · Hind Siliguri font (Google Fonts)

**Data sources:** official government documents. The full list with URLs will be added once the dataset is ingested.

**AI coding assistant:** [Claude Code](https://claude.com/claude-code) (Anthropic) helped write code and documentation.
