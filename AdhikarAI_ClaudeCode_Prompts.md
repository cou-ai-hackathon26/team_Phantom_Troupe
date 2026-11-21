# AdhikarAI — Claude Code Prompt Pack

How to use this file:

1. Do the **Before you start** steps yourself (5 minutes).
2. Paste **Prompt 0** into Claude Code. It writes `CLAUDE.md` and `plan.md` only, no code.
3. Read `plan.md`, fix anything you don't like, then paste **Prompt 1**, **Prompt 2** … one at a time.
4. After every prompt: run what it tells you, check the "Done when" list, then commit before the next prompt.

Tip: start each prompt in **plan mode** (Shift+Tab in Claude Code) so it shows its plan before editing. Approve, then let it code.

---

## Before you start (do this yourself)

```text
adhikarai/
├── docs/
│   └── pipeline.md            ← copy of AdhikarAI_AI_Engineering_Pipeline_v1.2_Free_Stack.md
├── data/
│   ├── processed/             ← unzip AdhikarAI_data.zip here (8 JSONL + all_documents.jsonl + README.txt)
│   └── originals/             ← any original PDFs you have (Labour Act PDF etc.)
└── .env                       ← create it yourself, never paste keys into chat
```

Create accounts (all free, **never add a card**):

- Supabase → new project → Connect → copy the **Session pooler** connection string.
- Qdrant Cloud → create **Free** cluster → copy cluster URL + API key.
- Groq → console.groq.com → API Keys → create key. Open the **Models** and **Limits** pages and note which LLMs are listed.

Put them in `.env` (Claude Code will create `.env.example` with the same names):

```env
DATABASE_URL=postgresql+asyncpg://...      # Supabase session pooler string, with +asyncpg
QDRANT_URL=https://....cloud.qdrant.io:6333
QDRANT_API_KEY=...
GROQ_API_KEY=...
LLM_MODEL=...                              # fill after Prompt 4's model test
```

Install locally: Python 3.11+, Node.js LTS, Git, Tesseract with Bengali data (`ben`), ffmpeg.

---

## Prompt 0 — write CLAUDE.md and plan.md (no code yet)

```text
You are the lead engineer for AdhikarAI (অধিকারAI), a hackathon project for the CoU AI Hackathon 2026,
team Phantom Troupe. Read docs/pipeline.md fully, and look at data/processed/README.txt and the first
3 lines of data/processed/all_documents.jsonl. Do NOT write application code in this step.

Create two files only:

1) CLAUDE.md — permanent project rules you will follow in every later session:
   - Product: voice-first Bangla legal/public-service assistant. Four areas: land (namjari, land tax),
     police GD, social allowances (old-age, widow, disability), workers' rights (Labour Act 2006).
     Users may type or speak standard Bangla, one regional dialect, Banglish or English.
   - Every answer must come only from retrieved official text, with citations. If no source supports the
     answer, return exactly this refusal:
     "দুঃখিত, এই প্রশ্নের উত্তর আমার কাছে থাকা সরকারি নথিতে পাইনি। সাহায্যের জন্য জাতীয় হেল্পলাইন ৩৩৩-এ কল করুন।"
   - Stack (fixed, all free, never anything that needs a payment card):
     Backend: Python 3.11, FastAPI, Pydantic v2, Uvicorn, SQLAlchemy 2 async + asyncpg, Pytest.
     Metadata DB: Supabase PostgreSQL (free plan). Vector DB: Qdrant Cloud free cluster (qdrant-client).
     Embeddings: intfloat/multilingual-e5-base run locally with sentence-transformers
       ("query: " / "passage: " prefixes, normalized vectors, 768 dims; e5-small 384 dims as fallback).
     Sparse: BM25 (rank_bm25) with a Bangla-aware tokenizer. Fusion: RRF, k=60.
     LLM: Groq API free tier via the official groq Python SDK, model name from env LLM_MODEL.
     Speech-to-text: browser Web Speech API (bn-BD) first; Groq Whisper (whisper-large-v3, language="bn")
       fallback through the backend.
     OCR: local only — Tesseract (ben+eng) first, one local second engine (Surya, EasyOCR or PaddleOCR).
       Never send page images to any cloud API.
     PDF: PyMuPDF; Bijoy/SutonnyMJ legacy-font to Unicode converter.
     Frontend: latest stable Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui, Bangla font via next/font.
     No text-to-speech. No Redis unless needed. No Docker required for the default path
       (cloud DBs); keep an optional offline docker-compose profile with local Postgres + Qdrant.
   - Secrets: read only from .env via pydantic-settings. Never print, log, echo or commit .env or keys.
     Keep .env.example updated with names only.
   - Groq free tier is rate-limited: wrap every Groq call with timeout + retry with backoff on HTTP 429,
     at most 2 LLM calls per question, cache answers by normalized-question hash.
   - Laptop is an RTX 3050 laptop GPU with 16 GB RAM: never load the OCR model and the embedding model on
     the GPU at the same time; device auto-detect with CPU fallback.
   - Code quality: type hints, small modules matching docs/pipeline.md section 5, thin route handlers,
     business logic in services, Pydantic schemas for every request/response and every LLM JSON output,
     pytest for each service, ruff formatting. Frontend: strict TypeScript, no `any` except Web Speech API types,
     components small and named clearly.
   - Working style: one phase at a time from plan.md. Before coding a phase, restate its goal and the files
     you will touch. After coding: run the tests, tell me exactly how to run and check it, tick the boxes in
     plan.md, and stop. Do not start the next phase until I say so. Never invent legal facts, fees, amounts or
     dates in code, prompts, seed data or UI copy.
   - Hackathon rules: credit every tool, library, model and data source in README.md.

2) plan.md — a phased build plan for 3 days (21–23 Nov) plus a demo-polish block, MVP first.
   Use exactly these phases, each with: goal, files to create/change, step checklist (- [ ]),
   how to test, "Done when" criteria, and rough time estimate:
     Phase 1  Scaffold + config + connection checks (backend, frontend skeleton, Supabase, Qdrant, Groq ping)
     Phase 2  Ingestion of the existing JSONL data → Postgres + Qdrant + BM25 index
     Phase 3  Hybrid retrieval (dense + BM25 + RRF) + retrieval test CLI + small retrieval eval
     Phase 4  LLM orchestration: Groq client, Call 1 normalize/classify, safety gate, Call 2 grounded answer,
              citation + numeric validation, refusal, /api/v1/chat, answer cache
     Phase 5  Frontend UI (Next.js) wired to /api/v1/chat with citations and source viewer
     Phase 6  Voice input: browser bn-BD + Groq Whisper fallback endpoint
     Phase 7  PDF ingestion for new documents: PyMuPDF, legacy-font conversion, local OCR
     Phase 8  Evaluation: gold set, metrics, dense-vs-hybrid ablation, results shown in UI
     Phase 9  Demo polish: README with credits, demo script, warm-up script, offline fallback, final QA
   Also include: a short architecture diagram (mermaid), the API contract (request/response JSON for every
   endpoint), the Postgres table list with columns, the Qdrant collection settings, the env variable list,
   a risk list with mitigations (Groq 429, Supabase/Qdrant pause after inactivity, weak venue internet,
   Whisper weak on Bangla, OCR quality), and a "cut list" of what to drop first if time runs short.

When both files are written, show me a short summary and wait.
```

---

## Prompt 1 — Phase 1: scaffold and connections

```text
Implement Phase 1 of plan.md, following CLAUDE.md.

Backend (backend/):
- FastAPI app with routers under app/api/routes, settings in app/core/config.py (pydantic-settings, reads ../.env),
  structured logging, CORS for http://localhost:3000.
- GET /api/v1/health returns status of: Postgres (SELECT 1), Qdrant (list collections), Groq (models.list or a
  1-token call), embedding model (lazy, not loaded at startup). Each check has a timeout and never leaks secrets.
- Supabase notes: use the session pooler URL with asyncpg; if prepared-statement errors appear, set
  statement_cache_size=0 in connect_args. Use SSL.
- requirements.txt with pinned versions, .env.example, ruff config, pytest setup with one health test (mocked).
- scripts/check_connections.py: prints OK/FAIL for each service, never prints keys.

Frontend (frontend/):
- Next.js App Router + TypeScript + Tailwind + shadcn/ui initialized. Bangla font Hind Siliguri (or Noto Sans
  Bengali) via next/font, lang="bn" on <html>.
- A placeholder home page that calls /api/v1/health through NEXT_PUBLIC_API_URL and shows each service status.

Also: root README.md skeleton, .gitignore (must include .env, data caches, model caches, node_modules),
optional infra/docker-compose.yml with an "offline" profile (local postgres + qdrant) and the api service.

Done when: `python scripts/check_connections.py` shows OK for Postgres, Qdrant and Groq; `uvicorn` and
`npm run dev` both run; the home page shows green statuses. Then stop and tick plan.md.
```

---

## Prompt 2 — Phase 2: ingest the existing data

```text
Implement Phase 2 of plan.md.

Input: data/processed/*.jsonl (fields: id, act, chapter, section, title, citation, text, source_url, source_file;
some files also have text_en and translation_note). Use all_documents.jsonl as the single source and the other
files only to verify counts.

Build:
- Postgres tables (SQLAlchemy models + a create_tables script; no Alembic needed): documents (one row per
  act/source file: id, title, area, issuer, source_url, source_file, language, review_status, created_at),
  chunks (id, document_id, area, act, chapter, section, title, citation, text, normalized_text, token_count,
  qdrant_point_id, created_at), query_logs, feedback. Area is one of: land, gd, allowance, labour — map each
  source file to its area in one explicit dict.
- Section-aware chunker: keep one legal section per chunk; split only sections longer than ~450 tokens on
  sentence boundaries ("।", "?", newline) with ~60-token overlap; never split inside a numbered sub-clause if
  avoidable. Each sub-chunk keeps the parent citation plus a part number.
- Bangla text normalizer used everywhere: Unicode NFC, unify similar characters (e.g. ড়/ড় forms, য়), collapse
  whitespace, and a helper that maps Bangla digits ০-৯ to ASCII for matching (keep the original text for display).
- Embedder (app/ingestion/embedder.py): e5-base, "passage: " prefix, batch size that fits a 4 GB GPU, CPU fallback.
- Qdrant: collection adhikarai_chunks, 768 dims, cosine, payload = chunk id, area, act, section, citation;
  payload index on area. Upsert in batches with deterministic UUIDs from chunk ids (re-running must not duplicate).
- BM25: tokenizer = normalize → remove punctuation incl. "।" → whitespace split → keep Bangla and ASCII digits;
  build rank_bm25 index over normalized_text and save to data/index/bm25.pkl with the chunk-id order.
- scripts/ingest_jsonl.py: idempotent, prints counts per area, number of chunks, and timing.
- Tests: chunker (long section splits, short section unchanged), normalizer, tokenizer, deterministic ids.

Done when: the script runs twice with identical counts, Postgres chunk count = Qdrant point count = BM25 doc
count, and a printed sample shows correct Bangla text (no Bijoy gibberish). Stop and tick plan.md.
```

---

## Prompt 3 — Phase 3: hybrid retrieval

```text
Implement Phase 3 of plan.md.

- app/services/retrieval_service.py: dense search (e5 "query: " prefix, top 20, optional area filter),
  BM25 search (top 20), both returning (chunk_id, score, rank).
- app/services/fusion_service.py: RRF score = Σ 1/(60 + rank); return top 5 with each chunk's dense rank,
  BM25 rank, dense cosine and fused score (keep these for the UI "how this answer was found" panel).
- Exact-section boost: if the query contains a section number (Bangla or ASCII digits, e.g. "ধারা ১২৩"),
  BM25 must be able to hit it — verify with a test.
- scripts/try_retrieval.py "প্রশ্ন" [--area labour]: prints the top 5 with citation, ranks and a 150-char snippet.
- data/evaluation/retrieval_seed.jsonl: create a template with 8 example rows (2 per area) containing ONLY the
  question and an empty expected_chunk_ids list — I will fill the expected ids myself. Do not guess answers.
- scripts/eval_retrieval.py: Recall@5 and MRR for dense-only, BM25-only and hybrid, printed as a table and saved
  to data/evaluation/retrieval_results.json.

Done when: try_retrieval works for one question per area and eval_retrieval runs on the seed file.
Stop and tick plan.md.
```

---

## Prompt 4 — Phase 4: LLM orchestration and /chat

```text
Implement Phase 4 of plan.md.

1) app/models/llm_client.py — Groq wrapper: async client, model from LLM_MODEL, JSON output mode,
   temperature 0.1, timeout, retry with exponential backoff on 429/5xx (max 3), logs token usage, never logs keys.
   scripts/test_llm_models.py: runs 5 fixed Bangla test prompts (one dialect, one Banglish) on each model id I pass
   on the command line and prints outputs + latency side by side, so I can choose LLM_MODEL.

2) Call 1 — app/services/query_normalizer.py (prompt in app/prompts/normalize.md):
   input = user text in standard Bangla, one regional dialect, Banglish or English.
   output JSON (Pydantic-validated): {"standard_bangla": str, "area": "land|gd|allowance|labour|unknown",
   "in_scope": bool, "needs_clarification": bool, "clarification_question": str|null}.
   Rules in the prompt: rewrite only, never answer; keep names, numbers and places exactly.

3) Safety gate — app/services/trust_policy.py: refuse (fixed refusal text from CLAUDE.md) when in_scope is
   false, or when the best dense cosine is below RETRIEVAL_MIN_SCORE (env, start 0.80, to be tuned on the eval
   set) AND no BM25 hit in the top 3. If needs_clarification is true, return the clarification question instead.

4) Call 2 — app/services/generation_service.py (prompt in app/prompts/answer_bn.md):
   input = standard_bangla question + top 5 chunks, each as [chunk_id] citation + text.
   output JSON: {"answer": str, "used_chunk_ids": [str], "found": bool}.
   Prompt rules: answer in simple Bangla, short (max ~120 words) plus numbered steps if the source lists steps;
   use only the given chunks; copy numbers, amounts, dates exactly; if the chunks don't answer, found=false.

5) Validation — app/services/citation_validator.py: found=false or empty used_chunk_ids → refusal; drop any
   chunk id not in the retrieved set; numeric check: every number in the answer (Bangla or ASCII digits) must
   appear in at least one used chunk, otherwise mark status "partial" and add a warning (do not silently pass).

6) Orchestrator + POST /api/v1/chat:
   request {"message": str, "area": optional, "debug": bool}
   response {"status": "answered|partial|refused|clarify", "answer": str, "citations": [{"chunk_id", "act",
   "section", "title", "citation", "excerpt", "source_url"}], "normalized_question": str, "area": str,
   "trace": {dense/BM25/fused ranks and scores} only when debug=true, "latency_ms": int, "cached": bool}.
   Cache by hash of normalized question (Postgres table or in-memory LRU), log every request to query_logs
   (no personal data), GET /api/v1/sources/{chunk_id}, GET /api/v1/sources?area=, POST /api/v1/feedback.

7) Tests with the LLM mocked: refusal paths, invalid chunk id dropped, numeric mismatch → partial,
   clarification path, cache hit.

Done when: curl examples in the README return a cited answer for one question per area and the exact refusal
text for an off-topic question. Stop and tick plan.md.
```

---

## Prompt 5 — Phase 5: the frontend (professional, clean, focused)

```text
Implement Phase 5 of plan.md: the Next.js frontend. Use the frontend-design approach: deliberate, calm,
trustworthy public-service look — not a generic chatbot template.

Design system (put tokens in tailwind config / CSS variables, light theme first, dark theme optional):
- Colors: one primary accent, deep green (#0B6E4F range) for actions and focus; neutral warm-gray surfaces;
  status colors only for status: answered = green, partial = amber, refused = slate, clarify = blue.
  WCAG AA contrast everywhere.
- Type: Hind Siliguri or Noto Sans Bengali; body 17–18px, line-height 1.7 (Bangla needs room); clear hierarchy,
  max 2 weights per screen.
- Spacing on a 4/8px scale, rounded-xl cards, subtle borders instead of heavy shadows, no gradients, no emoji.
- Mobile-first: perfect at 360px width, then tablet and desktop (centered column, max-width ~760px for chat).

Screens and components:
1) Header: wordmark "অধিকারAI", tagline "সরকারি নথি থেকে আপনার অধিকারের উত্তর", links: হোম · নথিসমূহ · কীভাবে কাজ করে.
2) Home / chat (app/page.tsx):
   - Empty state: one-line intro, four large area cards (জমি ও নামজারি, জিডি, সামাজিক ভাতা, শ্রমিক অধিকার)
     with a simple line icon (lucide), each card shows 2 example questions as chips; tapping a chip asks it.
   - Composer fixed at the bottom: large round mic button (56–64px, primary), text input with placeholder
     "প্রশ্ন বলুন বা লিখুন…", send button; Enter sends, Shift+Enter new line. (Mic logic comes in Phase 6 —
     render the button and a disabled state for now.)
   - User message bubble; assistant answer card containing: status badge (উত্তর পাওয়া গেছে / আংশিক যাচাই /
     উত্তর পাওয়া যায়নি / আরও তথ্য দরকার), the answer with numbered steps, inline citation markers [১][২]
     (Bangla numerals), a "সূত্র" list below with act + section + title; actions: copy, helpful / not helpful.
   - Clicking a citation opens a side sheet (bottom sheet on mobile) with the full excerpt, act, section,
     and an "মূল উৎস দেখুন" link to source_url.
   - Refused answer card: the fixed refusal text, plus a prominent "৩৩৩-এ কল করুন" button (tel:333).
   - Collapsible "এই উত্তর কীভাবে পাওয়া গেল" panel (request with debug=true): normalized question, detected
     area, table of top 5 with dense rank, BM25 rank, fused score — this is for the judges' demo.
   - Loading: skeleton answer card with "নথি খুঁজছি…"; errors in Bangla with a retry button.
   - Persistent small disclaimer: "এটি আইনি পরামর্শ নয়; তথ্য যাচাই করতে সংশ্লিষ্ট অফিসে যোগাযোগ করুন।"
3) /sources: list documents by area with search and filter, each opens its sections.
4) /about: how it works (simple 4-step diagram: প্রশ্ন → নথি খোঁজা → যাচাই → উত্তর), data sources with links,
   limitations, credits (all tools/models/data), team Phantom Troupe.

Engineering:
- Typed API client (lib/api.ts) matching the backend schemas exactly; types in lib/types.ts.
- State with React hooks; conversation kept in memory for the session only (no accounts, no storage of chats).
- Accessibility: semantic HTML, visible focus rings, aria-live="polite" on new answers, all icons labelled,
  full keyboard use, prefers-reduced-motion respected, Bangla lang attributes.
- No new UI libraries beyond shadcn/ui, lucide-react and Tailwind.

Done when: I can ask one question per area from the UI, see the badge, citations, source sheet and trace panel,
the refusal card shows the 333 button, and the layout looks right at 360px and 1440px (take screenshots if you
can). Stop and tick plan.md.
```

---

## Prompt 6 — Phase 6: voice input

```text
Implement Phase 6 of plan.md.

Frontend (hooks/useSpeechInput.ts + mic UI):
- Use window.SpeechRecognition || window.webkitSpeechRecognition with lang "bn-BD", interimResults true,
  continuous false. Mic states: idle → listening (pulsing ring + live interim text + stop button) → done
  (final text placed in the input for the user to edit; do NOT auto-send).
- Handle errors in Bangla: not-allowed (mic permission), no-speech, network, unsupported browser.
- If SpeechRecognition is not available (e.g. Firefox), fall back to MediaRecorder: record up to 30 s, upload to
  POST /api/v1/chat/voice/transcribe, put the returned transcript in the input.
- Small hint under the composer on first use: "মাইকে চাপ দিয়ে আপনার ভাষায় প্রশ্ন বলুন".

Backend:
- POST /api/v1/chat/voice/transcribe: accept audio upload (max 10 MB / 30 s), convert to 16 kHz mono WAV with
  ffmpeg in a temp dir, call Groq Whisper (whisper-large-v3, language "bn", temperature 0, prompt with domain words:
  নামজারি, খতিয়ান, খাজনা, জিডি, থানা, বয়স্ক ভাতা, বিধবা ভাতা, প্রতিবন্ধী ভাতা, শ্রম আইন), return {"transcript"}.
  Delete audio files immediately after transcription. Same 429 retry policy.
- Also keep POST /api/v1/chat/voice (transcribe + run chat) as in docs/pipeline.md 13.4a.
- Tests with Groq mocked and a tiny generated WAV.

Done when: in Chrome I can speak a question, edit the text, send it and get an answer; in Firefox the recording
fallback works. Stop and tick plan.md.
```

---

## Prompt 7 — Phase 7: PDF, legacy font and local OCR (for new documents)

```text
Implement Phase 7 of plan.md, following docs/pipeline.md sections 7.1–7.2.

- app/ingestion/pdf_parser.py: PyMuPDF page-by-page text with page numbers.
- Page classifier: text page / legacy-font page (mostly Latin letters and symbols like ¯ © ‡ Ö in a Bangla doc) /
  scanned page (little or no text).
- app/ingestion/legacy_font_converter.py: Bijoy/SutonnyMJ → Unicode mapping, then the post-fix rules
  (ৰ→ক্ষ, ত্দ→্ত, ন্ত্ম→ন্ত, রম্ন→রু, ু্য→্যু, ত্প→ৎপ, misplaced reph). Unit tests with known pairs, e.g.
  "eq¯‹fvZv" → "বয়স্কভাতা".
- app/ingestion/ocr_service.py: render page at 300 DPI → Tesseract ben+eng with confidence; if mean confidence
  < OCR_MIN_CONFIDENCE, run OCR_SECOND_ENGINE (surya | easyocr | paddleocr, local only) and keep the better result.
  Store engine name + confidence per page; mark low-confidence pages review_status="needs_review".
  Load the OCR model, finish all pages, free GPU memory, then embed (never both on GPU at once).
- scripts/compare_ocr.py <pdf> --pages 1-3: runs every installed engine and writes side-by-side text files so I
  can pick OCR_SECOND_ENGINE.
- scripts/ingest_pdf.py <pdf> --area <area> --title "...": parse → convert/OCR → section-aware chunk →
  Postgres + Qdrant + rebuild BM25, reusing Phase 2 code. Original PDF copied to data/originals with checksum.

Done when: one text PDF, one legacy-font PDF and one scanned page ingest correctly and become searchable.
Stop and tick plan.md.
```

---

## Prompt 8 — Phase 8: evaluation

```text
Implement Phase 8 of plan.md.

- data/evaluation/gold.jsonl format: id, question, variant (standard|dialect|banglish|english|off_topic),
  area, expected_chunk_ids, must_include (key facts), must_not_include. Create the file with the questions only
  and empty expected fields for me to fill — do not invent legal facts.
- scripts/run_eval.py: runs the full /chat pipeline on gold.jsonl (respect Groq limits: sleep between calls,
  resume from checkpoint) and reports: retrieval Recall@5 and MRR, citation validity rate, correct refusal rate on
  off_topic, false-answer rate, answer must_include coverage, p50/p95 latency; ablation rows for dense-only vs
  hybrid. Save results to data/evaluation/results.json with timestamp, model name and sample count.
- Use the eval to suggest a RETRIEVAL_MIN_SCORE value (print the trade-off table); do not change it automatically.
- Frontend: add an "মূল্যায়ন" section on /about that reads results.json through GET /api/v1/eval/latest and
  shows the numbers in a clean table with sample count and date. Show only measured numbers.

Done when: run_eval completes on the filled gold set and the table appears on /about. Stop and tick plan.md.
```

---

## Prompt 9 — Phase 9: demo polish

```text
Implement Phase 9 of plan.md.

- README.md: what it is, architecture diagram, setup in 10 commands, env names, how to ingest, run, test, eval;
  a Credits section listing every library, model (e5, Groq-hosted LLM and Whisper, OCR engines), service
  (Supabase, Qdrant Cloud, Groq) and every data source with its official URL.
- scripts/warmup.py: pings Supabase and Qdrant (prevents inactivity pause), loads the embedding model, and
  pre-caches answers for the demo questions in docs/demo_script.md.
- docs/demo_script.md: 3-minute demo — voice question in dialect about unpaid wages → trace panel → citation
  sheet → off-topic question → refusal with 333 → evaluation table.
- Offline fallback: document how to switch to the docker-compose "offline" profile and re-ingest locally.
- Final QA pass: run all tests, ruff, `npm run build`, check console errors, check 360px layout, check that no key
  appears in logs or the repo (git grep for key patterns), check every UI string is natural Bangla.
- List anything still unfinished in plan.md under "Known limitations".

Done when: a fresh clone + README steps works end to end. Stop and give me a final checklist.
```

---

## Useful one-liners during the build

- Stuck or looping: `Stop. Summarize what you tried, what failed and the error. Propose 2 options and wait.`
- Before a risky change: `Show me the diff plan first, don't edit yet.`
- New session (context lost): `Read CLAUDE.md and plan.md, tell me which phase is in progress and what is left in it.`
- Groq 429 during testing: `Add a demo cache hit for this question and lower test calls; don't change the model.`
- UI review: `Review the UI against the Phase 5 design system in plan.md and list concrete fixes, most visible first.`
