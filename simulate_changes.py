"""Simulate Help Center changes on the real vector store, to demo the daily delta.

    python simulate_changes.py --update 360051014713   # next run: that article is "updated"
    python simulate_changes.py --remove 360016253694   # next run: that article is "added" again
    python simulate_changes.py --orphan                # next run: a fake retired article is "deleted"

Then run `python main.py` and check the RUN SUMMARY line. Flags can be combined.
Nothing on the Help Center is touched; only the vector store's state is altered.
"""

from __future__ import annotations

import argparse
import sys

from openai import OpenAI

from kbsync.config import Settings
from kbsync.vector_store import STATIC_CHUNKING, OpenAIVectorStore

ORPHAN_ID = "999999999"


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--update", metavar="ARTICLE_ID", help="mark this article's chunks as outdated")
    parser.add_argument("--remove", metavar="ARTICLE_ID", help="remove this article's chunks from the store")
    parser.add_argument("--orphan", action="store_true", help="add a chunk for an article that no longer exists")
    args = parser.parse_args()
    if not (args.update or args.remove or args.orphan):
        parser.print_help()
        return 1

    settings = Settings.from_env()
    client = OpenAI(api_key=settings.openai_api_key, max_retries=5)
    store = OpenAIVectorStore.connect(client, settings.vector_store_id, settings.vector_store_name)
    vs_id = store.vector_store_id
    files = list(client.vector_stores.files.list(vector_store_id=vs_id, limit=100))

    def of_article(article_id: str):
        return [f for f in files if (f.attributes or {}).get("article_id") == article_id]

    if args.update:
        targets = of_article(args.update)
        for f in targets:
            client.vector_stores.files.update(
                f.id, vector_store_id=vs_id, attributes={**f.attributes, "content_hash": "simulated-outdated"}
            )
        print(f"--update {args.update}: marked {len(targets)} chunk(s) outdated -> expect updated=1")

    if args.remove:
        targets = of_article(args.remove)
        store.remove_files([f.id for f in targets])
        print(f"--remove {args.remove}: removed {len(targets)} chunk(s) -> expect added=1")

    if args.orphan:
        text = (
            "# Retired article (simulation)\n"
            "Article URL: https://support.optisigns.com/hc/en-us/articles/999999999-retired\n\n"
            "This article no longer exists on the Help Center.\n"
        )
        uploaded = client.files.create(
            file=("999999999-retired--00.md", text.encode("utf-8"), "text/markdown"), purpose="assistants"
        )
        client.vector_stores.files.create(
            vector_store_id=vs_id,
            file_id=uploaded.id,
            attributes={
                "article_id": ORPHAN_ID, "content_hash": "simulated", "chunk_index": 0, "chunk_total": 1,
                "url": "https://support.optisigns.com/hc/en-us/articles/999999999-retired", "title": "Retired",
            },
            chunking_strategy=STATIC_CHUNKING,
        )
        print("--orphan: added a chunk for retired article 999999999 -> expect deleted=1")

    print("\nNow run: python main.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
