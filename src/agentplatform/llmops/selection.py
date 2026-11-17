"""Per-request canary selection. APIM sets the headers; the BFF stores them here for the agents."""

from __future__ import annotations

from contextvars import ContextVar

REQUEST_PROMPT_REF: ContextVar[str] = ContextVar("aap_prompt_ref", default="")
REQUEST_MODEL: ContextVar[str] = ContextVar("aap_model_deployment", default="")
