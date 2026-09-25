# `docintel/fixtures/`: offline extraction results

Synthetic Document Intelligence results used in offline mode. The extractor loads
`<doc_id>.json` by exact name (`FIXTURES / f"{doc_id}.json"`), so only files named after a
document id are read; this README is ignored. Each file has `fields` (name to `value` and
`confidence`) and, for bank statements, `pages`. All names, employers and amounts are invented.

| File | What it does |
|---|---|
| [`L-1001-bank.json`](L-1001-bank.json) | Bank statement for loan L-1001. |
| [`L-1001-paystub.json`](L-1001-paystub.json) | Paystub for L-1001. |
| [`L-1001-w2.json`](L-1001-w2.json) | W-2 for L-1001. |
| [`L-1002-bank.json`](L-1002-bank.json) | Bank statement for L-1002 (one field has low confidence, 0.62, so the rules add a `C-DOC-L-1002-bank` legible-copy condition). |
| [`L-1002-paystub.json`](L-1002-paystub.json) | Paystub for L-1002. |
| [`L-1002-w2.json`](L-1002-w2.json) | W-2 for L-1002. |
| [`L-1003-bank.json`](L-1003-bank.json) | Bank statement for L-1003. |
| [`L-1003-paystub.json`](L-1003-paystub.json) | Paystub for L-1003. |
| [`L-1003-w2.json`](L-1003-w2.json) | W-2 for L-1003. |
