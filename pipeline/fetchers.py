"""Fetchers turn a source definition into a list of normalised items.

Everything degrades gracefully: a dead feed or a network hiccup returns [] and
is recorded as a "miss", never crashes the run. Robustness matters because the
source set is meant to churn — links rot, that's expected and handled.
"""
from __future__ import annotations

import hashlib
import time
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

UA = "frontier-radar/1.0 (+https://github.com/ ; personal edge-of-internet scanner)"
HEADERS = {"User-Agent": UA}
TIMEOUT = 20


def item_id(url: str) -> str:
    return hashlib.sha1((url or "").strip().lower().encode("utf-8")).hexdigest()[:16]


def _get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kw)


def _mk(title, url, source, published=None, summary="", points=None):
    return {
        "id": item_id(url),
        "title": (title or "").strip() or "(untitled)",
        "url": url,
        "source_id": source["id"],
        "source_title": source.get("title", source["id"]),
        "source_tags": source.get("tags", []),
        "published": published,
        "summary": (summary or "")[:2000],
        "points": points,
    }


# --------------------------------------------------------------------------- #
# RSS / Atom
# --------------------------------------------------------------------------- #
def fetch_rss(source) -> list[dict]:
    feed_url = source.get("feed")
    if not feed_url:
        return []
    try:
        d = feedparser.parse(feed_url, agent=UA)
    except Exception:
        return []
    items = []
    for e in d.entries[:30]:
        link = e.get("link")
        if not link:
            continue
        pub = None
        if e.get("published_parsed"):
            pub = time.strftime("%Y-%m-%dT%H:%M:%SZ", e.published_parsed)
        elif e.get("updated_parsed"):
            pub = time.strftime("%Y-%m-%dT%H:%M:%SZ", e.updated_parsed)
        summary = e.get("summary", "") or ""
        items.append(_mk(e.get("title"), link, source, pub, summary))
    return items


# --------------------------------------------------------------------------- #
# arXiv (Atom API, no key)
# --------------------------------------------------------------------------- #
def fetch_arxiv(source) -> list[dict]:
    q = source.get("query", "cat:cs.HC")
    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results=25"
    )
    try:
        r = _get(url)
        d = feedparser.parse(r.content)
    except Exception:
        return []
    items = []
    for e in d.entries:
        link = e.get("link")
        pub = None
        if e.get("published_parsed"):
            pub = time.strftime("%Y-%m-%dT%H:%M:%SZ", e.published_parsed)
        items.append(_mk(e.get("title"), link, source, pub, e.get("summary", "")))
    return items


# --------------------------------------------------------------------------- #
# Hacker News (Firebase API, no key). We take NEW stories, not the front page:
# we want things before they go viral. Low points is a feature here.
# --------------------------------------------------------------------------- #
def fetch_hn(source) -> list[dict]:
    try:
        ids = _get("https://hacker-news.firebaseio.com/v0/newstories.json").json()[:60]
    except Exception:
        return []
    items = []
    for i in ids:
        try:
            it = _get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json").json()
        except Exception:
            continue
        if not it or it.get("type") != "story":
            continue
        link = it.get("url")  # external link only; skip Ask/Show text posts w/o url
        if not link:
            continue
        pub = None
        if it.get("time"):
            pub = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(it["time"]))
        items.append(_mk(it.get("title"), link, source, pub, "", points=it.get("score", 0)))
    return items


# --------------------------------------------------------------------------- #
# Are.na — a public channel's blocks. Are.na is itself an anti-algorithmic
# curation network, so its outbound links are prime candidate-discovery fuel.
# --------------------------------------------------------------------------- #
def fetch_arena(source) -> list[dict]:
    slug = source.get("channel")
    if not slug:
        return []
    try:
        r = _get(f"https://api.are.na/v2/channels/{slug}/contents?per=40&direction=desc")
        data = r.json()
    except Exception:
        return []
    items = []
    for b in data.get("contents", []):
        link = b.get("source", {}).get("url") if b.get("source") else None
        if not link:
            continue
        title = b.get("title") or b.get("generated_title") or ""
        items.append(_mk(title, link, source, b.get("created_at"), b.get("description", "") or ""))
    return items


FETCHERS = {
    "rss": fetch_rss,
    "arxiv": fetch_arxiv,
    "hn": fetch_hn,
    "arena": fetch_arena,
}


def fetch_source(source) -> list[dict]:
    fn = FETCHERS.get(source.get("kind", "rss"), fetch_rss)
    try:
        return fn(source)
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Feed auto-discovery: given a homepage URL, find its RSS/Atom feed.
# Used to promote a discovered candidate domain into a real subscribable source.
# --------------------------------------------------------------------------- #
COMMON_PATHS = ["feed", "rss", "feed.xml", "rss.xml", "atom.xml", "index.xml", "feed/", "rss/"]


def discover_feed(homepage: str) -> str | None:
    try:
        r = _get(homepage)
    except Exception:
        return None
    if r.status_code >= 400:
        return None

    # 1) <link rel="alternate" type="application/rss+xml">
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        for link in soup.find_all("link", rel=lambda v: v and "alternate" in v):
            t = (link.get("type") or "").lower()
            if "rss" in t or "atom" in t or "xml" in t:
                href = link.get("href")
                if href:
                    cand = urljoin(homepage, href)
                    if _looks_like_feed(cand):
                        return cand
    except Exception:
        pass

    # 2) common conventional paths
    base = f"{urlparse(homepage).scheme}://{urlparse(homepage).netloc}/"
    for p in COMMON_PATHS:
        cand = urljoin(base, p)
        if _looks_like_feed(cand):
            return cand
    return None


def _looks_like_feed(url: str) -> bool:
    try:
        d = feedparser.parse(url, agent=UA)
        return bool(d.entries) and not d.bozo or bool(d.entries)
    except Exception:
        return False
