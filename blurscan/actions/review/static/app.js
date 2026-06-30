"use strict";
// blurscan review SPA. Talks to the local API in server.py.

const state = { token: "", dryRun: false, items: [], view: [], current: -1, heat: false };

function esc(s) {
  // Escape user-controlled text (filenames) before inserting into HTML.
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, method = "GET", body = null) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.headers["X-Blurscan-Token"] = state.token;
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  return res.ok ? res.json() : Promise.reject(new Error(res.status));
}

function filtered() {
  const f = document.getElementById("filter").value;
  const keep = {
    flagged: (c) => c === "blurry" || c === "borderline",
    blurry: (c) => c === "blurry",
    borderline: (c) => c === "borderline",
    all: () => true,
  }[f];
  return state.items
    .filter((it) => keep(it.classification))
    .sort((a, b) => a.score - b.score); // blurriest first
}

function renderCounts() {
  const c = { blurry: 0, borderline: 0, sharp: 0 };
  state.items.forEach((it) => (c[it.classification] = (c[it.classification] || 0) + 1));
  document.getElementById("counts").textContent =
    `${state.items.length} images — blurry ${c.blurry}, borderline ${c.borderline}, sharp ${c.sharp}`;
}

function renderGrid() {
  state.view = filtered();
  const grid = document.getElementById("grid");
  grid.innerHTML = "";
  state.view.forEach((it, i) => {
    const card = document.createElement("figure");
    card.className = "card" + (it.decision && it.decision !== "keep" ? ` decided-${it.decision}` : "");
    const name = esc(it.name);
    card.innerHTML =
      `<img loading="lazy" src="/api/thumb/${encodeURIComponent(it.id)}" alt="${name}">` +
      (it.decision && it.decision !== "keep" ? `<span class="decision-tag">${esc(it.decision)}</span>` : "") +
      `<figcaption class="meta"><span class="badge ${esc(it.classification)}">${esc(it.classification)}</span> ` +
      `<span class="score">${it.score.toFixed(0)}</span><div class="name">${name}</div></figcaption>`;
    card.onclick = () => openDetail(i);
    grid.appendChild(card);
  });
}

function detailSrc(it) {
  const id = encodeURIComponent(it.id);
  return state.heat ? `/api/heatmap/${id}` : `/api/image/${id}`;
}

function openDetail(viewIndex) {
  state.current = viewIndex;
  const it = state.view[viewIndex];
  if (!it) return;
  document.getElementById("detail-img").src = detailSrc(it);
  document.getElementById("detail-name").textContent = it.name;
  document.getElementById("detail-stats").innerHTML =
    `<dt>class</dt><dd>${it.classification}</dd>` +
    `<dt>method</dt><dd>${it.method}</dd>` +
    `<dt>score</dt><dd>${it.score.toFixed(1)}</dd>` +
    `<dt>global</dt><dd>${it.score_global.toFixed(1)}</dd>` +
    `<dt>fft</dt><dd>${it.fft_ratio.toFixed(3)}</dd>` +
    `<dt>decision</dt><dd>${it.decision}</dd>`;
  document.getElementById("detail").hidden = false;
}

function closeDetail() {
  document.getElementById("detail").hidden = true;
  state.current = -1;
}

function toggleHeatmap() {
  state.heat = !state.heat;
  const it = state.view[state.current];
  if (it) document.getElementById("detail-img").src = detailSrc(it);
}

async function decide(value) {
  const it = state.view[state.current];
  if (!it) return;
  await api("/api/decision", "POST", { id: it.id, decision: value });
  it.decision = value;
  renderGrid();
  if (state.current >= 0 && state.current < state.view.length - 1) openDetail(state.current + 1);
  else closeDetail();
}

function onKey(e) {
  if (document.getElementById("detail").hidden) return;
  const map = { k: "keep", x: "quarantine", t: "tag" };
  if (map[e.key]) decide(map[e.key]);
  else if (e.key === "h") toggleHeatmap();
  else if (e.key === "ArrowRight") openDetail(Math.min(state.current + 1, state.view.length - 1));
  else if (e.key === "ArrowLeft") openDetail(Math.max(state.current - 1, 0));
  else if (e.key === "Escape") closeDetail();
}

async function init() {
  const data = await api("/api/results");
  state.token = data.token;
  state.dryRun = data.dry_run;
  state.items = data.items;
  document.getElementById("dryrun").hidden = !state.dryRun;
  renderCounts();
  renderGrid();

  document.getElementById("filter").onchange = renderGrid;
  document.addEventListener("keydown", onKey);
  document.getElementById("detail").onclick = (e) => {
    if (e.target.id === "detail") closeDetail();
  };
  document.querySelectorAll(".decision-buttons button").forEach((b) => {
    b.onclick = () => decide(b.dataset.decision);
  });
  document.getElementById("heatmap-toggle").onclick = toggleHeatmap;
  document.getElementById("apply").onclick = async () => {
    const s = await api("/api/apply", "POST", {});
    alert(`${s.dry_run ? "[dry-run] " : ""}quarantined ${s.quarantined}, tagged ${s.tagged}` +
      (s.tag_error ? `\n${s.tag_error}` : ""));
  };
  document.getElementById("done").onclick = () => api("/api/shutdown", "POST", {}).catch(() => {});
}

init();
