"""Frontier scoring.

The score answers one question: "how far is this from the algorithmic centre?"
High = individual-origin, pre-viral, edge-of-field, scarce. Low = mainstream,
already-popular, hype. Every score ships with human-readable reasons so the site
can show *why* something surfaced — and so you can tune the heuristic by feel.

A small random jitter is added on purpose: determinism is how a feed ossifies.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

# Words that smell like the edge (essays, prototypes, primary work)...
EDGE_WORDS = {
    "essay", "prototype", "devlog", "experiment", "experimental", "notebook",
    "tools for thought", "local-first", "from scratch", "handmade", "in the wild",
    "a theory of", "notes on", "field notes", "speculative", "prototyping",
    "we built", "i built", "i made", "homemade", "self-hosted", "zine",
}
# ...and words that smell like the centre (hype, listicles, commerce).
HYPE_WORDS = {
    "top 10", "top 5", "best of", "you won't believe", "ultimate guide",
    "deal", "discount", "sale", "giveaway", "vs", "review roundup",
    "everything you need to know", "explained", "tier list", "trailer",
    "release date", "leaked", "rumor", "rumour",
}


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _is_mainstream(domain: str, mainstream: set[str]) -> bool:
    return any(domain == m or domain.endswith("." + m) for m in mainstream)


def _recency_boost(published: str | None) -> float:
    if not published:
        return 0.0
    try:
        dt = datetime.strptime(published[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return 0.0
    age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    if age_days < 0:
        return 0.0
    # fresh but not obsessively so: full boost < 3d, fades out by ~21d
    return max(0.0, min(0.15, 0.15 * (1 - age_days / 21)))


def score_item(item: dict, source: dict, mainstream: set[str]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    s = 0.5
    text = f"{item.get('title','')} {item.get('summary','')}".lower()
    domain = _domain(item.get("url", ""))

    # --- origin: individual/edge domain vs. the centre ---
    if _is_mainstream(domain, mainstream):
        s -= 0.22
        reasons.append("mainstream domain (−)")
    else:
        s += 0.10
        reasons.append("off-centre domain (+)")

    # --- pre-viral bonus: reward LOW popularity where we have a signal (HN) ---
    pts = item.get("points")
    if isinstance(pts, (int, float)):
        if pts <= 5:
            s += 0.12
            reasons.append("pre-viral / low points (+)")
        elif pts >= 150:
            s -= 0.12
            reasons.append("already popular (−)")

    # --- scarcity: sources that rarely post are worth more when they do ---
    src_items = source.get("stats", {}).get("items", 0)
    if source.get("status") in ("seed", "active") and src_items and src_items < 6:
        s += 0.06
        reasons.append("scarce source (+)")

    # --- lexical resonance ---
    if any(w in text for w in EDGE_WORDS):
        s += 0.10
        reasons.append("edge vocabulary (+)")
    if any(w in text for w in HYPE_WORDS):
        s -= 0.12
        reasons.append("hype vocabulary (−)")

    # --- language arbitrage: non-latin (JP/CJK etc.) content is under-served
    #     in English feeds and vice-versa; a small nudge to reward crossing over.
    if re.search(r"[぀-ヿ一-鿿가-힯]", item.get("title", "")):
        s += 0.05
        reasons.append("language arbitrage (+)")

    # --- recency ---
    rb = _recency_boost(item.get("published"))
    if rb:
        s += rb
        reasons.append("fresh (+)")

    # --- source's own track record ---
    avg = source.get("stats", {}).get("avg", 0.5)
    s += (avg - 0.5) * 0.2  # good sources lift their items a little

    # --- exploration jitter: never fully deterministic ---
    s += random.uniform(-0.04, 0.04)

    return max(0.0, min(1.0, round(s, 4))), reasons
