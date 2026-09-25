"""Loop layer: the critic. Deterministic rules first (fail-closed), then one bounded repair pass."""

from __future__ import annotations

from datetime import date

from agentplatform.context.builder import ContextPack


def check(conditions: list[dict], pack: ContextPack, as_of: date) -> dict:
    ids_in_pack = pack.guideline_ids()
    uncited, not_in_evidence, not_in_force = [], [], []
    for c in conditions:
        gids = c.get("guideline_ids") or []
        if not gids:
            uncited.append(c["id"])
            continue
        for g in gids:
            if g not in ids_in_pack:
                not_in_evidence.append(c["id"])
                break
            meta = pack.source_map.get(g) or next(
                (m for m in pack.source_map.values() if m.get("guideline_id") == g), {}
            )
            eff_to = meta.get("effective_to")
            if meta.get("effective_from") and (
                date.fromisoformat(meta["effective_from"]) > as_of
                or (eff_to and date.fromisoformat(eff_to) < as_of)
            ):
                not_in_force.append(c["id"])
                break
    notes = ["evidence pack is LIMITED (search degraded); decision disabled"] if pack.limited else []
    return {
        "passed": not (uncited or not_in_evidence or not_in_force),
        "uncited": uncited,
        "not_in_evidence": not_in_evidence,
        "not_in_force": not_in_force,
        "notes": notes,
    }
