"""Hybrid retrieval with temporal validity and security trimming.

Azure: Azure AI Search — BM25 + vector (integrated Azure OpenAI vectorizer via VectorizableTextQuery)
fused by RRF, then the semantic ranker; OData filter carries as-of date and the caller's groups.
Offline: an in-memory stand-in that implements the same contract (BM25 + hashed-embedding cosine,
reciprocal rank fusion, a term-overlap 'semantic' reranker, identical filter semantics)."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol

from agentplatform.config import Settings, azure_credential, get_settings

DATA = Path(__file__).parent / "data"
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the",
    "a",
    "an",
    "of",
    "and",
    "or",
    "to",
    "is",
    "are",
    "for",
    "in",
    "on",
    "with",
    "be",
    "must",
    "by",
    "when",
    "what",
    "how",
}


class SearchUnavailable(RuntimeError):
    """Raised by backends on 5xx / network failure (retryable)."""


@dataclass(frozen=True)
class Chunk:
    id: str
    title: str
    section: str
    content: str
    effective_from: date
    effective_to: date | None
    allowed_groups: tuple[str, ...]
    guideline_id: str = ""
    version: str = ""
    program: str = ""
    params: tuple[tuple[str, object], ...] = ()  # machine-readable rule parameters (Search: params_json)

    def param(self, key: str, default: object = None) -> object:
        return dict(self.params).get(key, default)

    def in_force(self, as_of: date) -> bool:
        return self.effective_from <= as_of and (self.effective_to is None or as_of <= self.effective_to)


@dataclass
class SearchQuery:
    text: str
    as_of: date
    groups: frozenset[str]
    top: int = 5
    program: str | None = None


@dataclass
class SearchHit:
    chunk: Chunk
    score: float
    reranker_score: float = 0.0
    signals: dict[str, float] = field(default_factory=dict)


class SearchBackend(Protocol):
    def search(self, q: SearchQuery) -> list[SearchHit]: ...


def load_corpus(name: str = "guidelines") -> list[Chunk]:
    raw = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))["chunks"]
    return [
        Chunk(
            id=c["id"],
            title=c["title"],
            section=c["section"],
            content=c["content"],
            effective_from=date.fromisoformat(c["effective_from"]),
            effective_to=date.fromisoformat(c["effective_to"]) if c.get("effective_to") else None,
            allowed_groups=tuple(c["allowed_groups"]),
            guideline_id=c.get("guideline_id", c["id"]),
            version=c.get("version", ""),
            program=c.get("program", ""),
            params=tuple(sorted((c.get("params") or {}).items())),
        )
        for c in raw
    ]


def tokenize(text: str) -> list[str]:
    return [t for t in _WORD.findall(text.lower()) if t not in _STOP]


def hashed_embedding(text: str, dim: int = 256) -> list[float]:
    """Deterministic offline embedding (feature hashing of unigrams + bigrams). Stand-in for
    text-embedding-3-small; the contract (unit vector, cosine) is what matters for tests."""
    vec = [0.0] * dim
    toks = tokenize(text)
    for gram in toks + [f"{a}_{b}" for a, b in itertools.pairwise(toks)]:
        h = int(hashlib.md5(gram.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) % 2 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def build_odata_filter(as_of: date, groups: frozenset[str], program: str | None = None) -> str:
    """Temporal validity + security trimming, pushed down to Azure AI Search."""
    ts = f"{as_of.isoformat()}T00:00:00Z"
    safe_groups = ",".join(sorted(g.replace("'", "''") for g in groups))
    parts = [
        f"effective_from le {ts}",
        f"(effective_to eq null or effective_to ge {ts})",
        f"allowed_groups/any(g: search.in(g, '{safe_groups}', ','))",
    ]
    if program:
        parts.append(f"program eq '{program.replace(chr(39), chr(39) * 2)}'")
    return " and ".join(parts)


class InMemoryHybridSearch:
    """Offline stand-in for Azure AI Search hybrid + semantic ranker + security filters."""

    def __init__(self, chunks: list[Chunk], *, k1: float = 1.5, b: float = 0.75, rrf_k: int = 60) -> None:
        self.chunks = chunks
        self.k1, self.b, self.rrf_k = k1, b, rrf_k
        self._docs = {c.id: tokenize(f"{c.title} {c.section} {c.content}") for c in chunks}
        self._vecs = {c.id: hashed_embedding(f"{c.title}. {c.content}") for c in chunks}
        self._avgdl = sum(len(t) for t in self._docs.values()) / max(len(self._docs), 1)
        df: Counter[str] = Counter()
        for toks in self._docs.values():
            df.update(set(toks))
        n = len(chunks)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.fail_next = 0  # chaos hook: raise SearchUnavailable N times

    def _allowed(self, c: Chunk, q: SearchQuery) -> bool:
        return (
            c.in_force(q.as_of)
            and bool(set(c.allowed_groups) & q.groups)
            and (q.program is None or not c.program or c.program == q.program)
        )

    def _bm25(self, qt: list[str], cid: str) -> float:
        toks = self._docs[cid]
        tf = Counter(toks)
        s = 0.0
        for t in qt:
            if t not in tf:
                continue
            f = tf[t]
            s += (
                self._idf.get(t, 0)
                * f
                * (self.k1 + 1)
                / (f + self.k1 * (1 - self.b + self.b * len(toks) / self._avgdl))
            )
        return s

    def search(self, q: SearchQuery) -> list[SearchHit]:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise SearchUnavailable("in-memory search: simulated 503")
        pool = [c for c in self.chunks if self._allowed(c, q)]  # filters apply pre-ranking, like Search
        qt = tokenize(q.text)
        qv = hashed_embedding(q.text)
        lex = sorted(pool, key=lambda c: -self._bm25(qt, c.id))
        vec = sorted(pool, key=lambda c: -sum(a * b for a, b in zip(qv, self._vecs[c.id], strict=True)))
        fused: dict[str, float] = {}
        for ranking in (lex, vec):
            for rank, c in enumerate(ranking):
                fused[c.id] = fused.get(c.id, 0.0) + 1.0 / (self.rrf_k + rank + 1)
        by_id = {c.id: c for c in pool}
        candidates = sorted(fused, key=lambda i: -fused[i])[:50]
        hits = []
        qset = set(qt)
        for cid in candidates:
            c = by_id[cid]
            title_overlap = len(qset & set(tokenize(c.title))) / max(len(qset), 1)
            body_overlap = len(qset & set(self._docs[cid])) / max(len(qset), 1)
            rerank = round(4.0 * (0.6 * body_overlap + 0.4 * title_overlap), 4)  # 0..4 like semantic ranker
            hits.append(SearchHit(c, fused[cid], rerank, {"bm25": self._bm25(qt, cid)}))
        hits.sort(key=lambda h: (-h.reranker_score, -h.score))
        return [h for h in hits if h.reranker_score > 0 or h.signals["bm25"] > 0][: q.top]


class AzureAISearchBackend:
    """Azure AI Search: hybrid (text + integrated vectorizer) + semantic ranker + OData security filter."""

    SELECT = (
        "id",
        "guideline_id",
        "version",
        "title",
        "section",
        "content",
        "effective_from",
        "effective_to",
        "allowed_groups",
        "program",
        "params_json",
    )

    def __init__(self, index_name: str, settings: Settings | None = None) -> None:
        from azure.search.documents import SearchClient

        s = settings or get_settings()
        self.client = SearchClient(s.search_endpoint, index_name, azure_credential(s))

    def search(self, q: SearchQuery) -> list[SearchHit]:
        from azure.core.exceptions import HttpResponseError, ServiceRequestError
        from azure.search.documents.models import VectorizableTextQuery

        try:
            results = self.client.search(
                search_text=q.text,
                vector_queries=[
                    VectorizableTextQuery(text=q.text, k_nearest_neighbors=50, fields="content_vector")
                ],
                query_type="semantic",
                semantic_configuration_name="default",
                filter=build_odata_filter(q.as_of, q.groups, q.program),
                select=list(self.SELECT),
                top=q.top,
            )
            hits = []
            for r in results:
                chunk = Chunk(
                    id=r["id"],
                    title=r["title"],
                    section=r.get("section", ""),
                    content=r["content"],
                    effective_from=date.fromisoformat(str(r["effective_from"])[:10]),
                    effective_to=date.fromisoformat(str(r["effective_to"])[:10])
                    if r.get("effective_to")
                    else None,
                    allowed_groups=tuple(r.get("allowed_groups") or ()),
                    guideline_id=r.get("guideline_id", r["id"]),
                    version=r.get("version", ""),
                    program=r.get("program", ""),
                    params=tuple(sorted(json.loads(r.get("params_json") or "{}").items())),
                )
                hits.append(SearchHit(chunk, r["@search.score"], r.get("@search.reranker_score") or 0.0))
            return hits
        except (HttpResponseError, ServiceRequestError) as exc:
            raise SearchUnavailable(str(exc)) from exc


def get_search_backend(corpus: str = "guidelines", settings: Settings | None = None) -> SearchBackend:
    s = settings or get_settings()
    if s.azure and s.search_endpoint:
        index = s.search_guidelines_index if corpus == "guidelines" else s.search_hr_index
        return AzureAISearchBackend(index, s)
    return InMemoryHybridSearch(load_corpus(corpus))
