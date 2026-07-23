"""Write the public JSON the static site reads."""
from __future__ import annotations

from . import state


def write_digest(items: list[dict], meta: dict) -> None:
    out = {
        "generated": state.now_iso(),
        "count": len(items),
        "meta": meta,
        "items": [
            {
                "title": it["title"],
                "ja_title": it.get("ja_title"),
                "url": it["url"],
                "source": it["source_title"],
                "source_id": it["source_id"],
                "tags": it.get("source_tags", []),
                "published": it.get("published"),
                "score": it["score"],
                "distance": it.get("distance"),
                "interest": it.get("interest"),
                "judged": it.get("judged", False),
                "kind": it.get("kind"),
                "reasons": it.get("reasons", []),
                "reasons_interest": it.get("reasons_interest", []),
                "ja": it.get("ja"),
                "excerpt": _clean(it.get("summary", "")),
                "explore": it.get("explore", False),
            }
            for it in items
        ],
    }
    state._save(state.SITE_DATA / "digest.json", out)


def write_sources(sources: dict, candidates: dict) -> None:
    srcs = sources["sources"]
    by_status = {}
    for s in srcs:
        by_status.setdefault(s["status"], []).append({
            "id": s["id"], "title": s["title"], "url": s["url"],
            "tags": s.get("tags", []), "added": s.get("added"),
            "avg": s.get("stats", {}).get("avg"), "items": s.get("stats", {}).get("items"),
            "discovered_via": s.get("discovered_via"),
        })
    cand = candidates.get("candidates", {})
    leaderboard = sorted(
        ({"domain": d, "count": e["count"], "referrers": e["referrers"],
          "promoted": e.get("promoted", False)} for d, e in cand.items() if not e.get("promoted")),
        key=lambda x: x["count"], reverse=True,
    )[:30]
    out = {
        "generated": state.now_iso(),
        "counts": {k: len(v) for k, v in by_status.items()},
        "by_status": by_status,
        "candidate_leaderboard": leaderboard,
        "history": candidates.get("history", [])[-60:][::-1],
    }
    state._save(state.SITE_DATA / "sources.json", out)


def _clean(html: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:280]
