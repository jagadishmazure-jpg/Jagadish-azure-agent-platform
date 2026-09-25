#!/usr/bin/env bash
# Docker-free equivalent of docker-compose: every service as its own process over real HTTP
# (same env contract as Container Apps). Ctrl-C stops everything.
set -euo pipefail
export AAP_MODE=${AAP_MODE:-offline} AAP_A2A_REMOTE=1 AAP_CHECKPOINT_DIR=${AAP_CHECKPOINT_DIR:-.checkpoints}
export A2A_UNDERWRITING_AGENT_URL=http://127.0.0.1:9203 A2A_CRM_AGENT_URL=http://127.0.0.1:9201 \
       A2A_ERP_AGENT_URL=http://127.0.0.1:9202 \
       MCP_CREDIT_BUREAU_URL=http://127.0.0.1:9101/mcp MCP_LOS_URL=http://127.0.0.1:9102/mcp
pids=()
trap 'kill "${pids[@]}" 2>/dev/null' EXIT
PORT=9101 python -m agentplatform.mcp_servers credit-bureau & pids+=($!)
PORT=9102 python -m agentplatform.mcp_servers los & pids+=($!)
PORT=9201 python -m agentplatform.a2a crm-agent & pids+=($!)
PORT=9202 python -m agentplatform.a2a erp-agent & pids+=($!)
PORT=9203 python -m agentplatform.a2a underwriting-agent & pids+=($!)
uvicorn agentplatform.bff:app --port 8080 & pids+=($!)
echo "BFF on http://localhost:8080  (try: curl -X POST localhost:8080/loans/L-1001/underwrite)"
wait
