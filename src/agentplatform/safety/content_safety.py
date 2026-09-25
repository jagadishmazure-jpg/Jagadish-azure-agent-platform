"""Content Safety gate for what users send and for what we retrieve or extract (indirect prompt injection).

Offline: deterministic pattern checks. Azure: `azure-ai-contentsafety` analyze_text for harm
categories + Prompt Shields REST (`text:shieldPrompt`, api-version 2024-09-01) for attacks, both with
Entra ID (managed identity) — no keys.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agentplatform.config import Settings, azure_credential, get_settings

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)",
    r"disregard (the )?(system|previous) (prompt|instructions)",
    r"you are now (?!approved)",
    r"\bsystem prompt\b",
    r"reveal (your|the) (instructions|prompt|secrets?)",
    r"approve (this|the) (loan|file) (regardless|without)",
    r"exfiltrate|send (all|the) (data|records) to",
    r"\bBEGIN (SYSTEM|ADMIN) OVERRIDE\b",
]
HARM_PATTERNS = {"violence": [r"\bkill (you|him|her|them)\b"], "self_harm": [r"\bhurt myself\b"]}
SEVERITY_BLOCK = 4  # Content Safety severities 0/2/4/6; block at medium+


@dataclass
class SafetyVerdict:
    allowed: bool
    attack_detected: bool = False
    categories: dict[str, int] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


class ContentSafetyGate:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    # ---------------- offline -----------------
    @staticmethod
    def _offline(text: str) -> SafetyVerdict:
        reasons, cats = [], {}
        low = text.lower()
        attack = any(re.search(p, low, re.I) for p in INJECTION_PATTERNS)
        if attack:
            reasons.append("prompt-injection pattern")
        for cat, pats in HARM_PATTERNS.items():
            if any(re.search(p, low) for p in pats):
                cats[cat] = 4
                reasons.append(f"harm:{cat}")
        blocked = attack or any(v >= SEVERITY_BLOCK for v in cats.values())
        return SafetyVerdict(not blocked, attack, cats, reasons)

    # ---------------- azure -----------------
    def _azure_harm(self, text: str) -> dict[str, int]:
        from azure.ai.contentsafety import ContentSafetyClient
        from azure.ai.contentsafety.models import AnalyzeTextOptions

        client = ContentSafetyClient(self.settings.content_safety_endpoint, azure_credential(self.settings))
        result = client.analyze_text(AnalyzeTextOptions(text=text[:10000]))
        return {c.category.lower(): int(c.severity or 0) for c in result.categories_analysis}

    def _azure_shield(self, user_prompt: str, documents: list[str]) -> tuple[bool, list[bool]]:
        import httpx

        token = (
            azure_credential(self.settings).get_token("https://cognitiveservices.azure.com/.default").token
        )
        url = f"{self.settings.content_safety_endpoint.rstrip('/')}/contentsafety/text:shieldPrompt"
        resp = httpx.post(
            url,
            params={"api-version": "2024-09-01"},
            headers={"Authorization": f"Bearer {token}"},
            json={"userPrompt": user_prompt, "documents": documents[:5]},
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()
        return (
            bool(body.get("userPromptAnalysis", {}).get("attackDetected")),
            [bool(d.get("attackDetected")) for d in body.get("documentsAnalysis", [])],
        )

    # ---------------- public -----------------
    def check_inbound(self, text: str) -> SafetyVerdict:
        if not self.settings.azure:
            return self._offline(text)
        cats = self._azure_harm(text)
        attack, _ = self._azure_shield(text, [])
        blocked = attack or any(v >= SEVERITY_BLOCK for v in cats.values())
        return SafetyVerdict(not blocked, attack, cats, ["prompt shield"] if attack else [])

    def check_documents(self, docs: list[str]) -> list[SafetyVerdict]:
        """Indirect-injection screen for retrieved passages and OCR text before packing."""
        if not self.settings.azure:
            return [self._offline(d) for d in docs]
        verdicts: list[SafetyVerdict] = []
        for i in range(0, len(docs), 5):
            batch = docs[i : i + 5]
            _, flags = self._azure_shield("", batch)
            verdicts += [SafetyVerdict(not f, f, {}, ["document attack"] if f else []) for f in flags]
        return verdicts


def get_safety_gate(settings: Settings | None = None) -> ContentSafetyGate:
    return ContentSafetyGate(settings)
