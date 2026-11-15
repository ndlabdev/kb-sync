from __future__ import annotations

from pathlib import Path

import pytest

from kbsync.config import Settings
from kbsync.zendesk import Article

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://support.optisigns.com"


def make_article(article_id: int, title: str, body: str, updated_at: str = "2026-10-01T00:00:00Z") -> Article:
    slug_words = title.replace(" ", "-").replace("?", "")
    return Article(
        id=article_id,
        title=title,
        html_url=f"{BASE}/hc/en-us/articles/{article_id}-{slug_words}",
        body_html=body,
        updated_at=updated_at,
        edited_at=updated_at,
        section_id=1,
    )


@pytest.fixture
def youtube_article() -> Article:
    return make_article(333, "How do I add a YouTube video?", (FIXTURES / "article_youtube.html").read_text())


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        openai_api_key="test",
        vector_store_id="vs_test",
        vector_store_name="support-kb",
        openai_model="test-model",
        zendesk_base_url=BASE,
        locale="en-us",
        max_articles=None,
        output_dir=tmp_path / "articles",
        report_dir=tmp_path / "runs",
        chunk_max_tokens=700,
        upload_workers=4,
        dry_run=False,
        prune_deleted=True,
        gist_id=None,
        gist_token=None,
    )
