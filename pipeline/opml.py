"""Export the live source set as OPML.

OPML is the standard subscription-list format every RSS reader imports
(NetNewsWire, Feedly, Inoreader, Reeder ...). We regenerate it on every run, so
it always reflects the *current* source set — including feeds the system
auto-discovered — not a hand-maintained snapshot. Written to site/ so the
published page can offer a one-click "subscribe to everything" download.
"""
from __future__ import annotations

from xml.sax.saxutils import quoteattr

from . import state

# tag -> group. First matching group (in this order) wins.
GROUPS = [
    ("日本語 / Japanese", {"ja"}),
    ("Tools for Thought", {"tools-for-thought", "interfaces", "local-first"}),
    ("Games / Experimental", {"gamedev", "experimental", "political"}),
    ("Creative / Art / Curation", {"art", "craft", "design", "creative", "curation", "interviews"}),
    ("Ideas / Science / Culture", {"ideas", "philosophy", "science", "essays", "progress",
                                   "meta", "physics", "society", "books", "rigor", "culture",
                                   "commentary", "sustainability", "contrarian"}),
    ("Tech / Frontier", {"tech", "computing", "frontier", "research"}),
    ("Auto-discovered", {"discovered"}),
]


def _group_of(tags: list[str]) -> str:
    t = set(tags or [])
    for name, keys in GROUPS:
        if t & keys:
            return name
    return "Other"


def _outline(s: dict) -> str:
    title = quoteattr(s.get("title", s["id"]))
    xml = quoteattr(s["feed"])
    html = quoteattr(s.get("url", s["feed"]))
    return f'      <outline type="rss" text={title} title={title} xmlUrl={xml} htmlUrl={html}/>'


def write_opml(sources: dict) -> int:
    # Only real, importable http(s) feeds; skip engines (HN/arXiv) and retired.
    feeds = [s for s in sources["sources"]
             if s.get("feed") and str(s["feed"]).startswith("http") and s.get("status") != "retired"]

    buckets: dict[str, list[str]] = {}
    for s in feeds:
        buckets.setdefault(_group_of(s.get("tags", [])), []).append(s)

    body = []
    order = [g[0] for g in GROUPS] + ["Other"]
    for g in order:
        items = buckets.get(g)
        if not items:
            continue
        items.sort(key=lambda s: s.get("title", "").lower())
        body.append(f'    <outline text={quoteattr(g)} title={quoteattr(g)}>')
        body.extend(_outline(s) for s in items)
        body.append("    </outline>")

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<opml version="2.0">\n'
        "  <head>\n"
        "    <title>frontier-radar — off-algorithm feeds</title>\n"
        f"    <dateModified>{state.now_iso()}</dateModified>\n"
        "  </head>\n"
        "  <body>\n"
        + "\n".join(body) + "\n"
        "  </body>\n"
        "</opml>\n"
    )
    (state.ROOT / "site" / "frontier-radar.opml").write_text(xml, encoding="utf-8")
    return len(feeds)
