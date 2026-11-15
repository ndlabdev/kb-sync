"""Checks the shape of the OpenAI calls without network, using a stub client."""

from types import SimpleNamespace

import pytest

from kbsync.chunker import chunk_document
from kbsync.cleaner import to_markdown
from kbsync.vector_store import STATIC_CHUNKING, OpenAIVectorStore

from .conftest import BASE


class StubClient:
    def __init__(self, fail_batch=False):
        self.created, self.deleted, self.batches = [], [], []
        self.fail_batch = fail_batch
        self.files = SimpleNamespace(create=self._create_file, delete=self._delete_file)
        self.vector_stores = SimpleNamespace(
            file_batches=SimpleNamespace(create=self._create_batch),
            files=SimpleNamespace(list=self._list, delete=lambda file_id, vector_store_id: None),
        )

    def _create_file(self, file, purpose):
        assert purpose == "assistants"
        name, data, mime = file
        assert name.endswith(".md") and mime == "text/markdown" and b"Article URL:" in data
        self.created.append(name)
        return SimpleNamespace(id=f"file-{len(self.created)}")

    def _delete_file(self, file_id):
        self.deleted.append(file_id)

    def _create_batch(self, vector_store_id, files):
        if self.fail_batch:
            raise RuntimeError("batch failed")
        self.batches.append(files)

    def _list(self, vector_store_id, limit):
        return [
            SimpleNamespace(id="file-a", status="completed",
                            attributes={"article_id": "56987330525587", "content_hash": "h", "chunk_index": 0.0, "chunk_total": 1.0}),
            SimpleNamespace(id="manual", status="completed", attributes=None),
        ]


def _doc_and_chunks(article):
    doc = to_markdown(article, BASE, {})
    return doc, chunk_document(doc, 120)


def test_upload_sends_one_batch_with_per_file_attributes(youtube_article):
    client = StubClient()
    store = OpenAIVectorStore(client, "vs_1", per_minute=6000)
    doc, chunks = _doc_and_chunks(youtube_article)
    ids = store.upload_article(doc, chunks)
    assert len(ids) == len(chunks) == len(client.created)
    (batch,) = client.batches
    assert [f["attributes"]["chunk_index"] for f in batch] == list(range(len(chunks)))
    assert all(f["attributes"]["article_id"] == "333" and f["chunking_strategy"] == STATIC_CHUNKING for f in batch)


def test_failed_batch_rolls_back_uploaded_files(youtube_article):
    client = StubClient(fail_batch=True)
    store = OpenAIVectorStore(client, "vs_1", per_minute=6000)
    doc, chunks = _doc_and_chunks(youtube_article)
    with pytest.raises(RuntimeError):
        store.upload_article(doc, chunks)
    assert sorted(client.deleted) == sorted(f"file-{i + 1}" for i in range(len(chunks)))


def test_list_files_parses_attributes_and_ignores_foreign_files():
    remote = OpenAIVectorStore(StubClient(), "vs_1").list_files()
    assert len(remote) == 1
    assert remote[0].article_id == 56987330525587 and remote[0].chunk_total == 1
