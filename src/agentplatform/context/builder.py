"""The context builder is the knowledge-plane runtime.

Input: topics/questions, principal (tenant + groups), business as-of date, optional graph anchor and
tool facts. Output: a packed, cited, budgeted evidence bundle plus a source map and a log of what
was dropped and why (ACL, not-in-force, injection, budget). Agents never call Search directly."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from agentplatform.context.sanitize import estimate_tokens, redact_pii
from agentplatform.harness.identity import Principal
from agentplatform.harness.tracing import span
from agentplatform.knowledge.graph import EntityGraph, GraphFact
from agentplatform.knowledge.search import Chunk, SearchBackend, SearchQuery, load_corpus
from agentplatform.safety.content_safety import ContentSafetyGate

# Share of the token budget per evidence class (policy first, then facts, then relationships).
BUDGET_SPLIT = {"guideline": 0.50, "tool": 0.25, "graph": 0.15, "document": 0.10}

# Degrade path when Search is down: a small, versioned snapshot of the most-cited guidelines.
KNOWN_GUIDELINE_CACHE = ["GL-DTI-200", "GL-INC-110", "GL-AST-220", "GL-CR-100", "GL-DOC-400"]


@dataclass
class EvidenceItem:
    source_id: str
    kind: str  # guideline | graph | document | tool
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextPack:
    as_of: date
    items: list[EvidenceItem] = field(default_factory=list)
    dropped: list[tuple[str, str]] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    limited: bool = False
    tokens_used: dict[str, int] = field(default_factory=dict)

    @property
    def source_map(self) -> dict[str, dict[str, Any]]:
        return {i.source_id: {"kind": i.kind, **i.meta} for i in self.items}

    def ids(self, kind: str | None = None) -> list[str]:
        return [i.source_id for i in self.items if kind is None or i.kind == kind]

    def guideline_ids(self) -> set[str]:
        """Both chunk ids (GL-DTI-200.v2) and family ids (GL-DTI-200) are valid citations."""
        out: set[str] = set()
        for i in self.items:
            if i.kind == "guideline":
                out |= {i.source_id, i.meta.get("guideline_id", i.source_id)}
        return out

    def rule(self, guideline_id: str) -> dict[str, Any] | None:
        """Machine-readable parameters of the in-force version of a guideline family, if packed."""
        for i in self.items:
            if i.kind == "guideline" and i.meta.get("guideline_id") == guideline_id:
                return {"chunk_id": i.source_id, **i.meta.get("params", {})}
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "items": [
                {"source_id": i.source_id, "kind": i.kind, "text": i.text, "meta": i.meta} for i in self.items
            ],
            "dropped": [list(d) for d in self.dropped],
            "queries": list(self.queries),
            "limited": self.limited,
            "tokens_used": dict(self.tokens_used),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ContextPack:
        return cls(
            as_of=date.fromisoformat(d["as_of"]),
            items=[
                EvidenceItem(i["source_id"], i["kind"], i["text"], i.get("meta", {}))
                for i in d.get("items", [])
            ],
            dropped=[tuple(x) for x in d.get("dropped", [])],
            queries=list(d.get("queries", [])),
            limited=bool(d.get("limited")),
            tokens_used=dict(d.get("tokens_used", {})),
        )

    def merge(self, other: ContextPack) -> None:
        have = set(self.ids())
        self.items += [i for i in other.items if i.source_id not in have]
        self.dropped += other.dropped
        self.queries += other.queries
        self.limited = self.limited or other.limited

    def render(self) -> str:
        lines = [f"# Evidence pack (as of {self.as_of.isoformat()}){' [LIMITED]' if self.limited else ''}"]
        for i in self.items:
            lines.append(f"[{i.source_id}] ({i.kind}) {i.text}")
        return "\n".join(lines)


class ContextBuilder:
    def __init__(
        self,
        search: SearchBackend,
        *,
        graph: EntityGraph | None = None,
        safety: ContentSafetyGate | None = None,
        budget_tokens: int = 2400,
        cache_corpus: list[Chunk] | None = None,
    ) -> None:
        self.search = search
        self.graph = graph
        self.safety = safety or ContentSafetyGate()
        self.budget_tokens = budget_tokens
        self._cache_corpus = cache_corpus

    # ---- public ----------------------------------------------------------------
    def build(
        self,
        *,
        topics: list[str],
        principal: Principal,
        as_of: date,
        program: str | None = None,
        graph_anchor: str | None = None,
        tool_facts: dict[str, str] | None = None,
        top_per_topic: int = 3,
    ) -> ContextPack:
        pack = ContextPack(as_of=as_of)
        with span("context.build", tenant=principal.tenant_id, topics=len(topics), as_of=as_of.isoformat()):
            chunks: dict[str, Chunk] = {}
            for topic in topics:
                pack.queries.append(topic)
                q = SearchQuery(topic, as_of, principal.groups, top=top_per_topic, program=program)
                for hit in self.search.search(q):  # SearchUnavailable propagates to the harness
                    chunks.setdefault(hit.chunk.id, hit.chunk)
            self._pack_guidelines(pack, list(chunks.values()), principal, as_of)
            self._pack_graph(pack, graph_anchor)
            self._pack_tools(pack, tool_facts or {})
        return pack

    def build_from_cache(self, *, principal: Principal, as_of: date, reason: str) -> ContextPack:
        """Degrade exit: known-guideline snapshot, marked LIMITED so decisions are disabled downstream."""
        corpus = self._cache_corpus or load_corpus("guidelines")
        chosen = [c for c in corpus if c.guideline_id in KNOWN_GUIDELINE_CACHE]
        pack = ContextPack(as_of=as_of, limited=True)
        pack.dropped.append(("*", f"search unavailable: {reason}"))
        self._pack_guidelines(pack, chosen, principal, as_of)
        return pack

    # ---- internals ---------------------------------------------------------------
    def _budget(self, kind: str) -> int:
        return int(self.budget_tokens * BUDGET_SPLIT[kind])

    def _admit(self, pack: ContextPack, item: EvidenceItem) -> bool:
        used = pack.tokens_used.get(item.kind, 0)
        cost = estimate_tokens(item.text)
        if used + cost > self._budget(item.kind):
            pack.dropped.append((item.source_id, "budget"))
            return False
        pack.tokens_used[item.kind] = used + cost
        pack.items.append(item)
        return True

    def _pack_guidelines(
        self, pack: ContextPack, chunks: list[Chunk], principal: Principal, as_of: date
    ) -> None:
        # Defense in depth: re-apply ACL + temporal checks even though Search filtered already.
        admitted: list[Chunk] = []
        for c in chunks:
            if not set(c.allowed_groups) & principal.groups:
                pack.dropped.append((c.id, "acl"))
            elif not c.in_force(as_of):
                pack.dropped.append((c.id, "not-in-force"))
            else:
                admitted.append(c)
        verdicts = self.safety.check_documents([c.content for c in admitted])
        seen_families: set[str] = set()
        for c, v in zip(admitted, verdicts, strict=True):
            if not v.allowed:
                pack.dropped.append((c.id, "injection"))
                continue
            if c.guideline_id in seen_families:
                pack.dropped.append((c.id, "duplicate-family"))
                continue
            seen_families.add(c.guideline_id)
            self._admit(
                pack,
                EvidenceItem(
                    c.id,
                    "guideline",
                    f"{c.title}: {redact_pii(c.content)}",
                    {
                        "guideline_id": c.guideline_id,
                        "version": c.version,
                        "params": dict(c.params),
                        "effective_from": c.effective_from.isoformat(),
                        "effective_to": c.effective_to.isoformat() if c.effective_to else None,
                    },
                ),
            )

    def _pack_graph(self, pack: ContextPack, anchor: str | None) -> None:
        if not (self.graph and anchor):
            return
        facts: list[GraphFact] = self.graph.neighborhood(anchor, hops=2)
        for f in facts:
            self._admit(pack, EvidenceItem(f.source_id, "graph", f.render(), {"relation": f.relation}))

    def _pack_tools(self, pack: ContextPack, facts: dict[str, str]) -> None:
        for sid, text in facts.items():
            self._admit(pack, EvidenceItem(sid, "tool", redact_pii(text)))
