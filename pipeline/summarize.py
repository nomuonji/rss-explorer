"""Optional Japanese/English blurbs via the Claude API.

Entirely optional. If ANTHROPIC_API_KEY is not set (or the SDK isn't installed,
or the call fails), the pipeline just ships titles + excerpts. Never fatal.
Uses a cheap model and a single batched call to keep cost near zero.
"""
from __future__ import annotations

import json
import os

MODEL = "claude-haiku-4-5-20251001"


def summarize_items(items: list[dict]) -> None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not items:
        return
    try:
        import anthropic
    except ImportError:
        return

    payload = [
        {"i": n, "title": it["title"], "source": it["source_title"],
         "excerpt": (it.get("summary") or "")[:280]}
        for n, it in enumerate(items)
    ]
    prompt = (
        "You curate a feed for someone bored of mainstream tech/games/social media, "
        "hunting for genuinely novel ideas at the edges of the internet.\n"
        "For EACH item below, write a one-sentence Japanese blurb (<=45 chars) that says "
        "why it might be interesting or what's novel about it — concrete, no hype, honest. "
        "If it looks dull, say so plainly.\n"
        "Return ONLY a JSON array of objects: {\"i\": <index>, \"ja\": \"...\"}.\n\n"
        f"ITEMS:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=MODEL, max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        arr = json.loads(text)
        by_i = {o["i"]: o.get("ja", "") for o in arr if isinstance(o, dict)}
        for n, it in enumerate(items):
            if by_i.get(n):
                it["blurb_ja"] = by_i[n]
    except Exception:
        return
