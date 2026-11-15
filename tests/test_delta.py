from kbsync.delta import RemoteFile, build_plan


def files(article_id, content_hash, total, status="completed", prefix=None, indexes=None):
    prefix = prefix or f"f{article_id}{content_hash}"
    return [
        RemoteFile(f"{prefix}-{i}", article_id, content_hash, i, total, status)
        for i in (indexes if indexes is not None else range(total))
    ]


def test_new_article_is_added():
    plan = build_plan({1: "a"}, [], prune_missing=True)
    assert plan.add == [1]


def test_same_hash_and_all_chunks_present_is_skipped():
    plan = build_plan({1: "a"}, files(1, "a", 2), prune_missing=True)
    assert plan.skip == [1] and not plan.add and not plan.update


def test_changed_hash_is_updated_and_old_files_queued_for_removal():
    plan = build_plan({1: "b"}, files(1, "a", 2), prune_missing=True)
    assert plan.update == {1: ["f1a-0", "f1a-1"]}


def test_partial_previous_upload_is_redone():
    plan = build_plan({1: "a"}, files(1, "a", 3, indexes=[0, 1]), prune_missing=True)
    assert 1 in plan.update


def test_failed_file_forces_reupload():
    remote = files(1, "a", 1, status="failed")
    plan = build_plan({1: "a"}, remote, prune_missing=True)
    assert plan.update == {1: ["f1a-0"]}


def test_leftover_old_version_next_to_good_copy_is_cleaned_up():
    # crash after uploading the new version but before deleting the old one
    remote = files(1, "new", 1) + files(1, "old", 2)
    plan = build_plan({1: "new"}, remote, prune_missing=True)
    assert plan.skip == [1]
    assert sorted(plan.cleanup) == ["f1old-0", "f1old-1"]


def test_missing_article_is_deleted_only_when_pruning():
    remote = files(1, "a", 1) + files(2, "b", 1)
    assert build_plan({1: "a"}, remote, prune_missing=True).delete == {2: ["f2b-0"]}
    assert build_plan({1: "a"}, remote, prune_missing=False).delete == {}


def test_article_that_failed_to_convert_is_not_deleted():
    remote = files(1, "a", 1) + files(2, "b", 1)
    plan = build_plan({1: "a"}, remote, prune_missing=True, source_ids={1, 2})
    assert plan.delete == {}
