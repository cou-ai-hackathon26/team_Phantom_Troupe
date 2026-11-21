"""Repair rendering artefacts in Bangla text extracted from PDFs.

Two sources of damage, both seen in the bdlaws.minlaw.gov.bd print PDFs:
1. Browser print-to-PDF duplicates dependent vowel signs ("অধ্যাায়", "সৃৃষ্টি", "ঃঃ").
2. Leftovers from an old Bijoy -> Unicode conversion on the source site ("ৰমতা", "দরখাসত্দ").

Every rule here fixes a sequence that is invalid or never occurs in correct Bangla, so applying it
to clean text is a no-op. Rules were derived from the real corpus; see tests/unit/test_text_repair.py.
"""

import re

_CONS = "\u0995-\u09b9\u09dc\u09dd\u09df"  # ক–হ, ড়, ঢ়, য়
_VOWEL_SIGNS = "\u09be-\u09cc\u09d7"  # া … ৌ, ৗ
_HASANTA = "\u09cd"

_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # ৌ followed by a stray au length mark
    (re.compile("\u09cc\u09d7"), "\u09cc"),
    # doubled dependent vowel sign / visarga / chandrabindu: "াা" -> "া", "ঃঃ" -> "ঃ"
    (re.compile(f"([{_VOWEL_SIGNS}\u0981\u0983])\\1+"), r"\1"),
    # doubled ra-phala: "ক্র্রয়" -> "ক্রয়"
    (re.compile("(\u09cd\u09b0)\\1+"), r"\1"),
    # Bijoy leftovers
    (re.compile("\u09f0"), "\u0995\u09cd\u09b7"),  # ৰ -> ক্ষ   (রৰিত -> রক্ষিত)
    (re.compile(f"([{_CONS}])\u09a4\u09cd\u09a6"), "\\1\u09cd\u09a4"),  # সত্দ -> স্ত
    (re.compile("\u09a8\u09cd\u09a4\u09cd\u09ae"), "\u09a8\u09cd\u09a4"),  # ন্ত্ম -> ন্ত
    (re.compile("\u09b0\u09ae\u09cd\u09a8"), "\u09b0\u09c1"),  # রম্ন -> রু   (শুরম্ন -> শুরু)
    (re.compile("\u09c1\u09cd\u09af"), "\u09cd\u09af\u09c1"),  # ু্য -> ্যু
    (re.compile("\u09a4\u09cd\u09aa"), "\u09ce\u09aa"),  # ত্প -> ৎপ
    # misplaced la-phala:  লিস্ন -> ল্লি, সংশিস্নষ্ট -> সংশ্লিষ্ট
    (re.compile(f"([{_CONS}])([\u09bf\u09c7\u09c8])\u09b8\u09cd\u09a8"), "\\1\u09cd\u09b2\\2"),
    # misplaced reph: consonant + র্ + vowel sign  ->  র্ + consonant + vowel sign (ভর্ু -> র্ভু)
    (re.compile(f"([{_CONS}])\u09b0{_HASANTA}([{_VOWEL_SIGNS}])"), "\u09b0\u09cd\\1\\2"),
    # words split by a stray space on old bdlaws pages: "ক্ষে ত্রে", "উদ্দে শ্যে", "রেজিস্টা র", "রক্ষি ত".
    # Both halves are non-words; the tail is only joined when the word ends there.
    (
        re.compile('(ক্ষে|দ্দে|স্টা|ক্ষি) (ত্রে|ত্র|শ্যে|শ্য|রে|র|ত)(?=[\\s,।;:)\\-"”’]|$)'),
        r"\1\2",
    ),
)


def repair_bangla(text: str) -> str:
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text


# Bijoy/SutonnyMJ text extracted without conversion is mostly Latin letters plus these symbols.
_BIJOY_MARKERS = set("¯©‡ÖÕ†¨Ô–¨")


def looks_like_legacy_bijoy(text: str, min_chars: int = 40) -> bool:
    letters = [c for c in text if not c.isspace() and not c.isdigit()]
    if len(letters) < min_chars:
        return False
    bangla = sum(1 for c in letters if "\u0980" <= c <= "\u09ff")
    markers = sum(1 for c in letters if c in _BIJOY_MARKERS)
    latin = sum(1 for c in letters if c.isascii() and c.isalpha())
    return bangla / len(letters) < 0.1 and (markers >= 3 or latin / len(letters) > 0.5)
