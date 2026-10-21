// [wip] ECLIPSE vs PCA: live numbers from /api/lens-report, and one person on both maps.
const G = window.GLIMPSE;
const el = (id) => document.getElementById(id);
const TOPIC_KEY = "glimpse-topic";

// [key, label, short plain name used in the summary]
const MEASURES = [
  ["shows_model", "Shows what the model looks at", "shows what the model looks at"],
  ["score_read", "Left to right follows the score", "follows the model's score"],
  ["disagree_read", "Keeps where good models disagree", "keeps where good models disagree"],
  ["change_shown", "Share of a suggested change you can see", "shows suggested changes"],
  ["map_right", "Change drawn past the right line", "draws changes past the right line"],
  ["trust", "Keeps who is near whom", "keeps who is near whom"],
  ["kept", "Keeps how spread out people are", "keeps how spread out people are"],
];
const TIE = 0.01;
const pct = (v) => (v == null ? "—" : Math.round(v * 100) + "%");

let report = null, scenes = {};

function bar(v, cls) {
  return `<span class="ec-val">${pct(v)}</span><span class="ec-bar ${cls}" aria-hidden="true">` +
    `<i style="width:${Math.max(0, Math.min(1, v || 0)) * 100}%"></i></span>`;
}

function renderTable() {
  const L = report.lenses;
  el("ec-table").querySelector("tbody").innerHTML = MEASURES.map(([k, label]) => {
    const a = L.pca[k], b = L.eclipse[k];
    const better = a == null || b == null ? "—"
      : Math.abs(b - a) <= TIE ? "same" : b > a ? "ECLIPSE" : "PCA";
    return `<tr><td>${G.esc(label)}</td><td>${bar(a, "pca")}</td><td>${bar(b, "eclipse")}</td>` +
      `<td class="ec-better ${better.toLowerCase()}">${better}</td></tr>`;
  }).join("");
}

// One plain sentence for what ECLIPSE gains and one for what it gives up.
function renderSummary() {
  const L = report.lenses, topic = G.topicName(report.key, report.dataset);
  // "shows X (99% vs 65%), keeps Y (...) and ..." with the winner's number first
  const list = (rows, win, lose) => {
    const parts = rows.map(([k, , name]) => `${name} (${pct(L[win][k])} vs ${pct(L[lose][k])})`);
    return parts.length < 2 ? parts.join("")
      : parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1];
  };
  const wins = MEASURES.filter(([k]) => L.eclipse[k] - L.pca[k] > TIE);
  const losses = MEASURES.filter(([k]) => L.pca[k] - L.eclipse[k] > TIE);
  el("summary").innerHTML = `<b>${G.esc(topic)}:</b> ` +
    (wins.length ? `ECLIPSE ${G.esc(list(wins, "eclipse", "pca"))}. ` : "ECLIPSE wins nothing here. ") +
    (losses.length ? `The trade-off: PCA ${G.esc(list(losses, "pca", "eclipse"))}.`
      : "It gives up nothing measured here.");
}

function drawMap(div, scene) {
  const P = G.mapColors(), dark = G.isDark(), panel = scene.panels.linear;
  const q = scene.query, cf = panel.cfs, m = panel.metrics;
  const line = (lines, color, dash) => lines.map((ln) => ({
    type: "scatter", mode: "lines", x: ln.x, y: ln.y, hoverinfo: "skip",
    line: { color, width: 2.4, dash: dash || "solid" } }));
  const mark = (pt, color, symbol, size) => ({
    type: "scatter", mode: "markers", x: [pt.x], y: [pt.y], hoverinfo: "skip",
    marker: { color, symbol, size, line: { color: P.outline, width: 1 } } });
  const traces = [
    { type: "heatmap", x: panel.field.x, y: panel.field.y, z: panel.field.z, zmin: 0, zmax: 1,
      colorscale: P.field, opacity: P.fieldOpacity, showscale: false, hoverinfo: "skip",
      zsmooth: "best" },
    { type: "scatter", mode: "markers", x: scene.points.map((p) => p.x),
      y: scene.points.map((p) => p.y), hoverinfo: "skip",
      marker: { size: 3, color: dark ? "rgba(240,240,248,0.35)" : "rgba(30,30,40,0.3)" } },
    ...line(panel.boundary, P.line), ...line(panel.worst, P.worst, "dash"),
  ];
  const target = m.safe_ok !== false ? cf.ellice : m.quick_ok !== false ? cf.standard : null;
  if (m.quick_ok !== false) traces.push(mark(cf.standard, P.quick, "x", 10));
  if (m.safe_ok !== false) traces.push(mark(cf.ellice, P.safe, "square", 9));
  traces.push(mark(q, P.you, "star", 15));
  const xs = scene.points.map((p) => p.x).sort((a, b) => a - b);
  const ys = scene.points.map((p) => p.y).sort((a, b) => a - b);
  const at = (s, f) => s[Math.round((s.length - 1) * f)];
  const pad = (lo, hi) => [lo - 0.08 * (hi - lo), hi + 0.08 * (hi - lo)];
  const tc = dark ? { bg: "#1c2027", font: "#e6e6ea" } : { bg: "#ffffff", font: "#222222" };
  Plotly.react(div, traces, {
    paper_bgcolor: tc.bg, plot_bgcolor: tc.bg, font: { color: tc.font }, showlegend: false,
    margin: { l: 6, r: 6, t: 6, b: 6 },
    xaxis: { visible: false, constrain: "domain",
             range: pad(Math.min(at(xs, 0.02), q.x), Math.max(at(xs, 0.98), q.x)) },
    yaxis: { visible: false, constrain: "domain", scaleanchor: "x",
             range: pad(Math.min(at(ys, 0.02), q.y), Math.max(at(ys, 0.98), q.y)) },
    annotations: target ? [{ x: target.x, y: target.y, ax: q.x, ay: q.y, xref: "x", yref: "y",
      axref: "x", ayref: "y", showarrow: true, arrowhead: 3, arrowwidth: 1.6,
      arrowcolor: P.arrow, text: "" }] : [],
  }, { displayModeBar: false, responsive: true, staticPlot: true });
}

function renderMaps() {
  for (const kind of ["pca", "eclipse"]) {
    const s = scenes[kind];
    if (!s) continue;
    drawMap(el("map-" + kind), s);
    const m = s.panels.linear.metrics;
    const share = m.safe_ok !== false ? m.safe_on_map : m.quick_on_map;
    el("cap-" + kind).textContent = `· ${pct(share)} of the change shows`;
  }
  const s = scenes.pca;
  if (s) el("maps-who").textContent = `Example person #${s.query.id}, simple model.`;
}

async function load(key) {
  el("busy").textContent = "Loading…";
  try {
    const [r, a, b] = await Promise.all([
      fetch(`/api/lens-report?dataset=${encodeURIComponent(key)}`).then((x) => x.json()),
      fetch(`/api/scene?dataset=${encodeURIComponent(key)}&lens=pca`).then((x) => x.json()),
      fetch(`/api/scene?dataset=${encodeURIComponent(key)}&lens=eclipse`).then((x) => x.json()),
    ]);
    if (r.error || a.error || b.error) throw new Error(r.error || a.error || b.error);
    report = r;
    scenes = { pca: a, eclipse: b };
    renderSummary();
    renderTable();
    renderMaps();
    el("busy").textContent = "";
  } catch (e) {
    el("busy").textContent = "Couldn’t load: " + e.message;
  }
}

async function init() {
  let datasets = [];
  try { datasets = (await (await fetch("/api/datasets")).json()).datasets; } catch (e) {}
  const sel = el("dataset");
  sel.innerHTML = datasets.map((d) =>
    `<option value="${G.esc(d.key)}">${G.esc(G.topicName(d.key, d.label))}</option>`).join("");
  let saved = null;
  try { saved = localStorage.getItem(TOPIC_KEY); } catch (e) {}
  if (datasets.some((d) => d.key === saved)) sel.value = saved;
  sel.addEventListener("change", () => load(sel.value));
  if (sel.value) load(sel.value);
}

document.addEventListener("glimpse-theme", () => { if (report) renderMaps(); });
init();
