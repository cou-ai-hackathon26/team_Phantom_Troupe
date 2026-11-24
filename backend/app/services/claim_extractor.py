"""Deterministic claim extraction: fees/amounts, time limits, age limits and validity periods in passages.

No LLM: patterns over the passage text give a number, its unit, the exact sentence and its position, so every
claim cites the original passage. A number is classified only by cue words in its own clause or sentence
(ফি, ভাতা, জরিমানা, আয়, বয়স, মেয়াদ, মধ্যে …); without a cue it is not a claim. Context words (applicant,
variant, place, period, programme, min/max) are recorded so that claims are compared only in the same context.
Garbled text (digits split by spaces in compiled guides, OCR digit soup, ranges) gives low-confidence claims
that are never compared. Required-document claims come from Call 2 with a verified quote (conflict_disclosure).
"""

import re
import unicodedata
from collections.abc import Iterator, Mapping

from app.ingestion.text_normalizer import bn_to_ascii_digits
from app.schemas.conflict import Claim, ClaimKind
from app.services.citation_validator import BN_NUMBER_WORDS
from app.services.retrieval_service import programmes_named

QUOTE_CHARS = 260
NOISE_DIGIT_SHARE = 0.3  # a sentence that is mostly digits is a garbled table


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(unicodedata.normalize("NFC", pattern), re.IGNORECASE)


_D = "[0-9০-৯]"
_NUM = rf"((?:{_D}{{1,3}}(?:,{_D}{{2,3}})+|{_D}+)(?:\.{_D}{{1,2}})?)(?![0-9০-৯])"
_WORDS = "|".join(sorted((unicodedata.normalize("NFC", w) for w in BN_NUMBER_WORDS), key=len, reverse=True))
_WORD_VALUE = {unicodedata.normalize("NFC", w): v for w, v in BN_NUMBER_WORDS.items()}

AMOUNT = _p(rf"(?<![0-9০-৯.,]){_NUM}\s*(হাজার)?\s*(?:/-)?\s*(?:টাকা|৳|tk\.?|taka)|(?:৳|tk\.?)\s*{_NUM}")
DURATION = _p(
    rf"(?:(?<![0-9০-৯.,]){_NUM}|(?<!\S)({_WORDS}))\s*"
    r"(কার্যদিবস|কর্মদিবস|working\s+days?|দিন|days?|মাস(?!িক)|months?|বছর|বৎসর|years?|ঘণ্টা|ঘন্টা|hours?)"
)

UNITS: list[tuple[re.Pattern[str], str]] = [
    (_p(r"কার্যদিবস|কর্মদিবস|working"), "working_day"),
    (_p(r"দিন|day"), "day"),
    (_p(r"মাস|month"), "month"),
    (_p(r"বছর|বৎসর|year"), "year"),
    (_p(r"ঘণ্টা|ঘন্টা|hour"), "hour"),
]
AMOUNT_CATEGORIES: list[tuple[str, re.Pattern[str]]] = [  # first match wins
    ("fine", _p(r"জরিমানা|অর্থদণ্ড|অর্থদন্ড|\bfine\b")),
    ("tax", _p(r"উন্নয়ন কর|খাজনা|করের হার|কর বাবদ|ভ্যাট|\btax\b|\bvat\b")),
    ("income_limit", _p(r"আয়|\bincome\b")),
    ("allowance_amount", _p(r"ভাতা|আর্থিক সহায়তা|অনুদান|বৃত্তি|\ballowance\b|\bstipend\b")),
    ("application_fee", _p(r"ফি|ফিস|মাশুল|চার্জ|খরচ|সেবা মূল্য|\bfees?\b|\bcharges?\b")),
]
BUDGET = _p(r"বাজেট|বরাদ্দ|\bbudget\b")
PENALTY_TERM = _p(r"কারাদণ্ড|কারাদন্ড|দণ্ডিত|দন্ডিত|জেল|imprisonment")
AGE = _p(r"বয়স|\bage\b|\baged\b")
VALIDITY = _p(r"মেয়াদ|বৈধ|\bvalid")
DEADLINE = _p(r"মধ্যে|সময়|নিষ্পত্তি|সম্পন্ন|অনধিক|\bwithin\b|\bdays? of\b")
BOUND_MIN = _p(r"ন্যূনতম|সর্বনিম্ন|অন্তত|কমপক্ষে|ঊর্ধ্ব|উর্ধ্ব|তদূর্ধ্ব|\bat least\b|\bminimum\b|\babove\b")
BOUND_MAX = _p(r"সর্বোচ্চ|অনধিক|অনূর্ধ্ব|অতিক্রম না|অধিক নয়|বেশি নয়|এর কম|\bat most\b|\bmaximum\b|\bnot exceeding\b")
# a statement about the past ("ছিল", "সে সময়ে", "প্রাথমিকভাবে … আনা হয়"): a historical figure, not a current rule
HISTORICAL = _p(
    r"ছিল|ছিলো|সে সময়|সেসময়|শুরুতে|প্রাথমিকভাবে|প্রথম পর্যায়ে|চালু করা হয়|চালু হয়|আওতায় আনা হয়|প্রবর্তিত হয়"
    r"|\bwas\b|\bwere\b|\binitially\b"
)
PERIOD_LOOKBACK_CHARS = 160  # a year just before a line break belongs to the next line ("২০২৬-২৭\nঅর্থবছরে …")
CONDITIONAL = _p(r"যদি|তবে|শর্ত|ব্যতীত|ছাড়া|\bprovided\b|\bunless\b|\bexcept\b")

CONTEXT_CUES: dict[str, dict[str, re.Pattern[str]]] = {
    "applicant": {
        "male": _p(r"পুরুষ|\bmale\b|\bmen\b"),
        "female": _p(r"মহিলা|নারী|\bfemale\b|\bwomen\b"),
        "disabled": _p(r"প্রতিবন্ধী|\bdisab"),
        "child": _p(r"শিশু|\bchild"),
        "worker": _p(r"শ্রমিক|\bworker"),
        "freedom_fighter": _p(r"মুক্তিযোদ্ধা"),
        "student": _p(r"ছাত্র|শিক্ষার্থী|\bstudent"),
        "expatriate": _p(r"প্রবাসী"),
    },
    "variant": {
        "urgent": _p(r"জরুরি|জরুরী|\burgent\b|\bexpress\b"),
        "regular": _p(r"সাধারণ|নিয়মিত|\bregular\b|\bnormal\b"),
        "online": _p(r"অনলাইন|\bonline\b"),
        "manual": _p(r"ম্যানুয়াল|\bmanual\b"),
        "renewal": _p(r"নবায়ন|\brenewal\b"),
        "duplicate": _p(r"ডুপ্লিকেট|\bduplicate\b"),
        "correction": _p(r"সংশোধন|\bcorrection\b"),
    },
    "location": {
        "city": _p(r"সিটি কর্পোরেশন|মহানগর|\bcity corporation\b"),
        "municipality": _p(r"পৌরসভা|\bmunicipal"),
        "union": _p(r"ইউনিয়ন|\bunion parishad\b"),
        "rural": _p(r"গ্রাম|পল্লী|\brural\b"),
    },
}
FISCAL_YEAR = re.compile(r"(?<![0-9])((?:19|20)[0-9]{2})\s*[-–/]\s*([0-9]{2}|(?:19|20)[0-9]{2})(?![0-9])")
CALENDAR_YEAR = _p(r"(?<![0-9])((?:19|20)[0-9]{2})\s*(?:সালে|সাল থেকে|সাল হতে|সাল হইতে|খ্রিস্টাব্দ|খ্রিষ্টাব্দ|খ্রি)")
_SENTENCE = re.compile(r"[^।!?|\n;]+[।!?|;]?")
_CLAUSE_BREAK = _p(r"[,;]|\sএবং\s")


def _number(raw: str) -> float:
    return float(bn_to_ascii_digits(raw).replace(",", ""))


def _sentences(text: str) -> Iterator[tuple[int, str]]:
    for m in _SENTENCE.finditer(text):
        if m.group(0).strip():
            yield m.start(), m.group(0)


def _clause(sentence: str, start: int, end: int) -> str:
    left = max((m.end() for m in _CLAUSE_BREAK.finditer(sentence, 0, start)), default=0)
    right = next((m.start() for m in _CLAUSE_BREAK.finditer(sentence, end)), len(sentence))
    return sentence[left:right]


def context_cues(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for dimension, cues in CONTEXT_CUES.items():
        found = sorted(name for name, pattern in cues.items() if pattern.search(text))
        if dimension == "applicant" and {"male", "female"} <= set(found):
            found = [f for f in found if f not in ("male", "female")]  # "men and women" = everyone
        if found:
            out[dimension] = found
    return out


def _periods(sentence: str) -> list[str]:
    ascii_text = bn_to_ascii_digits(sentence)
    out = set()
    for m in FISCAL_YEAR.finditer(ascii_text):
        first, second = int(m.group(1)), m.group(2)
        nxt = int(second) if len(second) == 4 else (first // 100) * 100 + int(second)
        if nxt == first + 1:
            out.add(f"FY{first}-{str(nxt)[-2:]}")
    out.update(m.group(1) for m in CALENDAR_YEAR.finditer(ascii_text))
    return sorted(out)


def _noisy(sentence: str) -> bool:
    compact = sentence.replace(" ", "")
    digits = sum(ch.isdigit() for ch in compact)
    return "...." in sentence or (len(compact) > 0 and digits / len(compact) > NOISE_DIGIT_SHARE)


def _suspicious_number(sentence: str, start: int) -> bool:
    """A digit right before the number (with one space: "৭০ ০ টাকা" in compiled guides) or a range ("১০-১৫")."""
    before = sentence[max(0, start - 2) : start]
    return bool(re.search(r"[0-9০-৯]\s$|[-–]\s*$", before))


def _amount_category(clause: str, sentence: str) -> str | None:
    if BUDGET.search(clause):
        return None  # programme budgets ("৫২৩৯.২৫ কোটি টাকা") are not amounts a citizen pays or gets
    for text in (clause, sentence):
        for category, pattern in AMOUNT_CATEGORIES:
            if pattern.search(text):
                return category
    return None


def _duration_category(clause: str, sentence: str, unit: str) -> str | None:
    for text in (clause, sentence):
        if PENALTY_TERM.search(text):
            return None  # prison terms in penal sections are not service timelines
        if AGE.search(text):
            return "age_limit" if unit == "year" else None
        if VALIDITY.search(text):
            return "validity"
        if DEADLINE.search(text):
            return "deadline"
    return None


KIND_OF: dict[str, ClaimKind] = {
    "fine": "fee",
    "tax": "fee",
    "allowance_amount": "fee",
    "application_fee": "fee",
    "income_limit": "eligibility",
    "age_limit": "eligibility",
    "deadline": "processing_time",
    "validity": "validity_period",
}


def _bound(clause: str) -> str | None:
    is_min, is_max = bool(BOUND_MIN.search(clause)), bool(BOUND_MAX.search(clause))
    return "min" if is_min and not is_max else "max" if is_max and not is_min else None


def _quote(sentence: str, start: int, end: int) -> str:
    flat = sentence.strip()
    if len(flat) <= QUOTE_CHARS:
        return " ".join(flat.split())
    lo = max(0, start - QUOTE_CHARS // 2)
    return "… " + " ".join(sentence[lo : lo + QUOTE_CHARS].split()) + " …"


def extract_claims(labelled: Mapping[str, object], programmes: Mapping[str, str] | None = None) -> list[Claim]:
    """Claims in every official and web passage of the prompt (personal-document passages are skipped)."""
    claims: list[Claim] = []
    for label, chunk in labelled.items():
        if getattr(chunk, "kind", "official") == "user":
            continue
        document_id = getattr(chunk, "document_id", None) or getattr(chunk, "id", label)
        doc_programme = (programmes or {}).get(document_id)
        text = unicodedata.normalize("NFC", getattr(chunk, "text", ""))
        for offset, sentence in _sentences(text):
            noisy = _noisy(sentence)
            periods = _periods(sentence) or _periods(text[max(0, offset - PERIOD_LOOKBACK_CHARS) : offset])
            if not periods and HISTORICAL.search(sentence):
                periods = ["historical"]
            conditional = bool(CONDITIONAL.search(sentence))
            for m, is_amount in [
                *((m, True) for m in AMOUNT.finditer(sentence)),
                *((m, False) for m in DURATION.finditer(sentence)),
            ]:
                clause = _clause(sentence, m.start(), m.end())
                if is_amount:
                    raw = m.group(1) or m.group(3)
                    value = _number(raw) * (1000 if m.group(2) else 1)
                    unit, category = "BDT", _amount_category(clause, sentence)
                else:
                    raw = m.group(1) or m.group(2)
                    value = _number(raw) if m.group(1) else float(_WORD_VALUE.get(raw, 0))
                    unit = next(u for pattern, u in UNITS if pattern.search(m.group(3)))
                    category = _duration_category(clause, sentence, unit)
                if category is None or value <= 0:
                    continue
                context = context_cues(clause) or context_cues(sentence)
                programme = programmes_named(clause) or programmes_named(sentence)
                if not programme and doc_programme:
                    programme = {doc_programme}
                if programme:
                    context = {**context, "programme": sorted(programme)}
                if periods:
                    context = {**context, "period": periods}
                claims.append(
                    Claim(
                        id=f"{label}:{offset + m.start()}",
                        kind=KIND_OF[category],
                        category=category,
                        value=value,
                        unit=unit,
                        bound=_bound(clause),
                        original_text=" ".join(m.group(0).split()),
                        quote=_quote(sentence, m.start(), m.end()),
                        label=label,
                        chunk_id=getattr(chunk, "id", label),
                        document_id=document_id,
                        section=getattr(chunk, "section", None),
                        page=getattr(chunk, "page_start", None),
                        context=context,
                        conditional=conditional,
                        confidence="low" if noisy or _suspicious_number(sentence, m.start()) else "high",
                    )
                )
    return claims
