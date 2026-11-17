"""Load versioned Prompty files (https://prompty.ai) checked in under ``prompty/``.

The markdown pack in ``pack/`` stays the runtime source for agents. Prompty files are the
LLMOps artifact: same instructions, plus the model, parameters and inputs a canary compares.
PyYAML is imported lazily so the BFF image, which never loads this module, does not need it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

PROMPTY_DIR = Path(__file__).parent / "prompty"
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class PromptySpec:
    name: str
    version: str
    description: str
    model_api: str
    deployment: str
    api_version: str
    parameters: dict[str, Any]
    inputs: dict[str, Any]
    body: str
    path: str

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    @property
    def sha(self) -> str:
        return hashlib.sha256(self.body.encode()).hexdigest()[:12]

    def render(self, values: dict[str, str]) -> str:
        missing = sorted({m.group(1) for m in _PLACEHOLDER.finditer(self.body)} - set(values))
        if missing:
            raise KeyError(f"{self.ref}: missing inputs {', '.join(missing)}")

        def sub(match: re.Match[str]) -> str:
            return values[match.group(1)]

        return _PLACEHOLDER.sub(sub, self.body)


def _load_yaml():
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dev extra always has PyYAML
        raise RuntimeError("Reading Prompty files needs PyYAML. Install the dev extra.") from exc
    return yaml


def parse_prompty(text: str, *, path: str = "") -> PromptySpec:
    if not text.startswith("---"):
        raise ValueError(f"{path or 'prompty'}: missing front matter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path or 'prompty'}: front matter was not closed")
    meta = _load_yaml().safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{path or 'prompty'}: front matter must be a mapping")
    model = meta.get("model") or {}
    configuration = model.get("configuration") or {}
    name = str(meta.get("name") or "")
    version = str(meta.get("version") or "")
    if not name or not version:
        raise ValueError(f"{path or 'prompty'}: name and version are required")
    return PromptySpec(
        name=name,
        version=version,
        description=str(meta.get("description") or ""),
        model_api=str(model.get("api") or "chat"),
        deployment=str(configuration.get("azure_deployment") or ""),
        api_version=str(configuration.get("api_version") or ""),
        parameters=dict(model.get("parameters") or {}),
        inputs=dict(meta.get("inputs") or {}),
        body=parts[2].strip(),
        path=path,
    )


def load_prompty(path: Path) -> PromptySpec:
    return parse_prompty(path.read_text(encoding="utf-8"), path=path.name)


class PromptyPack:
    def __init__(self, specs: list[PromptySpec]) -> None:
        self._by_ref = {s.ref: s for s in specs}

    def get(self, name: str, version: str | None = None) -> PromptySpec:
        if version:
            spec = self._by_ref.get(f"{name}@{version}")
            if spec is None:
                raise KeyError(f"{name}@{version}")
            return spec
        candidates = [s for s in self._by_ref.values() if s.name == name]
        if not candidates:
            raise KeyError(name)
        return max(candidates, key=lambda s: tuple(int(x) for x in s.version.split(".")))

    def refs(self) -> list[str]:
        return sorted(self._by_ref)


@lru_cache(maxsize=1)
def load_prompty_pack() -> PromptyPack:
    paths = sorted(PROMPTY_DIR.glob("*.prompty"))
    if not paths:
        raise FileNotFoundError(f"no Prompty files in {PROMPTY_DIR}")
    return PromptyPack([load_prompty(p) for p in paths])
