"""Graph RAG over borrower / property / entity relationships.

Edges come from systems of record (CRM contacts, LOS parties, employer from VOE, county records),
each carrying a source id so graph facts are citable. Azure path: Cosmos DB for Apache Gremlin
(or a Cosmos NoSQL adjacency container); offline: in-memory adjacency with the same k-hop contract."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GraphFact:
    subject: str
    relation: str
    object: str
    source_id: str

    def render(self) -> str:
        return f"{self.subject} -[{self.relation}]-> {self.object} (source {self.source_id})"


@dataclass
class EntityGraph:
    nodes: dict[str, dict] = field(default_factory=dict)
    edges: list[GraphFact] = field(default_factory=list)

    def add_node(self, node_id: str, kind: str, **props) -> None:
        self.nodes[node_id] = {"kind": kind, **props}

    def add_edge(self, s: str, rel: str, o: str, source_id: str) -> None:
        self.edges.append(GraphFact(s, rel, o, source_id))

    def neighborhood(self, start: str, hops: int = 2) -> list[GraphFact]:
        seen, out, frontier = {start}, [], deque([(start, 0)])
        while frontier:
            node, d = frontier.popleft()
            if d >= hops:
                continue
            for e in self.edges:
                if node in (e.subject, e.object):
                    if e not in out:
                        out.append(e)
                    nxt = e.object if e.subject == node else e.subject
                    if nxt not in seen:
                        seen.add(nxt)
                        frontier.append((nxt, d + 1))
        return out

    def related_parties(
        self, borrower: str, counterparties: set[str], hops: int = 2
    ) -> list[list[GraphFact]]:
        """Paths (<= hops) connecting the borrower to any counterparty (seller, listing agent, builder)."""
        paths: list[list[GraphFact]] = []
        queue: deque[tuple[str, list[GraphFact]]] = deque([(borrower, [])])
        while queue:
            node, path = queue.popleft()
            if path and node in counterparties:
                paths.append(path)
                continue
            if len(path) >= hops:
                continue
            for e in self.edges:
                if e.relation in ("seller_of", "listing_agent_for", "collateral_for", "applicant_on"):
                    continue  # transaction edges don't count as a relationship
                if node in (e.subject, e.object):
                    nxt = e.object if e.subject == node else e.subject
                    if all(nxt not in (p.subject, p.object) for p in path) and nxt != borrower:
                        queue.append((nxt, [*path, e]))
        return paths


def demo_graph() -> EntityGraph:
    """Synthetic parties for the demo loan files."""
    g = EntityGraph()
    for nid, kind in [
        ("borrower:B-1001", "borrower"),
        ("borrower:B-1002", "borrower"),
        ("borrower:B-1003", "borrower"),
        ("employer:Fabrikam Homes LLC", "employer"),
        ("employer:Contoso Health", "employer"),
        ("employer:Woodgrove Bank", "employer"),
        ("property:12 Elm St", "property"),
        ("property:88 Lake Rd", "property"),
        ("property:5 Birch Ct", "property"),
        ("party:Fabrikam Homes LLC", "seller"),
        ("party:Pat Lee", "seller"),
        ("party:Sam Ortiz", "seller"),
        ("party:Alex Rivera", "person"),
    ]:
        g.add_node(nid, kind)
    g.add_edge("borrower:B-1001", "employed_by", "employer:Contoso Health", "VOE-1001")
    g.add_edge("party:Pat Lee", "seller_of", "property:12 Elm St", "LOS-PARTY-1001")
    g.add_edge("property:12 Elm St", "collateral_for", "loan:L-1001", "LOS-1001")

    g.add_edge("borrower:B-1002", "employed_by", "employer:Woodgrove Bank", "VOE-1002")
    g.add_edge("party:Sam Ortiz", "seller_of", "property:88 Lake Rd", "LOS-PARTY-1002")

    # L-1003: borrower works for the builder that is selling the home -> non-arm's-length.
    g.add_edge("borrower:B-1003", "employed_by", "employer:Fabrikam Homes LLC", "VOE-1003")
    g.add_edge("employer:Fabrikam Homes LLC", "same_entity", "party:Fabrikam Homes LLC", "SOS-REG-7781")
    g.add_edge("party:Fabrikam Homes LLC", "seller_of", "property:5 Birch Ct", "LOS-PARTY-1003")
    g.add_edge("borrower:B-1003", "family_of", "party:Alex Rivera", "CRM-CONTACT-3301")
    return g
