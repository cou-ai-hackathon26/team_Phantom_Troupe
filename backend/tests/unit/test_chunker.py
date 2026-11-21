"""Chunker tests use synthetic placeholder text (no legal content) and a whitespace token counter."""

from app.ingestion.chunker import chunk_section, split_text, whitespace_token_counter
from app.schemas.ingestion import SectionRecord

count = whitespace_token_counter


def _record(text: str) -> SectionRecord:
    return SectionRecord(
        id="test-doc-s9",
        document_id="test-doc",
        area="labour",
        act="পরীক্ষামূলক আইন",
        section="৯",
        title="পরীক্ষার শিরোনাম",
        citation="পরীক্ষামূলক আইন, ধারা ৯",
        text=text,
        source_file="fixture.pdf",
        notes=["টীকা"],
    )


def test_short_section_unchanged() -> None:
    rec = _record("৯। (১) শব্দ শব্দ শব্দ।\n(২) শব্দ শব্দ।")
    chunks = chunk_section(rec, count)
    assert len(chunks) == 1
    assert chunks[0].id == "test-doc-s9"
    assert chunks[0].part is None
    assert chunks[0].text == rec.text
    assert chunks[0].notes == ["টীকা"]


def test_long_section_splits_on_clause_boundaries_with_parts() -> None:
    clauses = [f"({i}) " + " ".join(["শব্দ"] * 30) + "।" for i in range(1, 11)]  # 10 x ~32 tokens
    rec = _record("\n".join(clauses))
    chunks = chunk_section(rec, count, max_tokens=120, overlap_tokens=40)
    assert len(chunks) > 1
    assert [c.part for c in chunks] == list(range(1, len(chunks) + 1))
    assert chunks[1].id == "test-doc-s9-p2"
    for c in chunks:
        assert c.citation == rec.citation
        assert c.token_count <= 120 + 5
        # every line of every chunk is a whole clause (no clause cut in half)
        assert all(line in clauses for line in c.text.split("\n"))


def test_overlap_repeats_trailing_clause() -> None:
    clauses = [f"({i}) " + " ".join(["শব্দ"] * 20) + "।" for i in range(1, 9)]
    parts = split_text("\n".join(clauses), "শিরোনাম", count, max_tokens=80, overlap_tokens=30)
    assert len(parts) > 1
    assert parts[0].split("\n")[-1] == parts[1].split("\n")[0]


def test_single_overlong_clause_split_on_sentence_end() -> None:
    sentence = " ".join(["শব্দ"] * 40) + "।"
    text = "(১) " + " ".join([sentence] * 5)
    parts = split_text(text, "শিরোনাম", count, max_tokens=100, overlap_tokens=0)
    assert len(parts) >= 2
    assert all(count(p) <= 100 for p in parts)
    assert all(p.rstrip().endswith("।") for p in parts)


def test_normalized_text_has_ascii_digits() -> None:
    chunk = chunk_section(_record("৯। শব্দ ১২৩।"), count)[0]
    assert "123" in chunk.normalized_text
    assert "১২৩" in chunk.text
