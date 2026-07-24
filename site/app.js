const $ = (s, r = document) => r.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const esc = s => (s || "").replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
const host = u => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };
const fmtDate = s => s ? s.slice(0, 10) : "";
const hasJa = t => /[぀-ヿ]/.test(t || "");

// Tabs
document.querySelectorAll(".tabbtn").forEach(b => b.onclick = () => {
  document.querySelectorAll(".tabbtn").forEach(x => x.classList.remove("active"));
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  $("#" + b.dataset.tab).classList.add("active");
});

async function getJSON(path) {
  try { const r = await fetch(path + "?t=" + Date.now()); if (!r.ok) return null; return await r.json(); }
  catch { return null; }
}

// ------- taste feedback (kept in localStorage; exported to preferences.yaml) -------
const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k) || "[]"); } catch { return []; } },
  has(k, v) { return store.get(k).includes(v); },
  toggle(k, v) { const a = store.get(k), i = a.indexOf(v); if (i < 0) a.push(v); else a.splice(i, 1); localStorage.setItem(k, JSON.stringify(a)); return i < 0; },
};
const PINS = "rssx_pins", LIKES = "rssx_likes", DISLIKES = "rssx_dislikes";

// Optional live sync to Baserow (only if site/baserow.config.js set window.BASEROW).
// Fire-and-forget; failures never block the UI. `type` is pin|block|like|dislike.
function baserowWrite(type, value) {
  const b = window.BASEROW;
  if (!b || !b.tableId || !b.token) return;
  fetch(`${b.apiUrl}/api/database/rows/table/${b.tableId}/?user_field_names=true`, {
    method: "POST",
    headers: { "Authorization": `Token ${b.token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ type, value, active: true }),
  }).catch(() => { });
}

function buildPrefsYaml() {
  const y = ["# rss-explorer preferences — generated from your reactions on the site.",
    "# Merge these into config/preferences.yaml and commit.", ""];
  const sect = (name, arr) => { y.push(name + ":" + (arr.length ? "" : " []")); arr.forEach(v => y.push("  - " + v)); };
  sect("pin", store.get(PINS)); sect("boost_domains", store.get(LIKES)); sect("mute_domains", store.get(DISLIKES));
  return y.join("\n") + "\n";
}
function downloadPrefs() {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([buildPrefsYaml()], { type: "text/yaml" }));
  a.download = "preferences.yaml"; a.click();
}
function updateExportCount() {
  const n = store.get(PINS).length + store.get(LIKES).length + store.get(DISLIKES).length;
  const b = $("#export-btn"); if (b) b.textContent = `⚙ 設定を書き出す${n ? ` (${n})` : ""}`;
}

// ------- Feed with filters -------
let FEED = [];
const filters = { lang: "all", sort: "score", hideNews: false };

function isJa(it) {
  return !!it.ja_title || hasJa(it.title) || (it.tags || []).includes("ja");
}

function scoreClass(s) { return s >= 0.62 ? "hi" : s <= 0.42 ? "lo" : ""; }

function card(it) {
  const c = el("div", "card" + (it.explore ? " explore" : ""));

  // two-score rail: interest (面白さ) + distance (辺境度)
  const rail = el("div", "rail");
  const iv = it.interest == null ? "–" : it.interest.toFixed(2);
  const dv = it.distance == null ? "–" : it.distance.toFixed(2);
  rail.appendChild(el("span", "sc int " + scoreClass(it.interest ?? 0), `面白 ${iv}`));
  rail.appendChild(el("span", "sc dist " + scoreClass(it.distance ?? 0), `辺境 ${dv}`));
  if (it.judged) rail.appendChild(el("span", "sc ai", "AI採点"));
  if (it.pinned) rail.appendChild(el("span", "sc pin", "📌 確定"));
  if (it.kind) rail.appendChild(el("span", "kind k-" + it.kind, it.kind));
  c.appendChild(rail);

  const headline = it.ja_title || it.title;
  const h = el("h3", null, `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(headline)}</a>`);
  c.appendChild(h);
  if (it.ja_title && it.title && it.ja_title !== it.title)
    c.appendChild(el("div", "origtitle", esc(it.title)));

  const src = el("div", "src");
  src.innerHTML = `${esc(it.source)} · <span>${esc(host(it.url))}</span>` +
    (it.published ? ` · ${fmtDate(it.published)}` : "") +
    (it.explore ? ` · <span class="explore-badge">探索</span>` : "");
  c.appendChild(src);

  if (it.ja) c.appendChild(el("div", "blurb", esc(it.ja)));
  else if (it.excerpt) c.appendChild(el("div", "excerpt", esc(it.excerpt)));

  const chips = el("div", "chips");
  (it.tags || []).forEach(t => chips.appendChild(el("span", "tagchip", "#" + esc(t))));
  [...(it.reasons_interest || []), ...(it.reasons || [])].forEach(r => {
    const cls = r.includes("(+)") ? "plus" : r.includes("(−)") ? "minus" : "";
    chips.appendChild(el("span", "chip " + cls, esc(r)));
  });
  c.appendChild(chips);

  // taste actions: confirm the source, or nudge more/less of this domain
  const acts = el("div", "acts");
  const TYPE = { [PINS]: "pin", [LIKES]: "like", [DISLIKES]: "dislike" };
  const mkBtn = (label, key, val, title) => {
    const b = el("button", "act-btn" + (store.has(key, val) ? " on" : ""), label);
    b.title = title;
    b.onclick = e => {
      e.stopPropagation();
      const on = store.toggle(key, val);
      b.classList.toggle("on", on);
      if (on) baserowWrite(TYPE[key], val);   // live sync when turning a reaction ON
      updateExportCount();
    };
    return b;
  };
  acts.appendChild(mkBtn("📌 確定", PINS, it.source_id, "このソースを確定ソースにする（書き出しに含める）"));
  acts.appendChild(mkBtn("👍", LIKES, host(it.url), "この系統をもっと（ドメインを加点）"));
  acts.appendChild(mkBtn("👎", DISLIKES, host(it.url), "この系統を減らす（ドメインを減点）"));
  c.appendChild(acts);
  return c;
}

function drawFeed() {
  const list = $("#feed-list");
  list.innerHTML = "";
  let items = FEED.slice();
  if (filters.lang === "ja") items = items.filter(isJa);
  else if (filters.lang === "en") items = items.filter(it => !isJa(it));
  if (filters.hideNews) items = items.filter(it => it.kind !== "news");
  const key = filters.sort;
  items.sort((a, b) => (b[key] ?? 0) - (a[key] ?? 0));

  if (!items.length) { list.appendChild(el("div", "empty", "この条件に合うものがありません。")); return; }
  items.forEach(it => list.appendChild(card(it)));
}

function renderFeed(d) {
  if (!d || !d.items || !d.items.length) {
    $("#feed-list").appendChild(el("div", "empty", "まだデータがありません。<code>python -m pipeline.run</code> を実行するか、GitHub Actions の初回実行を待ってください。"));
    return;
  }
  $("#gen").textContent = "· " + fmtDate(d.generated);
  const m = d.meta || {};
  $("#feed-meta").innerHTML = [
    `ソース総数 <b>${m.sources_total ?? "?"}</b>`,
    `今回発見 <b>${(m.discovered_this_run || []).length}</b>`,
    `候補追跡中 <b>${m.candidates_tracked ?? 0}</b>`,
    m.judge_enabled ? `AI採点 <b>${m.items_judged}</b>件` : `AI採点 <b>オフ</b>（APIキー未設定）`,
  ].join(" ");
  FEED = d.items;
  drawFeed();
}

// filter wiring
document.querySelectorAll("#ctl-lang .pill").forEach(b => b.onclick = () => {
  document.querySelectorAll("#ctl-lang .pill").forEach(x => x.classList.remove("active"));
  b.classList.add("active"); filters.lang = b.dataset.lang; drawFeed();
});
document.querySelectorAll("#ctl-sort .pill").forEach(b => b.onclick = () => {
  document.querySelectorAll("#ctl-sort .pill").forEach(x => x.classList.remove("active"));
  b.classList.add("active"); filters.sort = b.dataset.sort; drawFeed();
});
$("#hide-news").onchange = e => { filters.hideNews = e.target.checked; drawFeed(); };
$("#export-btn").onclick = downloadPrefs;

// ------- Sources tab (unchanged structure) -------
function renderSources(d) {
  if (!d) { $("#src-counts").appendChild(el("div", "empty", "ソースデータ待ち。")); return; }
  const c = d.counts || {};
  [["pinned", "pinned"], ["seed", "seed"], ["active", "active"], ["trial", "trial"], ["retired", "retired"]].forEach(([k, cls]) => {
    const s = el("div", "stat " + cls);
    s.appendChild(el("div", "n", c[k] || 0));
    s.appendChild(el("div", "l", k));
    $("#src-counts").appendChild(s);
  });

  const hist = $("#src-history");
  const h = d.history || [];
  if (!h.length) hist.appendChild(el("div", "hint", "まだ増殖イベントはありません（初回実行後に現れます）。"));
  h.forEach(e => {
    const row = el("div", "hrow");
    row.appendChild(el("span", "date", e.date || ""));
    row.appendChild(el("span", "act " + (e.action || ""), e.action || ""));
    row.appendChild(el("span", "detail", `${esc(e.domain || "")} — ${esc(e.detail || "")}`));
    hist.appendChild(row);
  });

  const cand = $("#src-cand");
  const lb = d.candidate_leaderboard || [];
  if (!lb.length) cand.appendChild(el("div", "hint", "候補はまだありません。"));
  lb.forEach(x => {
    const row = el("div", "crow");
    row.appendChild(el("span", "cnt", "×" + x.count));
    row.appendChild(el("span", "dom", esc(x.domain)));
    row.appendChild(el("span", "refs", (x.referrers || []).slice(0, 4).join(", ")));
    cand.appendChild(row);
  });

  const wrap = $("#src-lists");
  const bs = d.by_status || {};
  [["active", "稼働中"], ["seed", "seed（出発点）"], ["trial", "試験中"], ["retired", "引退"]].forEach(([k, label]) => {
    const arr = bs[k] || [];
    if (!arr.length) return;
    const g = el("div", "srcgroup");
    g.appendChild(el("h3", null, `${label} (${arr.length})`));
    arr.sort((a, b) => (b.avg || 0) - (a.avg || 0)).forEach(s => {
      const row = el("div", "srcitem");
      const via = s.discovered_via ? ` <span class="tagchip">← ${esc((s.discovered_via || []).join(","))}</span>` : "";
      row.innerHTML = `<span><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>${via}</span>` +
        `<span class="avg">${s.avg != null ? s.avg.toFixed(2) : "—"} · ${s.items || 0}件</span>`;
      g.appendChild(row);
    });
    wrap.appendChild(g);
  });
}

(async () => {
  updateExportCount();
  renderFeed(await getJSON("data/digest.json"));
  renderSources(await getJSON("data/sources.json"));
})();
