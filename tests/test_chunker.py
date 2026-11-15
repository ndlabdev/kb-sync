import re

from kbsync.chunker import chunk_document, count_tokens
from kbsync.cleaner import to_markdown

from .conftest import BASE, make_article


def _long_article():
    sections = []
    for i in range(12):
        para = " ".join(f"Step {i}.{j}: open the Screens page and change setting number {j}." for j in range(25))
        sections.append(f"<h2>Section {i}</h2><p>{para}</p>")
    sections.append("<h2>Config</h2><pre><code>line1\n\nline2\nline3</code></pre>")
    return make_article(900, "Long guide", "".join(sections))


def test_every_chunk_fits_the_limit_and_is_citable():
    doc = to_markdown(_long_article(), BASE, {})
    chunks = chunk_document(doc, max_tokens=300)
    assert len(chunks) > 5
    for chunk in chunks:
        assert chunk.tokens <= 300
        assert count_tokens(chunk.text) == chunk.tokens
        assert chunk.text.startswith("# Long guide")
        assert f"Article URL: {doc.url}" in chunk.text
        assert chunk.total == len(chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_header_names_the_section_and_code_fence_stays_whole():
    doc = to_markdown(_long_article(), BASE, {})
    chunks = chunk_document(doc, max_tokens=300)
    config = [c for c in chunks if "line1" in c.text]
    assert len(config) == 1
    assert "line1\n\nline2\nline3" in config[0].text
    for chunk in chunks:
        assert chunk.text.count("```") % 2 == 0


def test_heading_is_never_last_line_of_a_chunk():
    doc = to_markdown(_long_article(), BASE, {})
    for chunk in chunk_document(doc, max_tokens=300):
        last = chunk.text.rstrip().split("\n")[-1]
        assert not re.match(r"^#{2,6} ", last)


def test_short_article_is_one_chunk(youtube_article):
    doc = to_markdown(youtube_article, BASE, {})
    chunks = chunk_document(doc, max_tokens=700)
    assert len(chunks) == 1
    assert chunks[0].filename == f"{doc.slug}--00.md"


# ---------------------------------------------------------------- embedding preparation

from kbsync.chunker import prepare_for_embedding  # noqa: E402

FIRE_TV_LIKE = (
    "<h3>In this article, we'll show how to set up OptiSigns on an Amazon Fire TV.</h3>"
    "<ul>" + "".join(f'<li><a href="#S{i % 4}">Section {i} of the guide</a></li>' for i in range(18)) + "</ul>"
    "<p>Turn a TV with an Amazon Fire TV Stick into a digital sign.</p>"
    "<table><tr><td><strong>IMPORTANT</strong></td></tr><tr><td>OptiSigns will end support for Fire TV "
    "Sticks. We recommend the Android Stick Player or the Amazon Signage Stick.</td></tr></table>"
    "<h2>Which Fire TV Devices Work with OptiSigns?</h2><p>Fire OS 7 works. Fire OS 8 is not supported.</p>"
    + "".join(f'<p><a name="S{i}"></a></p><h2>Step {i}</h2><p>'  + "Open settings and change an option. " * 40 + "</p>" for i in range(4))
    + "<h3>That’s all!</h3><p>OptiSigns is the leader in <a href='https://www.optisigns.com/'>digital signage "
    "software</a>. If you have any additional questions, concerns or any feedback about OptiSigns, feel free "
    "to reach out to our support team at <a href='mailto:support@optisigns.com'>support@optisigns.com</a>.</p>"
)


def _fire_tv():
    return to_markdown(make_article(360016174554, "Set Up OptiSigns on Fire TV", FIRE_TV_LIKE), BASE, {})


def test_key_warning_lands_in_the_first_chunk():
    chunks = chunk_document(_fire_tv(), max_tokens=700)
    first = chunks[0].text
    assert "IMPORTANT" in first and "Android Stick Player" in first
    assert "Fire OS 8 is not supported" in first


def test_toc_boilerplate_and_lede_heading_are_not_embedded():
    doc = _fire_tv()
    text = "".join(c.text for c in chunk_document(doc, max_tokens=700))
    assert "](#" not in text
    assert "additional questions" not in text and "leader in" not in text and "That’s all" not in text
    assert "› In this article" not in text
    assert "In this article, we'll show how to set up OptiSigns" in text  # kept as plain text


def test_markdown_file_itself_keeps_everything():
    body = _fire_tv().body
    assert "- [Section 0 of the guide](#step-0)" in body  # table of contents kept, links resolved
    assert "If you have any additional questions" in body


def test_code_blocks_are_never_filtered():
    md = "```\n- [x](#y)\nIf you have any additional questions\n```"
    assert prepare_for_embedding(md) == md


def test_sign_off_variants_are_dropped():
    for line in (
        "If you have any additional questions, concerns or any feedback about OptiSigns, feel free to reach out to our support team.",
        "For any additional questions, concerns, or feedback about OptiSigns, feel free to reach out to our support team at support@optisigns.com.",
        "If you require any further assistance or have additional questions, please contact support.",
    ):
        assert prepare_for_embedding(f"Body text.\n\n{line}") == "Body text."
    kept = "The Q&A app lets viewers send additional questions to the host."
    assert prepare_for_embedding(kept) == kept
