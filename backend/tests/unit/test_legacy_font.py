import pytest

from app.ingestion.legacy_font_converter import convert_bijoy


@pytest.mark.parametrize(
    ("bijoy", "unicode_text"),
    [
        ("eq¯‹fvZv", "বয়স্কভাতা"),  # the known pair from docs/pipeline.md 7.2
        ("Avgvi", "আমার"),
        ("wkÿv", "শিক্ষা"),  # pre-base ি moved after শ
        ("‡Kv‡bv", "কোনো"),  # ে + া joined to ো
        ("cÖwZ", "প্রতি"),  # ra-phala, then pre-base ি
        ("Kg©x", "কর্মী"),  # reph moved before ম
        ("Kv‡h©i", "কার্যের"),  # reph across a pre-base vowel
        ("w¯Íi", "স্তির"),  # pre-base ি moves after the whole conjunct
        ("evsjv‡`k", "বাংলাদেশ"),
        ("1234", "১২৩৪"),
    ],
)
def test_known_pairs(bijoy: str, unicode_text: str) -> None:
    result = convert_bijoy(bijoy)
    assert result.text == unicode_text
    assert result.trustworthy


def test_unmapped_glyphs_are_reported() -> None:
    result = convert_bijoy("eq¯‹fvZv ÞÞÞ ßßß")
    assert result.unmapped_ratio > 0.02
    assert not result.trustworthy
