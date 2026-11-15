"""Decide what to upload. Pure functions: no I/O, so every case is unit-tested.

The vector store itself is the state: every file we upload carries attributes
(article_id, content_hash, chunk_index, chunk_total). Reading them back at the start of a
run tells us what is already indexed, so the job needs no database or state file and is
safe to run in a throw-away container.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

BROKEN_STATUSES = {"failed", "cancelled"}


@dataclass(frozen=True)
class RemoteFile:
    file_id: str
    article_id: int
    content_hash: str
    chunk_index: int
    chunk_total: int
    status: str


@dataclass
class SyncPlan:
    add: list[int] = field(default_factory=list)
    # article id -> files of the old version, removed only after the new version is uploaded
    update: dict[int, list[str]] = field(default_factory=dict)
    skip: list[int] = field(default_factory=list)
    # article id gone from the Help Center -> its files
    delete: dict[int, list[str]] = field(default_factory=dict)
    # leftovers from interrupted runs (old versions, failed files) next to a good copy
    cleanup: list[str] = field(default_factory=list)


def build_plan(
    local_hashes: dict[int, str],
    remote_files: Iterable[RemoteFile],
    prune_missing: bool,
    source_ids: set[int] | None = None,
) -> SyncPlan:
    """local_hashes: articles converted this run. source_ids: every id the Help Center returned,
    including ones that failed to convert; those are kept, never treated as deleted."""
    still_published = set(local_hashes) | (source_ids or set())
    by_article: dict[int, list[RemoteFile]] = defaultdict(list)
    for remote in remote_files:
        by_article[remote.article_id].append(remote)

    plan = SyncPlan()
    for article_id, content_hash in local_hashes.items():
        files = by_article.get(article_id, [])
        if not files:
            plan.add.append(article_id)
            continue
        current = [f for f in files if f.content_hash == content_hash and f.status not in BROKEN_STATUSES]
        if _is_complete(current):
            plan.skip.append(article_id)
            keep = {f.file_id for f in current}
            plan.cleanup.extend(f.file_id for f in files if f.file_id not in keep)
        else:
            # Content changed, or the last upload of this version was partial: upload it again.
            plan.update[article_id] = [f.file_id for f in files]

    if prune_missing:
        for article_id, files in by_article.items():
            if article_id not in still_published:
                plan.delete[article_id] = [f.file_id for f in files]
    return plan


def _is_complete(files: list[RemoteFile]) -> bool:
    if not files:
        return False
    total = files[0].chunk_total
    indexes = {f.chunk_index for f in files}
    return all(f.chunk_total == total for f in files) and indexes == set(range(total)) and len(files) == total
