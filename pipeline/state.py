"""Persistent state = the system's memory.

Everything the pipeline learns (which sources exist, how good they are, which
domains are candidates for promotion, what we've already shown) lives in
`data/*.json` and is committed back to the repo by the GitHub Action. That is
what makes the source set *evolve* across runs instead of being fixed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = ROOT / "config"
SITE_DATA = ROOT / "site" / "data"

SOURCES_FILE = DATA / "sources.json"
CANDIDATES_FILE = DATA / "candidates.json"
SEEN_FILE = DATA / "seen.json"

SEEN_MAX = 6000  # keep the dedupe ledger bounded


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _save(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_sources() -> dict:
    return _load(SOURCES_FILE, {"sources": []})


def save_sources(obj: dict) -> None:
    _save(SOURCES_FILE, obj)


def load_candidates() -> dict:
    return _load(CANDIDATES_FILE, {"candidates": {}, "history": []})


def save_candidates(obj: dict) -> None:
    _save(CANDIDATES_FILE, obj)


def load_seen() -> dict:
    return _load(SEEN_FILE, {"ids": {}})


def save_seen(obj: dict) -> None:
    # Trim oldest entries if we blow past the cap.
    ids = obj.get("ids", {})
    if len(ids) > SEEN_MAX:
        newest = sorted(ids.items(), key=lambda kv: kv[1], reverse=True)[:SEEN_MAX]
        obj["ids"] = dict(newest)
    _save(SEEN_FILE, obj)


def new_source(sid, title, url, feed=None, kind="rss", status="trial", tags=None, added=None):
    return {
        "id": sid,
        "title": title,
        "url": url,
        "feed": feed,
        "kind": kind,
        "status": status,          # seed | active | trial | retired
        "tags": tags or [],
        "added": added or today(),
        "weight": 1.0,
        "stats": {"items": 0, "score_sum": 0.0, "avg": 0.5, "last_item": None, "misses": 0},
    }


def record_item_score(source: dict, score: float) -> None:
    st = source.setdefault("stats", {"items": 0, "score_sum": 0.0, "avg": 0.5, "last_item": None, "misses": 0})
    st["items"] += 1
    st["score_sum"] += score
    st["avg"] = round(st["score_sum"] / st["items"], 4)
    st["last_item"] = today()
