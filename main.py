"""Entry point: run one sync and exit (0 = success, 1 = something failed).

    python main.py                 # full sync
    DRY_RUN=true python main.py    # scrape + clean + chunk only, no OpenAI calls
"""

from __future__ import annotations

import logging
import sys

from kbsync.config import Settings
from kbsync.pipeline import run
from kbsync.report import RunReport, save_report
from kbsync.zendesk import build_session, fetch_articles


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    for noisy in ("httpx", "httpx2", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    log = logging.getLogger("main")

    settings = Settings.from_env()
    try:
        settings.validate()
    except ValueError as exc:  # missing or invalid configuration: say what to fix, no traceback
        log.error("configuration error: %s", exc)
        return 1

    report: RunReport | None = None
    try:
        session = build_session()

        def fetch():
            return fetch_articles(session, settings.zendesk_base_url, settings.locale, settings.max_articles)

        store = None
        if not settings.dry_run:
            from openai import OpenAI

            from kbsync.vector_store import OpenAIVectorStore

            client = OpenAI(api_key=settings.openai_api_key, max_retries=5)
            store = OpenAIVectorStore.connect(client, settings.vector_store_id, settings.vector_store_name)

        report = run(settings, fetch, store)
    except Exception as exc:
        log.exception("sync aborted")
        report = report or RunReport.start(dry_run=settings.dry_run)
        report.error(None, "fatal", exc)
        report.finish()

    url = save_report(report, settings)
    log.info(report.summary_line())
    if url:
        log.info("last run artefact: %s", url)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
