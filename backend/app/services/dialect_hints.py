"""Deterministic dialect glossary for Call 1.

The LLM rewrites dialect into standard Bangla, but in tests (scripts/eval_normalization.py) it kept dropping or
swapping dialect question words (কিল্লাই, ক্যানে, কনে, কিলা → "কখন", "কী", nothing), which changes the question.
Code spots the known words and appends a short glossary line to the Call 1 input; the LLM still writes the
sentence. The user's text, the cache key and the logs are unchanged, and it is still one LLM call.

Only words whose dialect meaning is well established are listed. A word that is also a standard word with another
meaning carries both meanings, and the LLM picks by context.
"""

import re

from app.ingestion.text_normalizer import normalize_text

_TOKEN = re.compile(r"[ঀ-৿]+")

HOW = "কীভাবে"
WHY = "কেন"
WHERE = "কোথায়"

GLOSSARY: dict[str, str] = {
    # question words — the ones the models got wrong most
    "কেমনে": HOW,
    "ক্যামনে": HOW,
    "কেম্নে": HOW,
    "কিলা": f"{HOW} (Sylhet)",
    "কিল্লাই": WHY,
    "কিয়ল্লাই": WHY,
    "ক্যান": WHY,
    "ক্যা": WHY,
    "ক্যারে": WHY,
    "ক্যানে": f"{WHY} (Rangpur/Rajshahi)",
    "কোনটে": WHERE,
    "কুনঠে": WHERE,
    "কুন্ঠে": WHERE,
    "কনে": f"{WHERE} (Khulna/Jashore; in standard Bangla কনে means bride)",
    "কই": f"{WHERE} (or, in some dialects, বলি = I say)",
    "কয়": "কত (or, in some dialects, বলে = says)",
    "কিতা": "কী",
    "কিয়া": "কী",
    # pronouns
    "আঁই": "আমি",
    "মুই": "আমি",
    "হামি": "আমি",
    "আঁর": "আমার",
    "মোর": "আমার",
    "হামার": "আমার",
    "আঁরে": "আমাকে",
    "মোরে": "আমাকে",
    "হামাক": "আমাকে",
    "আমারে": "আমাকে",
    "মোগো": "আমাদের",
    "আঙ্গো": "আমাদের",
    "হামরা": "আমরা",
    "আন্নে": "আপনি",
    "অনে": "আপনি",
    "আফনে": "আপনি",
    "আপনে": "আপনি",
    "হ্যায়": "সে",
    "হেয়": "সে",
    "হ্যারা": "তারা",
    "হেরা": "তারা",
    # negatives
    "ন": "না (negative placed before the verb, Chattogram/Noakhali)",
    "নায়": "না / -নি (negative, Sylhet)",
    # verbs
    "অইছে": "হয়েছে",
    "হইছে": "হয়েছে",
    "অইবো": "হবে",
    "অইলো": "হলো",
    "অইলে": "হলে",
    "আইসে": "এসেছে",
    "গরে": "করে (Chattogram)",
    "গরা": "করা (Chattogram)",
    "গরিবার": "করতে (Chattogram)",
    "গরি": "করি (Chattogram)",
    "দিয়ুম": "দেব",
    "কইবান": "বলবেন",
    "করবাম": "করব",
    "করুম": "করব",
    "করমু": "করব",
    "দিমু": "দেব",
    "পাইম": "পাব",
    "করতি": "করতে",
    "যাতি": "যেতে",
    "গেলি": "গেলে",
    "পাতি": "পেতে (Khulna; in standard Bangla পাতি means ordinary)",
    "করতিচে": "করছে",
    "লাগবেনে": "লাগবে",
    # other words
    "টেকা": "টাকা",
    "টাহা": "টাকা",
    "ট্যাহা": "টাকা",
    "অহন": "এখন",
    "আইজকা": "আজ",
    "লাইগা": "জন্য",
    "লাগি": "জন্য",
    "ইয়ান": "এটা",
    "ইটা": "এটা",
    "মাইনসে": "মানুষ",
    "মাইনসেরা": "মানুষেরা",
    "বুড়া": "বয়স্ক",
    "জাগা": "জায়গা / জমি",
    "জাগার": "জায়গার / জমির",
    # added 24 Nov: left untranslated in the 18-case dialect suite (data/evaluation/dialect_suite.json)
    "টেঁয়া": "টাকা",
    "টেহা": "টাকা",
    "কাইল": "গতকাল (past) / আগামীকাল (future)",
    "বিহাল": "বিকেল",
    "বিয়াল": "বিকেল",
    "গইল্যা": "গত (Chattogram)",
    "ডর": "ভয়",
    "নাগতেছে": "লাগছে",
    "এলা": "এখন (Rangpur)",
    "এলাও": "এখনো (Rangpur)",
    "সোয়ামি": "স্বামী",
    "জামাই": "স্বামী (in dialects; in standard Bangla also son-in-law)",
    "ছোঁয়া": "ছেলে (Rajshahi; in standard Bangla ছোঁয়া means touch)",
    "ছোঁয়াটা": "ছেলেটা (Rajshahi)",
    "একান": "একটা (Rangpur)",
    "ভাগি": "পালিয়ে (ভাগি গেছে = পালিয়ে গেছে)",
    "থিক্যা": "থেকে",
    "থেইক্যা": "থেকে",
    "থাইক্যা": "থেকে",
    "গেইয়ে": "গেছে (Chattogram)",
    "গইরজুম": "করব (Chattogram)",
    "হরে": "করে (Barishal)",
    "হরতে": "করতে (Barishal)",
    "হরছে": "করেছে (Barishal)",
    "হরার": "করার (Barishal)",
    "গাইলমন্দ": "গালমন্দ",
    "দেহি": "দেখি",
    "এহন": "এখন",
    "অখন": "এখন",
    "আছিল": "ছিল",
    "আছিলাম": "ছিলাম",
    "থানাত": "থানায়",
    "কইরবার": "করতে (Rangpur)",
    "কোনঠে": WHERE,
    "হব্যে": "হবে (Rajshahi)",
    "কহিতে": "বলতে",
}

# Chattogram words: with one of these, কেনে is "how" (Chattogram), not "why".
_CHATTOGRAM = {"আঁই", "আঁর", "আঁরে", "অনে", "গরে", "গরা", "গরি", "গরিবার", "ইয়ান", "দিয়ুম", "কইবান"}


_PAST_NEGATIVE = {"নাই", "নায়"}


def dialect_hints(text: str) -> list[tuple[str, str]]:
    words = _TOKEN.findall(normalize_text(text))
    seen: dict[str, str] = {}
    for prev, word in zip(words, words[1:], strict=False):
        # "দেয় নায়", "আইসে নাই": a verb followed by নাই/নায় is the past negative (দেয়নি, আসেনি), not "won't"/"doesn't"
        if word in _PAST_NEGATIVE and prev not in _PAST_NEGATIVE:
            seen[f"{prev} {word}"] = f"past negative: write {prev}'s standard verb with -নি (did not …)"
        # Chattogram/Noakhali "ন দিয়ে", "ন জানি": the negative comes before the verb
        if prev == "ন":
            seen[f"ন {word}"] = f"negative: {word} না / -নি (the user says it did not or does not happen)"
    for word in words:
        if word in seen:
            continue
        if word == "কেনে":
            seen[word] = HOW if _CHATTOGRAM & set(words) else f"{HOW} (Chattogram) or {WHY} (Rangpur)"
        elif word in GLOSSARY:
            seen[word] = GLOSSARY[word]
    return list(seen.items())


def with_hints(text: str) -> str:
    """The Call 1 input: the question, plus a glossary line when it has known dialect words."""
    hints = dialect_hints(text)
    if not hints:
        return text
    return text + "\n\nDialect hints (from a fixed glossary): " + "; ".join(f"{w} = {m}" for w, m in hints)
