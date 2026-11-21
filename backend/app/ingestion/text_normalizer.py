"""Bangla text normalization (used at ingestion AND query time) and the BM25 tokenizer.

Two levels:
- normalize_text(): display-safe. NFC, unify equivalent code-point sequences, tidy whitespace.
- normalize_for_search(): additionally strips zero-width joiners and maps Bangla digits to ASCII,
  so "ধারা ১২৩" and "ধারা 123" match. Original text is always kept separately for display.
"""

import re
import unicodedata

BN_DIGITS = "০১২৩৪৫৬৭৮৯"
_BN_TO_ASCII = str.maketrans(BN_DIGITS, "0123456789")
_ASCII_TO_BN = str.maketrans("0123456789", BN_DIGITS)

_ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
_SPACES = re.compile(r"[ \t  -   　]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")

# Equivalent spellings that NFC does not unify on its own.
_EQUIVALENTS = (
    ("ত্‍", "ৎ"),  # ত + ্ + ZWJ  -> ৎ (khanda ta)
    ("অা", "আ"),  # অ + া -> আ (seen in some PDF extractions)
    ("৷", "।"),  # ৷ (currency numerator four, used as danda on old bdlaws pages) -> ।
)

# BM25: strip punctuation (incl. Bangla danda) but keep Bangla letters/marks, ASCII letters and digits.
_PUNCT = re.compile(r"[^\wঀ-৿]+", re.UNICODE)


def bn_to_ascii_digits(text: str) -> str:
    return text.translate(_BN_TO_ASCII)


def ascii_to_bn_digits(text: str) -> str:
    return text.translate(_ASCII_TO_BN)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for src, dst in _EQUIVALENTS:
        text = text.replace(src, dst)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    return _MANY_NEWLINES.sub("\n\n", text).strip()


def normalize_for_search(text: str) -> str:
    text = normalize_text(text)
    text = _ZERO_WIDTH.sub("", text)
    text = bn_to_ascii_digits(text)
    return text.lower()


def tokenize(text: str) -> list[str]:
    """BM25 tokenizer: normalize -> drop punctuation (incl. '।') -> whitespace split."""
    text = normalize_for_search(text).replace("।", " ").replace("॥", " ")
    text = _PUNCT.sub(" ", text)
    return [tok for tok in text.split() if tok and tok != "_"]
