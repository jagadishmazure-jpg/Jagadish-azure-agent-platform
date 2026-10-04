# `docintel/`: document extraction

Azure AI Document Intelligence (v4.0, API `2024-11-30`) prebuilt models for mortgage documents:
`prebuilt-payStub.us`, `prebuilt-tax.us.w2` and `prebuilt-bankStatement.us`. OCR runs before any
LLM sees a document, so agents reason over field/value pairs with confidence, never raw pixels.
Runs offline by default (`AAP_MODE=offline`); `AAP_MODE=azure` switches to the Azure adapter. Offline, fields come from the JSON files in [`fixtures/`](fixtures/README.md).

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Exports `get_extractor` and the result types. |
| [`extractor.py`](extractor.py) | `DocumentExtractor`, `get_extractor()`, `ExtractedDocument` (`doc_id`, `doc_type`, `model_id`, `fields`, `pages`, `get()`) and `FieldValue` (`value`, `confidence`). `PREBUILT_MODELS` maps document types to model ids. |
| [`fixtures/`](fixtures/README.md) | Offline extraction results for the three synthetic loans. |

Low-confidence fields are not guessed: the intake node turns them into a "provide a legible
copy" condition (see [`docs/failure-table.md`](../../../docs/failure-table.md)).

Tests: `pytest tests/test_knowledge.py -k docintel`.
