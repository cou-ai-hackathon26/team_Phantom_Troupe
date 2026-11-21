import json

from fastapi import APIRouter, HTTPException

from app.core.config import DATA_DIR

router = APIRouter(prefix="/eval", tags=["evaluation"])

RESULTS = DATA_DIR / "evaluation" / "results.json"


@router.get("/latest")
async def latest() -> dict:
    """The most recent scripts/run_eval.py output (measured numbers only)."""
    if not RESULTS.exists():
        raise HTTPException(404, detail="no evaluation results yet — run scripts/run_eval.py")
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    data.pop("details", None)
    return data
