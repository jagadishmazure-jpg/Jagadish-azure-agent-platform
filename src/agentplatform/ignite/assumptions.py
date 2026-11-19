"""What this offline module copies from the Ignite 2026 sources, and what it does not.

The maturity map is taken from the Foundry Agent Service post (November 2026) and the
Durable Task extension article on Microsoft Learn. Anything the sources do not specify
is listed in ``ASSUMPTIONS`` and repeated in the module README. This package does not
call Foundry, the Durable Task Scheduler, or a model.
"""

from __future__ import annotations

SOURCES: dict[str, str] = {
    "foundry_agent_service_ignite_2026": (
        "https://devblogs.microsoft.com/foundry/whats-new-in-foundry-agent-service-at-ignite-2026/"
    ),
    "durable_task_microsoft_agent_framework": (
        "https://learn.microsoft.com/en-us/azure/durable-task/sdks/durable-agents-microsoft-agent-framework"
    ),
}

# Labels use the words in those two sources. "coming_soon" is the post's phrase for
# Toolbox support of Web Search, which is already GA on prompt agents.
MATURITY: dict[str, str] = {
    "copilot_harness": "public_preview",
    "voice": "ga",
    "a2a_tool": "ga",
    "computer_use": "ga",
    "browser_automation": "ga",
    "browser_private_network": "preview",
    "toolbox_tool_policies": "preview",
    "web_search_on_prompt_agents": "ga",
    "web_search_toolbox": "coming_soon",
    "work_iq": "preview",
    "fabric_iq": "preview",
    "hosted_agent_long_running_recovery": "ga",
    "hosted_agent_egress_controls": "ga",
    "durable_task_extension": "ga",
}

ASSUMPTIONS: tuple[str, ...] = (
    "The Foundry post presents the Microsoft Copilot harness and hosted agents as two authoring choices: a prompt agent whose loop and sandbox Microsoft runs, or your own code and orchestration on the hosted-agent runtime. This mock places a hosted agent definition on the harness (the platform still owns the loop and the sandbox; the bank supplies knowledge, skills, and tools). The post does not say a hosted agent executes inside the Copilot harness.",
    "The harness stand-in runs the bank's skills in a fixed order. The public-preview harness uses a model to choose the next tool call. There is no model call on this path.",
    "Hosted-agent long-running recovery reruns the handler, so the application has to save progress and make side effects idempotent. Idle sessions release compute and keep saved state (idle timeout is configurable from 2 minutes to 4 hours, 15 minutes by default). This mock reruns the handler and skips skills already recorded on the session. It does not implement the timeout.",
    "Network egress controls are documented for hosted agents and are enforced outside the sandbox. The harness section of the post says Microsoft runs the sandbox, but it does not describe those egress controls for harness agents. This mock blocks egress for the whole demo.",
    "Toolbox tool-policy shape is not specified (policies are in preview). The allow-list in this package is a stand-in. The same is true of the monitoring dashboard: the post names it, and the counters here are in-memory.",
    "Web Search is generally available for prompt agents, and the post says Toolbox support is coming soon, so this Toolbox does not expose Web Search. Work IQ and Fabric IQ are preview integrations and are not implemented.",
    "Voice barge-in is a flag that drops the in-progress spoken reply. The post describes interrupt, pause, and a change of direction, and native telephony. It does not publish the event schema.",
    "Browser automation's access to applications behind private virtual networks is preview. Session records flag it and do not open a socket. Recordings are labeled as customer-owned storage and are not written anywhere.",
    "The credit-officer gate is a banking control in this scenario. The harness post's named human-oversight feature is browser automation Live View and Take control, which this mock also implements. The post does not describe a credit-decision approval API.",
    "The Learn article says each durable agent call is checkpointed and that completed agent calls are not re-executed on recovery. It does not describe a billing API. This mock treats a skipped re-execution as a skipped re-bill, because another model invocation is what would add another model charge. Durable Task Scheduler charges are not modeled. Token counts are fixed per agent so tests can assert them; they are not Azure prices.",
    "Session TTL (default 14 days, minimum deletion delay 5 minutes, .NET only in the article) and the 1 MB Durable Task Scheduler entity-state limit are not implemented.",
    "Checkpoint JSON is this package's format, not the Durable Task Scheduler history table. Nothing dials a scheduler. Hosting in the article is Azure Functions (AgentFunctionApp) or your own worker against the scheduler; both are named in the docs and neither is started here.",
    "Foundry hosted-agent recovery reruns the handler. Durable Task does not re-execute a completed agent call. Those are different product behaviors and this package keeps them on separate types.",
)
