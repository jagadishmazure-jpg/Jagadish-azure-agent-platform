# `knowledge/`: temporal + ACL retrieval and graph RAG

The knowledge plane. Hybrid retrieval with temporal validity and security trimming runs
against Azure AI Search (BM25 + vectors via an integrated Azure OpenAI vectorizer, fused by
RRF, then the semantic ranker) or, offline, an in-memory stand-in with the same contract and
filter semantics. A small entity graph provides citable relationship facts for related-party
detection.
Runs offline by default (`AAP_MODE=offline`); `AAP_MODE=azure` switches to the Azure adapter.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package docstring and exports. |
| [`graph.py`](graph.py) | `EntityGraph` (`add_node`, `add_edge`, `neighborhood`, `related_parties`), `GraphFact` (each edge carries a source id so it can be cited) and `demo_graph()` with the synthetic parties. |
| [`index_schema.py`](index_schema.py) | `build_index()` (AI Search index: hybrid fields, vector profile, semantic configuration `default`, filterable temporal/ACL fields) and `to_document()`; shared by the seeding script and the tests. |
| [`search.py`](search.py) | `SearchQuery`, `SearchHit`, `Chunk` (`in_force(as_of)`, `param`), `build_odata_filter(as_of, groups, program)`, `InMemoryHybridSearch`, `AzureAISearchBackend`, `get_search_backend()`, `load_corpus()` and `SearchUnavailable` (retryable). |
| [`data/`](data/README.md) | Synthetic guideline and HR corpora. |

Tests: `pytest tests/test_knowledge.py` (version in force, confidential overlay hidden,
reranker score range, OData syntax, context builder, cache degrade, graph RAG, redaction).
