"""Quality check for the exported Markdown files.

    python qa.py                 # checks ./articles, prints a summary
    python qa.py articles --json qa_report.json

Exit code 1 if any ERROR-level issue is found, so it can gate CI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kbsync.cleaner import github_slug  # noqa: E402

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"

HTML_TAG = re.compile(
    r"</?(div|span|p|br|table|tbody|thead|tr|td|th|iframe|script|style|img|a|strong|em|b|i|u|ul|ol|li|h[1-6]|font|section|figure|button|form|input|svg)\b[^>]*>",
    re.IGNORECASE,
)
HTML_ENTITY = re.compile(r"&(nbsp|amp|lt|gt|quot|#\d+|#x[0-9a-f]+);", re.IGNORECASE)
LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]*)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^(#{1,6})\s*(.*)$")
NAV_PHRASES = (
    "was this article helpful", "related articles", "articles in this section", "return to top",
    "have more questions", "submit a request", "sign in", "recently viewed articles",
    "follow this article", "comments", "powered by zendesk",
)
FRONT_MATTER_KEYS = ("title", "article_id", "url", "updated_at")


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"')
    return meta, text[end + 5 :]


def outside_code(lines: list[str]):
    """Yield (line_no, line) for lines outside fenced code blocks, and fence balance."""
    in_fence = False
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield i, line


def heading_slugs(text: str) -> set[str]:
    """Anchors a Markdown renderer gives the headings of a file (GitHub style, de-duplicated)."""
    seen: Counter = Counter()
    slugs = set()
    _, body = split_front_matter(text)
    for _, line in outside_code(body.split("\n")):
        m = HEADING.match(line)
        if m and m.group(2).strip():
            base = github_slug(re.sub(r"[*_`]|\[([^\]]*)\]\([^)]*\)", r"\1", m.group(2)))
            slugs.add(base if not seen[base] else f"{base}-{seen[base]}")
            seen[base] += 1
    return slugs


def check_file(path: Path, all_names: set[str], slugs_by_file: dict[str, set[str]]) -> tuple[list[dict], dict]:
    issues: list[dict] = []

    def add(level: str, code: str, msg: str, line: int | None = None) -> None:
        issues.append({"file": path.name, "level": level, "code": code, "msg": msg,
                       "line": line + offset if line else line})

    text = path.read_text(encoding="utf-8")
    meta, body = split_front_matter(text)
    lines = body.split("\n")
    offset = text[: len(text) - len(body)].count("\n")  # report line numbers of the file itself

    # Structure
    missing = [k for k in FRONT_MATTER_KEYS if not meta.get(k)]
    if missing:
        add(ERROR, "front_matter", f"missing front matter keys: {', '.join(missing)}")
    if not re.search(r"^# .+", body, re.MULTILINE):
        add(ERROR, "no_title", "no '# Title' line")
    if "Article URL: http" not in body:
        add(ERROR, "no_url", "no 'Article URL:' line (citations depend on it)")
    fences = sum(1 for l in lines if l.lstrip().startswith("```"))
    if fences % 2:
        add(ERROR, "fence", "unbalanced ``` code fence")

    content = "\n".join(l for _, l in outside_code(lines))
    words = len(re.findall(r"\w+", content))
    if words < 40:
        add(WARN, "short", f"very short article body ({words} words): check nothing was dropped")

    # Leftover HTML / entities / junk characters
    for no, line in outside_code(lines):
        prose = re.sub(r"`[^`]*`", "", line)  # inline code may legitimately show HTML
        if HTML_TAG.search(prose):
            add(ERROR, "html_tag", f"leftover HTML: {line.strip()[:100]}", no)
        if HTML_ENTITY.search(prose):
            add(WARN, "entity", f"HTML entity left: {line.strip()[:100]}", no)
        if any(ch in line for ch in ("\u00a0", "\u200b", "\ufeff")):
            add(WARN, "invisible_char", "non-breaking / zero-width character", no)
        if re.search(r"\\[_*\[\]#]", line) and not line.lstrip().startswith("|"):
            add(INFO, "escape", f"escaped markdown char: {line.strip()[:100]}", no)
        low = line.lower().strip()
        if any(low == p or low.startswith(p + "?") or low.startswith(p + ".") for p in NAV_PHRASES):
            add(ERROR, "nav_text", f"site chrome text: {line.strip()[:80]}", no)
        m = HEADING.match(line)
        if m and not m.group(2).strip():
            add(WARN, "empty_heading", "empty heading", no)
        if m and m.group(2).strip() == "image":  # our alt-text placeholder; a real "Image" heading is fine
            add(ERROR, "image_heading", f"heading made of an image's alt text: {line.strip()}", no)
        if line.rstrip().endswith("\\") and not line.lstrip().startswith("|"):
            add(INFO, "hard_break", "line ends with a backslash hard break", no)
        if re.fullmatch(r"\|\s*\*\*(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\*\*\s*\|", line.strip()):
            add(WARN, "callout_table", "NOTE/TIP box rendered as a one-column table", no)
        if re.fullmatch(r"\s*(\*\*|__|\*|_)\s*", line):
            add(WARN, "stray_emphasis", "line with only emphasis markers", no)

    # Headings
    levels = [len(m.group(1)) for _, l in outside_code(lines) if (m := HEADING.match(l))]
    if levels.count(1) > 1:
        add(WARN, "multi_h1", f"{levels.count(1)} H1 headings (only the title should be H1)")
    for prev, cur in zip(levels, levels[1:]):
        if cur > prev + 1:
            add(INFO, "heading_jump", f"heading level jumps from H{prev} to H{cur}")
            break

    # Links and images
    stats = Counter()
    for no, line in outside_code(lines):
        for bang, label, target in LINK.findall(line):
            kind = "image" if bang else "link"
            stats[kind] += 1
            if not target:
                add(ERROR, "empty_target", f"{kind} with empty target: [{label}]", no)
                continue
            if kind == "link" and not label.strip():
                add(WARN, "empty_label", f"link without text -> {target}", no)
            if target.startswith("#"):
                stats["anchor_link"] += 1
                if target[1:] not in slugs_by_file[path.name]:
                    add(ERROR, "broken_anchor", f"in-page link to missing heading {target}", no)
            elif target.startswith("./"):
                stats["relative_link"] += 1
                name, _, fragment = target[2:].partition("#")
                if name not in all_names:
                    add(ERROR, "broken_relative", f"relative link to missing file {name}", no)
                elif fragment and fragment not in slugs_by_file[name]:
                    add(WARN, "broken_fragment", f"{name} has no heading #{fragment}", no)
            elif target.startswith("/"):
                add(ERROR, "root_relative", f"site-relative link will break offline: {target}", no)
            elif re.search(r"/hc/[^/]+/articles/\d+", target) and "Article URL" not in line:
                add(INFO, "external_article", f"article link not rewritten (not in export?): {target}", no)
            if kind == "image" and target.startswith("data:"):
                add(WARN, "data_uri", "inline data: image", no)

    # Tables: every row in a table block has the same number of cells
    table: list[tuple[int, str]] = []
    for no, line in list(outside_code(lines)) + [(10**9, "")]:
        if line.strip().startswith("|"):
            table.append((no, line))
            continue
        if table:
            counts = {l.strip().strip("|").count("|") for _, l in table}
            if len(counts) > 1:
                add(WARN, "table_shape", "table rows have different column counts", table[0][0])
            if len(table) > 1 and not re.match(r"^\|\s*:?-{3,}", table[1][1].strip()):
                add(WARN, "table_header", "table without header separator row", table[0][0])
            stats["tables"] += 1
            table = []

    stats["words"] = words
    stats["code_blocks"] = fences // 2
    return issues, {"file": path.name, "hash": hashlib.sha256(body.encode()).hexdigest(), **stats}


def run(folder: Path) -> dict:
    files = sorted(folder.glob("*.md"))
    names = {f.name for f in files}
    slugs_by_file = {f.name: heading_slugs(f.read_text(encoding="utf-8")) for f in files}
    issues: list[dict] = []
    stats: list[dict] = []
    for f in files:
        file_issues, file_stats = check_file(f, names, slugs_by_file)
        issues.extend(file_issues)
        stats.append(file_stats)

    by_hash = defaultdict(list)
    for s in stats:
        by_hash[s["hash"]].append(s["file"])
    for dupes in by_hash.values():
        if len(dupes) > 1:
            issues.append({"file": dupes[0], "level": WARN, "code": "duplicate", "msg": f"same content as {dupes[1:]}", "line": None})

    if len(files) < 30:
        issues.append({"file": "-", "level": ERROR, "code": "too_few", "msg": f"only {len(files)} files (brief needs >= 30)", "line": None})

    words = sorted(s["words"] for s in stats) or [0]
    return {
        "files": len(files),
        "issues": issues,
        "summary": {
            "by_level": Counter(i["level"] for i in issues),
            "by_code": Counter(f"{i['level']}:{i['code']}" for i in issues),
            "files_with_errors": len({i["file"] for i in issues if i["level"] == ERROR}),
            "words_min_median_max": [words[0], words[len(words) // 2], words[-1]],
            "links": sum(s.get("link", 0) for s in stats),
            "relative_links": sum(s.get("relative_link", 0) for s in stats),
            "anchor_links": sum(s.get("anchor_link", 0) for s in stats),
            "images": sum(s.get("image", 0) for s in stats),
            "tables": sum(s.get("tables", 0) for s in stats),
            "code_blocks": sum(s.get("code_blocks", 0) for s in stats),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", nargs="?", default="articles")
    parser.add_argument("--json", help="write the full report to this file")
    parser.add_argument("--show", type=int, default=40, help="max issues to print")
    args = parser.parse_args()

    report = run(Path(args.folder))
    s = report["summary"]
    print(f"files: {report['files']}  files with errors: {s['files_with_errors']}")
    print(f"issues: {dict(s['by_level'])}")
    print(f"words min/median/max: {s['words_min_median_max']}  links: {s['links']} "
          f"(relative {s['relative_links']}, in-page {s['anchor_links']})  images: {s['images']}  tables: {s['tables']}  code blocks: {s['code_blocks']}")
    for code, n in s["by_code"].most_common():
        print(f"  {n:5d}  {code}")
    order = {ERROR: 0, WARN: 1, INFO: 2}
    for issue in sorted(report["issues"], key=lambda i: order[i["level"]])[: args.show]:
        where = f"{issue['file']}:{issue['line']}" if issue["line"] else issue["file"]
        print(f"{issue['level']:5} {issue['code']:16} {where}  {issue['msg']}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, default=dict), encoding="utf-8")
    return 1 if s["by_level"].get(ERROR) else 0


if __name__ == "__main__":
    sys.exit(main())
