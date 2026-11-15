"""Everything that talks to the OpenAI Files + Vector Store APIs.

The pipeline depends on the VectorStoreGateway protocol only, so tests swap in a fake.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Protocol

from openai import NotFoundError, OpenAI

from .chunker import Chunk
from .cleaner import MarkdownDoc
from .delta import RemoteFile

log = logging.getLogger(__name__)

# Our chunks are <= 780 tokens, so with an 800-token static strategy OpenAI keeps each file
# as exactly one chunk. Overlap is 0 because our chunks already end on section/paragraph edges.
STATIC_CHUNKING = {"type": "static", "static": {"max_chunk_size_tokens": 800, "chunk_overlap_tokens": 0}}


class VectorStoreGateway(Protocol):
    vector_store_id: str

    def list_files(self) -> list[RemoteFile]: ...
    def upload_article(self, doc: MarkdownDoc, chunks: list[Chunk]) -> list[str]: ...
    def remove_files(self, file_ids: list[str]) -> int: ...
    def wait_until_indexed(self, timeout_s: float = 900) -> dict[str, int]: ...


class _RateLimiter:
    """Spaces calls evenly. Calls to /vector_stores/{id}/files and /file_batches share a
    per-vector-store limit (300/min); we stay under it with some headroom."""

    def __init__(self, per_minute: int) -> None:
        self._interval = 60.0 / per_minute
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self._interval
        if delay > 0:
            time.sleep(delay)


class OpenAIVectorStore:
    def __init__(self, client: OpenAI, vector_store_id: str, per_minute: int = 240) -> None:
        self.client = client
        self.vector_store_id = vector_store_id
        self._limit = _RateLimiter(per_minute)

    @classmethod
    def connect(cls, client: OpenAI, vector_store_id: str | None, name: str) -> "OpenAIVectorStore":
        """Use VECTOR_STORE_ID if given, else find the store by name, else create it.
        Finding by name keeps the daily job idempotent even if the id was never configured."""
        if vector_store_id:
            store = client.vector_stores.retrieve(vector_store_id)
        else:
            store = next((s for s in client.vector_stores.list(limit=100) if s.name == name), None)
            if store is None:
                store = client.vector_stores.create(name=name, metadata={"managed_by": "kb-sync"})
                log.info("created vector store %s (%s)", store.id, name)
        log.info("using vector store %s (%s)", store.id, store.name)
        return cls(client, store.id)

    # -------------------------------------------------------------- read

    def list_files(self) -> list[RemoteFile]:
        remote: list[RemoteFile] = []
        for vs_file in self.client.vector_stores.files.list(vector_store_id=self.vector_store_id, limit=100):
            attrs = vs_file.attributes or {}
            if "article_id" not in attrs:
                continue  # not ours (e.g. uploaded by hand): never touch it
            remote.append(
                RemoteFile(
                    file_id=vs_file.id,
                    article_id=int(attrs["article_id"]),
                    content_hash=str(attrs.get("content_hash", "")),
                    chunk_index=int(attrs.get("chunk_index", 0)),
                    chunk_total=int(attrs.get("chunk_total", 0)),
                    status=vs_file.status,
                )
            )
        return remote

    # -------------------------------------------------------------- write

    def upload_article(self, doc: MarkdownDoc, chunks: list[Chunk]) -> list[str]:
        """Upload every chunk of one article, then attach them in one file batch.
        If anything fails, the files uploaded so far are deleted and the error is raised:
        the previous version of the article (if any) is still in the store, untouched."""
        uploaded: list[str] = []
        try:
            for chunk in chunks:
                file = self.client.files.create(
                    file=(chunk.filename, chunk.text.encode("utf-8"), "text/markdown"),
                    purpose="assistants",
                )
                uploaded.append(file.id)
            self._limit.wait()
            self.client.vector_stores.file_batches.create(
                vector_store_id=self.vector_store_id,
                files=[
                    {
                        "file_id": file_id,
                        "attributes": _attributes(doc, chunk),
                        "chunking_strategy": STATIC_CHUNKING,
                    }
                    for file_id, chunk in zip(uploaded, chunks)
                ],
            )
            return uploaded
        except Exception:
            for file_id in uploaded:
                self._delete_raw_file(file_id)
            raise

    def remove_files(self, file_ids: list[str]) -> int:
        removed = 0
        for file_id in file_ids:
            self._limit.wait()
            try:
                self.client.vector_stores.files.delete(file_id, vector_store_id=self.vector_store_id)
            except NotFoundError:
                pass
            self._delete_raw_file(file_id)  # otherwise the file lingers in storage and is billed
            removed += 1
        return removed

    def wait_until_indexed(self, timeout_s: float = 900) -> dict[str, int]:
        """Embedding is asynchronous; wait so the run report reflects the final state."""
        deadline = time.monotonic() + timeout_s
        while True:
            counts = self.client.vector_stores.retrieve(self.vector_store_id).file_counts
            if counts.in_progress == 0 or time.monotonic() > deadline:
                return {
                    "completed": counts.completed,
                    "in_progress": counts.in_progress,
                    "failed": counts.failed,
                    "total": counts.total,
                }
            time.sleep(5)

    def _delete_raw_file(self, file_id: str) -> None:
        try:
            self.client.files.delete(file_id)
        except NotFoundError:
            pass


def _attributes(doc: MarkdownDoc, chunk: Chunk) -> dict[str, str | float | bool]:
    # Max 16 keys; strings max 512 chars. article_id is a string: 14-digit ids, no float rounding.
    return {
        "article_id": str(doc.article_id),
        "content_hash": doc.content_hash,
        "chunk_index": chunk.index,
        "chunk_total": chunk.total,
        "url": doc.url[:512],
        "title": doc.title[:200],
    }
