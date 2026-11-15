from ask import clean_answer


def test_leaked_citation_marker_is_removed():
    raw = "then click **Save**. \ue200filecite\ue202turn1file1\ue202turn1file8\ue201\n3. To show it on a screen"
    assert clean_answer(raw) == "then click **Save**.\n3. To show it on a screen"


def test_marker_without_delimiters_is_removed():
    assert clean_answer("Click Save. filecite turn1file1 turn1file8") == "Click Save."


def test_normal_answer_is_unchanged():
    text = "- Go to **Files/Assets**\n- Paste the URL\n\nArticle URL: https://support.optisigns.com/hc/en-us/articles/1"
    assert clean_answer(text) == text
