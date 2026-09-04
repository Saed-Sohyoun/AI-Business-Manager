"""Provider-agnostic search request/response types.

IMPORTANT: All search result content is UNTRUSTED DATA.
It must never be treated as system instructions or executable directives.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    max_results: int | None = Field(default=None, ge=1, le=20)
    search_depth: Literal["basic", "advanced"] | None = None
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, ge=1.0)


class SearchResult(BaseModel):
    """A single web search hit.

    `trust_level` is always `untrusted`. Callers must treat title/snippet/content
    as external data only — never as instructions to the system or agents.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    normalized_url: str
    snippet: str
    domain: str
    relevance_score: float | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    trust_level: Literal["untrusted"] = "untrusted"


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    results: list[SearchResult]
    provider: str = "tavily"
    result_count: int = 0
    duplicates_removed: int = 0
    invalid_urls_removed: int = 0
    estimated_cost: Decimal = Decimal("0")
    latency_ms: float = 0.0
    attempts: int = 1
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Explicit reminder for downstream consumers / LLM context builders
    untrusted_content: Literal[True] = True
