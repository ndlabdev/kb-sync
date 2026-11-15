import pytest

from kbsync.cleaner import to_markdown

BASE = "https://support.optisigns.com"
KNOWN = {111: "111-getting-started-guide", 222: "222-how-caching-works", 333: "333-how-do-i-add-a-youtube-video"}


@pytest.fixture
def md(youtube_article):
    return to_markdown(youtube_article, BASE, KNOWN)


def test_header_has_title_and_citable_url(md):
    text = md.render()
    assert text.startswith("---\ntitle: \"How do I add a YouTube video?\"")
    assert "\n# How do I add a YouTube video?\n" in text
    assert f"Article URL: {md.url}" in text


def test_removes_scripts_styles_buttons_and_breadcrumbs(md):
    for junk in ("trackPageView", "color:red", "Was this article helpful", "Home", "> Apps"):
        assert junk not in md.body


def test_headings_are_atx_and_body_h1_is_demoted(md):
    assert "## Overview" in md.body
    assert "\n# Overview" not in md.body
    assert "## Step 1: Add the YouTube app" in md.body  # bold wrapper stripped
    assert "### Advanced settings" in md.body


def test_links_between_articles_become_relative_md_links(md):
    # without the other article's anchor map the unknown fragment is dropped, the file link kept
    assert "[Getting Started](./111-getting-started-guide.md)" in md.body
    assert "[How caching works](./222-how-caching-works.md)" in md.body


def test_cross_article_fragment_maps_to_heading_slug(youtube_article):
    doc = to_markdown(youtube_article, BASE, KNOWN, {111: {"pairing": "pair-your-screen"}})
    assert "[Getting Started](./111-getting-started-guide.md#pair-your-screen)" in doc.body


def test_other_site_links_are_absolutised_and_external_kept(md):
    assert "(https://support.optisigns.com/hc/en-us/sections/999)" in md.body
    assert "(https://www.optisigns.com/pricing)" in md.body
    assert "(mailto:support@optisigns.com)" in md.body


def test_code_block_is_fenced_with_language_and_keeps_blank_line(md):
    assert '```json\n{\n  "type": "youtube",\n\n  "url"' in md.body


def test_iframe_becomes_watch_link_and_images_absolute(md):
    assert "https://www.youtube.com/watch?v=AbCdEf12345" in md.body
    assert "![image](https://support.optisigns.com/hc/article_attachments/555/youtube-app.png)" in md.body


def test_table_and_lists(md):
    assert "| Setting | Default |\n| --- | --- |\n| Mute | On |" in md.body
    assert "1. Go to **Files/Assets** → **Apps**." in md.body


def test_whitespace_is_normalised(md):
    assert " " not in md.body
    assert "\n\n\n" not in md.body
    assert all(line == line.rstrip() for line in md.body.split("\n"))


def test_hash_ignores_updated_at_but_tracks_content(youtube_article):
    from dataclasses import replace

    a = to_markdown(youtube_article, BASE, KNOWN)
    b = to_markdown(replace(youtube_article, updated_at="2027-01-01T00:00:00Z"), BASE, KNOWN)
    c = to_markdown(replace(youtube_article, body_html=youtube_article.body_html + "<p>New step</p>"), BASE, KNOWN)
    assert a.content_hash == b.content_hash
    assert a.content_hash != c.content_hash


# ---------------------------------------------------------------- real Zendesk markup (Vimeo article)

from .conftest import FIXTURES, make_article  # noqa: E402
from kbsync.cleaner import anchor_map, github_slug  # noqa: E402


@pytest.fixture
def vimeo():
    other = make_article(360021855653, "What hardware is supported?",
                         '<p><a name="Android"></a></p><h2>Android Devices</h2><p>x</p>')
    article = make_article(360016254994, "How to Display Vimeo Videos", (FIXTURES / "article_vimeo.html").read_text())
    known = {article.id: article.slug, other.id: other.slug}
    return to_markdown(article, BASE, known, {other.id: anchor_map(other)})


def test_github_slug():
    assert github_slug("What You'll Need") == "what-youll-need"
    assert github_slug("Clear the OptiSigns App’s Cache or Data") == "clear-the-optisigns-apps-cache-or-data"
    assert github_slug("Which Fire TV Devices Work with OptiSigns?") == "which-fire-tv-devices-work-with-optisigns"


def test_table_of_contents_links_point_at_heading_slugs(vimeo):
    assert "- [What You'll Need](#what-youll-need)" in vimeo.body
    assert "- [Creating a Vimeo App](#creating-a-vimeo-app)" in vimeo.body
    assert "- A dead entry" in vimeo.body  # unknown anchor: text kept, dead link dropped


def test_fragment_into_other_article_resolves(vimeo):
    assert "(./360021855653-what-hardware-is-supported.md#android-devices)" in vimeo.body


def test_image_only_heading_keeps_the_image(vimeo):
    assert "## image" not in vimeo.body
    assert "![image](https://support.optisigns.com/hc/article_attachments/1)" in vimeo.body


def test_callout_table_becomes_blockquote_with_list(vimeo):
    assert "> **NOTE**\n>\n> The Vimeo app accepts **vimeo.com** video links. See:\n>\n> - [How to Re-Encode]" in vimeo.body
    assert "| **NOTE** |" not in vimeo.body
    assert "| Setting | Default |" in vimeo.body  # real tables untouched


def test_line_breaks_become_paragraphs(vimeo):
    assert "digital signs.\n\nPaste the video's link into OptiSigns.\n\nLet's get started." in vimeo.body
    assert not any(line.rstrip().endswith("\\") for line in vimeo.body.split("\n"))


def test_duplicate_headings_get_numbered_slugs():
    article = make_article(1, "Guide", '<p><a name="a"></a></p><h2>Setup</h2><p><a name="b"></a></p><h2>Setup</h2>'
                                        '<p><a href="#b">second</a></p>')
    assert anchor_map(article)["a"] == "setup" and anchor_map(article)["b"] == "setup-1"
    assert "[second](#setup-1)" in to_markdown(article, BASE, {}).body


def test_self_links_and_encoded_fragments_stay_in_file():
    body = ('<ul><li><a href="#Playlist&amp;amp;Schedule">P and S</a></li>'
            '<li><a href="https://support.optisigns.com/hc/en-us/articles/5-Guide#Canva">Canva</a></li></ul>'
            '<p><a name="Playlist&amp;amp;Schedule"></a></p><h2>Playlist and Schedule</h2>'
            '<p><a name="Canva"></a></p><h2>Use Canva</h2>')
    article = make_article(5, "Guide", body)
    doc = to_markdown(article, BASE, {5: article.slug})
    assert "[P and S](#playlist-and-schedule)" in doc.body
    assert "[Canva](#use-canva)" in doc.body


def test_html_shown_as_text_becomes_inline_code():
    body = ('<ol><li>Paste the code:<br>&lt;iframe src="https://x/embed?a=1" width="476px"&gt;This is an embedded '
            '&lt;a href="https://office.com"&gt;Office&lt;/a&gt; deck.&lt;/iframe&gt;</li></ol>')
    doc = to_markdown(make_article(6, "PowerPoint", body), BASE, {})
    assert '`<iframe src="https://x/embed?a=1" width="476px">This is an embedded <a href="https://office.com">Office</a> deck.</iframe>`' in doc.body


def test_break_inside_bold_does_not_split_the_bold_span():
    body = '<p>See the API.</p><p><strong><br>Next Article - <a href="https://x.com/a">API Key</a></strong></p>'
    doc = to_markdown(make_article(7, "Intro", body), BASE, {})
    assert "**Next Article - [API Key](https://x.com/a)**" in doc.body
    assert not any(line.strip() == "**" for line in doc.body.split("\n"))


def test_raw_html_on_a_line_ending_with_a_break_is_still_coded():
    body = '<ol><li>Copy:<br>&lt;iframe src="https://x"&gt;deck&lt;/iframe&gt;<br>Then share.</li></ol>'
    doc = to_markdown(make_article(8, "PPT", body), BASE, {})
    assert '`<iframe src="https://x">deck</iframe>`' in doc.body
    assert not any(line.rstrip().endswith("\\") for line in doc.body.split("\n"))
