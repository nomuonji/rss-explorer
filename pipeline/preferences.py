"""User taste: pins (confirmed sources), blocks, and score nudges.

This is the only place the system knows what *you* like — the heuristics and the
LLM judge estimate general quality, but preferences here bend the ranking toward
your taste and lock in sources you never want to lose.
"""
from __future__ import annotations

from urllib.parse import urlparse

import yaml

from . import state

DEFAULTS = {
    "pin": [], "block": [], "boost_keywords": [], "mute_keywords": [],
    "boost_domains": [], "mute_domains": [], "boost_tags": [],
}


def _domain(url: str) -> str:
    try:
        return urlparse(url or "").netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _slug(domain: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", domain.lower()).strip("-")[:40] or "pinned"


def load_prefs() -> dict:
    path = state.CONFIG / "preferences.yaml"
    prefs = dict(DEFAULTS)
    if path.exists():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for k in DEFAULTS:
                v = loaded.get(k)
                if isinstance(v, list):
                    prefs[k] = [str(x).strip() for x in v if str(x).strip()]
        except Exception:
            pass
    # normalise the match-by-value lists
    for k in ("boost_domains", "mute_domains"):
        prefs[k] = [d.lower().replace("www.", "") for d in prefs[k]]
    prefs["boost_tags"] = [t.lower() for t in prefs["boost_tags"]]
    return prefs


def apply_pins(sources: dict, prefs: dict) -> list[str]:
    """Mark matching sources as pinned; add brand-new pinned feeds."""
    pinned_ids = []
    existing_ids = {s["id"] for s in sources["sources"]}
    for entry in prefs.get("pin", []):
        match = None
        if entry in existing_ids:
            match = next(s for s in sources["sources"] if s["id"] == entry)
        elif entry.startswith("http"):
            match = next((s for s in sources["sources"]
                          if s.get("feed") == entry or s.get("url") == entry), None)
            if not match:  # a feed we don't have yet -> add it, pinned
                sid = _slug(_domain(entry))
                while sid in existing_ids:
                    sid += "-x"
                existing_ids.add(sid)
                src = state.new_source(sid, title=_domain(entry) or entry, url=entry,
                                       feed=entry, kind="rss", status="pinned", tags=["pinned"])
                sources["sources"].append(src)
                pinned_ids.append(sid)
                continue
        else:  # treat as a domain
            match = next((s for s in sources["sources"]
                          if _domain(s.get("url", "")) == entry or _domain(s.get("feed", "")) == entry), None)
        if match:
            match["status"] = "pinned"
            match["weight"] = max(match.get("weight", 1.0), 1.5)
            pinned_ids.append(match["id"])
    return pinned_ids


def apply_blocks(sources: dict, prefs: dict) -> list[str]:
    block = set(prefs.get("block", []))
    if not block:
        return []
    blocked = []
    for s in sources["sources"]:
        if (s["id"] in block or _domain(s.get("url", "")) in block
                or s.get("feed") in block or _domain(s.get("feed", "")) in block):
            s["status"] = "blocked"
            blocked.append(s["id"])
    return blocked


def is_blocked_item(item: dict, prefs: dict) -> bool:
    block = set(prefs.get("block", []))
    if not block:
        return False
    return _domain(item.get("url", "")) in block or item.get("source_id") in block


def score_adjust(item: dict, source: dict, prefs: dict) -> tuple[float, list[str]]:
    """Return (interest delta, reasons) from the user's stated taste."""
    delta, reasons = 0.0, []
    text = f"{item.get('title','')} {item.get('summary','')}".lower()
    dom = _domain(item.get("url", ""))
    tags = [t.lower() for t in source.get("tags", [])]

    for kw in prefs.get("boost_keywords", []):
        if kw.lower() in text:
            delta += 0.15
            reasons.append(f"好み:{kw} (+)")
    for kw in prefs.get("mute_keywords", []):
        if kw.lower() in text:
            delta -= 0.30
            reasons.append(f"ミュート:{kw} (−)")
    if dom in prefs.get("boost_domains", []):
        delta += 0.12
        reasons.append("好みドメイン (+)")
    if dom in prefs.get("mute_domains", []):
        delta -= 0.25
        reasons.append("苦手ドメイン (−)")
    if any(t in prefs.get("boost_tags", []) for t in tags):
        delta += 0.10
        reasons.append("好みタグ (+)")
    if source.get("status") == "pinned":
        delta += 0.08
        reasons.append("確定ソース (+)")
    return delta, reasons
