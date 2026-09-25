# `mortgage/data/`: synthetic systems-of-record data

Seed data for the mock systems of record. It is read by exact path
(`mortgage/data/loans.json` in `mcp_servers/_data.py`), so this README is not loaded.

| File | What it does |
|---|---|
| [`loans.json`](loans.json) | Three synthetic loan files (`L-1001`, `L-1002`, `L-1003`) served by the LOS MCP server, plus `credit` records for the bureau server and `crm` records for the CRM agent. |
