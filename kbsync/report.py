"""Run report: the 'last run artefact' the brief asks for, plus the log summary line."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .config import Settings

log = logging.getLogger(__name__)


@dataclass
class RunReport:
    started_at: str
    dry_run: bool
    vector_store_id: str | None = None
    finished_at: str | None = None
    duration_s: float | None = None
    fetched: int = 0
    fetch_complete: bool = True
    corpus_files: int = 0  # markdown files written
    corpus_chunks: int = 0  # chunks across the whole corpus
    added: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0
    failed: int = 0
    files_uploaded: int = 0
    chunks_embedded: int = 0  # 1 uploaded file == 1 chunk (see chunker.py)
    files_removed: int = 0
    index_status: dict[str, int] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)
    articles: list[dict] = field(default_factory=list)

    @classmethod
    def start(cls, dry_run: bool) -> "RunReport":
        return cls(started_at=_now(), dry_run=dry_run)

    def record(self, article_id: int, slug: str, action: str, chunks: int = 0) -> None:
        self.articles.append({"id": article_id, "slug": slug, "action": action, "chunks": chunks})

    def error(self, article_id: int | None, stage: str, exc: BaseException) -> None:
        self.errors.append({"article_id": article_id, "stage": stage, "error": f"{type(exc).__name__}: {exc}"})

    def finish(self) -> None:
        self.finished_at = _now()
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.finished_at)
        self.duration_s = round((end - start).total_seconds(), 1)

    @property
    def ok(self) -> bool:
        return self.failed == 0 and not any(e["stage"] == "fatal" for e in self.errors)

    def summary_line(self) -> str:
        return (
            f"RUN SUMMARY added={self.added} updated={self.updated} skipped={self.skipped} "
            f"deleted={self.deleted} failed={self.failed} | files_uploaded={self.files_uploaded} "
            f"chunks_embedded={self.chunks_embedded} files_removed={self.files_removed} | "
            f"corpus={self.corpus_files} files/{self.corpus_chunks} chunks | "
            f"duration={self.duration_s}s dry_run={self.dry_run}"
        )


GIST_API = "https://api.github.com/gists"
HISTORY_FILE = "history.log"
LATEST_FILE = "latest.json"
HISTORY_KEEP = 400  # lines; one per run, so more than a year of daily runs


def save_report(report: RunReport, settings: Settings, session=None) -> str | None:
    """Write runs/last_run.json (+ a timestamped copy). If a Gist is configured, also publish
    the run there and return its URL: a no-login link to the last run and the run history."""
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    body = json.dumps(asdict(report), indent=2, ensure_ascii=False)
    stamp = report.started_at.replace(":", "").replace("-", "")[:15]
    (settings.report_dir / "last_run.json").write_text(body, encoding="utf-8")
    (settings.report_dir / f"run-{stamp}.json").write_text(body, encoding="utf-8")

    if not (settings.gist_id and settings.gist_token):
        return None
    try:
        return publish_to_gist(report, settings.gist_id, settings.gist_token, session)
    except Exception as exc:  # publishing the report must never fail the sync itself
        log.warning("could not publish run report to gist: %s", exc)
        return None


def publish_to_gist(report: RunReport, gist_id: str, token: str, session=None) -> str:
    """Overwrite latest.json and append one summary line to history.log.
    The Gist keeps every version under Revisions, so each daily run stays visible."""
    import requests

    http = session or requests.Session()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    current = http.get(f"{GIST_API}/{gist_id}", headers=headers, timeout=30)
    current.raise_for_status()
    gist = current.json()
    old_history = ((gist.get("files") or {}).get(HISTORY_FILE) or {}).get("content") or ""
    line = f"{report.started_at} {report.summary_line()}"
    history = "\n".join((old_history.strip().splitlines() + [line])[-HISTORY_KEEP:]) + "\n"

    latest = asdict(report)
    # Skipped articles are the unchanged majority; list only what this run touched.
    latest["articles"] = [a for a in report.articles if a["action"] != "skipped"]
    payload = {
        "description": "kb-sync: daily help-center -> vector store sync, last run + history",
        "files": {
            LATEST_FILE: {"content": json.dumps(latest, indent=2, ensure_ascii=False)},
            HISTORY_FILE: {"content": history},
        },
    }
    updated = http.patch(f"{GIST_API}/{gist_id}", headers=headers, json=payload, timeout=30)
    updated.raise_for_status()
    url = updated.json().get("html_url") or gist.get("html_url") or f"https://gist.github.com/{gist_id}"
    log.info("run report published: %s", url)
    return url


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
