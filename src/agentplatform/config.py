"""Runtime settings. Offline (mocks) by default; `AAP_MODE=azure` switches every adapter to Azure.

Platform layer: one place that maps azd outputs (env vars) to adapters, so no agent reads env directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    mode: str = "offline"
    tenant_id: str = "contoso-mortgage"
    foundry_project_endpoint: str = ""
    foundry_model: str = "gpt-5-mini"
    foundry_fallback_model: str = ""
    azure_openai_endpoint: str = ""
    embedding_deployment: str = "text-embedding-3-small"
    search_endpoint: str = ""
    search_guidelines_index: str = "investor-guidelines"
    search_hr_index: str = "hr-policies"
    docintel_endpoint: str = ""
    content_safety_endpoint: str = ""
    cosmos_endpoint: str = ""
    cosmos_database: str = "agentplatform"
    servicebus_namespace: str = ""
    managed_identity_client_id: str = ""
    appinsights_connection_string: str = ""
    checkpoint_dir: str = ".checkpoints"
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def azure(self) -> bool:
        return self.mode == "azure"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            mode=_env("AAP_MODE", "offline").lower(),
            tenant_id=_env("AAP_TENANT_ID", "contoso-mortgage"),
            foundry_project_endpoint=_env("FOUNDRY_PROJECT_ENDPOINT"),
            foundry_model=_env("FOUNDRY_MODEL", "gpt-5-mini"),
            foundry_fallback_model=_env("FOUNDRY_FALLBACK_MODEL"),
            azure_openai_endpoint=_env("AZURE_OPENAI_ENDPOINT"),
            embedding_deployment=_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"),
            search_endpoint=_env("AZURE_SEARCH_ENDPOINT"),
            search_guidelines_index=_env("AZURE_SEARCH_GUIDELINES_INDEX", "investor-guidelines"),
            search_hr_index=_env("AZURE_SEARCH_HR_INDEX", "hr-policies"),
            docintel_endpoint=_env("AZURE_DOCINTEL_ENDPOINT"),
            content_safety_endpoint=_env("AZURE_CONTENT_SAFETY_ENDPOINT"),
            cosmos_endpoint=_env("AZURE_COSMOS_ENDPOINT"),
            cosmos_database=_env("AZURE_COSMOS_DATABASE", "agentplatform"),
            servicebus_namespace=_env("AZURE_SERVICEBUS_NAMESPACE"),
            managed_identity_client_id=_env("AZURE_CLIENT_ID"),
            appinsights_connection_string=_env("APPLICATIONINSIGHTS_CONNECTION_STRING"),
            checkpoint_dir=_env("AAP_CHECKPOINT_DIR", ".checkpoints"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


def azure_credential(settings: Settings | None = None):
    """Managed identity in Container Apps (AZURE_CLIENT_ID = user-assigned MI), dev creds locally.

    Never keys: every Bicep resource disables local auth where the service allows it.
    """
    from azure.identity import DefaultAzureCredential

    s = settings or get_settings()
    return DefaultAzureCredential(managed_identity_client_id=s.managed_identity_client_id or None)
