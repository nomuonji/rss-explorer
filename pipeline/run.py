"""Orchestrator. Run:  python -m pipeline.run

One pass = fetch → score → dedupe → discover new sources → curate the source
set → render JSON for the site → persist memory back to data/.
"""
from __future__ import annotations

import os
import random
from pathlib import Path
from urllib.parse import urlparse

import yaml


def _load_dotenv() -> None:
    """Minimal .env loader for local runs (no extra dependency). On GitHub the
    values come from repo secrets via the workflow env, so this is a no-op there."""
    env = Path(__file__).resolve().parents[1] / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

from . import discovery, opml, preferences, render, state
from .fetchers import discover_feed, fetch_source, item_id
from .scoring import blend, distance_score, interest_score
from .summarize import judge_items

SEED_FEED_PROBE_BUDGET = 16  # resolve this many missing seed feeds per run


def _domain(url: str) -> str:
    try:
        return urlparse(url or "").netloc.lower().replace("www.", "")
    except Exception:
        return ""


def load_config() -> dict:
    return yaml.safe_load((state.CONFIG / "seeds.yaml").read_text(encoding="utf-8"))


def load_mainstream() -> set[str]:
    out = set()
    for line in (state.CONFIG / "mainstream.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line.lower().replace("www.", ""))
    return out


def sync_seeds_into_state(cfg: dict, sources: dict) -> None:
    """Make sure everything in seeds.yaml exists as a source (status=seed),
    without clobbering learned stats for sources that already exist."""
    existing = {s["id"]: s for s in sources["sources"]}
    for d in cfg.get("discovery_sources", []):
        if d["id"] not in existing:
            src = state.new_source(
                d["id"], d.get("title", d["id"]), d.get("feed") or f"engine://{d['id']}",
                feed=d.get("feed"), kind=d["kind"], status="seed", tags=d.get("tags", []),
            )
            for k in ("query", "channel"):
                if k in d:
                    src[k] = d[k]
            sources["sources"].append(src)
    for d in cfg.get("seeds", []):
        if d["id"] not in existing:
            sources["sources"].append(state.new_source(
                d["id"], d.get("title", d["id"]), d["url"],
                feed=d.get("feed"), kind="rss", status="seed", tags=d.get("tags", []),
            ))


def resolve_missing_feeds(sources: dict) -> int:
    """Auto-discover feeds for rss sources that don't have one yet (budgeted)."""
    budget = SEED_FEED_PROBE_BUDGET
    resolved = 0
    for s in sources["sources"]:
        if budget <= 0:
            break
        if s.get("kind") == "rss" and not s.get("feed") and s.get("status") != "retired":
            budget -= 1
            feed = discover_feed(s["url"])
            if feed:
                s["feed"] = feed
                resolved += 1
            else:
                s.setdefault("stats", {})["misses"] = s["stats"].get("misses", 0) + 1
    return resolved


def choose_exploration(sources: dict, k: int) -> list[dict]:
    """epsilon-greedy: deliberately re-sample retired / low-data sources so the
    watch-list never freezes into a fixed set."""
    pool = [s for s in sources["sources"]
            if s["status"] == "retired" or (s["status"] == "trial" and s.get("stats", {}).get("items", 0) < 2)]
    random.shuffle(pool)
    return pool[:k]


def run():
    cfg = load_config()
    settings = cfg.get("settings", {})
    mainstream = load_mainstream()

    prefs = preferences.load_prefs()
    sources = state.load_sources()
    candidates = state.load_candidates()
    seen = state.load_seen()

    sync_seeds_into_state(cfg, sources)
    # apply the user's taste to the source set: pin confirmed sources, block others
    pinned_ids = preferences.apply_pins(sources, prefs)
    blocked_ids = preferences.apply_blocks(sources, prefs)
    resolved = resolve_missing_feeds(sources)

    sources_by_id = {s["id"]: s for s in sources["sources"]}
    known_domains = {_domain(s["url"]) for s in sources["sources"] if s.get("url")}
    known_domains.discard("")

    # --- FETCH --------------------------------------------------------------
    active = [s for s in sources["sources"] if s["status"] in ("seed", "active", "trial", "pinned")]
    explore_k = max(1, round(settings.get("explore_fraction", 0.15) * settings.get("digest_size", 40) / 4))
    explorers = choose_exploration(sources, explore_k)
    explore_ids = {s["id"] for s in explorers}

    all_items: list[dict] = []
    for s in active + explorers:
        items = fetch_source(s)
        if not items and s.get("kind") == "rss" and s["status"] not in ("seed",):
            s.setdefault("stats", {})["misses"] = s["stats"].get("misses", 0) + 1
        for it in items:
            it["explore"] = s["id"] in explore_ids
        all_items.extend(items)

    # --- SCORE: distance (obscurity) and interest (worth), kept separate ----
    prefer_ja = settings.get("prefer_language", "ja") == "ja"
    for it in all_items:
        src = sources_by_id.get(it["source_id"], {})
        dist, dr = distance_score(it, src, mainstream)
        inter, ir = interest_score(it, src, prefer_ja)
        pdelta, pr = preferences.score_adjust(it, src, prefs)  # your taste bends it
        inter = max(0.0, min(1.0, inter + pdelta))
        it["distance"] = dist
        it["interest"] = inter
        it["judged"] = False
        it["pinned"] = src.get("status") == "pinned"
        it["reasons"] = dr
        it["reasons_interest"] = ir + pr
        it["score"] = blend(dist, inter, judged=False,
                            w_interest_heur=settings.get("interest_weight_heuristic", 0.5))
        state.record_item_score(src, it["score"])

    # --- DISCOVERY (feed the co-citation graph with everything we saw) -------
    discovery.update_candidates(candidates, all_items, sources_by_id, known_domains, mainstream)

    # --- DEDUPE (and drop anything you've blocked) --------------------------
    fresh = [it for it in all_items
             if it["id"] not in seen.get("ids", {}) and not preferences.is_blocked_item(it, prefs)]

    # --- JUDGE a shortlist with the LLM (real interestingness + Japanese) ----
    # Only the heuristic top-N is judged, so interest can affect selection while
    # keeping the API call small. No key => this is a no-op and we keep heuristics.
    size = settings.get("digest_size", 40)
    fresh.sort(key=lambda it: it["score"], reverse=True)
    shortlist = fresh[: settings.get("judge_shortlist", size * 2)]
    n_judged = judge_items(shortlist)
    for it in shortlist:
        if it.get("judged"):
            it["score"] = blend(it["distance"], it["interest"], judged=True,
                                w_interest_judged=settings.get("interest_weight_judged", 0.6))

    # --- RANK with diversity caps, reserving a slice for exploration --------
    # Caps stop any single engine (e.g. HN) or domain from flooding the digest,
    # which is what keeps the feed varied rather than "just Hacker News".
    fresh.sort(key=lambda it: it["score"], reverse=True)
    reserve = round(settings.get("explore_fraction", 0.15) * size)
    max_per_domain = settings.get("max_per_domain", 2)
    max_per_source = settings.get("max_per_source", 8)

    domc, srcc, seen_urls, digest = {}, {}, set(), []

    def pick_from(pool, limit):
        for it in pool:
            if len(digest) >= limit:
                break
            if it["url"] in seen_urls:
                continue
            dom = _domain(it["url"])
            if domc.get(dom, 0) >= max_per_domain:
                continue
            if srcc.get(it["source_id"], 0) >= max_per_source:
                continue
            digest.append(it)
            seen_urls.add(it["url"])
            domc[dom] = domc.get(dom, 0) + 1
            srcc[it["source_id"]] = srcc.get(it["source_id"], 0) + 1

    pick_from([it for it in fresh if it["explore"]], reserve)  # exploration first
    pick_from(fresh, size)                                     # then best overall

    # --- mark shown ---------------------------------------------------------
    for it in digest:
        seen.setdefault("ids", {})[it["id"]] = state.today()

    # --- GROW & CURATE the source set ---------------------------------------
    promoted = discovery.promote_candidates(candidates, sources, settings)
    life = discovery.manage_lifecycle(sources, settings)
    candidates.setdefault("history", []).extend(life["history"])

    # --- RENDER + PERSIST ---------------------------------------------------
    meta = {
        "sources_total": len(sources["sources"]),
        "counts": _status_counts(sources),
        "feeds_resolved_this_run": resolved,
        "discovered_this_run": [p["id"] for p in promoted],
        "graduated_this_run": life["changes"]["graduated"],
        "retired_this_run": life["changes"]["retired"],
        "candidates_tracked": len(candidates.get("candidates", {})),
        "items_seen_this_run": len(all_items),
        "items_judged": n_judged,
        "judge_enabled": n_judged > 0,
        "pinned": pinned_ids,
        "blocked": blocked_ids,
    }
    render.write_digest(digest, meta)
    render.write_sources(sources, candidates)
    meta["opml_feeds"] = opml.write_opml(sources)

    state.save_sources(sources)
    state.save_candidates(candidates)
    state.save_seen(seen)

    print("== rss-explorer run complete ==")
    for k, v in meta.items():
        print(f"  {k}: {v}")
    print(f"  digest_items: {len(digest)}")


def _status_counts(sources: dict) -> dict:
    c = {}
    for s in sources["sources"]:
        c[s["status"]] = c.get(s["status"], 0) + 1
    return c


if __name__ == "__main__":
    run()
