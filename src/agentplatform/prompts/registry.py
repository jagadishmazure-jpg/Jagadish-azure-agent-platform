from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from agentplatform.prompts import schemas

PACK_DIR = Path(__file__).parent / "pack"


@dataclass(frozen=True)
class PromptSpec:
    id: str
    version: str
    owner: str
    risk_tier: str
    output_schema: str | None
    body: str

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def sha(self) -> str:
        return hashlib.sha256(self.body.encode()).hexdigest()[:12]

    def schema(self) -> type[BaseModel] | None:
        return getattr(schemas, self.output_schema) if self.output_schema else None


def _parse(path: Path) -> PromptSpec:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing front matter")
    _, front, body = text.split("---", 2)
    meta = {}
    for line in front.strip().splitlines():
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip()
    schema = meta.get("output_schema") or None
    if schema and not hasattr(schemas, schema):
        raise ValueError(f"{path.name}: unknown output_schema {schema}")
    return PromptSpec(
        meta["id"], meta["version"], meta["owner"], meta.get("risk_tier", "medium"), schema, body.strip()
    )


class PromptPack:
    def __init__(self, specs: list[PromptSpec]) -> None:
        self._by_ref = {s.ref: s for s in specs}

    def get(self, prompt_id: str, version: str | None = None) -> PromptSpec:
        if version:
            return self._by_ref[f"{prompt_id}@{version}"]
        candidates = [s for s in self._by_ref.values() if s.id == prompt_id]
        if not candidates:
            raise KeyError(prompt_id)
        return max(candidates, key=lambda s: tuple(int(x) for x in s.version.split(".")))

    def refs(self) -> list[str]:
        return sorted(self._by_ref)


@lru_cache(maxsize=1)
def load_pack() -> PromptPack:
    return PromptPack([_parse(p) for p in sorted(PACK_DIR.glob("*.md"))])
