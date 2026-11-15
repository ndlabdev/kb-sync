"""Turn Zendesk article HTML into clean, self-contained Markdown."""

from __future__ import annotations

import hashlib
import html
import re
from collections import Counter
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter

from .zendesk import Article

# Bump when cleaning/chunking output changes: every article then counts as "updated" once.
PIPELINE_VERSION = "3"

# Never part of article content; the API body rarely has them, but we strip defensively.
DROP_TAGS = ("script", "style", "noscript", "form", "button", "input", "select", "textarea", "svg", "nav", "aside")
DROP_SELECTORS = (
    "[role=navigation]", ".breadcrumbs", ".article-votes", ".article-share",
    ".related-articles", ".advert", ".ad", ".ads", ".sidebar",
)
ARTICLE_PATH = re.compile(r"^/hc/(?:[a-z]{2}(?:-[a-z]{2})?/)?articles/(?P<id>\d+)", re.IGNORECASE)
VIDEO_HOSTS = ("youtube.com", "youtube-nocookie.com", "youtu.be", "vimeo.com", "wistia", "loom.com")
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
CALLOUT_LABELS = {"NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION", "INFO", "PRO TIP"}
_SLUG_DROP = re.compile(r"[^\w\- ]", re.UNICODE)


@dataclass(frozen=True)
class MarkdownDoc:
    article_id: int
    slug: str
    title: str
    url: str
    updated_at: str
    body: str
    content_hash: str

    @property
    def filename(self) -> str:
        return f"{self.slug}.md"

    def render(self) -> str:
        front_matter = (
            "---\n"
            f"title: {_yaml_str(self.title)}\n"
            f"article_id: {self.article_id}\n"
            f"url: {self.url}\n"
            f"updated_at: {self.updated_at}\n"
            "---\n\n"
        )
        return f"{front_matter}# {self.title}\n\nArticle URL: {self.url}\n\n{self.body}\n"


class _Converter(MarkdownConverter):
    """markdownify with language detection for <pre><code class="language-x">."""

    def __init__(self, **options):
        super().__init__(
            heading_style="ATX",
            bullets="-",
            strong_em_symbol="*",
            newline_style="BACKSLASH",
            escape_underscores=False,
            escape_misc=False,
            table_infer_header=True,
            code_language_callback=_code_language,
            **options,
        )


def _code_language(el: Tag) -> str:
    for node in (el, el.find("code")):
        if isinstance(node, Tag):
            for cls in node.get("class") or []:
                if cls.startswith(("language-", "lang-")):
                    return cls.split("-", 1)[1]
    return ""


def to_markdown(
    article: Article,
    base_url: str,
    known_slugs: dict[int, str],
    known_anchors: dict[int, dict[str, str]] | None = None,
) -> MarkdownDoc:
    """Convert one article.

    known_slugs maps article id -> slug for every article in this run, so links between
    articles can point at the local .md file instead of the website.
    known_anchors maps article id -> {zendesk anchor id: markdown heading slug}, so
    `other.md#Anchor` links land on the right heading too (see anchor_map).
    """
    soup = BeautifulSoup(article.body_html, "html.parser")
    _strip_noise(soup)
    _fix_images(soup, base_url)  # first: image-only headings stop being headings
    own_anchors = _anchor_map(soup, article.title)  # before empty <a name> targets are removed
    _replace_embeds(soup)
    _callouts_to_quotes(soup)
    _fix_links(soup, base_url, known_slugs, own_anchors, known_anchors or {}, article.id)
    _demote_h1(soup)
    _hoist_edge_breaks(soup)

    body = _Converter().convert_soup(soup)
    body = _tidy(body)
    digest = hashlib.sha256(
        f"{PIPELINE_VERSION}\n{article.title}\n{article.html_url}\n{body}".encode("utf-8")
    ).hexdigest()
    return MarkdownDoc(
        article_id=article.id,
        slug=article.slug,
        title=article.title,
        url=article.html_url,
        updated_at=article.updated_at,
        body=body,
        content_hash=digest,
    )


def github_slug(text: str) -> str:
    """The anchor GitHub (and most Markdown renderers) give a heading."""
    return _SLUG_DROP.sub("", " ".join(text.split()).lower()).replace(" ", "-")


def anchor_map(article: Article) -> dict[str, str]:
    """{anchor id used on the Help Center page: slug of the Markdown heading it points at}."""
    soup = BeautifulSoup(article.body_html, "html.parser")
    _strip_noise(soup)
    _fix_images(soup, "")
    return _anchor_map(soup, article.title)


# ---------------------------------------------------------------- HTML clean-up steps


def _strip_noise(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()
    for selector in DROP_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()


def _replace_embeds(soup: BeautifulSoup) -> None:
    """An <iframe> has no Markdown form; keep the video as a link so the content isn't lost."""
    for frame in soup.find_all(["iframe", "video", "embed"]):
        src = frame.get("src")
        if not src:
            source = frame.find("source")
            src = source.get("src") if source else None
        if not src:
            frame.decompose()
            continue
        url = _canonical_video_url(src if not src.startswith("//") else "https:" + src)
        label = "Video" if any(h in url for h in VIDEO_HOSTS) else "Embedded content"
        p = soup.new_tag("p")
        a = soup.new_tag("a", href=url)
        a.string = f"{label}: {url}"
        p.append(a)
        frame.replace_with(p)


def _canonical_video_url(src: str) -> str:
    parsed = urlparse(src)
    if "youtube" in parsed.netloc and "/embed/" in parsed.path:
        video_id = parsed.path.split("/embed/", 1)[1].split("/")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    if "youtube" in parsed.netloc and parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        return f"https://www.youtube.com/watch?v={video_id}" if video_id else src
    return src


def _is_empty_anchor(el) -> bool:
    return (
        isinstance(el, Tag)
        and el.name == "a"
        and not el.get("href")
        and bool(el.get("name") or el.get("id"))
        and not el.get_text(strip=True)
        and el.find("img") is None
    )


def _anchor_map(soup: BeautifulSoup, title: str) -> dict[str, str]:
    """Zendesk tables of contents link to `<a name="X">` / `id="X"` targets. Those vanish in
    Markdown, where a heading's anchor is its slug, so map each target to the slug of the
    heading it belongs to. Slugs are de-duplicated like GitHub does (-1, -2...), counting the
    document title, which is the first heading of the file."""
    seen: Counter[str] = Counter()

    def unique(base: str) -> str:
        n = seen[base]
        seen[base] += 1
        return base if n == 0 else f"{base}-{n}"

    title_slug = unique(github_slug(title))
    mapping: dict[str, str] = {}
    for h in soup.find_all(HEADINGS):
        text = " ".join(h.get_text().split())
        if not text:
            continue
        slug = unique(github_slug(text))
        targets = [h]
        targets += h.find_all(attrs={"id": True}) + h.find_all("a", attrs={"name": True})
        prev = h.find_previous_sibling()
        while prev is not None:
            inner = [c for c in prev.find_all(True)] if prev.name in ("p", "div", "span") else []
            if _is_empty_anchor(prev):
                targets.append(prev)
            elif inner and not prev.get_text(strip=True) and all(_is_empty_anchor(c) for c in inner):
                targets += inner  # <p><a name="X"></a></p><h2>...</h2>
            else:
                break
            prev = prev.find_previous_sibling()
        for el in targets:
            for key in (el.get("id"), el.get("name")):
                if key:
                    mapping.setdefault(key, slug)
        mapping.setdefault(slug, slug)  # links that already use the slug keep working

    # Any other id: send the reader to the section it sits in.
    for el in soup.find_all(attrs={"id": True}) + soup.find_all("a", attrs={"name": True}):
        for key in (el.get("id"), el.get("name")):
            if key and key not in mapping:
                section = el.find_previous(HEADINGS)
                text = " ".join(section.get_text().split()) if section else ""
                mapping[key] = github_slug(text) if text else title_slug
    return mapping


def _lookup_anchor(anchors: dict[str, str], fragment: str) -> str | None:
    for key in (fragment, html.unescape(fragment), html.unescape(html.unescape(fragment))):
        if key in anchors:
            return anchors[key]
    return anchors.get(github_slug(html.unescape(fragment)))


def _callouts_to_quotes(soup: BeautifulSoup) -> None:
    """Zendesk NOTE/TIP/IMPORTANT boxes are one-column tables. As Markdown tables they squash
    lists into one line; a blockquote keeps the meaning and the structure."""
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        cells = [r.find_all(["td", "th"], recursive=False) for r in rows]
        if not rows or any(len(c) != 1 for c in cells) or table.find("table"):
            continue
        quote = soup.new_tag("blockquote")
        for i, (cell,) in enumerate(cells):
            label = cell.get_text(" ", strip=True).rstrip(":").upper()
            if i == 0 and label in CALLOUT_LABELS:
                p = soup.new_tag("p")
                strong = soup.new_tag("strong")
                strong.string = label
                p.append(strong)
                quote.append(p)
                continue
            if cell.find(["p", "ul", "ol", "div", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"]):
                for child in list(cell.contents):
                    quote.append(child.extract())
            else:
                p = soup.new_tag("p")
                for child in list(cell.contents):
                    p.append(child.extract())
                quote.append(p)
        table.replace_with(quote)


def _fix_links(
    soup: BeautifulSoup,
    base_url: str,
    known_slugs: dict[int, str],
    own_anchors: dict[str, str],
    known_anchors: dict[int, dict[str, str]],
    self_id: int | None = None,
) -> None:
    site_host = urlparse(base_url).netloc
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        has_content = a.get_text(strip=True) or a.find("img")
        if not has_content:
            a.decompose()  # empty anchors (old "name" targets, stray tags)
            continue
        if not href:
            a.unwrap()
            continue
        if href.startswith("#"):
            target = _lookup_anchor(own_anchors, href[1:])
            if target:
                a["href"] = f"#{target}"
            else:
                a.unwrap()  # points nowhere in this document: keep the words, drop the dead link
            continue
        if href.startswith(("mailto:", "tel:")):
            continue
        parsed = urlparse(href)
        same_site = parsed.netloc in ("", site_host)
        match = ARTICLE_PATH.match(parsed.path) if same_site else None
        if match and int(match["id"]) in known_slugs:
            # Link to another article we exported: point at the sibling file (and heading).
            target_id = int(match["id"])
            anchors = own_anchors if target_id == self_id else known_anchors.get(target_id, {})
            slug = _lookup_anchor(anchors, parsed.fragment) if parsed.fragment else None
            if target_id == self_id:  # a page linking to its own section: stay in this file
                if slug:
                    a["href"] = f"#{slug}"
                else:
                    a.unwrap()
                continue
            a["href"] = f"./{known_slugs[target_id]}.md" + (f"#{slug}" if slug else "")
        elif href.startswith("/"):
            # Site-relative link to something we don't export: keep it working outside the site.
            a["href"] = urljoin(base_url + "/", href)
        # Absolute external links and plain relative links are left as they are.


def _fix_images(soup: BeautifulSoup, base_url: str) -> None:
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src or src.startswith("data:"):
            img.decompose()
            continue
        if src.startswith("//"):
            img["src"] = "https:" + src
        elif src.startswith("/"):
            img["src"] = urljoin(base_url + "/", src)
        if not img.get("alt"):
            img["alt"] = "image"
    # A heading holding only an image would become "## image": make it a plain paragraph.
    for h in soup.find_all(HEADINGS):
        if not h.get_text(strip=True):
            if h.find("img"):
                h.name = "p"
            else:
                h.decompose()


INLINE_TAGS = ("strong", "b", "em", "i", "u", "span", "a", "font")


def _hoist_edge_breaks(soup: BeautifulSoup) -> None:
    """`<strong><br>Next article</strong>` would put a line break inside the bold span;
    move breaks at the start or end of an inline tag just outside it."""
    for br in soup.find_all("br"):
        while br.parent is not None and br.parent.name in INLINE_TAGS:
            parent = br.parent
            kids = [c for c in parent.contents if not (isinstance(c, str) and not c.strip())]
            if kids and kids[0] is br:
                parent.insert_before(br.extract())
            elif kids and kids[-1] is br:
                parent.insert_after(br.extract())
            else:
                break


def _demote_h1(soup: BeautifulSoup) -> None:
    # The document title is the only H1; body H1s become H2.
    for h1 in soup.find_all("h1"):
        h1.name = "h2"


# ---------------------------------------------------------------- Markdown clean-up

_RAW_ELEMENT = re.compile(r"<(iframe|script|embed|object|video|audio|div|span|img|a|p)\b[^\n]*?</\1>", re.I)
_RAW_TAG = re.compile(r"<(iframe|script|embed|object|video|audio|div|span|img|a|p|br)\b[^>\n]*/?>", re.I)


def _code_raw_html(line: str) -> str:
    """Articles that *show* embed code (e.g. an <iframe> snippet) as text: as raw HTML a
    Markdown viewer would render or strip it, so put it in inline code."""
    parts = line.split("`")
    for i in range(0, len(parts), 2):  # even parts are outside inline code spans
        segment = _RAW_ELEMENT.sub(lambda m: f"`{m.group(0)}`", parts[i])
        if segment == parts[i]:
            segment = _RAW_TAG.sub(lambda m: f"`{m.group(0)}`", parts[i])
        parts[i] = segment
    return "`".join(parts)


_BOLD_HEADING = re.compile(r"^(#{1,6}) \*\*(.+?)\*\*\s*$")
_EMPTY_EMPHASIS = re.compile(r"(\*\*\s*\*\*|(?<!\*)\*\s+\*(?!\*))")


def _tidy(markdown: str) -> str:
    """Whitespace and heading fixes outside fenced code blocks; code is left untouched."""
    markdown = markdown.replace("\u00a0", " ").replace("\u200b", "").replace("\r\n", "\n")
    out: list[str] = []
    in_fence = False

    def emit(line: str) -> None:
        if not line.strip() and out and not out[-1].strip():
            return  # collapse runs of blank lines
        out.append(line)

    for line in markdown.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line.rstrip())
            continue
        if in_fence:
            out.append(line)
            continue
        line = line.rstrip()
        # 1. Content fixes first, so every line gets them whatever happens to its line break.
        line = _EMPTY_EMPHASIS.sub("", line)
        line = _BOLD_HEADING.sub(r"\1 \2", line)
        if "<" in line:
            line = _code_raw_html(line)
        if re.fullmatch(r"#{1,6}", line.strip()):
            line = ""  # heading that only held whitespace/images
        # 2. <br> comes out as a trailing backslash; a paragraph break reads cleaner and embeds
        #    better. Not inside tables, and not when it would split a **bold** span in two.
        if not line.lstrip().startswith("|"):
            quote = ">" if line.lstrip().startswith(">") else ""
            if line.strip() in ("\\", ">", "> \\"):
                line = quote
            elif line.endswith("\\") and not line.endswith("\\\\") and line.count("**") % 2 == 0:
                emit(line[:-1].rstrip())
                line = quote
        emit(line)
    return "\n".join(out).strip()


def _yaml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
