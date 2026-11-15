# kb-sync

Scrapes a Zendesk Help Center into clean Markdown, keeps an OpenAI vector store in sync with it once a day (uploading only what changed), and backs a support assistant that answers from those docs with cited article URLs.

- **Daily job logs:** _published after the first scheduled run on Railway (link added in a follow-up commit)._
- **Sample answer:** _screenshot of the assistant answering "How do I add a YouTube video?" added in a follow-up commit._

## Run with Docker

Needs only Docker and an OpenAI API key. Runs one sync and exits 0 on success.

```bash
docker build -t kb-sync .
docker run --rm -e API_KEY=sk-... kb-sync main.py     # key only
docker run --rm --env-file .env kb-sync main.py       # or every variable from .env
```

The vector store is found by name (`support-kb`) or created, so a fresh OpenAI account needs only the key.

## Run locally

Setup, once (Python 3.12):

```bash
pip install -r requirements.txt
cp .env.sample .env                  # then set OPENAI_API_KEY
```

Run:

```bash
python main.py                       # scrape, clean, chunk, upload the delta; logs added / updated / skipped
```

Optional:

```bash
DRY_RUN=true python main.py          # preview: writes ./articles/*.md, no OpenAI calls
python ask.py "How do I add a YouTube video?"   # ask the assistant from the terminal
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q                            # unit tests, no network needed
python qa.py                         # quality checks on the exported ./articles
```

## Chunking strategy

- **Split on structure, not a fixed size.** Articles are split on headings and consecutive sections are packed up to 700 tokens; long sections fall back to paragraph splits, and code blocks are never cut.
- **Every chunk is self-contained and citable.** Each starts with `# Title › Section` and `Article URL:`, so any retrieved chunk carries its context and a link.
- **1 file = 1 chunk.** Each chunk is uploaded as its own file with a static 800-token, 0-overlap strategy, so OpenAI never re-splits it. The logged chunk count is exact (396 articles, 1,062 chunks), and per-chunk attributes drive the daily delta. No overlap is needed because cuts fall on section boundaries.
- **Noise stays out of the vectors.** Tables of contents, the repeated support sign-off and intro sentences styled as headings are dropped from chunks (the `.md` files keep them), so an article's first chunk holds its key content.

## How it works

1. **Fetch**: Help Center API, drafts skipped. The API returns only the article body, so navigation and ads never enter the pipeline.
2. **Clean**: HTML to Markdown with headings, code blocks and tables kept; links between articles become relative `.md` links; `qa.py` reports 0 errors on all 396 files.
3. **Delta**: each file in the store carries `article_id` and `content_hash`, read back on every run, so the job keeps no state of its own. Changed articles are uploaded before their old files are removed; articles gone from the Help Center are deleted.
4. **Report**: a `RUN SUMMARY added= updated= skipped= ...` log line and a JSON report, also published to a GitHub Gist.

Verified runs: first sync `added=396`; next run `skipped=396` with nothing uploaded; after `simulate_changes.py` altered the store, `added=1 updated=1 deleted=1 skipped=394`.

## Daily job

A Railway cron job built from the `Dockerfile` (`railway.toml`), daily at 02:13 UTC. Variables: `OPENAI_API_KEY`, `VECTOR_STORE_ID`, `GIST_ID`, `GIST_TOKEN`.

## Notes

- The OpenAI Assistants API was retired in August 2026, so the assistant runs on the Responses API with `file_search` over the same vector store, with the system prompt verbatim. The model is set by `OPENAI_MODEL`.
- `articles/` is a snapshot of the export on 2026-11-15. The daily job updates the vector store, not this folder; regenerate it with `DRY_RUN=true python main.py`.
