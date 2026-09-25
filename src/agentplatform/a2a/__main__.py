"""Serve one A2A agent: `python -m agentplatform.a2a crm-agent` (Container Apps: AGENT_ID env)."""

from __future__ import annotations

import os
import sys

import uvicorn


def main() -> None:
    from agentplatform.a2a.agents import HANDLERS
    from agentplatform.a2a.catalog import spec_by_id
    from agentplatform.a2a.server import create_a2a_app
    from agentplatform.harness.tracing import configure_tracing

    agent_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AGENT_ID", "crm-agent")
    spec = spec_by_id(agent_id)
    configure_tracing(f"a2a-{agent_id}")
    uvicorn.run(
        create_a2a_app(spec, HANDLERS[agent_id]), host="0.0.0.0", port=int(os.environ.get("PORT", spec.port))
    )


if __name__ == "__main__":
    main()
