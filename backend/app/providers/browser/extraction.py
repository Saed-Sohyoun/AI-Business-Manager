"""Raw extraction contract and content limiting helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawLink:
    url: str
    text: str = ""


@dataclass
class RawPageExtraction:
    """Unvalidated extraction produced by a navigator backend."""

    requested_url: str
    final_url: str
    title: str = ""
    visible_text: str = ""
    links: list[RawLink] = field(default_factory=list)
    page_metadata: dict[str, str] = field(default_factory=dict)
    status_code: int | None = None
    redirect_count: int = 0
    content_length: int | None = None


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def limit_links(links: list[RawLink], max_links: int) -> tuple[list[RawLink], bool]:
    if len(links) <= max_links:
        return links, False
    return links[:max_links], True


def limit_metadata(
    metadata: dict[str, str],
    max_items: int,
) -> tuple[dict[str, str], bool]:
    if len(metadata) <= max_items:
        return metadata, False
    items = list(metadata.items())[:max_items]
    return dict(items), True


# Fixed Playwright extraction scripts — NEVER built from page/user input.
EXTRACT_LINKS_JS = """
(elements) => elements.slice(0, 500).map((el) => ({
  href: el.href || '',
  text: (el.innerText || '').trim().slice(0, 200)
}))
"""

EXTRACT_META_JS = """
(elements) => {
  const out = {};
  for (const el of elements.slice(0, 200)) {
    const name = el.getAttribute('name') || el.getAttribute('property') || el.getAttribute('http-equiv');
    const content = el.getAttribute('content');
    if (name && content && !(name in out)) {
      out[String(name).slice(0, 120)] = String(content).slice(0, 500);
    }
  }
  return out;
}
"""


def parse_content_length(headers: Any) -> int | None:
    if headers is None:
        return None
    try:
        value = headers.get("content-length")
    except Exception:  # noqa: BLE001
        return None
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
