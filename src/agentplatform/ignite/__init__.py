"""Ignite 2026 portfolio module: Copilot harness, Toolboxes, and durable agents.

Offline stand-ins only. Read ``assumptions.py`` before treating a behavior as a product fact.
The two sources are ``SOURCES`` in that module.
"""

from agentplatform.ignite.assumptions import ASSUMPTIONS, MATURITY, SOURCES

__all__ = ["ASSUMPTIONS", "MATURITY", "SOURCES", "demo"]


def demo() -> None:
    import asyncio

    asyncio.run(_demo())


async def _demo() -> None:
    from agentplatform.ignite.durable import (
        DurableWorkflowWorker,
        InquiryLog,
        ModelClient,
        TaskHub,
        billed_tokens,
    )
    from agentplatform.ignite.harness import CopilotHarness
    from agentplatform.ignite.skills import commercial_loan_agent
    from agentplatform.ignite.toolbox import LoanToolbox

    toolbox = LoanToolbox()
    harness = CopilotHarness(toolbox, commercial_loan_agent())
    paused = await harness.start("APP-4401")
    print(
        f"harness status={paused.status} compute_held={paused.compute_held} "
        f"bookings={toolbox.metrics['bookings']} hard_pulls={toolbox.metrics['hard_pulls']}"
    )
    done = await harness.resume(paused.run_id, officer_id="officer-lee", approved=True)
    print(
        f"harness status={done.status} outcome={done.state['outcome']} "
        f"bookings={toolbox.metrics['bookings']} handler_runs={harness.handler_runs}"
    )
    voice = await harness.voice_turn("What is the status of APP-4401?")
    print(f"voice maturity={voice['maturity']} barged_in={voice['barged_in']} bookings={voice['bookings']}")

    bureau = InquiryLog()
    hub = TaskHub()
    worker_a = DurableWorkflowWorker("worker-a", hub, ModelClient(), bureau)
    waiting = worker_a.start("APP-4401")
    print(
        f"durable status={waiting['status']} compute_held={worker_a.compute_held} "
        f"billed_tokens={billed_tokens(waiting)} hard_pulls={bureau.hard_pulls}"
    )
    worker_b = DurableWorkflowWorker("worker-b", TaskHub.loads(hub.export()), ModelClient(), bureau)
    finished = worker_b.signal(waiting["instance_id"], officer_id="officer-lee", approved=True)
    print(
        "durable resumed_on=worker-b "
        f"model_calls={worker_b.model.invocations} billed_tokens={billed_tokens(finished)} "
        f"hard_pulls={bureau.hard_pulls}"
    )
