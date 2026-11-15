"""One sync run: fetch -> clean -> chunk -> diff against the vector store -> apply delta."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from .chunker import Chunk, chunk_document
from .cleaner import MarkdownDoc, anchor_map, to_markdown
from .config import Settings
from .delta import build_plan
from .report import RunReport
from .vector_store import VectorStoreGateway
from .zendesk import Article

log = logging.getLogger(__name__)

Fetcher = Callable[[], tuple[list[Article], bool]]


def run(settings: Settings, fetch: Fetcher, store: VectorStoreGateway | None) -> RunReport:
    """`store=None` means dry run: everything except talking to OpenAI."""
    report = RunReport.start(dry_run=store is None)
    report.vector_store_id = store.vector_store_id if store else None

    # 1. Fetch
    articles, complete = fetch()
    report.fetched, report.fetch_complete = len(articles), complete

    # 2. Clean -> Markdown files on disk
    known_slugs = {a.id: a.slug for a in articles}
    known_anchors: dict[int, dict[str, str]] = {}
    for article in articles:  # first pass: heading anchors, so cross-article #fragments resolve
        try:
            known_anchors[article.id] = anchor_map(article)
        except Exception:
            known_anchors[article.id] = {}
    docs: dict[int, MarkdownDoc] = {}
    for article in articles:
        try:
            docs[article.id] = to_markdown(article, settings.zendesk_base_url, known_slugs, known_anchors)
        except Exception as exc:
            log.exception("convert failed for article %s", article.id)
            report.failed += 1
            report.error(article.id, "convert", exc)
    _write_markdown(settings.output_dir, docs.values(), replace_all=complete)
    report.corpus_files = len(docs)

    # 3. Chunk
    chunks: dict[int, list[Chunk]] = {aid: chunk_document(doc, settings.chunk_max_tokens) for aid, doc in docs.items()}
    report.corpus_chunks = sum(len(c) for c in chunks.values())
    log.info("corpus: %d markdown files, %d chunks", report.corpus_files, report.corpus_chunks)

    # 4. Diff against what is already indexed
    remote = store.list_files() if store else []
    plan = build_plan(
        {aid: doc.content_hash for aid, doc in docs.items()},
        remote,
        # Only prune when we saw the whole Help Center; a capped or partial fetch must never delete.
        prune_missing=settings.prune_deleted and complete,
        source_ids={a.id for a in articles},
    )
    log.info(
        "plan: add=%d update=%d skip=%d delete=%d cleanup=%d",
        len(plan.add), len(plan.update), len(plan.skip), len(plan.delete), len(plan.cleanup),
    )
    for aid in plan.skip:
        report.skipped += 1
        report.record(aid, docs[aid].slug, "skipped", len(chunks[aid]))

    if store is None:
        for aid in plan.add + list(plan.update):
            report.record(aid, docs[aid].slug, "would_upload", len(chunks[aid]))
        report.added, report.updated = len(plan.add), len(plan.update)
        report.finish()
        return report

    # 5. Upload new + changed articles (new version first, old version removed afterwards)
    to_remove: list[str] = list(plan.cleanup)
    jobs = [(aid, "added") for aid in plan.add] + [(aid, "updated") for aid in plan.update]
    with ThreadPoolExecutor(max_workers=settings.upload_workers) as pool:
        futures = {pool.submit(store.upload_article, docs[aid], chunks[aid]): (aid, action) for aid, action in jobs}
        for future in as_completed(futures):
            aid, action = futures[future]
            try:
                file_ids = future.result()
            except Exception as exc:
                log.error("upload failed for %s: %s", docs[aid].slug, exc)
                report.failed += 1
                report.error(aid, "upload", exc)
                continue
            report.files_uploaded += len(file_ids)
            report.chunks_embedded += len(file_ids)
            setattr(report, action, getattr(report, action) + 1)
            report.record(aid, docs[aid].slug, action, len(file_ids))
            log.info("%s %s (%d chunks)", action, docs[aid].slug, len(file_ids))
            if action == "updated":
                to_remove.extend(plan.update[aid])

    # 6. Deletions: articles gone from the Help Center
    for aid, file_ids in plan.delete.items():
        to_remove.extend(file_ids)
        report.deleted += 1
        report.record(aid, "", "deleted", 0)
        log.info("deleted article %s (%d files)", aid, len(file_ids))

    if to_remove:
        report.files_removed = store.remove_files(to_remove)

    # 7. Wait for embedding to finish so the report shows the real index state
    if report.files_uploaded:
        report.index_status = store.wait_until_indexed()
        if report.index_status.get("in_progress"):
            log.warning("indexing still in progress at timeout: %s", report.index_status)

    report.finish()
    return report


def _write_markdown(out_dir: Path, docs, replace_all: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = {doc.filename for doc in docs}
    for doc in docs:
        (out_dir / doc.filename).write_text(doc.render(), encoding="utf-8")
    if replace_all:  # remove files of articles that no longer exist
        for path in out_dir.glob("*.md"):
            if path.name not in wanted:
                path.unlink()
