"""Browser request/response types.

All extracted website content is UNTRUSTED DATA and must never be used as
system instructions.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BrowserFetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    metadata: dict[str, Any] = Field(default_factory=dict)
    include_links: bool = True
    include_metadata: bool = True
    include_text: bool = True


class BrowserLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    text: str = ""
    trust_level: Literal["untrusted"] = "untrusted"


class BrowserPageSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_url: str
    final_url: str
    title: str = ""
    visible_text: str = ""
    links: list[BrowserLink] = Field(default_factory=list)
    page_metadata: dict[str, str] = Field(default_factory=dict)
    status_code: int | None = None
    redirect_count: int = 0
    domain: str = ""
    text_truncated: bool = False
    links_truncated: bool = False
    metadata_truncated: bool = False
    content_length: int | None = None
    latency_ms: float = 0.0
    execution_id: str
    provider: str = "playwright"
    metadata: dict[str, Any] = Field(default_factory=dict)
    trust_level: Literal["untrusted"] = "untrusted"
    untrusted_content: Literal[True] = True
