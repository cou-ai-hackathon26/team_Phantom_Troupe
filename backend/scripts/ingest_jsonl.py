"""Idempotent ingestion: data/processed/all_documents.jsonl -> chunks -> Postgres + Qdrant + BM25.

Usage (from backend/):
    python scripts/ingest_jsonl.py                  # all three stores
    python scripts/ingest_jsonl.py --skip-postgres  # without Supabase
    python scripts/ingest_jsonl.py --recreate       # drop + recreate the Qdrant collection (model change)

Re-running gives identical counts: Postgres rows and Qdrant points are upserted by deterministic ids,
stale chunks are deleted, and the BM25 pickle is rebuilt from the same chunk list.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.pipeline import ingest_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-postgres", action="store_true")
    parser.add_argument("--recreate", action="store_true", help="drop and recreate the Qdrant collection")
    args = parser.parse_args()
    return asyncio.run(ingest_all(args.skip_postgres, args.recreate))


if __name__ == "__main__":
    raise SystemExit(main())
