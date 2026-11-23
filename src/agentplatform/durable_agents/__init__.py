"""Offline stand-in for the Durable Task extension for Microsoft Agent Framework.

Completed agent calls are replayed from the checkpoint and are not executed again.
The import paths on Microsoft Learn are not in the pinned packages; see the module
docstrings for the `[verify]` notes.
"""

from agentplatform.durable_agents.loan import build_loan_app, loan_review_orchestration
from agentplatform.durable_agents.runtime import DurableAgentApp, JsonHistoryStore

__all__ = [
    "DurableAgentApp",
    "JsonHistoryStore",
    "build_loan_app",
    "loan_review_orchestration",
]
