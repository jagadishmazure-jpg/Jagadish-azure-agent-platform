"""Azure AI Search index definition shared by the seeding script and the tests.

Hybrid (BM25 + HNSW vectors via integrated Azure OpenAI vectorizer) + semantic configuration
"default" + filterable temporal/ACL fields that `build_odata_filter` targets."""

from __future__ import annotations

import json
from typing import Any

from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from agentplatform.knowledge.search import Chunk

EMBED_DIMS = 1536  # text-embedding-3-small


def build_index(
    name: str, aoai_endpoint: str, embedding_deployment: str = "text-embedding-3-small"
) -> SearchIndex:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SimpleField(name="guideline_id", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="version", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="section", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(
            name="effective_from", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True
        ),
        SimpleField(
            name="effective_to", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True
        ),
        SimpleField(
            name="allowed_groups",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
        ),
        SimpleField(name="program", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="params_json", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBED_DIMS,
            vector_search_profile_name="hnsw-aoai",
        ),
    ]
    vector = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[
            VectorSearchProfile(name="hnsw-aoai", algorithm_configuration_name="hnsw", vectorizer_name="aoai")
        ],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name="aoai",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=aoai_endpoint,
                    deployment_name=embedding_deployment,
                    model_name="text-embedding-3-small",
                ),
            )
        ],
    )
    semantic = SemanticSearch(
        default_configuration_name="default",
        configurations=[
            SemanticConfiguration(
                name="default",
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="section")],
                ),
            )
        ],
    )
    return SearchIndex(name=name, fields=fields, vector_search=vector, semantic_search=semantic)


def to_document(c: Chunk, vector: list[float] | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "id": c.id.replace(".", "_"),  # keys: letters, digits, _ - =
        "guideline_id": c.guideline_id,
        "version": c.version,
        "title": c.title,
        "section": c.section,
        "content": c.content,
        "effective_from": f"{c.effective_from.isoformat()}T00:00:00Z",
        "effective_to": f"{c.effective_to.isoformat()}T00:00:00Z" if c.effective_to else None,
        "allowed_groups": list(c.allowed_groups),
        "program": c.program,
        "params_json": json.dumps(dict(c.params)),
    }
    if vector is not None:
        doc["content_vector"] = vector
    return doc
