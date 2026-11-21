import unicodedata

from app.ingestion.text_normalizer import (
    ascii_to_bn_digits,
    bn_to_ascii_digits,
    normalize_for_search,
    normalize_text,
    tokenize,
)


def test_nfc_unifies_nukta_forms() -> None:
    precomposed = "ড়"  # ড়
    decomposed = "ড়"  # ড + ়
    assert normalize_text(precomposed) == normalize_text(decomposed)
    assert normalize_text("য়") == normalize_text("য়")  # য়


def test_khanda_ta_and_old_danda() -> None:
    assert normalize_text("উৎ") == normalize_text("উত্‍")
    assert normalize_text("হইবে৷") == "হইবে।"


def test_whitespace_collapsed_but_lines_kept() -> None:
    assert normalize_text("  এক  দুই \n\n\n\nতিন  ") == "এক দুই\n\nতিন"


def test_digit_maps_round_trip() -> None:
    assert bn_to_ascii_digits("ধারা ১২৩") == "ধারা 123"
    assert ascii_to_bn_digits("123") == "১২৩"


def test_search_form_strips_zero_width_and_maps_digits() -> None:
    assert normalize_for_search("ধারা‌ ১২৩ Section") == "ধারা 123 section"


def test_tokenizer_drops_punctuation_and_danda() -> None:
    tokens = tokenize("১২৩। (১) মজুরী, ছুটি; “শ্রমিক”-এর অধিকার।")
    assert tokens == ["123", "1", "মজুরী", "ছুটি", "শ্রমিক", "এর", "অধিকার"]


def test_tokenizer_matches_bangla_and_ascii_section_numbers() -> None:
    assert tokenize("ধারা ১২৩") == tokenize("ধারা 123")


def test_output_is_nfc() -> None:
    out = normalize_text("কাগজপত্র")
    assert unicodedata.is_normalized("NFC", out)
