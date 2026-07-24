"""Read taste feedback from a Baserow table (server-side, token via env).

This is what makes the feedback loop *automatic*: reactions written from the
site land in a Baserow table, and every pipeline run pulls them and folds them
into the same preferences the ranker already understands — no manual editing of
preferences.yaml.

Safe by construction: the token lives only in the environment (a GitHub secret
in CI, .env locally), never in the committed repo or the public site.

Env:
  BASEROW_TOKEN     database token (Authorization: Token <...>)
  BASEROW_TABLE_ID  numeric id of the feedback table
  BASEROW_API_URL   optional, defaults to https://api.baserow.io

Expected table columns (user field names): `type` (pin|block|like|dislike) and
`value` (a source id, domain, or feed URL). An optional boolean `active`
(default treated as true) lets a row be switched off without deleting it.
"""
from __future__ import annotations

import os

import requests

MAP = {
    "pin": "pin",
    "block": "block",
    "like": "boost_domains",
    "dislike": "mute_domains",
}


def fetch_feedback() -> dict | None:
    token = os.environ.get("BASEROW_TOKEN")
    table = os.environ.get("BASEROW_TABLE_ID")
    if not token or not table:
        return None
    base = os.environ.get("BASEROW_API_URL", "https://api.baserow.io").rstrip("/")
    headers = {"Authorization": f"Token {token}"}
    out = {v: [] for v in ("pin", "block", "boost_domains", "mute_domains")}

    url = f"{base}/api/database/rows/table/{table}/?user_field_names=true&size=200"
    try:
        while url:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code != 200:
                return None  # misconfigured / no access -> behave as "no feedback"
            data = r.json()
            for row in data.get("results", []):
                if row.get("active") is False:
                    continue
                t = _cell(row.get("type"))
                val = (_cell(row.get("value")) or "").strip()
                key = MAP.get((t or "").lower())
                if key and val and val not in out[key]:
                    out[key].append(val)
            url = data.get("next")
    except requests.RequestException:
        return None
    return out


def _cell(v):
    """Baserow single-select fields arrive as {'value': '...'}; text as str."""
    if isinstance(v, dict):
        return v.get("value")
    if isinstance(v, list) and v:
        first = v[0]
        return first.get("value") if isinstance(first, dict) else first
    return v
