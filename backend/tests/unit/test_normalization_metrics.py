"""Checks used by scripts/eval_normalization.py (no LLM involved)."""

from app.evaluation.normalization_metrics import dialect_leftovers, has_negation, missing_terms, person_ok


def test_negation_words_and_attached_ni() -> None:
    assert has_negation("মালিক বেতন দিচ্ছে না, এখন কী করব?")
    assert has_negation("বাবার ভাতার টাকা কেন আসেনি?")
    assert has_negation("মালিক ছুটি দেয়নি।")
    assert has_negation("এ বিষয়ে কোনো নিয়ম নেই?")


def test_whether_and_ni_nouns_are_not_negative() -> None:
    assert not has_negation("আমার জমির নামজারি হয়েছে কি না, কীভাবে বুঝব?")
    assert not has_negation("নামজারি হয়েছে কিনা কীভাবে বুঝব?")
    assert not has_negation("খাজনা অনলাইনে দেওয়া যায় কি?")
    assert not has_negation("কোম্পানি কি শুনানি ছাড়া ছাঁটাই করতে পারে?")
    assert not has_negation("আপনি কি বলতে পারবেন, জিডি করতে কী লাগে?")


def test_person() -> None:
    assert person_ok("first", "আমার জমির খতিয়ান কীভাবে তুলব?")
    assert not person_ok("first", "আপনার জমির খতিয়ান কীভাবে তুলবেন?")
    assert person_ok("first", "এখন কী করব?")  # first-person verb, no pronoun
    assert person_ok("second", "আপনি কি বলতে পারবেন, জিডি করতে কী লাগে?")
    assert not person_ok("second", "আমি কি বলতে পারব?")
    assert person_ok("none", "যেকোনো লেখা")


def test_dialect_leftovers_and_terms() -> None:
    assert dialect_leftovers("আমার জমির নামজারি অইছে কিনা কেমনে বুঝুম?") == ["অইছে", "কেমনে", "বুঝুম"]
    assert dialect_leftovers("আমার জমির নামজারি হয়েছে কি না, কীভাবে বুঝব?") == []
    assert missing_terms(["নামজারি", "বয়স্ক ভাতা"], "নামজারি কীভাবে করব?") == ["বয়স্ক ভাতা"]
