from datetime import date

import pytest

from agentplatform.context import ContextBuilder, redact_pii
from agentplatform.docintel import PREBUILT_MODELS, get_extractor
from agentplatform.harness.identity import Principal
from agentplatform.knowledge import (
    InMemoryHybridSearch,
    SearchQuery,
    SearchUnavailable,
    build_odata_filter,
    demo_graph,
    load_corpus,
)

UW = frozenset({"underwriting"})


@pytest.fixture
def search():
    return InMemoryHybridSearch(load_corpus())


def test_temporal_rag_returns_version_in_force(search):
    q = "maximum debt-to-income ratio"
    early = search.search(SearchQuery(q, date(2025, 3, 10), UW, top=1))
    late = search.search(SearchQuery(q, date(2025, 9, 15), UW, top=1))
    assert early[0].chunk.id == "GL-DTI-200.v1"
    assert late[0].chunk.id == "GL-DTI-200.v2"


def test_security_filter_hides_confidential_overlay(search):
    q = "investor overlay minimum credit score high DTI"
    as_of = date(2025, 11, 20)
    assert all(h.chunk.id != "GL-OVL-900.v1" for h in search.search(SearchQuery(q, as_of, UW, top=10)))
    senior = search.search(SearchQuery(q, as_of, frozenset({"underwriting-senior"}), top=10))
    assert any(h.chunk.id == "GL-OVL-900.v1" for h in senior)


def test_hybrid_scores_have_semantic_reranker_range(search):
    hits = search.search(SearchQuery("large deposit sourcing", date(2025, 9, 1), UW))
    assert hits[0].chunk.guideline_id == "GL-AST-210"
    assert all(0 <= h.reranker_score <= 4 for h in hits)


def test_odata_filter_matches_azure_syntax():
    f = build_odata_filter(date(2025, 9, 15), frozenset({"underwriting", "o'brien"}), "conventional")
    assert "effective_from le 2025-09-15T00:00:00Z" in f
    assert "(effective_to eq null or effective_to ge 2025-09-15T00:00:00Z)" in f
    assert "search.in(g, 'o''brien,underwriting', ',')" in f
    assert f.endswith("program eq 'conventional'")


def test_context_builder_drops_injection_and_cites(search):
    b = ContextBuilder(search, graph=demo_graph())
    p = Principal("uw1", "contoso-mortgage", UW)
    pack = b.build(
        topics=["income and credit common questions", "maximum debt-to-income ratio"],
        principal=p,
        as_of=date(2025, 9, 15),
        graph_anchor="borrower:B-1003",
        tool_facts={"CREDIT-RPT-1": "SSN 123-45-6789 score 742"},
    )
    assert ("GL-MISC-999.v1", "injection") in pack.dropped
    assert "GL-DTI-200" in pack.guideline_ids() and "GL-DTI-200.v2" in pack.guideline_ids()
    assert "SOS-REG-7781" in pack.ids("graph")
    assert "123-45-6789" not in pack.render()


def test_context_builder_degrades_to_cache(search):
    search.fail_next = 1
    b = ContextBuilder(search)
    p = Principal("uw1", "t", UW)
    with pytest.raises(SearchUnavailable):
        b.build(topics=["dti"], principal=p, as_of=date(2025, 9, 15))
    pack = b.build_from_cache(principal=p, as_of=date(2025, 9, 15), reason="503")
    assert pack.limited and "GL-DTI-200.v2" in pack.ids()


def test_graph_rag_detects_non_arms_length():
    g = demo_graph()
    paths = g.related_parties("borrower:B-1003", {"party:Fabrikam Homes LLC"})
    assert paths and [e.source_id for e in paths[0]] == ["VOE-1003", "SOS-REG-7781"]
    assert not g.related_parties("borrower:B-1001", {"party:Pat Lee"})


def test_docintel_offline_returns_fields_and_confidence():
    ex = get_extractor()
    doc = ex.extract("L-1002-bank", "bank_statement")
    assert doc.model_id == PREBUILT_MODELS["bank_statement"] == "prebuilt-bankStatement.us"
    assert doc.low_confidence() == ["EndingBalance"]
    assert ex.extract("L-1001-w2", "w2").get("WagesTipsAndOtherCompensation") == 118000.0


def test_redaction():
    assert redact_pii("acct no 1234567890 ssn 111-22-3333") == "account ****7890 ssn ***-**-****"
