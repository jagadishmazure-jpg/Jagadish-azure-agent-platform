from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LOANS = Path(__file__).resolve().parents[1] / "mortgage" / "data" / "loans.json"


@lru_cache(maxsize=1)
def seed() -> dict:
    return json.loads(LOANS.read_text(encoding="utf-8"))
