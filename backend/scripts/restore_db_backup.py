"""Restore a CSV backup made from Supabase (data/db_backup/<timestamp>/) into a Postgres database.

The target is a LOCAL database by default: the `offline` Postgres from infra/docker-compose.yml.
It never reads DATABASE_URL from .env, so it cannot write into Supabase by accident.

Usage (from backend/):
    docker compose -f ../infra/docker-compose.yml --profile offline up -d postgres
    python scripts/restore_db_backup.py ../data/db_backup/20261124-101500
    python scripts/restore_db_backup.py <folder> --url postgresql://user:pw@host:5432/db   # or env LOCAL_DATABASE_URL
    python scripts/restore_db_backup.py <folder> --replace    # empty non-empty tables first (TRUNCATE ... CASCADE)

Steps: verify sha256 of every CSV listed in manifest.json, create missing tables with Base.metadata.create_all
(idempotent, never drops), then COPY each CSV in foreign-key-safe order and check the row counts.

chunks source: chunks.csv (the Supabase COPY) when it is complete, i.e. its row count (parsed with the csv module)
equals the live count in the manifest (73,805 on 24 Nov); otherwise chunks_from_bm25.csv, rebuilt from the local
BM25 index (no created_at column, so the DB default fills it).

manifest.json: {"tables": {<table>: {"live_rows": int}}, "files": {<file.csv>: {"rows", "bytes", "sha256"}}}
"""

import argparse
import asyncio
import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base  # noqa: E402

# Matches the `postgres` service (offline profile) in infra/docker-compose.yml; the password is its local default.
DEFAULT_LOCAL_URL = "postgresql://adhikarai:adhikarai_local@localhost:5432/adhikarai"
# Parents before children: chunks -> documents, feedback -> query_logs.
TABLE_ORDER = ["documents", "chunks", "query_logs", "feedback", "answer_cache", "admin_users"]
# Candidate files per table, best first.
SOURCES = {"chunks": ["chunks.csv", "chunks_from_bm25.csv"]}
EXPECTED_CHUNKS = 73_805
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres"}


def plain_url(url: str) -> str:
    """asyncpg wants postgresql://; SQLAlchemy wants postgresql+asyncpg://. Accept either."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def csv_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as f:
        return next(csv.reader(f))


def csv_rows(path: Path) -> int:
    """Data rows, parsed with the csv module (quoted fields may span lines, so `wc -l` is wrong)."""
    csv.field_size_limit(sys.maxsize)
    with path.open(encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def load_manifest(folder: Path) -> dict[str, dict[str, dict[str, object]]]:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest.get("tables"), dict) or not isinstance(manifest.get("files"), dict):
        raise SystemExit("manifest.json: expected 'tables' and 'files' mappings")
    return manifest


def verify_files(folder: Path, files: dict[str, dict[str, object]]) -> None:
    for name, info in files.items():
        path = folder / name
        if not path.exists():
            raise SystemExit(f"FAIL  {path} is missing")
        if info.get("sha256") and sha256_file(path) != info["sha256"]:
            raise SystemExit(f"FAIL  {name}: sha256 does not match manifest.json")
    print(f"OK    sha256 matches manifest.json for {len(files)} files")


def pick_sources(folder: Path, manifest: dict[str, dict[str, dict[str, object]]]) -> dict[str, tuple[Path, int]]:
    """Table -> (CSV to load, expected rows). The first complete candidate wins."""
    picked: dict[str, tuple[Path, int]] = {}
    for table in TABLE_ORDER:
        live = manifest["tables"].get(table, {}).get("live_rows")
        expected = int(live) if isinstance(live, int) else (EXPECTED_CHUNKS if table == "chunks" else -1)
        for name in SOURCES.get(table, [f"{table}.csv"]):
            path = folder / name
            if not path.exists():
                continue
            rows = csv_rows(path)
            if expected < 0 or rows == expected:
                picked[table] = (path, rows)
                break
            print(f"SKIP  {name}: {rows} rows, expected {expected}")
        else:
            raise SystemExit(f"FAIL  no complete CSV for table {table}")
        print(f"OK    {table} <- {picked[table][0].name} ({picked[table][1]} rows)")
    return picked


async def create_tables(url: str) -> None:
    host = urlparse(url).hostname or ""
    connect_args: dict[str, object] = {"statement_cache_size": 0}
    if host not in _LOCAL_HOSTS:
        connect_args["ssl"] = "require"
    engine = create_async_engine(url.replace("postgresql://", "postgresql+asyncpg://", 1), connect_args=connect_args)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
    print("OK    tables exist:", ", ".join(sorted(Base.metadata.tables)))


async def load_tables(url: str, sources: dict[str, tuple[Path, int]], replace: bool) -> bool:
    host = urlparse(url).hostname or ""
    conn = await asyncpg.connect(url, statement_cache_size=0, ssl="require" if host not in _LOCAL_HOSTS else None)
    names = [n for n in TABLE_ORDER if n in sources]
    all_ok = True
    try:
        counts = {n: await conn.fetchval(f'SELECT count(*) FROM "{n}"') for n in names}
        busy = [n for n in names if counts[n]]
        if busy and not replace:
            raise SystemExit(f"FAIL  target tables not empty: {', '.join(busy)} (pass --replace to overwrite)")
        async with conn.transaction():
            if busy:
                await conn.execute("TRUNCATE " + ", ".join(f'"{n}"' for n in names) + " CASCADE")
            for name in names:
                path = sources[name][0]
                await conn.copy_to_table(
                    name,
                    source=str(path),
                    columns=csv_header(path),  # the live column order may differ from the models
                    format="csv",
                    header=True,
                )
        for name in names:
            got = await conn.fetchval(f'SELECT count(*) FROM "{name}"')
            expected = sources[name][1]
            ok = got == expected
            all_ok &= ok
            print(f"{'OK  ' if ok else 'FAIL'}  {name}: {got} rows in the database, {expected} in the CSV")
    finally:
        await conn.close()
    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, help="backup folder with manifest.json and <table>.csv files")
    parser.add_argument("--url", help="target Postgres URL (default: env LOCAL_DATABASE_URL, else offline compose DB)")
    parser.add_argument("--replace", action="store_true", help="truncate non-empty target tables before loading")
    args = parser.parse_args()

    folder: Path = args.folder.resolve()
    url = plain_url(args.url or os.environ.get("LOCAL_DATABASE_URL") or DEFAULT_LOCAL_URL)
    parsed = urlparse(url)
    print(f"Target: {parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')} (user {parsed.username})")

    manifest = load_manifest(folder)
    verify_files(folder, manifest["files"])
    sources = pick_sources(folder, manifest)
    asyncio.run(create_tables(url))
    ok = asyncio.run(load_tables(url, sources, args.replace))
    print("DONE  restore verified" if ok else "DONE  with row-count mismatches")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
