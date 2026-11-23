# AdhikarAI — 3-minute demo script

Updated 22 Nov for the full corpus; 🔊 read-aloud added 23 Nov. Q1–Q5 gave a correct answer or the correct refusal in every test run that day (`openai/gpt-oss-120b`, two or more runs each). **Re-check all five after any change to the model, prompts, code or data.**

## Before going on stage (30 minutes before)

1. `cd backend && .venv/bin/python scripts/warmup.py --tts`, then **read its output**: Q1–Q4 must be `answered` and Q5 `refused`, and every `tts` line `new` or `cached` (not `FAIL`). Refusals are never cached, so Q5 is always live (about 1–2 s); its spoken audio is cached, because the refusal text never changes. `--tts` spends ElevenLabs characters once per answer: check the balance in the ElevenLabs dashboard first.
2. Start the API (`.venv/bin/uvicorn app.main:app --port 8000`) and the UI (`cd frontend && npm run build && npx next start -p 3000`). The API needs its own time to load the index and model, so start it early.
3. Open **Chrome** at **`http://localhost:3000/?debug`**. Without `?debug` the "how this was found" panel is hidden. Allow the microphone once and set the language switch to **বাং**.
4. Ask Q1–Q4 once in the UI and read each answer against its source. Press **🔊 শুনুন** on each: it must play at once (from the cache). Then press **নতুন প্রশ্ন**. Don't reload without `?debug`.
5. Weak venue Wi-Fi? Use a phone hotspot and set `WEB_FALLBACK=false` before starting the API.

## Script

| Time | Do | Say (Bangla, short) |
|---|---|---|
| 0:00 | Home screen | "অধিকারAI সরকারি আইন ও নথি থেকে সূত্রসহ উত্তর দেয়। মানুষ নিজের ভাষায় প্রশ্ন বলবে।" |
| 0:15 | Tap the mic and say **Q1** (dialect). Correct the text to match Q1 so it hits the cache, then send. | "আঞ্চলিক ভাষায় বললাম; পাঠানোর আগে লেখাটা ঠিক করে নেওয়া যায়।" |
| 0:40 | Point at the answer card and its source, then tap **🔊 শুনুন** for a few seconds and **থামান** | "উত্তরের সাথে আইনের নাম আর ধারা। আর যিনি পড়তে পারেন না, তিনি শুনে নিতে পারেন।" |
| 0:55 | Open **"এই উত্তর কীভাবে পাওয়া গেল"** | "প্রশ্নটি প্রমিত বাংলায় সাজানো হয়েছে, বিষয় চেনা হয়েছে, আর অর্থ ও শব্দ, দুই রকম খোঁজের ফল মেলানো হয়েছে।" |
| 1:20 | Tap the source, then **মূল উৎস দেখুন** | "মূল ধারার লেখা আর সরকারি ওয়েবসাইটের লিংক।" |
| 1:40 | Ask **Q3** (named act and section) | "আইন আর ধারার নম্বর বললে সেই ধারাটিই আনে।" |
| 2:05 | Ask **Q4** (Constitution) | "শুধু শ্রম আইন নয়, সংবিধানসহ দেশের অন্যান্য আইনও আছে।" |
| 2:25 | Ask **Q5** (off-topic). Show the refusal card and the **৩৩৩** button. | "নথিতে নেই এমন প্রশ্নে বানিয়ে বলে না।" |
| 2:45 | Close | "এটি আইনি পরামর্শ নয়; সূত্র দেখে যাচাই করার সহায়ক। নির্ভুলতার মূল্যায়ন এখনো চলছে।" |

Q2 is the typed backup for Q1 if the microphone fails.

## Demo questions (pre-cached by `warmup.py`)

The warm-up script reads every line below that starts with `- Q`.

- Q1: মালিকে কি শ্রমিকরে নিয়োগপত্র দেওন লাগবো?
- Q2: মালিক কি শ্রমিককে নিয়োগপত্র দিতে বাধ্য?
- Q3: বাংলাদেশ শ্রম আইন ২০০৬ এর ধারা ১৯ এ কী বলা আছে?
- Q4: সংবিধানের অনুচ্ছেদ ২৭ কী বলে?
- Q5: আজকে ঢাকার আবহাওয়া কেমন থাকবে?

## Do not demo

Fixed on 23 Nov and checked once end to end on `openai/gpt-oss-20b`: old-age allowance, lay-off (also the dialect form),
"শ্রম আইনের ধারা ১৯", retrenchment in Bangla and Banglish, probation, GD requirements. Re-check them after `warmup.py`
before using any as an extra question.

| Topic | What happens now |
|---|---|
| Namjari documents | refused: the corpus has no official namjari document list (correct, but don't show it as an answer) |
| GD and allowance answers | cite compiled guides as official (plan 12.11) |
| মূল্যায়ন tab in `/admin` | numbers are from the old 55-chunk corpus |

If judges ask about these, say they are known open issues.

## If something fails

| Symptom | Fix |
|---|---|
| "কিছুক্ষণ পর আবার চেষ্টা করুন" (rate limit) | Ask a pre-cached question, or wait about 30 s. Uncached answers can take up to about 30 s. |
| Mic does nothing | Check the site permission and use Chrome, or type Q2. |
| 🔊 says "সার্ভারের পুরনো সংস্করণ…" | The API was started before the read-aloud update or before `ELEVENLABS_API_KEY` was added: restart it and ask again. |
| 🔊 says "এই মুহূর্তে উত্তরটি শোনানো যাচ্ছে না" or "বাংলা ভয়েস নেই" | ElevenLabs refused (often the free quota): skip 🔊. Desktop Chrome on Linux has no Bangla voice of its own, so there is no local fallback on the laptop. |
| "সার্ভারের সাথে সংযোগ হচ্ছে না" | Check that the API is running on :8000 and that `NEXT_PUBLIC_API_URL` points to it. |
| Health shows Postgres FAIL | Often just a slow cold connection (5 s limit): check again. If it persists, run `warmup.py --skip-cache`. |
| Health shows Qdrant FAIL | Run `warmup.py --skip-cache` to wake it. Questions can't be answered without Qdrant. |
