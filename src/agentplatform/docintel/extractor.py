"""Azure AI Document Intelligence (v4.0, API 2024-11-30) prebuilt models for mortgage documents.

OCR runs before any LLM sees a document: agents reason over field-value pairs + confidence, never
raw pixels. Offline mode returns fixture field-value pairs with confidences in the same shape."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentplatform.config import Settings, azure_credential, get_settings

PREBUILT_MODELS = {
    "paystub": "prebuilt-payStub.us",
    "w2": "prebuilt-tax.us.w2",
    "bank_statement": "prebuilt-bankStatement.us",
}
FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class FieldValue:
    value: Any
    confidence: float


@dataclass
class ExtractedDocument:
    doc_id: str
    doc_type: str
    model_id: str
    fields: dict[str, FieldValue] = field(default_factory=dict)
    pages: int = 1

    def get(self, name: str, default: Any = None) -> Any:
        f = self.fields.get(name)
        return f.value if f else default

    def low_confidence(self, threshold: float = 0.80) -> list[str]:
        return sorted(k for k, v in self.fields.items() if v.confidence < threshold)


class DocumentExtractor:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.fail_next = 0  # chaos hook

    def extract(self, doc_id: str, doc_type: str, source: str | bytes | None = None) -> ExtractedDocument:
        model_id = PREBUILT_MODELS[doc_type]
        if self.fail_next > 0:
            self.fail_next -= 1
            from agentplatform.harness.resilience import TransientError

            raise TransientError("document intelligence: simulated 429")
        if not self.settings.azure:
            return self._fixture(doc_id, doc_type, model_id)
        return self._azure(doc_id, doc_type, model_id, source)

    def _fixture(self, doc_id: str, doc_type: str, model_id: str) -> ExtractedDocument:
        data = json.loads((FIXTURES / f"{doc_id}.json").read_text(encoding="utf-8"))
        return ExtractedDocument(
            doc_id,
            doc_type,
            model_id,
            {k: FieldValue(v["value"], v["confidence"]) for k, v in data["fields"].items()},
            data.get("pages", 1),
        )

    def _azure(
        self, doc_id: str, doc_type: str, model_id: str, source: str | bytes | None
    ) -> ExtractedDocument:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

        client = DocumentIntelligenceClient(self.settings.docintel_endpoint, azure_credential(self.settings))
        body = (
            AnalyzeDocumentRequest(bytes_source=source)
            if isinstance(source, bytes)
            else AnalyzeDocumentRequest(url_source=source)
        )
        result = client.begin_analyze_document(model_id, body).result()
        fields: dict[str, FieldValue] = {}
        if result.documents:
            for name, f in (result.documents[0].fields or {}).items():
                value = (
                    f.get("valueCurrency", {}).get("amount")
                    if f.get("valueCurrency")
                    else f.get("valueNumber")
                    or f.get("valueDate")
                    or f.get("valueString")
                    or f.get("content")
                )
                fields[name] = FieldValue(value, float(f.get("confidence") or 0.0))
        return ExtractedDocument(doc_id, doc_type, model_id, fields, len(result.pages or []))


def get_extractor(settings: Settings | None = None) -> DocumentExtractor:
    return DocumentExtractor(settings)
