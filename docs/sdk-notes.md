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
| `agent-framework-orchestrations` | 1.2.0 | Prebuilt `SequentialBuilder`, `ConcurrentBuilder`, `HandoffBuilder`, `GroupChatBuilder`, `MagenticBuilder` (requires `agent-framework-core>=1.19.0,<2`). **Separate package**: `agent_framework.orchestrations` in core is only a lazy re-export shim and fails at import time without it. Verified 2026-09-29. |
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
* Tool approval: `@tool(approval_mode="always_require")`. The run returns `response.user_input_requests` (function-approval request contents); reply with `req.to_function_approval_response(approved=bool)` in a user `Message` on the **same `AgentSession`**. Verified: a denied reset never executes the tool; an approved one executes exactly once. MAF 1.19 logs one benign "Ignored an approval response ... did not match the active approval occurrence identity" warning per resumed turn in this flow; the result is still correct.
* `FoundryChatClient(project_endpoint=..., model=..., credential=...)` reads `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`.

## MAF prebuilt orchestrations (`agent-framework-orchestrations` 1.2.0, verified by running code)

Used by `src/agentplatform/orchestrations/`, with every behaviour below covered in `tests/test_orchestrations.py`.
Import from `agent_framework.orchestrations`.

* **Sequential.** `SequentialBuilder(*, participants, name=None, checkpoint_storage=None, chain_only_agent_responses=False, output_from=..., intermediate_output_from=None)`.
  * The workflow output is **only the last participant's `AgentResponse`**, not the whole conversation.
  * `.with_request_info(agents=[names])` pauses **after** each named agent answers. The request payload is an `AgentExecutorResponse` (`executor_id`, `agent_response`, `full_conversation`).
  * Reply `AgentRequestInfoResponse.approve()` to accept, or `.from_strings([...])` / `.from_messages([...])` to send feedback. Feedback re-runs the agent, which pauses again.
* **Concurrent.** `ConcurrentBuilder(*, participants, ...)`, then `.with_aggregator(callback | Executor)`.
  * The callback gets `list[AgentExecutorResponse]` (optionally also `ctx`), and its return value becomes the workflow output.
* **Handoff.** `HandoffBuilder(*, participants, name, description, checkpoint_storage, termination_condition)` with `.with_start_agent(agent)` (required: `build()` raises without it), `.add_handoff(source, [targets])`, `.with_termination_condition(fn(list[Message]) -> bool)`, `.with_autonomous_mode(...)` and `.with_checkpointing(...)`.
  * **Surprise:** participants must be real `Agent` objects built with **`require_per_service_call_history_persistence=True`**, or `build()` raises `ValueError`. This is not mentioned in the class docstring.
  * Routing tools are injected as `handoff_to_<agent name>`. A model hands off by calling one, and the call is short-circuited by middleware (a `handoff_sent` event with `HandoffSentEvent(source, target)`).
  * The receiving agent sees the cleaned conversation: text is kept, tool-call plumbing is stripped.
  * In non-autonomous mode, an agent that answers **without** handing off pauses the run with `HandoffAgentUserRequest`. Answer it with `HandoffAgentUserRequest.create_response(text)` or `.terminate()`.
  * Agents with no outgoing handoff log "No handoff configuration found ... may get stuck". This is benign for a terminal agent paired with a termination condition.
* **Group chat.** `GroupChatBuilder(*, participants, selection_func | orchestrator_agent | orchestrator (exactly one), termination_condition, max_rounds, checkpoint_storage, output_from, intermediate_output_from)`.
  * `selection_func(GroupChatState) -> name`, where `GroupChatState` has `current_round`, `participants` and `conversation`.
  * An `orchestrator_agent` must reply with `AgentOrchestrationOutput` JSON (`terminate`, `reason`, `next_speaker`, `final_message`; `extra="forbid"`), and costs one model call per round.
  * **Surprise:** by default the workflow output is **only the orchestrator's completion message**, for example "The group chat has reached its termination condition." or "... maximum number of rounds." Pass `output_from="all"` to receive participants' responses.
  * Hitting `max_rounds` logs "forcing completion" and yields that message rather than raising.
* **Magentic.** `MagenticBuilder(*, participants (non-empty names), manager_agent | manager | manager_factory | manager_agent_factory, enable_plan_review=False, max_round_count, max_stall_count=3, max_reset_count, checkpoint_storage, output_from, ...)`.
  * A `manager_agent` is wrapped in `StandardMagenticManager`, which drives it with its own prompts: facts ("Below I will present you a request..."), plan, a JSON progress ledger (`is_request_satisfied`, `is_in_loop`, `is_progress_being_made`, `next_speaker`, `instruction_or_question`, each `{reason, answer}`) and the final answer.
  * A custom manager subclasses `MagenticManagerBase` (`plan`, `replan`, `create_progress_ledger`, `prepare_final_answer`).
  * Plan review pauses with `MagenticPlanReviewRequest` (`plan`, `current_progress`, `is_stalled`). Answer with `.approve()` or `.revise(feedback)`.
  * A reset happens when `stall_count > max_stall_count` (strictly greater). **A reset clears the chat history and re-fires plan review**, so any evidence that a worker failed is gone unless the manager carries it forward in its plan or instruction.
  * Hitting round or reset caps yields "Workflow terminated due to reaching maximum round/reset count." as the output; nothing is raised.
  * Events: `magentic_orchestrator` with `MagenticOrchestratorEvent(event_type=PLAN_CREATED | REPLANNED | PROGRESS_LEDGER_UPDATED, ...)`, and `group_chat` with `GroupChatRequestSentEvent` / `GroupChatResponseReceivedEvent`.
  * **Docstring drift:** the `MagenticBuilder` docstring still mentions `.with_human_input_on_stall()` and `MagenticHumanInterventionRequest/Kind`. Neither exists in 1.2.0; plan review is the only built-in HITL hook.
* **Common.**
  * `WorkflowRunResult.get_request_info_events()` returns the pauses, and `workflow.run(responses={request_id: answer})` resumes.
  * Checkpointed builders resume in a fresh instance with `run(checkpoint_id=latest.checkpoint_id, checkpoint_storage=...)`, which re-surfaces the pending request.
  * Sequential and concurrent log a benign "Dead-end executors detected" warning at build time.

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

## azure-ai-evaluation 1.18.7

* `evaluate(data=<jsonl>, evaluators={...}, evaluator_config={name: {"column_mapping": {...}}}, azure_ai_project=<project endpoint str>, evaluation_name=..., tags=...)`.
* AI-assisted evaluators: `GroundednessEvaluator(model_config, credential=..., threshold=3)`, `RelevanceEvaluator(model_config, credential=...)`; `model_config` is an `AzureOpenAIModelConfiguration` TypedDict (`azure_endpoint`, `azure_deployment`, `api_version`).
* Custom evaluators are plain callables. **`evaluate()` derives required columns from the `__call__` signature** — a `**kwargs` parameter makes it demand a column named `_`/`kwargs` and fail. Our evaluators use explicit keyword parameters. Verified offline: `evaluate()` with only the custom evaluator runs without Azure (test_evals.py).

## Azure AI Search SDK 12.0.0 + service facts

* Index models used: `SearchIndex`, `SimpleField`/`SearchableField`/`SearchField`, `VectorSearch`, `HnswAlgorithmConfiguration`, `VectorSearchProfile(vectorizer_name=...)`, `AzureOpenAIVectorizer(vectorizer_name, parameters=AzureOpenAIVectorizerParameters(resource_url, deployment_name, model_name))`, `SemanticConfiguration`/`SemanticPrioritizedFields`/`SemanticSearch`; query with `VectorizableTextQuery` + `query_type="semantic"` + OData `filter`.
* Document keys may only contain letters, digits, `_`, `-`, `=` — so `GL-DTI-200.v1` is stored as `GL-DTI-200_v1` and the citation id is rebuilt from `guideline_id` + `version` on read.
* Semantic ranker billing: `free` plan (monthly allowance) on every tier; `standard` (pay-as-you-go) needs Basic+. Newer management API versions drop the `disabled` value. A usage-based "serverless" tier is listed on the pricing page; not used here.

## Azure RBAC role IDs (checked against the built-in roles reference)

| Role | GUID |
|---|---|
| Foundry User (formerly "Azure AI User") | 53ca6127-db72-4b80-b1b0-d745d6d5456d |
| Cognitive Services OpenAI User | 5e0bd9bd-7b93-4f28-af87-19fc36ad61bd |
| Cognitive Services User | a97b65f3-24c7-4388-baec-2e87135dc908 |
| Search Index Data Reader / Contributor | 1407120a-92aa-4202-b7e9-c0e197c71c8f / 8ebe5a00-799e-43f5-93ac-243d3dce84a7 |
| Search Service Contributor | 7ca78c08-252a-4471-8644-bb5ff32d4ba0 |
| Azure Service Bus Data Sender | 69a216fc-b8fb-44d8-bc22-1f3c2cd27a39 |
| Key Vault Secrets User | 4633458b-17de-408a-b874-0445c86b69e6 |
| AcrPull | 7f951dda-4ed3-4680-a7ca-43fe172d538d |
| Cosmos DB Built-in Data Contributor (data plane) | 00000000-0000-0000-0000-000000000002 |

## Agent Framework + Cosmos

* `agent_framework_azure_cosmos.CosmosCheckpointStorage` creates/uses a container partitioned on `/workflow_name` — the Bicep `checkpoints` container matches. That is why each run gets its own workflow name (`mortgage-uw:{run_id}`).

## Not verifiable offline

* Real Azure calls (Foundry agent creation, Search queries, DI analysis, Content Safety, Cosmos, Service Bus, App Insights export) are behind `AAP_MODE=azure` and were **not executed** — no Azure resources were created. Their code paths follow the signatures above and are import-checked in tests.
* Bicep was compiled with Bicep CLI 0.47.16 (`bicep build`); a real `azd provision` / what-if was not run.
* Docker is not available on the build box; Dockerfiles were not built. The same multi-service topology was exercised over real HTTP with `scripts/run_local_mesh.sh` (BFF → A2A agents → MCP servers as separate processes).
