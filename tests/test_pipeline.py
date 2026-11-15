"""End-to-end runs against an in-memory vector store."""

import itertools
from dataclasses import replace

from kbsync.delta import RemoteFile
from kbsync.pipeline import run

from .conftest import make_article


class FakeStore:
    vector_store_id = "vs_fake"

    def __init__(self, fail_ids=()):
        self.files: dict[str, RemoteFile] = {}
        self.fail_ids = set(fail_ids)
        self._ids = itertools.count()

    def list_files(self):
        return list(self.files.values())

    def upload_article(self, doc, chunks):
        if doc.article_id in self.fail_ids:
            raise RuntimeError("upload boom")
        ids = []
        for chunk in chunks:
            file_id = f"file-{next(self._ids)}"
            self.files[file_id] = RemoteFile(file_id, doc.article_id, doc.content_hash, chunk.index, chunk.total, "completed")
            ids.append(file_id)
        return ids

    def remove_files(self, file_ids):
        for file_id in file_ids:
            self.files.pop(file_id, None)
        return len(file_ids)

    def wait_until_indexed(self, timeout_s=900):
        return {"completed": len(self.files), "in_progress": 0, "failed": 0, "total": len(self.files)}


def corpus():
    return [make_article(i, f"Article {i}", f"<h2>Intro</h2><p>Body of article {i}.</p>") for i in range(1, 6)]


def test_first_run_adds_everything_then_second_run_skips(settings):
    store, articles = FakeStore(), corpus()
    first = run(settings, lambda: (articles, True), store)
    assert (first.added, first.updated, first.skipped) == (5, 0, 0)
    assert first.files_uploaded == first.chunks_embedded == 5
    assert len(list(settings.output_dir.glob("*.md"))) == 5

    second = run(settings, lambda: (articles, True), store)
    assert (second.added, second.updated, second.skipped, second.files_uploaded) == (0, 0, 5, 0)


def test_changed_article_is_replaced_and_old_files_removed(settings):
    store, articles = FakeStore(), corpus()
    run(settings, lambda: (articles, True), store)
    articles[0] = replace(articles[0], body_html="<h2>Intro</h2><p>Rewritten.</p>")
    report = run(settings, lambda: (articles, True), store)
    assert (report.added, report.updated, report.skipped) == (0, 1, 4)
    assert report.files_removed == 1
    assert len(store.files) == 5
    assert {f.article_id for f in store.files.values()} == {1, 2, 3, 4, 5}


def test_removed_article_is_deleted_but_not_on_partial_fetch(settings):
    store, articles = FakeStore(), corpus()
    run(settings, lambda: (articles, True), store)

    partial = run(settings, lambda: (articles[:2], False), store)  # e.g. MAX_ARTICLES=2
    assert partial.deleted == 0 and len(store.files) == 5

    full = run(settings, lambda: (articles[:4], True), store)
    assert full.deleted == 1 and len(store.files) == 4
    assert not (settings.output_dir / f"{articles[4].slug}.md").exists()


def test_upload_failure_is_reported_and_keeps_going(settings):
    store = FakeStore(fail_ids={2})
    report = run(settings, lambda: (corpus(), True), store)
    assert report.added == 4 and report.failed == 1 and not report.ok
    assert report.errors[0]["article_id"] == 2


def test_dry_run_touches_no_store(settings):
    report = run(replace(settings, dry_run=True), lambda: (corpus(), True), None)
    assert report.dry_run and report.added == 5 and report.files_uploaded == 0
    assert {a["action"] for a in report.articles} == {"would_upload"}
