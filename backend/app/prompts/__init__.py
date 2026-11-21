from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache
def load_prompt(name: str) -> str:
    """Load a prompt markdown file by stem, e.g. load_prompt("normalize")."""
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
