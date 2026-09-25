"""Create/refresh the Azure AI Search indexes (investor guidelines + HR policies) and upload the
synthetic corpora with embeddings.  Runs as an azd `postprovision` hook.

    python scripts/seed_search_index.py --dry-run     # offline: print index JSON + first document
    python scripts/seed_search_index.py               # needs AZURE_SEARCH_ENDPOINT, AZURE_OPENAI_ENDPOINT

The caller identity needs "Search Service Contributor" + "Search Index Data Contributor" on the search
service and "Cognitive Services OpenAI User" on the Foundry account (granted to the deployer by Bicep)."""

from __future__ import annotations

import argparse
import json
import sys

from agentplatform.config import azure_credential, get_settings
from agentplatform.knowledge.index_schema import build_index, to_document
from agentplatform.knowledge.search import load_corpus


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    s = get_settings()
    targets = {s.search_guidelines_index: "guidelines", s.search_hr_index: "hr_policies"}
    aoai = s.azure_openai_endpoint or "https://<foundry-account>.openai.azure.com"

    if a.dry_run or not s.search_endpoint:
        idx = build_index(s.search_guidelines_index, aoai, s.embedding_deployment)
        print(json.dumps(idx.as_dict(), indent=2, default=str)[:4000])
        print(json.dumps(to_document(load_corpus("guidelines")[0]), indent=2))
        if not a.dry_run:
            print("AZURE_SEARCH_ENDPOINT not set; dry run only.", file=sys.stderr)
        return 0

    from azure.identity import get_bearer_token_provider
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from openai import AzureOpenAI

    cred = azure_credential(s)
    embed = AzureOpenAI(
        azure_endpoint=aoai,
        api_version="2024-10-21",
        azure_ad_token_provider=get_bearer_token_provider(
            cred, "https://cognitiveservices.azure.com/.default"
        ),
    )
    admin = SearchIndexClient(s.search_endpoint, cred)
    for index_name, corpus in targets.items():
        admin.create_or_update_index(build_index(index_name, aoai, s.embedding_deployment))
        chunks = load_corpus(corpus)
        vectors = embed.embeddings.create(
            model=s.embedding_deployment, input=[c.content for c in chunks]
        ).data
        docs = [to_document(c, v.embedding) for c, v in zip(chunks, vectors, strict=True)]
        results = SearchClient(s.search_endpoint, index_name, cred).merge_or_upload_documents(docs)
        print(f"{index_name}: {sum(r.succeeded for r in results)}/{len(docs)} documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
