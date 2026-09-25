"""Register the single agents in Foundry Agent Service (azure-ai-projects 2.x, new Agents API).

    python scripts/foundry_register.py --dry-run            # offline: print agent definitions (default)
    python scripts/foundry_register.py --apply              # create a new version of each agent
    python scripts/foundry_register.py --invoke hr-policy-agent "How much parental leave do I get?"

--apply/--invoke need FOUNDRY_PROJECT_ENDPOINT, AZURE_SEARCH_CONNECTION (project connection name for
the AI Search resource), and an identity with the "Azure AI User" role on the project.

Note on security trimming: the Foundry AzureAISearchTool takes a *static* OData filter per agent
version. We pin "employees" + in-force today; per-caller ACL (e.g. people-managers) needs either a
per-audience agent version or the MAF path (agentplatform.single.hr_agent) that filters per request.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

from azure.ai.projects.models import (
    AISearchIndexResource,
    AzureAISearchQueryType,
    AzureAISearchTool,
    AzureAISearchToolResource,
    FunctionTool,
    PromptAgentDefinition,
)

from agentplatform.config import get_settings
from agentplatform.knowledge.search import build_odata_filter
from agentplatform.prompts import load_pack


def _fn(name: str, description: str, props: dict, required: list[str]) -> FunctionTool:
    return FunctionTool(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        },
        strict=True,
    )


def definitions(connection_id: str) -> dict[str, tuple[PromptAgentDefinition, dict[str, str]]]:
    s = get_settings()
    pack = load_pack()
    hr, it = pack.get("hr.policy"), pack.get("it.servicedesk")
    hr_def = PromptAgentDefinition(
        model=s.foundry_model,
        instructions=hr.body,
        tools=[
            AzureAISearchTool(
                azure_ai_search=AzureAISearchToolResource(
                    indexes=[
                        AISearchIndexResource(
                            project_connection_id=connection_id,
                            index_name=s.search_hr_index,
                            query_type=AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID,
                            top_k=3,
                            filter=build_odata_filter(date.today(), frozenset({"employees"})),
                        )
                    ]
                )
            )
        ],
    )
    # Function tools are executed by the caller (BFF) — the approval gate for reset_password lives there.
    it_def = PromptAgentDefinition(
        model=s.foundry_model,
        instructions=it.body,
        tools=[
            _fn("search_kb", "Search the IT knowledge base.", {"query": {"type": "string"}}, ["query"]),
            _fn(
                "create_ticket",
                "Create a service desk ticket.",
                {
                    "summary": {"type": "string"},
                    "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
                },
                ["summary", "priority"],
            ),
            _fn(
                "reset_password",
                "Reset a user's password (human approval required).",
                {"user_id": {"type": "string"}},
                ["user_id"],
            ),
        ],
    )

    def meta(p):
        return {
            "prompt_ref": p.ref,
            "prompt_sha": p.sha,
            "owner": p.owner,
            "repo": "azure-agent-platform",
        }

    return {"hr-policy-agent": (hr_def, meta(hr)), "it-servicedesk-agent": (it_def, meta(it))}


def _project():
    from azure.ai.projects import AIProjectClient

    from agentplatform.config import azure_credential

    s = get_settings()
    if not s.foundry_project_endpoint:
        sys.exit("FOUNDRY_PROJECT_ENDPOINT is not set (azd env get-values).")
    return AIProjectClient(endpoint=s.foundry_project_endpoint, credential=azure_credential(s))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--invoke", nargs=2, metavar=("AGENT", "INPUT"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    conn_name = os.getenv("AZURE_SEARCH_CONNECTION", "aisearch")

    if a.invoke:
        project = _project()
        openai = project.get_openai_client()
        r = openai.responses.create(
            input=a.invoke[1],
            extra_body={"agent_reference": {"name": a.invoke[0], "type": "agent_reference"}},
        )
        print(r.output_text)
        return 0
    if a.apply:
        project = _project()
        conn_id = project.connections.get(conn_name).id
        for name, (definition, meta) in definitions(conn_id).items():
            v = project.agents.create_version(
                agent_name=name,
                definition=definition,
                metadata=meta,
                description=f"{name} ({meta['prompt_ref']})",
            )
            print(f"registered {name} version {v.version}")
        return 0
    out = {
        n: {"definition": d.as_dict(), "metadata": m}
        for n, (d, m) in definitions(f"<connection:{conn_name}>").items()
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
