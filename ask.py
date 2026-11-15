"""Ask the assistant a question from the terminal, with the same system prompt as the Playground.

    python ask.py "How do I add a YouTube video?"

The Assistants API was retired on 2026-08-26; this uses the Responses API with the
file_search tool over the same vector store.
"""

from __future__ import annotations

import re
import sys

from openai import OpenAI

from kbsync.config import Settings

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""


# File search citation markers look like "\ue200filecite\ue202turn1file1\ue201". The API normally
# strips them into annotations; when one leaks into the text, remove it (and any stray marker chars).
_CITATION_MARKER = re.compile(r"\ue200[^\ue201]*\ue201")
_PRIVATE_USE = re.compile(r"[\ue000-\uf8ff]")
_BARE_MARKER = re.compile(r"\s*\b(?:filecite|cite)(?:\s*turn\d+file\d+)+\b")


def clean_answer(text: str) -> str:
    """Remove leaked citation markers; leaves the rest of the answer untouched."""
    text = _CITATION_MARKER.sub("", text)
    text = _PRIVATE_USE.sub(" ", text)
    text = _BARE_MARKER.sub("", text)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", text)).strip()


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    question = " ".join(sys.argv[1:]) or "How do I add a YouTube video?"
    settings = Settings.from_env()
    if not settings.openai_api_key:
        print("Set OPENAI_API_KEY first", file=sys.stderr)
        return 1
    client = OpenAI(api_key=settings.openai_api_key)
    store_id = settings.vector_store_id or next(
        (s.id for s in client.vector_stores.list(limit=100) if s.name == settings.vector_store_name), None
    )
    if not store_id:
        print("No vector store found; run main.py first", file=sys.stderr)
        return 1

    response = client.responses.create(
        model=settings.openai_model,
        instructions=SYSTEM_PROMPT,
        input=question,
        tools=[{"type": "file_search", "vector_store_ids": [store_id], "max_num_results": 6}],
        include=["file_search_call.results"],
    )
    print(f"Q: {question}\n")
    print(clean_answer(response.output_text))

    sources = []
    for item in response.output:
        for result in getattr(item, "results", None) or []:
            url = (result.attributes or {}).get("url")
            if url and url not in sources:
                sources.append(url)
    if sources:
        print("\nRetrieved from:\n" + "\n".join(f"- {u}" for u in sources[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
