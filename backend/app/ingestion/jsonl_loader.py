"""Read/write the processed section JSONL (data/processed/*.jsonl, all_documents.jsonl)."""

import json
from collections.abc import Iterable
from pathlib import Path

from app.ingestion.area_map import spec_for_source_file
from app.ingestion.text_normalizer import normalize_text
from app.schemas.ingestion import SectionRecord

PROCESSED_DIR_NAME = "processed"
ALL_DOCUMENTS = "all_documents.jsonl"


def write_jsonl(records: Iterable[SectionRecord], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec.model_dump(exclude_none=True), ensure_ascii=False) + "\n")
            n += 1
    return n


def _coerce(raw: dict) -> SectionRecord:
    """Accept both our records and the team's original JSONL (which lacks document_id/area)."""
    if "document_id" not in raw or "area" not in raw:
        spec = spec_for_source_file(raw["source_file"])
        raw = {**raw, "document_id": spec.document_id, "area": spec.area}
    raw = {**raw, "text": normalize_text(raw["text"]), "title": normalize_text(raw.get("title") or "")}
    return SectionRecord(**raw)


def read_jsonl(path: Path) -> list[SectionRecord]:
    records: list[SectionRecord] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                records.append(_coerce(json.loads(line)))
            except Exception as exc:
                raise ValueError(f"{path.name}:{line_no}: {exc}") from exc
    seen: set[str] = set()
    dupes = {r.id for r in records if r.id in seen or seen.add(r.id)}
    if dupes:
        raise ValueError(f"duplicate record ids in {path.name}: {sorted(dupes)[:5]}")
    return records


def rebuild_all_documents(processed_dir: Path) -> int:
    """all_documents.jsonl = concatenation of every other processed *.jsonl (sorted, de-duplicated)."""
    parts = sorted(p for p in processed_dir.glob("*.jsonl") if p.name != ALL_DOCUMENTS)
    lines: list[str] = []
    for part in parts:
        lines += [ln for ln in part.read_text(encoding="utf-8").splitlines() if ln.strip()]
    (processed_dir / ALL_DOCUMENTS).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)
