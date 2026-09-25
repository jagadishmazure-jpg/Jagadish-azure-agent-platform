"""OpenTelemetry backbone. Azure Monitor (App Insights) when a connection string is present,
console exporter when AAP_TRACE_CONSOLE=1, otherwise the SDK provider with no exporter."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace

_configured = False


def configure_tracing(service_name: str, connection_string: str | None = None) -> str:
    """Idempotent. Returns which backend was configured."""
    global _configured
    if _configured:
        return "already-configured"
    _configured = True
    conn = connection_string or os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    if conn:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=conn)
        return "azure-monitor"
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if os.environ.get("AAP_TRACE_CONSOLE") == "1":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return "console" if os.environ.get("AAP_TRACE_CONSOLE") == "1" else "sdk"


tracer = trace.get_tracer("agentplatform")


@contextmanager
def span(name: str, **attrs: Any):
    """Span with the doctrine's minimum attributes: tenant, thread, node, tool, tokens, cost, identity."""
    with tracer.start_as_current_span(name) as s:
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(f"aap.{k}", v if isinstance(v, str | int | float | bool) else str(v))
        yield s
