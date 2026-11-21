"""Source governance (docs/pipeline.md 6.2–7.1): preserve originals byte-for-byte with a checksum,
log provenance in data/sources_log.csv, and keep a JSON registry of documents added by ingest_pdf.py."""

import csv
import hashlib
import json
import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import DATA_DIR
from app.ingestion.area_map import DocumentSpec

REGISTRY_PATH = DATA_DIR / "sources_registry.json"
SOURCES_LOG = DATA_DIR / "sources_log.csv"
ORIGINALS_DIR = DATA_DIR / "originals"

LOG_HEADER = [
    "document_id", "title", "issuer", "domain", "source_url", "publication_date", "effective_date",
    "downloaded_at", "language", "version_status", "jurisdiction", "sha256", "extraction_method",
    "reviewed_by", "reviewed_at", "original_file",
]  # fmt: skip


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def preserve_original(pdf: Path, area: str, originals_dir: Path = ORIGINALS_DIR) -> tuple[Path, str]:
    """Copy into data/originals/<area>/ without ever overwriting a different file of the same name."""
    digest = sha256_of(pdf)
    target_dir = originals_dir / area
    target_dir.mkdir(parents=True, exist_ok=True)
    if pdf.resolve().is_relative_to(target_dir.resolve()):
        return pdf, digest
    target = target_dir / pdf.name
    n = 1
    while target.exists() and sha256_of(target) != digest:
        target = target_dir / f"{pdf.stem}_v{n}{pdf.suffix}"
        n += 1
    if not target.exists():
        shutil.copy2(pdf, target)
    return target, digest


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, DocumentSpec]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {d["document_id"]: DocumentSpec(**d) for d in raw}


def register(spec: DocumentSpec, path: Path = REGISTRY_PATH) -> None:
    specs = load_registry(path)
    specs[spec.document_id] = spec
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [asdict(s) for s in sorted(specs.values(), key=lambda s: s.document_id)], ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )


def log_source(
    spec: DocumentSpec,
    original: Path,
    sha256: str,
    extraction_method: str,
    version_status: str,
    path: Path = SOURCES_LOG,
) -> None:
    """Append a provenance row unless this exact file (sha256) is already logged for the document."""
    rows: list[dict[str, str]] = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    if any(r.get("document_id") == spec.document_id and r.get("sha256") == sha256 for r in rows):
        return
    new_file = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_HEADER)
        if new_file:
            writer.writeheader()
        writer.writerow(
            {
                "document_id": spec.document_id,
                "title": spec.title,
                "issuer": spec.issuer,
                "domain": spec.area,
                "source_url": spec.source_url or "",
                "publication_date": "",  # fill from the document; never guess
                "effective_date": "",
                "downloaded_at": datetime.now(UTC).date().isoformat(),
                "language": spec.language,
                "version_status": version_status,
                "jurisdiction": "Bangladesh",
                "sha256": sha256,
                "extraction_method": extraction_method,
                "reviewed_by": "",
                "reviewed_at": "",
                "original_file": str(original.relative_to(DATA_DIR))
                if original.is_relative_to(DATA_DIR)
                else original.name,
            }
        )
