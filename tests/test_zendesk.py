from kbsync.zendesk import Article, fetch_articles, slugify

BASE = "https://support.optisigns.com"


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    """Two pages; page 2 repeats an article (offset pagination drift) and has a draft."""

    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if "page=2" in url:
            return FakeResponse({
                "articles": [
                    _raw(2, "Second"),  # duplicate
                    _raw(3, "Draft one", draft=True),
                    _raw(4, "Fourth"),
                ],
                "next_page": None,
            })
        return FakeResponse({
            "articles": [_raw(1, "First"), _raw(2, "Second")],
            "next_page": f"{BASE}/api/v2/help_center/en-us/articles.json?page=2&per_page=100",
        })


def _raw(i, title, draft=False):
    return {
        "id": i, "title": title, "draft": draft, "body": "<p>x</p>",
        "html_url": f"{BASE}/hc/en-us/articles/{i}-{title.replace(' ', '-')}",
        "updated_at": "2026-01-01T00:00:00Z", "edited_at": "2026-01-01T00:00:00Z", "section_id": 9,
    }


def test_follows_pagination_skips_drafts_and_duplicates():
    session = FakeSession()
    articles, complete = fetch_articles(session, BASE)
    assert [a.id for a in articles] == [1, 2, 4]
    assert complete is True
    assert session.calls[1][1] is None  # next_page URL already carries the query string


def test_limit_marks_fetch_incomplete():
    articles, complete = fetch_articles(FakeSession(), BASE, limit=2)
    assert len(articles) == 2
    assert complete is False


def test_slug_uses_id_and_url_words():
    article = Article.from_api(_raw(56987330525587, "Connect ChatGPT, Claude & Grok"))
    assert article.slug == "56987330525587-connect-chatgpt-claude-grok"
    assert slugify("  Ünïcode -- Title!! ") == "n-code-title"
