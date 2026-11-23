"""Checks for Call 1 (dialect -> standard Bangla) that need no hand-written expected text.

Each test case is labelled with properties of the *question* (does it contain a negative, which grammatical
person, which terms must survive); these functions check the rewrite against them. The rewrite itself is
printed for a human to judge — these checks catch the dangerous failures (meaning reversed, "I" turned into
"you", dialect words left behind), not style.
"""

import re
from collections.abc import Sequence

from app.ingestion.text_normalizer import normalize_for_search

_TOKEN = re.compile(r"[ঀ-৿A-Za-z]+")
_WHETHER = re.compile(r"কি\s*না|কিনা")  # "whether" — contains না but is not a negative

NEGATIVE_WORDS = {"না", "নাই", "নেই", "নয়", "নি"}
# Pronouns and nouns that end in -নি and are not the negative suffix (পাইনি, করেনি, দেয়নি).
NOT_NEGATIVE_NI = {
    "আপনি",
    "তিনি",
    "উনি",
    "ইনি",
    "যিনি",
    "কোম্পানি",
    "পানি",
    "শুনানি",
    "জননী",
    "রানি",
    "রাণী",
    "কাহিনি",
    "খুনি",
    "বাণী",
    "ধ্বনি",
    "খনি",
}

FIRST_PERSON = {"আমি", "আমার", "আমাকে", "আমায়", "আমরা", "আমাদের", "আমাদেরকে"}
SECOND_PERSON = {"আপনি", "আপনার", "আপনাকে", "তুমি", "তোমার", "তোমাকে", "তুই", "তোর"}

# Words that belong to regional dialects only; none should survive in standard Bangla.
DIALECT_WORDS = {
    "অইছে",
    "অইবো",
    "অইলো",
    "অইলে",
    "অই",
    "হইছে",
    "হইবো",
    "কেমনে",
    "ক্যামনে",
    "কেম্নে",
    "কিলা",
    "বুঝুম",
    "করুম",
    "করমু",
    "দিমু",
    "যামু",
    "খামু",
    "তুলমু",
    "দিয়ুম",
    "পাইম",
    "করবাম",
    "পাইবাম",
    "টেকা",
    "টাহা",
    "ট্যাহা",
    "কিতা",
    "কিল্লাই",
    "আঁই",
    "আঁর",
    "আঁরে",
    "মুই",
    "মোর",
    "মোগো",
    "হামি",
    "হামার",
    "হামাক",
    "আন্নে",
    "অনে",
    "আফনে",
    "হ্যারা",
    "হ্যায়",
    "কোনটে",
    "কুনঠে",
    "লাইগা",
    "লাগি",
    "লাই",
    "লাগবো",
    "লাগবেনে",
    "দেওন",
    "করন",
    "যাওন",
    "অহন",
    "ক্যারে",
    "ক্যা",
    "ক্যানে",
    "কেনে",
    "নায়",
    "ইটা",
    "ইয়ান",
    "পাইবো",
    "দিবো",
    "পাইবার",
    "গরে",
    "গরিবার",
    "কইবান",
    "গেলছে",
    "হয়্যা",
    "করতিচে",
    "করতি",
    "যাতি",
    "গেলি",
    "হারায়া",
    "হারাই",
    "ধইরা",
    "নিয়া",
    "দিয়া",
    "কাম",
    "করাইতে",
    "আইসে",
    "আইজকা",
    "আছন",
    "জাগার",
    "বাপর",
    "মাইনসেরা",
    "কইরতে",
    "গেইলে",
}


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def has_negation(text: str) -> bool:
    """A negative word (না, নাই, নেই, নয়) or the attached past negative -নি (পাইনি, দেয়নি); "কি না" is not one."""
    for tok in tokens(_WHETHER.sub(" ", text)):
        if tok in NEGATIVE_WORDS:
            return True
        if len(tok) > 2 and tok.endswith("নি") and tok not in NOT_NEGATIVE_NI:
            return True
    return False


def person_ok(person: str, text: str) -> bool:
    """The speaker is not swapped: "I/my" never becomes only "you", and "you" never becomes only "I".
    (A first-person verb without a pronoun, e.g. "কী করব?", is fine; leftover dialect pronouns are caught
    by dialect_leftovers.)"""
    words = set(tokens(text))
    first, second = bool(words & FIRST_PERSON), bool(words & SECOND_PERSON)
    if person == "first":
        return first or not second
    if person == "second":
        return second or not first
    return True


def dialect_leftovers(text: str) -> list[str]:
    return sorted(set(tokens(text)) & DIALECT_WORDS)


def missing_terms(terms: Sequence[str], text: str) -> list[str]:
    """Terms not found in the text; "a|b" is satisfied by either spelling or phrasing."""
    norm = normalize_for_search(text)
    return [t for t in terms if not any(normalize_for_search(alt) in norm for alt in t.split("|"))]
