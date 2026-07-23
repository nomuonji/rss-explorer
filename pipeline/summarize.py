"""Optional LLM judge — the real interestingness signal + Japanese output.

If ANTHROPIC_API_KEY is set, Claude actually READS a shortlist of items and:
  - scores genuine interestingness 0-100 (novel idea / depth / would-change-how-
    you-see-something — NOT mere obscurity, NOT news/announcements),
  - writes a Japanese title and a one-line Japanese "why it's interesting",
  - tags a rough kind (idea / research / tool / news / other).

This is what lets an English feed be triaged in Japanese, and what turns
"far from the centre" into "actually worth your time". Entirely optional and
never fatal: no key / no SDK / any error → items keep their heuristic scores.
One batched call keeps cost near zero.
"""
from __future__ import annotations

import json
import os

MODEL = "claude-haiku-4-5-20251001"


def judge_items(items: list[dict]) -> int:
    """Mutates items in place. Returns how many were judged (0 if disabled)."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not items:
        return 0
    try:
        import anthropic
    except ImportError:
        return 0

    payload = [
        {"i": n, "title": it["title"], "source": it["source_title"],
         "excerpt": (it.get("summary") or "")[:320]}
        for n, it in enumerate(items)
    ]
    prompt = (
        "You curate a feed for a Japanese reader who is bored of mainstream "
        "tech/games/social-media and hunting for genuinely NOVEL, thought-changing "
        "ideas at the edges of the internet.\n\n"
        "For EACH item, judge it honestly:\n"
        "- interest: 0-100. HIGH = a real idea, argument, mechanism, or discovery "
        "that could change how someone sees things. LOW = news, announcements, "
        "product/funding/lawsuit/drama, listicles, or shallow posts. "
        "Being obscure is NOT interesting by itself. Be a harsh critic.\n"
        "- kind: one of idea|research|tool|news|other.\n"
        "- ja_title: a natural Japanese title (<=40 chars).\n"
        "- ja: one Japanese sentence (<=55 chars) on WHY it's interesting, or plainly why it's dull.\n\n"
        "Return ONLY a JSON array of "
        '{\"i\":<index>,\"interest\":<0-100>,\"kind\":\"...\",\"ja_title\":\"...\",\"ja\":\"...\"}.\n\n'
        f"ITEMS:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=MODEL, max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        arr = json.loads(text)
    except Exception:
        return 0

    by_i = {o["i"]: o for o in arr if isinstance(o, dict) and "i" in o}
    n_judged = 0
    for n, it in enumerate(items):
        o = by_i.get(n)
        if not o:
            continue
        try:
            it["interest"] = max(0.0, min(1.0, float(o.get("interest", 50)) / 100.0))
        except (TypeError, ValueError):
            continue
        it["judged"] = True
        it["kind"] = o.get("kind")
        if o.get("ja_title"):
            it["ja_title"] = o["ja_title"]
        if o.get("ja"):
            it["ja"] = o["ja"]
        it.setdefault("reasons_interest", []).append("AI判定 (" + str(o.get("interest")) + ")")
        n_judged += 1
    return n_judged
