# `llm/`: model clients

Model access for every agent. Offline, `MockChatClient` is a real MAF `BaseChatClient`, so
agents, tools, structured output and middleware behave as they would with Foundry, but answers
are deterministic. On Azure, `get_chat_client()` returns a Foundry chat client over the project
endpoint with managed identity, with an optional fallback deployment (`FOUNDRY_FALLBACK_MODEL`)
for 429/5xx.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Exports `get_chat_client`. |
| [`clients.py`](clients.py) | `MockChatClient` and `get_chat_client()`. |

Tests: `pytest tests/test_harness.py -k mock_client`.
