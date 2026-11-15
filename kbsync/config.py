"""Runtime settings, read once from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int | None) -> int | None:
    value = _env(name)
    return int(value) if value is not None else default


@dataclass(frozen=True)
class Settings:
    # OpenAI
    openai_api_key: str | None
    vector_store_id: str | None
    vector_store_name: str
    openai_model: str

    # Source (Zendesk Help Center)
    zendesk_base_url: str
    locale: str
    max_articles: int | None  # None = fetch everything

    # Processing
    output_dir: Path
    report_dir: Path
    chunk_max_tokens: int
    upload_workers: int
    dry_run: bool
    prune_deleted: bool

    # Optional: publish the run report to a GitHub Gist (a public, no-login link to the last run)
    gist_id: str | None
    gist_token: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            # API_KEY is accepted as an alias so `docker run -e API_KEY=...` works as written in the brief.
            openai_api_key=_env("OPENAI_API_KEY") or _env("API_KEY"),
            vector_store_id=_env("VECTOR_STORE_ID"),
            vector_store_name=_env("VECTOR_STORE_NAME", "support-kb") or "support-kb",
            openai_model=_env("OPENAI_MODEL", "gpt-6-luna") or "gpt-6-luna",
            zendesk_base_url=(_env("ZENDESK_BASE_URL", "https://support.optisigns.com") or "").rstrip("/"),
            locale=_env("ZENDESK_LOCALE", "en-us") or "en-us",
            max_articles=_env_int("MAX_ARTICLES", None),
            output_dir=Path(_env("OUTPUT_DIR", "articles") or "articles"),
            report_dir=Path(_env("REPORT_DIR", "runs") or "runs"),
            chunk_max_tokens=_env_int("CHUNK_MAX_TOKENS", 700) or 700,
            upload_workers=_env_int("UPLOAD_WORKERS", 8) or 8,
            dry_run=_env_bool("DRY_RUN", False),
            prune_deleted=_env_bool("PRUNE_DELETED", True),
            gist_id=_env("GIST_ID"),
            gist_token=_env("GIST_TOKEN"),
        )

    def validate(self) -> None:
        if not self.dry_run and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY (or API_KEY) is required unless DRY_RUN=true")
        if not 100 <= self.chunk_max_tokens <= 780:
            # Must stay under the 800-token static chunk size we ask OpenAI for, so 1 file == 1 chunk.
            raise ValueError("CHUNK_MAX_TOKENS must be between 100 and 780")
