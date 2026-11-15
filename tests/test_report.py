"""Publishing the run report to a GitHub Gist, against a stub HTTP session."""

import json
from dataclasses import replace

from kbsync.report import HISTORY_KEEP, RunReport, publish_to_gist, save_report


class StubResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        return self.payload


class StubGist:
    def __init__(self, history="", fail=False):
        self.history, self.fail, self.patches, self.headers = history, fail, [], None

    def get(self, url, headers, timeout):
        self.headers = headers
        if self.fail:
            return StubResponse({}, status=401)
        files = {"history.log": {"content": self.history}} if self.history else {}
        return StubResponse({"files": files, "html_url": "https://gist.github.com/abc"})

    def patch(self, url, headers, json, timeout):
        self.patches.append(json)
        return StubResponse({"html_url": "https://gist.github.com/abc"})


def _report():
    report = RunReport.start(dry_run=False)
    report.added, report.skipped = 1, 395
    report.record(1, "1-new", "added", 2)
    for i in range(2, 397):
        report.record(i, f"{i}-same", "skipped", 1)
    report.finish()
    return report


def test_publishes_latest_and_appends_history():
    gist = StubGist(history="2026-11-14T02:13:00+00:00 RUN SUMMARY added=396 ...\n")
    url = publish_to_gist(_report(), "abc", "token", gist)
    assert url == "https://gist.github.com/abc"
    assert gist.headers["Authorization"] == "Bearer token"
    files = gist.patches[0]["files"]
    history = files["history.log"]["content"].splitlines()
    assert len(history) == 2 and "added=1" in history[1] and "skipped=395" in history[1]
    latest = json.loads(files["latest.json"]["content"])
    assert latest["added"] == 1 and latest["skipped"] == 395
    assert latest["articles"] == [{"id": 1, "slug": "1-new", "action": "added", "chunks": 2}]  # skipped omitted


def test_history_is_capped():
    old = "".join(f"line {i}\n" for i in range(HISTORY_KEEP + 50))
    gist = StubGist(history=old)
    publish_to_gist(_report(), "abc", "token", gist)
    lines = gist.patches[0]["files"]["history.log"]["content"].splitlines()
    assert len(lines) == HISTORY_KEEP and "RUN SUMMARY" in lines[-1]


def test_description_does_not_name_the_company():
    gist = StubGist()
    publish_to_gist(_report(), "abc", "token", gist)
    assert "optisigns" not in gist.patches[0]["description"].lower()


def test_gist_failure_never_breaks_the_run(settings):
    configured = replace(settings, gist_id="abc", gist_token="bad")
    assert save_report(_report(), configured, StubGist(fail=True)) is None
    assert (settings.report_dir / "last_run.json").exists()  # local report still written


def test_without_gist_settings_only_local_files(settings):
    assert save_report(_report(), settings) is None
    assert (settings.report_dir / "last_run.json").exists()
