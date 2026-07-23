const $ = (s, r = document) => r.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const esc = s => (s || "").replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
const host = u => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };
const fmtDate = s => s ? s.slice(0, 10) : "";

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

function scoreClass(s) { return s >= 0.62 ? "hi" : s <= 0.42 ? "lo" : ""; }

function renderFeed(d) {
  const list = $("#feed-list");
  if (!d || !d.items || !d.items.length) {
    list.appendChild(el("div", "empty", "まだデータがありません。<code>python -m pipeline.run</code> を実行するか、GitHub Actions の初回実行を待ってください。"));
    return;
  }
  $("#gen").textContent = "· " + fmtDate(d.generated);
  const m = d.meta || {};
  const meta = $("#feed-meta");
  const bits = [
    `ソース総数 <b>${m.sources_total ?? "?"}</b>`,
    `今回発見 <b>${(m.discovered_this_run || []).length}</b>`,
    `候補追跡中 <b>${m.candidates_tracked ?? 0}</b>`,
    `巡回アイテム <b>${m.items_seen_this_run ?? 0}</b>`,
  ];
  meta.innerHTML = bits.join(" ");

  d.items.forEach(it => {
    const card = el("div", "card" + (it.explore ? " explore" : ""));
    const top = el("div", "top");
    top.appendChild(el("span", "score " + scoreClass(it.score), it.score.toFixed(2)));
    const h = el("h3", null, `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a>`);
    top.appendChild(h);
    card.appendChild(top);

    const src = el("div", "src");
    src.innerHTML = `${esc(it.source)} · <span>${esc(host(it.url))}</span>` +
      (it.published ? ` · ${fmtDate(it.published)}` : "") +
      (it.explore ? ` · <span class="explore-badge">探索</span>` : "");
    card.appendChild(src);

    if (it.blurb_ja) card.appendChild(el("div", "blurb", esc(it.blurb_ja)));
    else if (it.excerpt) card.appendChild(el("div", "excerpt", esc(it.excerpt)));

    const chips = el("div", "chips");
    (it.tags || []).forEach(t => chips.appendChild(el("span", "tagchip", "#" + esc(t))));
    (it.reasons || []).forEach(r => {
      const cls = r.includes("(+)") ? "plus" : r.includes("(−)") ? "minus" : "";
      chips.appendChild(el("span", "chip " + cls, esc(r)));
    });
    card.appendChild(chips);
    list.appendChild(card);
  });
}

function renderSources(d) {
  if (!d) { $("#src-counts").appendChild(el("div", "empty", "ソースデータ待ち。")); return; }
  const c = d.counts || {};
  const order = [["seed", "seed"], ["active", "active"], ["trial", "trial"], ["retired", "retired"]];
  const cc = $("#src-counts");
  order.forEach(([k, cls]) => {
    const s = el("div", "stat " + cls);
    s.appendChild(el("div", "n", c[k] || 0));
    s.appendChild(el("div", "l", k));
    cc.appendChild(s);
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
  renderFeed(await getJSON("data/digest.json"));
  renderSources(await getJSON("data/sources.json"));
})();
