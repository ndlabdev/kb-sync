"""Read published articles from a public Zendesk Help Center.

The Help Center API returns only the article body (no site header, nav, footer or ads),
which is why we read the API instead of crawling rendered HTML pages.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

PAGE_SIZE = 100  # Zendesk maximum


@dataclass(frozen=True)
class Article:
    id: int
    title: str
    html_url: str
    body_html: str
    updated_at: str
    edited_at: str | None
    section_id: int | None

    @property
    def slug(self) -> str:
        """`<id>-<readable-slug>`: the id keeps names unique, the words keep them readable."""
        last_segment = self.html_url.rstrip("/").rsplit("/", 1)[-1]
        readable = last_segment.split("-", 1)[1] if last_segment.startswith(f"{self.id}-") else self.title
        return f"{self.id}-{slugify(readable)}"

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Article":
        return cls(
            id=int(raw["id"]),
            title=(raw.get("title") or raw.get("name") or "").strip(),
            html_url=raw["html_url"],
            body_html=raw.get("body") or "",
            updated_at=raw.get("updated_at") or "",
            edited_at=raw.get("edited_at"),
            section_id=raw.get("section_id"),
        )


def slugify(text: str, max_len: int = 80) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len].rstrip("-") or "article"


class HttpSession(Protocol):
    def get(self, url: str, params: dict | None = None, timeout: float | None = None) -> Any: ...


def build_session() -> requests.Session:
    """Session with retries on 429/5xx; urllib3 honours Retry-After for 429."""
    retry = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "kb-sync/1.0", "Accept": "application/json"})
    return session


def fetch_articles(
    session: HttpSession,
    base_url: str,
    locale: str = "en-us",
    limit: int | None = None,
) -> tuple[list[Article], bool]:
    """Return (articles, complete).

    `complete` is False when we stopped early because of `limit`; the caller must not
    treat missing articles as deleted in that case.
    """
    url: str | None = f"{base_url}/api/v2/help_center/{locale}/articles.json"
    params: dict | None = {"per_page": PAGE_SIZE, "sort_by": "position", "sort_order": "asc"}
    articles: list[Article] = []
    seen: set[int] = set()

    while url:
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        for raw in payload.get("articles", []):
            if raw.get("draft"):
                continue
            article = Article.from_api(raw)
            if article.id in seen:  # offset pagination can repeat items if the list shifts mid-scan
                continue
            seen.add(article.id)
            articles.append(article)
            if limit is not None and len(articles) >= limit:
                log.info("fetched %d articles (limit reached)", len(articles))
                return articles, False
        url = payload.get("next_page")
        params = None  # next_page already carries the query string
    log.info("fetched %d articles", len(articles))
    return articles, True
