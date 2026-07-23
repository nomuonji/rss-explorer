"""Discovery = the reason this project isn't just a fixed RSS reader.

Three mechanisms keep the source set alive and growing:

  1. CO-CITATION.  When trusted sources (and the anti-algorithmic aggregators)
     keep linking to the same outside domain, that domain earns a "trial" slot.
     The edge tends to link to the edge; we follow those links.

  2. AUTO-SUBSCRIBE. A promoted domain gets its RSS/Atom feed auto-discovered
     and cached, so from then on we read it directly at the source.

  3. LIFECYCLE.  Trials that produce good items graduate to `active`; sources
     that go stale or low-signal are retired. The list curates itself.

Together with epsilon-greedy exploration (in run.py) this means the set of
things we watch is never frozen.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from . import state
from .fetchers import discover_feed


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _is_mainstream(domain: str, mainstream: set[str]) -> bool:
    return any(domain == m or domain.endswith("." + m) for m in mainstream)


def _slug(domain: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", domain.lower()).strip("-")[:40] or "src"


def _outbound_domains(item: dict, self_domain: str) -> set[str]:
    """External domains an item points at. For aggregator items (HN/Are.na), the
    item's own linked domain is the discovery signal; for blog posts we also mine
    links embedded in the summary/body."""
    out = set()
    d = _domain(item.get("url", ""))
    if d and d != self_domain:
        out.add(d)
    summary = item.get("summary", "") or ""
    if "<a" in summary:
        try:
            for a in BeautifulSoup(summary, "html.parser").find_all("a", href=True):
                dd = _domain(a["href"])
                if dd and dd != self_domain:
                    out.add(dd)
        except Exception:
            pass
    return out


def update_candidates(candidates: dict, items: list[dict], sources_by_id: dict,
                      known_domains: set[str], mainstream: set[str]) -> None:
    """Attribute each outbound domain to the source that referred it."""
    cand = candidates.setdefault("candidates", {})
    for it in items:
        src = sources_by_id.get(it["source_id"], {})
        # Only trusted referrers grow the graph: seeds, active sources, and the
        # curated aggregators. (A trial source can't yet vouch for others.)
        if src.get("status") not in ("seed", "active") and src.get("kind") not in ("hn", "arena", "arxiv", "rss"):
            continue
        if src.get("status") == "trial":
            continue
        self_dom = _domain(src.get("url", "") or it.get("url", ""))
        for dom in _outbound_domains(it, self_dom):
            if not dom or dom in known_domains or _is_mainstream(dom, mainstream):
                continue
            entry = cand.setdefault(dom, {
                "referrers": [], "count": 0, "first_seen": state.today(),
                "sample_url": it.get("url"), "feed": None, "checked": False, "promoted": False,
            })
            if it["source_id"] not in entry["referrers"]:
                entry["referrers"].append(it["source_id"])
            entry["count"] = len(entry["referrers"])


def promote_candidates(candidates: dict, sources: dict, settings: dict) -> list[dict]:
    """Turn well-referenced candidate domains into real `trial` sources."""
    promoted = []
    threshold = settings.get("promote_after_referrers", 2)
    budget = settings.get("probe_budget", 12)
    cand = candidates.setdefault("candidates", {})
    hist = candidates.setdefault("history", [])
    existing_ids = {s["id"] for s in sources["sources"]}

    # Probe the most-referenced unpromoted, unchecked candidates first.
    ranked = sorted(
        (d for d, e in cand.items() if not e.get("promoted") and not e.get("checked") and e["count"] >= threshold),
        key=lambda d: cand[d]["count"], reverse=True,
    )
    for dom in ranked:
        if budget <= 0:
            break
        budget -= 1
        entry = cand[dom]
        entry["checked"] = True
        feed = discover_feed(f"https://{dom}/")
        if not feed:
            hist.append({"date": state.today(), "domain": dom, "action": "probe-failed",
                         "detail": f"{entry['count']} referrers, no feed found"})
            continue
        sid = _slug(dom)
        while sid in existing_ids:
            sid += "-x"
        existing_ids.add(sid)
        src = state.new_source(
            sid, title=dom, url=f"https://{dom}/", feed=feed, kind="rss",
            status="trial", tags=["discovered"],
        )
        src["discovered_via"] = entry["referrers"][:5]
        sources["sources"].append(src)
        entry["promoted"] = True
        entry["feed"] = feed
        promoted.append(src)
        hist.append({"date": state.today(), "domain": dom, "action": "promoted",
                     "detail": f"referred by {', '.join(entry['referrers'][:5])}"})
    return promoted


def manage_lifecycle(sources: dict, settings: dict) -> dict:
    """Graduate good trials, retire stale/low-signal sources."""
    changes = {"graduated": [], "retired": []}
    grad_items = settings.get("trial_graduation_items", 3)
    retire_avg = settings.get("retire_below_avg", 0.28)
    retire_min = settings.get("retire_min_items", 8)
    hist_note = []

    for s in sources["sources"]:
        st = s.get("stats", {})
        items = st.get("items", 0)
        avg = st.get("avg", 0.5)

        if s["status"] == "trial" and items >= grad_items and avg >= retire_avg:
            s["status"] = "active"
            changes["graduated"].append(s["id"])
            hist_note.append({"date": state.today(), "domain": s["id"], "action": "graduated",
                              "detail": f"avg={avg} over {items} items"})

        # Never retire the curated aggregators — they are engines, not opinions.
        if s.get("kind") in ("hn", "arxiv", "arena"):
            continue
        if s["status"] in ("active", "trial", "seed") and items >= retire_min and avg < retire_avg:
            s["status"] = "retired"
            changes["retired"].append(s["id"])
            hist_note.append({"date": state.today(), "domain": s["id"], "action": "retired",
                              "detail": f"avg={avg} over {items} items"})
    return {"changes": changes, "history": hist_note}
