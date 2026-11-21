"""Pairs below were observed in the real bdlaws Labour Act PDFs (data/Workers — …)."""

import pytest

from app.ingestion.text_repair import looks_like_legacy_bijoy, repair_bangla


@pytest.mark.parametrize(
    ("broken", "fixed"),
    [
        ("প্রথম অধ্যাায়", "প্রথম অধ্যায়"),  # doubled া
        ("অনুযায়ীী", "অনুযায়ী"),  # doubled ী
        ("সৃৃষ্টি", "সৃষ্টি"),  # doubled ৃ
        ("দেয়ঃঃ-", "দেয়ঃ-"),  # doubled visarga
        ("ধৌৗতকরণ", "ধৌতকরণ"),  # stray au length mark
        ("বিক্র্রয়", "বিক্রয়"),  # doubled ra-phala
        ("রৰিত", "রক্ষিত"),  # Bijoy ৰ -> ক্ষ
        ("সার্বৰণিক", "সার্বক্ষণিক"),
        ("দরখাসত্দ", "দরখাস্ত"),  # Bijoy ত্দ
        ("সংক্রানত্দ", "সংক্রান্ত"),
        ("শুরম্ন", "শুরু"),  # Bijoy রম্ন
        ("উলিস্নখিত", "উল্লিখিত"),  # misplaced la-phala
        ("উলেস্নখ", "উল্লেখ"),
        ("সংশিস্নষ্ট", "সংশ্লিষ্ট"),
        ("অনত্দভর্ুক্ত", "অন্তর্ভুক্ত"),  # ত্দ + misplaced reph
        ("যে ক্ষে ত্রে বদলি", "যে ক্ষেত্রে বদলি"),  # stray space inside a word
        ("এর উদ্দে শ্যে,", "এর উদ্দেশ্যে,"),
        ("শ্রমিক রেজিস্টা র", "শ্রমিক রেজিস্টার"),
    ],
)
def test_repairs_observed_artefacts(broken: str, fixed: str) -> None:
    assert repair_bangla(broken) == fixed


@pytest.mark.parametrize(
    "clean",
    [
        "বাংলাদেশ শ্রম আইন, ২০০৬",
        "স্নান করিয়া",  # legitimate স্ন at word start is untouched
        "যে কোন প্রতিষ্ঠানে",
        "সে ক্ষেত্রে",
        "ক্ষতিপূরণ প্রদান করিবেন।",
    ],
)
def test_clean_text_is_unchanged(clean: str) -> None:
    assert repair_bangla(clean) == clean


def test_detects_bijoy_gibberish() -> None:
    assert looks_like_legacy_bijoy("eq¯‹fvZv cÖ`vb Kiv n‡e Ges Avek¨K KvMRcÎ RgvμvšÍ Kiæb")
    assert not looks_like_legacy_bijoy("বয়স্কভাতা প্রদান করা হইবে এবং প্রয়োজনীয় কাগজপত্র জমা দিতে হইবে")
    # plain English pages (common in government PDFs) must not be "converted"
    assert not looks_like_legacy_bijoy(
        "Section 1. The Government may, by notification in the official Gazette, make rules."
    )
    assert not looks_like_legacy_bijoy("Ministry of Law, Justice and Parliamentary Affairs — “Copyright” notice, 2019.")
