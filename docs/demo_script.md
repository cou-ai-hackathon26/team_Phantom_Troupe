# AdhikarAI — 3-minute demo script

**Before going on stage** (30 minutes before):

1. `cd backend && .venv/bin/python scripts/warmup.py` wakes Supabase and Qdrant, loads the embedding model and pre-caches every question below (real pipeline answers only).
2. Start the API (`.venv/bin/uvicorn app.main:app --port 8000`) and the UI (`cd frontend && npm run build && npx next start -p 3000`).
3. Open **Chrome** at `http://localhost:3000` and allow the microphone once. Firefox has no `bn-BD` speech recognition.
4. Weak venue Wi-Fi? Use a phone hotspot. If the cloud databases are unreachable, switch to the offline profile (see README → Offline fallback).

> The corpus currently covers the **Bangladesh Labour Act 2006**: the preamble and §§ 1–20 with amendment notes. The planned "unpaid wages" opener needs the wage-payment chapter, which isn't ingested yet. Until it is, open with lay-off compensation. When it's added, put the wage question in the list below and re-run `warmup.py`.

## Script

| Time | Do | Say (Bangla, short) |
|---|---|---|
| 0:00 | Home screen | "অধিকারAI সরকারি আইন থেকে উত্তর দেয়, সূত্রসহ। মানুষ নিজের ভাষায় প্রশ্ন বলবে।" |
| 0:15 | Tap the mic and say the **dialect question** (Q1). Show the recognized text in the box, then send. | "আঞ্চলিক ভাষায় বললাম; লেখাটা পাঠানোর আগে ঠিক করে নেওয়া যায়।" |
| 0:40 | Point at the answer card: status badge, numbered steps, `[১]` markers | "প্রতিটি কথার পাশে সূত্র নম্বর।" |
| 0:55 | Open **"এই উত্তর কীভাবে পাওয়া গেল"** | "প্রশ্নটি প্রমিত বাংলায় সাজানো হয়েছে, বিষয় চেনা হয়েছে, আর অর্থ ও শব্দ, দুই রকম খোঁজের ফল RRF দিয়ে মেলানো হয়েছে।" |
| 1:20 | Tap a `[১]` marker to open the source sheet, then tap **মূল উৎস দেখুন** | "মূল ধারার লেখা আর সরকারি ওয়েবসাইটের লিংক। সংশোধনী টীকাও আছে।" |
| 1:45 | Type the **off-topic question** (Q3) | "নথিতে নেই এমন প্রশ্নে অধিকারAI বানিয়ে বলে না।" Show the refusal card and the **৩৩৩-এ কল করুন** button. |
| 2:10 | Ask Q4 (a land question) | "জমির নথি এখনো যুক্ত হয়নি, তাই উত্তর দেয়নি। কোন বিষয়ে নথি আছে, সেটাই সীমা।" |
| 2:25 | Go to **কীভাবে কাজ করে** → মূল্যায়ন table | "পরীক্ষার প্রশ্নে মাপা ফল: বিষয়বহির্ভূত প্রশ্নে কত বার ঠিকভাবে বিরত থেকেছে, সূত্র কতটা সঠিক, সময় কত।" |
| 2:50 | Close | "ছোট, যাচাইযোগ্য, সূত্রনির্ভর ব্যবস্থা।" |

## Demo questions (pre-cached by `warmup.py`)

The warm-up script reads every line below that starts with `- Q`.

- Q1: লে-অফ অইলে শ্রমিকে কিছু টেকা পাইবো নি?
- Q2: চাকরি থেকে ছাঁটাই করলে কী কী পাওনা পাব?
- Q3: আজকে ঢাকার আবহাওয়া কেমন থাকবে?
- Q4: জমির নামজারি করতে কী কী কাগজ লাগে?
- Q5: শিক্ষানবিশ শ্রমিকের শিক্ষানবিশীকাল কত দিন?
- Q6: লে-অফ হলে শ্রমিক কি ক্ষতিপূরণ পায়?
- Q7: শ্রম আইনের ধারা ১৯ এ কী বলা আছে?
- Q8: মালিক কি শ্রমিককে নিয়োগপত্র দিতে বাধ্য?

**Voice note:** spoken Q1 may be transcribed slightly differently from the typed text, so it may miss the cache. That's fine: a live answer takes about 2–3 s when Groq isn't rate-limited. Don't ask questions back to back. The free tier throttles at a few answers per minute, and back-to-back evaluation runs measured 17–25 s per answer.

## If something fails

| Symptom | Fix |
|---|---|
| "কিছুক্ষণ পর আবার চেষ্টা করুন" (rate limit) | Ask a pre-cached question instead, or wait about 30 s. Teammates' own Groq keys add quota. |
| Mic does nothing | Check the site permission; use Chrome; the typed fallback always works. |
| "সার্ভারের সাথে সংযোগ হচ্ছে না" | Check that the API is running on :8000 and that `NEXT_PUBLIC_API_URL` points to it. |
| Health shows Postgres/Qdrant FAIL | Run `warmup.py` (paused free projects take a minute to wake), or use the offline profile. |
