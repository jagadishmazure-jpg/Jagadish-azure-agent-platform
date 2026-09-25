# SDK notes — what was verified (2026-09-25)

Everything below was checked by installing the packages into a clean Python 3.12 venv
(`uv pip install ...`) and introspecting / running the APIs, plus PyPI metadata and
Microsoft Learn pages. Where reality differed from the original assumptions, the code
follows reality and the difference is called out.

## Pinned versions (all install together)

| Package | Pinned | Notes |
|---|---|---|
| `agent-framework-core` | 1.19.0 | Microsoft Agent Framework (MAF) Python core: `Agent`, `WorkflowBuilder`, `Executor`, `@handler`, `@response_handler`, checkpoints. |
| `agent-framework-foundry` | 1.13.1 | `FoundryChatClient`, `FoundryAgent`, `FoundryEvals`. **Replaces** `agent-framework-azure-ai`, whose last release is `1.0.0rc6` (2026-03). |
| `agent-framework-azure-cosmos` | 1.0.0b260918 | `CosmosCheckpointStorage` (partition key `/workflow_name`), `CosmosHistoryProvider`. Beta. |
| `azure-ai-projects` | 2.6.1 | Foundry project SDK. 2.7.0 exists, but `agent-framework-foundry 1.13.1` pins `<2.7`, so 2.6.1 is the newest that resolves. |
| `azure-ai-evaluation` | 1.18.7 | `GroundednessEvaluator`, `RelevanceEvaluator`, `evaluate()`. (optional `[eval]` extra) |
| `azure-search-documents` | 12.0.0 | GA 12.x: `SearchClient.search(..., vector_queries=[VectorizableTextQuery], query_type="semantic", semantic_configuration_name=..., filter=...)`. |
| `azure-ai-documentintelligence` | 1.0.2 | `DocumentIntelligenceClient.begin_analyze_document(model_id, AnalyzeDocumentRequest(...))`, API `2024-11-30` (v4.0 GA). |
| `azure-ai-contentsafety` | 1.0.0 | `ContentSafetyClient.analyze_text(AnalyzeTextOptions(...))`. Prompt Shields is **not** in the SDK → called over REST. |
| `a2a-sdk[fastapi]` | 1.1.5 | A2A protocol **1.0**; protobuf types; FastAPI route helpers. |
| `mcp` | 2.2.0 | MCP Python SDK **2.x**. |
| `azure-monitor-opentelemetry` | 1.8.10 | `configure_azure_monitor()` distro. |
| `azure-identity` 1.25.3, `azure-cosmos` 4.17.1, `azure-servicebus` 7.14.3, `fastapi` 0.141.1, `uvicorn` 0.54.0, `httpx` 0.28.1 | | |

`azure-ai-agents` (1.1.0, 2025-08) is the *classic* threads/runs Agents SDK. The current Foundry
Agent Service surface used here is `azure-ai-projects` 2.x (`project.agents.create_version`).

## Microsoft Agent Framework 1.x (verified by running code)

* `Agent(client=<chat client>, instructions=..., name=..., tools=[...])`; `await agent.run(text, options={"response_format": PydanticModel})` → `response.value` is the parsed model.
* Custom/mock chat clients: subclass `BaseChatClient` and implement `async _inner_get_response(self, *, messages, stream, options, **kwargs)`. Mixing in `FunctionInvocationLayer` enables tool calling.
* Workflows: `WorkflowBuilder(start_executor=..., checkpoint_storage=..., name=..., max_iterations=N).add_edge(a, b).add_switch_case_edge_group(...)...build()`.
  * Executors: subclass `Executor`, decorate methods with `@handler`; `WorkflowContext[OutT, WorkflowOutT]`.
  * `ctx.send_message`, `ctx.yield_output`, `ctx.set_state` / `ctx.get_state` (**synchronous** in 1.19).
  * HITL: `await ctx.request_info(request_data, ResponseType)` + `@response_handler` method. The run ends with state `IDLE_WITH_PENDING_REQUESTS`; resume with `await workflow.run(responses={request_id: response})`.
  * Resume after process restart: `await workflow.run(checkpoint_id=..., checkpoint_storage=...)` re-emits pending `request_info` events, then `run(responses=...)`.
  * `FileCheckpointStorage(path, allowed_checkpoint_types=["module:Qualname", ...])` — application dataclasses must be allow-listed or checkpoint creation is skipped (pickle hardening).
  * `WorkflowRunResult.get_outputs()`, `.get_request_info_events()`, `.get_final_state()`.
* `FoundryChatClient(project_endpoint=..., model=..., credential=...)` reads `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`.

## Foundry Agent Service via `azure-ai-projects` 2.6.1

* `AIProjectClient(endpoint, credential)`; operation groups `agents`, `connections`, `deployments`, `indexes`, `datasets`, `evaluation_rules`, `beta.*`.
* Create/version an agent: `project.agents.create_version(agent_name=..., definition=PromptAgentDefinition(model=..., instructions=..., tools=[AzureAISearchTool(azure_ai_search=AzureAISearchToolResource(indexes=[AISearchIndexResource(project_connection_id=..., index_name=..., query_type=..., top_k=..., filter=...)]))]), metadata=..., description=...)`.
* Invoke: `project.get_openai_client().responses.create(input=..., extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}})` (changed from `"agent"` in 2.0).
* Legacy `.agents.create()/update()` were removed; only `create_version*`.
* Env var names used by samples: `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_NAME`.

## Foundry resource model (Bicep)

* Current model: **Foundry resource** = `Microsoft.CognitiveServices/accounts@2025-06-01`, `kind: 'AIServices'`, `properties.allowProjectManagement: true`, plus child `accounts/projects` and `accounts/deployments`. The older hub (`MachineLearningServices/workspaces` kind Hub/Project) is not used.
* Project endpoint output: `project.properties.endpoints['AI Foundry API']`.

## Models

* `gpt-4o-mini (2024-07-18)` is on the retirement schedule (Standard retired 2026-03-31; Global Standard dates announced as 2026-10-01 and later revised). `gpt-4.1-mini` retires 2026-10-14 with `gpt-5-mini` as replacement. **Default chat deployment here is `gpt-5-mini` (2025-08-07) GlobalStandard**, parameterized. Embeddings: `text-embedding-3-small` v1.
* Check the live retirement page before deploying: https://learn.microsoft.com/azure/ai-foundry/openai/concepts/model-retirements

## Document Intelligence v4.0 (2024-11-30 GA) prebuilt model IDs

`prebuilt-payStub.us`, `prebuilt-tax.us.w2`, `prebuilt-bankStatement.us` (all en-US).

## Content Safety

* SDK: `analyze_text` (harm categories Hate/SelfHarm/Sexual/Violence with severities).
* Prompt Shields: `POST {endpoint}/contentsafety/text:shieldPrompt?api-version=2024-09-01` body `{"userPrompt": str, "documents": [str]}` → `userPromptAnalysis.attackDetected`, `documentsAnalysis[].attackDetected`. Used on inbound text and on retrieved passages (indirect injection).

## A2A (a2a-sdk 1.1.5, protocol 1.0)

* **Well-known path is `/.well-known/agent-card.json`** (`a2a.utils.constants.AGENT_CARD_WELL_KNOWN_PATH`), not `/.well-known/agent.json` (that was the pre-0.3 path). Servers here publish the canonical path and a legacy alias.
* `AgentCard` fields: `name, description, supported_interfaces[AgentInterface(url, protocol_binding, tenant, protocol_version)], provider, version, documentation_url, capabilities(extensions...), security_schemes, security_requirements, default_input_modes, default_output_modes, skills[AgentSkill], signatures, icon_url`.
* JSON-RPC method names are PascalCase in 1.0 (`SendMessage`, `GetTask`, ...); roles are `ROLE_USER` / `ROLE_AGENT`; the `A2A-Version: 1.0` header is required.
* Server: implement `a2a.server.agent_execution.AgentExecutor.execute/cancel`, wire `DefaultRequestHandler(agent_executor, task_store, agent_card)` and mount with `add_a2a_routes_to_fastapi(app, agent_card_routes=create_agent_card_routes(card), jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=...))`.
* Inbound HTTP headers (for `traceparent`, tenant) are available at `context.call_context.state["headers"]`.
* Control-plane metadata (owner, side-effect class, allowed callers, eval score, stand-in flag) rides in `capabilities.extensions[]` (`AgentExtension(uri, description, params)`), because the card has no free-form metadata field.

## MCP (mcp 2.2.0)

* `FastMCP` was renamed: `from mcp.server.mcpserver import MCPServer` (importing `mcp.server.fastmcp` raises with a migration hint).
* `@server.tool()`; `server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True)` for HTTP hosting.
* Client: `from mcp import Client`; `async with Client(server_or_url) as c: await c.call_tool(name, args)`. Passing the `MCPServer` instance connects in-process (used by tests). Dict results come back as JSON text content.

## Not verifiable offline

* Real Azure calls (Foundry agent creation, Search queries, DI analysis, Content Safety, Cosmos, Service Bus, App Insights export) are behind `AAP_MODE=azure` and were **not executed** — no Azure resources were created. Their code paths follow the signatures above and are import-checked in tests.
* Bicep was compiled with Bicep CLI 0.47.16 (`bicep build`); a real `azd provision` / what-if was not run.
* Docker is not available on the build box; Dockerfiles were not built.
