"""Dialect glossary added to the Call 1 input (no LLM involved)."""

import pytest

from app.schemas.llm import NormalizeOutput
from app.services.dialect_hints import dialect_hints, with_hints
from app.services.query_normalizer import normalize_query
from tests.unit.test_orchestrator import FakeLLM


def test_finds_question_words_pronouns_and_negatives() -> None:
    hints = dict(dialect_hints("আঁর মা'র বিধবা ভাতা কিল্লাই বন্ধ অই গেছে?"))
    assert hints["কিল্লাই"] == "কেন" and hints["আঁর"] == "আমার"
    assert "না" in dict(dialect_hints("আঁই ন জানি"))["ন"]


def test_negative_phrases() -> None:
    hints = dict(dialect_hints("মালিকে ছুটি দেয় নায়, টাকা আইসে নাই, আঁই ন জানি"))
    assert "-নি" in hints["দেয় নায়"] and "-নি" in hints["আইসে নাই"]
    assert "negative" in hints["ন জানি"]


def test_kene_depends_on_chattogram_words() -> None:
    assert dict(dialect_hints("আঁই জিডি কেনে গরিবার?"))["কেনে"] == "কীভাবে"
    assert "কেন" in dict(dialect_hints("জিডি কেনে করে?"))["কেনে"]  # no Chattogram marker: both meanings


def test_standard_bangla_gets_no_hints() -> None:
    text = "মালিক কি শ্রমিককে নিয়োগপত্র দিতে বাধ্য?"
    assert dialect_hints(text) == []
    assert with_hints(text) == text


@pytest.mark.asyncio
async def test_normalizer_sends_hints_but_keeps_the_original() -> None:
    seen: dict[str, str] = {}

    class Capture(FakeLLM):
        async def complete_json(self, system, user, schema, **kw):  # noqa: ANN001, ANN003
            seen["user"] = user
            return await super().complete_json(system, user, schema, **kw)

    llm = Capture(NormalizeOutput(standard_bangla="নমুনা প্রশ্ন কেন?", area="land"))
    q = await normalize_query(llm, "নমুনা কিল্লাই?")  # type: ignore[arg-type]
    assert "Dialect hints" in seen["user"] and "কিল্লাই = কেন" in seen["user"]
    assert q.original == "নমুনা কিল্লাই?"
