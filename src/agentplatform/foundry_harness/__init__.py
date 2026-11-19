"""Offline stand-in for Foundry hosted agents: the Microsoft Copilot harness and Toolboxes.

The harness owns the agent loop and the sandbox. Callers supply knowledge, skills and tools.
Preview API shapes that are not in the pinned SDKs are marked ``[verify]``.
"""

from agentplatform.foundry_harness.harness import CopilotHarness
from agentplatform.foundry_harness.loan import load_agent_definition, load_skill, start_loan_review
from agentplatform.foundry_harness.toolbox import MockToolboxService

__all__ = [
    "CopilotHarness",
    "MockToolboxService",
    "load_agent_definition",
    "load_skill",
    "start_loan_review",
]
