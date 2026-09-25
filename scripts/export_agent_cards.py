"""Export A2A agent cards + directory policy to control-plane/ (checked in, diffed in CI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agentplatform.a2a.cards import card_json
from agentplatform.a2a.catalog import CATALOG

OUT = Path(__file__).resolve().parents[1] / "control-plane" / "agent-cards"


def render() -> dict[str, str]:
    files = {f"{s.id}.json": json.dumps(card_json(s), indent=2, sort_keys=True) + "\n" for s in CATALOG}
    policy = {
        s.id: {"allowed_callers": sorted(s.allowed_callers), "stage": s.stage, "standin": s.standin}
        for s in CATALOG
    }
    files["_policy.json"] = json.dumps(policy, indent=2, sort_keys=True) + "\n"
    return files


def main(check: bool = False) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    stale = []
    for name, text in render().items():
        p = OUT / name
        if check:
            if not p.exists() or p.read_text() != text:
                stale.append(name)
        else:
            p.write_text(text)
    if stale:
        print("stale agent cards:", stale, "- run python scripts/export_agent_cards.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(check="--check" in sys.argv))
