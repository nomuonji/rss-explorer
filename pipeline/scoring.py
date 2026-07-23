"""Two separate questions, two separate scores.

  distance : "how far from the algorithmic centre?"  (obscurity / origin)
  interest : "is this actually worth your attention?" (idea vs. ephemera)

They are NOT the same thing — an obscure press release is far-but-boring. The
final rank blends them, and both are shown on the card so you can see the
disagreement. `interest` here is only a heuristic proxy; when an API key is set,
pipeline/summarize.py has Claude read the item and overwrite it with a real
judgement (see run.py).

Everything ships human-readable reasons so you can tune by feel.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

# ---- interest signals -------------------------------------------------------
# Ideas / arguments / mechanisms — the stuff worth reading.
IDEA_WORDS = {
    "essay", "notes on", "a theory of", "why ", "how i", "how we", "how to think",
    "against", "in defense of", "in praise of", "the case for", "first principles",
    "framework", "mental model", "a taxonomy", "field notes", "on the nature of",
    "rethinking", "reconsidering", "what if", "speculative", "manifesto", "philosophy of",
    "from scratch", "we built", "i built", "i made", "handmade", "prototype", "devlog",
    "考察", "試論", "なぜ", "とは何か", "について", "自作", "作ってみた", "設計思想", "原理",
}
# Events / announcements / commerce / drama — usually not ideas.
NEWS_WORDS = {
    "launches", "launched", "announces", "announced", "unveils", "reveals",
    "raises $", "raises €", "funding round", "series a", "series b", "acquires",
    "acquired", "merger", "ipo", "lawsuit", "sues", "settles", "ceo", "resigns",
    "layoffs", "earnings", "quarterly", "stock", "shares", "valuation",
    "release date", "now available", "price", "deal", "discount", "sale", "coupon",
    "vs.", "review:", "hands-on", "leaked", "leak", "rumor", "rumour", "trailer",
    "update:", "patch notes", "版", "発表", "リリース", "提訴", "買収", "決算", "値下げ", "セール",
}
HYPE_WORDS = {
    "top 10", "top 5", "best of", "you won't believe", "ultimate guide",
    "everything you need to know", "tier list", "the truth about", "will shock you",
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
    return max(0.0, min(0.15, 0.15 * (1 - age_days / 21)))


def _is_japanese(text: str) -> bool:
    # hiragana or katakana present = almost certainly Japanese (not just CJK/Chinese)
    return bool(re.search(r"[぀-ヿ]", text or ""))


def distance_score(item: dict, source: dict, mainstream: set[str]) -> tuple[float, list[str]]:
    reasons, s = [], 0.5
    domain = _domain(item.get("url", ""))

    if _is_mainstream(domain, mainstream):
        s -= 0.24; reasons.append("mainstream domain (−)")
    else:
        s += 0.12; reasons.append("off-centre domain (+)")

    pts = item.get("points")
    if isinstance(pts, (int, float)):
        if pts <= 5:
            s += 0.10; reasons.append("pre-viral (+)")
        elif pts >= 150:
            s -= 0.12; reasons.append("already popular (−)")

    src_items = source.get("stats", {}).get("items", 0)
    if source.get("status") in ("seed", "active") and 0 < src_items < 6:
        s += 0.05; reasons.append("scarce source (+)")

    s += _recency_boost(item.get("published"))
    return max(0.0, min(1.0, round(s, 4))), reasons


def interest_score(item: dict, source: dict, prefer_ja: bool) -> tuple[float, list[str]]:
    """Heuristic proxy for 'is this a worthwhile idea?'. Overwritten by the LLM
    judge when available."""
    reasons, s = [], 0.5
    title = item.get("title", "")
    text = f"{title} {item.get('summary','')}".lower()

    if any(w in text for w in IDEA_WORDS):
        s += 0.16; reasons.append("idea / essay (+)")
    if any(w in text for w in NEWS_WORDS):
        s -= 0.20; reasons.append("news / announcement (−)")
    if any(w in text for w in HYPE_WORDS):
        s -= 0.14; reasons.append("hype (−)")

    # a question in the title tends to signal an argument, not an event
    if "?" in title or "？" in title:
        s += 0.06; reasons.append("poses a question (+)")

    # depth: a substantial body (full-text feed) beats a bare headline
    if len(item.get("summary", "") or "") > 600:
        s += 0.08; reasons.append("long-form (+)")
    elif len(item.get("summary", "") or "") < 60 and item.get("points") is None:
        s -= 0.05; reasons.append("thin (−)")

    # readability preference: surface Japanese-language items a little higher
    if prefer_ja and _is_japanese(title):
        s += 0.10; reasons.append("日本語 (+)")

    s += (source.get("stats", {}).get("avg", 0.5) - 0.5) * 0.15  # source track record
    s += random.uniform(-0.03, 0.03)                             # never deterministic
    return max(0.0, min(1.0, round(s, 4))), reasons


def blend(distance: float, interest: float, judged: bool, w_interest_judged=0.6,
          w_interest_heur=0.5) -> float:
    """Interest matters more once a model has actually read the item."""
    w = w_interest_judged if judged else w_interest_heur
    return round(w * interest + (1 - w) * distance, 4)
