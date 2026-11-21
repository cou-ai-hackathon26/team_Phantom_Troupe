"""Bijoy / SutonnyMJ (ASCII-encoded legacy Bangla font) -> Unicode.

Old government PDFs often use SutonnyMJ: the text layer holds Latin letters and symbols that the font
draws as Bangla ("eq¯‹fvZv" is "বয়স্কভাতা"). Conversion:
  1. longest-match mapping of glyph codes to Unicode (table below),
  2. move pre-base vowel signs (ি ে ৈ, typed before the consonant) after their consonant cluster,
  3. move reph (র্, typed after the cluster) before it,
  4. NFC (joins ে+া -> ো, ে+ৗ -> ৌ) and the corpus post-fix rules in text_repair.

The table covers letters, vowel signs, phalas, reph and common conjuncts. It is NOT exhaustive: every
conversion reports leftover unmapped characters, and pages above UNMAPPED_THRESHOLD should be OCR'd or
reviewed instead (see convert_page). Extend the table only from spot-checks against real page images.
"""

import re
import unicodedata
from dataclasses import dataclass

from app.ingestion.text_repair import repair_bangla

UNMAPPED_THRESHOLD = 0.02  # >2% leftover legacy glyph codes -> do not trust the conversion

REPH = "\x00REPH\x00"

# Multi-character sequences first (longest match wins), then single characters.
BIJOY_MAP: dict[str, str] = {
    # independent vowels
    "Av": "আ", "A": "অ", "B": "ই", "C": "ঈ", "D": "উ", "E": "ঊ", "F": "ঋ", "G": "এ", "H": "ঐ", "I": "ও", "J": "ঔ",
    # consonants
    "K": "ক", "L": "খ", "M": "গ", "N": "ঘ", "O": "ঙ", "P": "চ", "Q": "ছ", "R": "জ", "S": "ঝ", "T": "ঞ",
    "U": "ট", "V": "ঠ", "W": "ড", "X": "ঢ", "Y": "ণ", "Z": "ত", "_": "থ", "`": "দ", "a": "ধ", "b": "ন",
    "c": "প", "d": "ফ", "e": "ব", "f": "ভ", "g": "ম", "h": "য", "i": "র", "j": "ল", "k": "শ", "l": "ষ",
    "m": "স", "n": "হ", "o": "ড়", "p": "ঢ়", "q": "য়", "r": "ৎ",
    # signs
    "s": "ং", "t": "ঃ", "u": "ঁ", "&": "্",
    # dependent vowel signs (‡ ‰ w are pre-base: typed before the consonant)
    "v": "া", "w": "ি", "x": "ী", "y": "ু", "z": "ু", "~": "ূ", "„": "ৃ", "‡": "ে", "‰": "ৈ", "Š": "ৗ",
    # phalas and reph
    "Ö": "্র", "ª": "্র", "¨": "্য", "^": "্ব", "©": REPH,
    # conjuncts / half forms
    "ÿ": "ক্ষ", "°": "ক্ক", "³": "ক্ত", "·": "ক্স",
    "¯‹": "স্ক", "¯Í": "স্ত", "¯’": "স্থ", "¯§": "স্ম", "¯œ": "স্ন", "¯^": "স্ব", "¯": "স্",
    "š—": "ন্ত", "š": "ন্", "Í": "্ত", "—": "্ত", "‹": "্ক", "’": "্থ", "§": "্ম", "œ": "্ন",
    "¼": "ঙ্ক", "½": "ঙ্গ", "¾": "চ্চ", "¿": "চ্ছ", "Á": "জ্জ", "Â": "জ্ঞ", "Ä": "ঞ্চ", "Æ": "ঞ্জ",
    "È": "ট্ট", "É": "ড্ড", "Ê": "ণ্ট", "Ë": "ণ্ঠ", "Ì": "ণ্ড", "Î": "ত্ত", "Ï": "ত্থ",
    # punctuation and digits
    "|": "।", "Ò": "“", "Ó": "”", "Ô": "‘", "Õ": "’",
    "0": "০", "1": "১", "2": "২", "3": "৩", "4": "৪", "5": "৫", "6": "৬", "7": "৭", "8": "৮", "9": "৯",
}  # fmt: skip

_KEYS = sorted(BIJOY_MAP, key=len, reverse=True)
_TOKEN = re.compile("|".join(re.escape(k) for k in _KEYS))

_PRE_BASE = {"ি", "ে", "ৈ"}
_CONSONANTS = set("কখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহড়ঢ়য়ৎ")
_HASANTA = "্"


def _is_cluster_part(token: str) -> bool:
    """Consonant, conjunct ("ক্ষ") or phala ("্র") token — anything that belongs to a consonant cluster."""
    return bool(token) and (token[0] in _CONSONANTS or token.startswith(_HASANTA))


def _tokenize(text: str) -> tuple[list[str], int]:
    tokens: list[str] = []
    unmapped = 0
    pos = 0
    for m in _TOKEN.finditer(text):
        for ch in text[pos : m.start()]:  # characters with no mapping pass through
            tokens.append(ch)
            if not ch.isspace() and not ("ঀ" <= ch <= "৿") and ch not in ".,;:!?()[]-/'\"%":
                unmapped += 1
        tokens.append(BIJOY_MAP[m.group(0)])
        pos = m.end()
    for ch in text[pos:]:
        tokens.append(ch)
        if not ch.isspace() and not ("ঀ" <= ch <= "৿") and ch not in ".,;:!?()[]-/'\"%":
            unmapped += 1
    return tokens, unmapped


def _joins(prev: str, nxt: str) -> bool:
    """Two cluster tokens belong to one consonant cluster only when joined by a hasanta."""
    return prev.endswith(_HASANTA) or nxt.startswith(_HASANTA)


def _cluster_end(tokens: list[str], start: int) -> int:
    """Index just past the consonant cluster that starts at `start`."""
    j = start + 1
    while j < len(tokens) and _is_cluster_part(tokens[j]) and _joins(tokens[j - 1], tokens[j]):
        j += 1
    return j


def _move_pre_base_vowels(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _PRE_BASE and i + 1 < len(tokens) and _is_cluster_part(tokens[i + 1]):
            j = _cluster_end(tokens, i + 1)
            out.extend(tokens[i + 1 : j])
            out.append(tok)
            i = j
        else:
            out.append(tok)
            i += 1
    return out


def _move_reph(tokens: list[str]) -> list[str]:
    out: list[str] = []
    for tok in tokens:
        if tok != REPH:
            out.append(tok)
            continue
        k = len(out)
        while k > 0 and not _is_cluster_part(out[k - 1]) and out[k - 1] not in (" ", "\n"):
            k -= 1  # skip vowel signs already placed after the cluster
        if k > 0 and _is_cluster_part(out[k - 1]):
            k -= 1
            while k > 0 and _is_cluster_part(out[k - 1]) and _joins(out[k - 1], out[k]):
                k -= 1
        out.insert(k, "র্")
    return out


@dataclass
class Conversion:
    text: str
    unmapped_ratio: float

    @property
    def trustworthy(self) -> bool:
        return self.unmapped_ratio <= UNMAPPED_THRESHOLD


def convert_bijoy(text: str) -> Conversion:
    tokens, unmapped = _tokenize(text)
    tokens = _move_reph(_move_pre_base_vowels(tokens))
    out = unicodedata.normalize("NFC", "".join(tokens))
    out = repair_bangla(out)
    visible = sum(1 for ch in text if not ch.isspace()) or 1
    return Conversion(text=out, unmapped_ratio=unmapped / visible)
