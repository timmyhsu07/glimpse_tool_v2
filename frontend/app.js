

const COLORS = {
  good: "#2f6f9f", bad: "#c0573f",
  boundary: "#1f2d6b", worst: "#e65100", fan: "#2aa198",
  query: "#0d47a1", you: "#00695c",
  std: "#4a148c", ell: "#b71c1c",
  deltaLin: "#3949ab", deltaMlp: "#00897b", immutable: "#9e9e9e",
};

const FIELD_SCALE = [
  [0.0, "#aaffaa"], [0.25, "#ccffcc"], [0.5, "#f4f6fa"],
  [0.75, "#ffccff"], [1.0, "#ffaaff"],
]; //  

const G = window.GLIMPSE;
const state = { dataset: "pima", query: null, custom: null, point: null };

const el = (id) => document.getElementById(id);
const plotDivs = { linear: el("plot-linear"), mlp: el("plot-mlp") };
const deltaDiv = el("plot-delta");
let plotsReady = false;
let formDataset = null;
let lastScene = null;
let currentUser = null;
let loading = false;
let savedEntries = [];
let panelItems = [];
const PENDING_KEY = "glimpse-pending-save";
const VIEW_KEY = "glimpse-map-view";
const GRAPH_KEY = "glimpse-old-graph";
const DISPUTED_SHARE = 0.15;      // "most disputed" = this share with the widest ranges
let mapView = "both";
let oldGraph = false;             // false = density map (default), true = the dot map
let showDisputed = false;

const pct = (v) => (v * 100).toFixed(0) + "%";
const f3 = (v) => (v == null ? "  n/a" : v.toFixed(3));

function fmtVal(v, integer) {
  if (v == null || isNaN(v)) return "—";
  if (integer) return (Math.round(v) + 0).toLocaleString();
  const a = Math.abs(v);
  if (a >= 1000) return (Math.round(v) + 0).toLocaleString();
  return (Number(v.toFixed(a >= 100 ? 0 : a >= 10 ? 1 : 2)) + 0)
    .toString();
}
const ordinal = (n) => {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

const isDark = () => G.isDark();

function themeColors() {
  return isDark()
    ? { paper: "#1c2027", plot: "#1c2027", font: "#e6e6ea",
        legendBg: "rgba(28,32,39,0.82)", legendBorder: "#333a45", zero: "#8a8f99" }
    : { paper: "#ffffff", plot: "#ffffff", font: "#222222",
        legendBg: "rgba(255,255,255,0.75)", legendBorder: "#cccccc", zero: "#888888" };
}

document.addEventListener("glimpse-theme", () => {
  if (plotsReady && lastScene) {
    redrawPlots(lastScene);
    renderLegend(lastScene);
  }
});

function polyTraces(lines, color, width, opacity, name, showlegend) {
  const traces = lines.map((ln) => ({
    type: "scatter", mode: "lines", x: ln.x, y: ln.y,
    line: { color, width }, opacity, showlegend: false, hoverinfo: "skip",
  }));
  if (showlegend)
    traces.push({ type: "scatter", mode: "lines", x: [null], y: [null],
                  line: { color, width: 3 }, name, hoverinfo: "skip" });
  return traces;
}

function markerTrace(pt, color, name, symbol, size) {
  return {
    type: "scatter", mode: "markers", x: [pt.x], y: [pt.y],
    marker: { size, color, symbol, opacity: 0.85,
              line: { color: "#000", width: 0.7 } },
    name, showlegend: false,
    hovertemplate: `${name}<extra></extra>`,
  };
}

function buildPanelTraces(scene, which) {
  const panel = scene.panels[which];
  const legend = which === "linear";
  const traces = [];
  const f = panel.field;
  const tc = themeColors();

  traces.push({
    type: "heatmap", x: f.x, y: f.y, z: f.z,
    zmin: 0, zmax: 1, colorscale: FIELD_SCALE, zsmooth: "best",
    opacity: oldGraph ? 0.9 : 0.4, hoverinfo: "none", showscale: which === colorbarPanel(),
    colorbar: { title: { text: `chance of ${scene.class_names[1]}`, side: "right",
                         font: { color: tc.font } },
                tickfont: { color: tc.font },
                thickness: 12, len: 0.9, x: 1.02 },
  });

  traces.push(...polyTraces(panel.fan, COLORS.fan, 1, 0.14,
                            "other good models", legend));

  if (oldGraph) traces.push(...dotTraces(scene, legend));
  else traces.push(densityTrace(scene));

  traces.push(...polyTraces(panel.boundary, COLORS.boundary, 2.6, 1,
                            "model's line", legend));
  traces.push(...polyTraces(panel.worst, COLORS.worst, 2.4, 0.95,
                            "strictest good model", legend));

  const q = scene.query, cf = panel.cfs;
  const qName = q.from_map ? "Person at this spot"
              : q.custom ? "You" : `Person #${q.id}`;
  traces.push({
    type: "scatter", mode: "markers", x: [q.x], y: [q.y],
    marker: { size: q.custom ? 15 : 12,
              color: q.custom ? COLORS.you : COLORS.query,
              symbol: "star", opacity: 0.95, line: { color: "#000", width: 0.7 } },
    name: "person", showlegend: false, customdata: [q.id],
    hovertemplate: `${qName}<extra></extra>`,
  });
  // Ink, not purple, so the ✕ stays visible on the violet density map.
  if (quickOk(scene, which))
    traces.push(markerTrace(cf.standard, isDark() ? "#f2f2f2" : "#111111", "quick change", "x", 10));
  if (safeOk(scene, which))
    traces.push(markerTrace(cf.ellice, COLORS.ell, "safe change", "square", 9));
  traces.push({
    type: "scatter", mode: "markers", x: [null], y: [null], name: "what if",
    marker: { size: 15, symbol: "star-open", color: isDark() ? "#ffd166" : "#a15c00",
              line: { width: 2 } },
    showlegend: false, hovertemplate: "What if<extra></extra>",
  });
  return traces;
}

// Whether the search found a change that convinces every good model. When it
// didn't (it can't, e.g. on Credit with the locked values), nothing is shown as "safe".
const safeOk = (scene, which) => scene.panels[which].metrics.safe_ok !== false;
const quickOk = (scene, which) => scene.panels[which].metrics.quick_ok !== false;
const kindOk = (scene, which, kind) => (kind === "safe" ? safeOk : quickOk)(scene, which);
// Where the map's arrow points: the safe change if there is one, else the quick one,
// else nowhere.
const arrowTarget = (scene, which) =>
  safeOk(scene, which) ? scene.panels[which].cfs.ellice
    : quickOk(scene, which) ? scene.panels[which].cfs.standard : null;

// The dot map ("old GLIMPSE graph"): one dot per person, with a hover card.
function dotTraces(scene, legend) {
  const kf = scene.key_features || [];
  const [goodName, badName] = scene.class_names;
  const card = (p) => {
    const vals = kf.map((f, i) =>
      `${G.esc(f.label)} ${fmtVal(p.v[i], f.integer)}${f.unit ? " " + G.esc(f.unit) : ""}`);
    return `<b>${p.p >= 0.5 ? G.esc(badName) : G.esc(goodName)}</b> · ` +
      `${pct(p.p)} chance of ${G.esc(badName)}<br>` +
      `models say ${pct(p.lo)}–${pct(p.hi)}<br>${vals.join(" · ")}`;
  };
  const traces = [];
  for (const [c, color, label] of [[0, COLORS.good, goodName], [1, COLORS.bad, badName]]) {
    const sel = scene.points.filter((p) => p.outcome === c);
    traces.push({
      type: "scatter", mode: "markers",
      x: sel.map((p) => p.x), y: sel.map((p) => p.y),
      customdata: sel.map((p) => p.id), meta: "people", text: sel.map(card),
      marker: { size: 5, color, opacity: 0.55, line: { color: "white", width: 0.3 } },
      name: label, showlegend: legend,
      hovertemplate: "%{text}<extra></extra>",
    });
  }
  if (showDisputed) {
    const sel = disputed(scene);
    traces.push({
      type: "scatter", mode: "markers", x: sel.map((p) => p.x), y: sel.map((p) => p.y),
      marker: { size: 11, color: "rgba(0,0,0,0)",
                line: { color: isDark() ? "#ffd166" : "#8a5a00", width: 1.6 } },
      name: "most disputed", showlegend: false, hoverinfo: "skip",
    });
  }
  return traces;
}

// The people the models disagree about most: the widest chance ranges.
function disputed(scene) {
  const pts = scene.points, n = Math.max(1, Math.round(pts.length * DISPUTED_SHARE));
  return [...pts].sort((a, b) => (b.hi - b.lo) - (a.hi - a.lo)).slice(0, n);
}

// The density map: where people are, without showing any one of them.
// One strong violet, see-through where few people are and dark where many are.
const DENSITY = { light: "88,52,196", dark: "185,160,255" };
function densityTrace(scene) {
  const c = isDark() ? DENSITY.dark : DENSITY.light;
  return {
    type: "histogram2dcontour", x: scene.points.map((p) => p.x),
    y: scene.points.map((p) => p.y), nbinsx: 28, nbinsy: 28, ncontours: 8,
    colorscale: [[0, `rgba(${c},0)`], [0.12, `rgba(${c},0.22)`],
                 [0.5, `rgba(${c},0.55)`], [1, `rgba(${c},0.9)`]],
    contours: { coloring: "fill", showlines: true },
    line: { color: `rgba(${c},0.95)`, width: 1 },
    showscale: false, hoverinfo: "skip", name: "people",
  };
}

// Axis ranges. Both axes use constrain "domain", so Plotly keeps equal scale by
// shrinking the plot area, never by changing these ranges. A map click keeps the
// current view: the star lands under the pointer and the map does not shift.
function viewRanges(div, scene, which) {
  const fl = div._fullLayout;
  if (scene.query.from_map && fl && fl.xaxis && div.dataset.view === scene.dataset)
    return [fl.xaxis.range.slice(), fl.yaxis.range.slice()];
  div.dataset.view = scene.dataset;
  return defaultRanges(scene, which);
}

// The starting view frames where most people are (2nd to 98th percentile), so a
// few extreme people don't squeeze everyone into a corner; you and your change
// are always in view.
const FRAME_PCT = 0.02;
function quantile(sorted, f) {
  const i = (sorted.length - 1) * f, lo = Math.floor(i);
  return sorted[lo] + (sorted[Math.ceil(i)] - sorted[lo]) * (i - lo);
}
function defaultRanges(scene, which) {
  const q = scene.query, to = arrowTarget(scene, which) || q;
  const px = scene.points.map((p) => p.x).sort((a, b) => a - b);
  const py = scene.points.map((p) => p.y).sort((a, b) => a - b);
  const xs = [quantile(px, FRAME_PCT), quantile(px, 1 - FRAME_PCT), q.x, to.x];
  const ys = [quantile(py, FRAME_PCT), quantile(py, 1 - FRAME_PCT), q.y, to.y];
  const grow = (lo, hi) => [lo - 0.08 * (hi - lo), hi + 0.08 * (hi - lo)];
  return [grow(Math.min(...xs), Math.max(...xs)), grow(Math.min(...ys), Math.max(...ys))];
}

function panelLayout(scene, which) {
  const q = scene.query, cf = scene.panels[which].cfs;
  const [xr, yr] = viewRanges(plotDivs[which], scene, which);
  const tc = themeColors();
  return {
    paper_bgcolor: tc.paper, plot_bgcolor: tc.plot, font: { color: tc.font },
    margin: { l: 8, r: which === "mlp" ? 4 : 10, t: 6, b: 8 },
    xaxis: { showticklabels: false, ticks: "", range: xr, zeroline: false, constrain: "domain",
             color: tc.font },
    yaxis: { showticklabels: false, ticks: "", range: yr, zeroline: false, constrain: "domain",
             scaleanchor: "x", scaleratio: 1, color: tc.font },
    legend: { x: 0.02, y: 0.98, bgcolor: tc.legendBg,
              font: { size: 10, color: tc.font }, bordercolor: tc.legendBorder,
              borderwidth: 1 },
    showlegend: false, hovermode: "closest",
    // a dot is only picked when the pointer is on it; anywhere else is a spot
    hoverdistance: DOT_PX,
    // keep the user's zoom while clicking around the same dataset
    uirevision: scene.dataset,
    annotations: arrowTarget(scene, which) ? [{
      x: arrowTarget(scene, which).x, y: arrowTarget(scene, which).y, ax: q.x, ay: q.y,
      xref: "x", yref: "y", axref: "x", ayref: "y",
      showarrow: true, arrowhead: 3, arrowsize: 1.2, arrowwidth: 1.6,
      arrowcolor: "#111", opacity: 0.85, text: "",
    }] : [],
  };
}

function deltaTraces(scene) {
  const rows = [...scene.deltas].sort((a, b) =>
    Math.max(Math.abs(b.linear.delta_std), Math.abs(b.mlp.delta_std)) -
    Math.max(Math.abs(a.linear.delta_std), Math.abs(a.mlp.delta_std)))
    .slice(0, 12).reverse();

  const label = (r) => (r.missing ? r.label + " ✱" : r.label);
  const mk = (which, color, name) => ({
    type: "bar", orientation: "h", name,
    y: rows.map(label), x: rows.map((r) => r[which].delta_std),
    marker: { color: rows.map((r) => (r.immutable ? COLORS.immutable : color)),
              opacity: 0.85 },
    customdata: rows.map((r) => [
      fmtVal(r.x0_real, r.integer), fmtVal(r[which].cf_real, r.integer),
      Math.round(r.pct_x0), Math.round(r[which].pct_cf),
      r.immutable ? " · can't change" : "",
    ]),
    hovertemplate:
      "%{y}: %{customdata[0]} → %{customdata[1]}<br>" +
      "rank %{customdata[2]}% → %{customdata[3]}%{customdata[4]}" +
      "<extra>" + name + "</extra>",
  });
  return [mk("linear", COLORS.deltaLin, "simple model"),
          mk("mlp", COLORS.deltaMlp, "flexible model")];
}

function deltaLayout() {
  const tc = themeColors();
  return {
    paper_bgcolor: tc.paper, plot_bgcolor: tc.plot, font: { color: tc.font },
    margin: { l: 190, r: 20, t: 8, b: 40 }, barmode: "group",
    xaxis: { title: "size of change (standardized)", color: tc.font,
             zeroline: true, zerolinecolor: tc.zero, zerolinewidth: 1.5 },
    yaxis: { automargin: true, color: tc.font },
    legend: { x: 0.99, y: 0.02, xanchor: "right",
              bgcolor: tc.legendBg, bordercolor: tc.legendBorder,
              borderwidth: 1, font: { size: 11, color: tc.font } },
  };
}

function renderLensNote(scene) {
  const L = scene.lens, q = L.quality;
  el("lens-note").innerHTML =
    `<b>${L.label} map:</b> ${L.blurb} ` +
    `<span class="sub">Keeps who-is-near-whom about ` +
    `<b>${Math.round(q.trust * 100)}%</b> faithful` +
    `${L.is_linear ? " and is exactly reversible" : ""}.</span>`;
}

function renderLegend(scene) {
  const [g, b] = scene.class_names;
  const people = oldGraph
    ? `<li><span class="dot" style="background:${COLORS.good}"></span> ${G.esc(g)}` +
      ` <span class="dot" style="background:${COLORS.bad}"></span> ${G.esc(b)}</li>`
    : `<li><span class="sw" style="background:rgb(${isDark() ? DENSITY.dark : DENSITY.light})"></span> Many people</li>`;
  el("legend").innerHTML = [
    `<li><span class="sw" style="background:#aaffaa"></span> ${G.esc(g)} side` +
      ` <span class="sw" style="background:#ffaaff"></span> ${G.esc(b)} side</li>`,
    people,
    `<li><span class="sw line" style="background:${COLORS.boundary}"></span> Model’s line</li>`,
    `<li><span class="sw line" style="background:${COLORS.fan}"></span> Other good models</li>`,
    `<li><span class="sw line" style="background:${COLORS.worst}"></span> Strictest model</li>`,
    `<li>★ You · ✕ Quick change · ▪ Safe change</li>`,
    `<li>${G.tip("Background: the simple model’s chance of " + b + ". " +
      "Line: where it flips. Other good models: models that fit the data about as well. " +
      "Strictest: the one least on your side. Quick change: smallest change for this model. " +
      "Safe change: smallest change that works for every good model.")}</li>`,
  ].join("");
}

function renderVerdict(scene) {
  const q = scene.query;
  el("verdict-who").textContent =
    q.from_map ? "Person at this spot" : q.custom ? "You" : `Person #${q.id}`;
  const [goodName, badName] = scene.class_names;
  const lm = scene.panels.linear.metrics;
  const predName = lm.pred_bad ? badName : goodName;
  el("verdict").className = lm.pred_bad ? "bad" : "good";

  const close = lm.p_bad_best_x0 < 0.5 && lm.p_bad_worst_x0 > 0.5;
  el("verdict-headline").innerHTML =
    `<span class="vhead">${G.esc(predName)}</span>` +
    `<span class="badge ${close ? "close" : "clear"}">` +
    `${close ? "⚠ Close call · models disagree" : "✓ Clear · models agree"}</span>`;

  el("verdict-models").innerHTML = ["linear", "mlp"].map((which) => {
    const m = scene.panels[which].metrics;
    const name = which === "linear" ? "Simple model" : "Flexible model";
    const lo = Math.round(m.p_bad_best_x0 * 100);
    const hi = Math.round(m.p_bad_worst_x0 * 100);
    const erm = Math.round(m.p_bad_erm_x0 * 100);
    const side = m.pred_bad ? badName : goodName;
    return `<div class="vmodel ${m.pred_bad ? "bad" : "good"}">
      <div class="vlabel">${name}</div>
      <div class="vpred">${G.esc(side)}</div>
      <div class="vrange">${lo}–${hi}% chance of ${G.esc(badName)}
        ${G.tip(`Bar: what every model that fits the data about as well says. ` +
          `Tick: best guess, ${erm}%.`, "right")}</div>
      <div class="vbar" role="img" aria-label="${lo} to ${hi} percent, best guess ${erm}">
        <span style="left:${lo}%;right:${100 - hi}%"></span><i style="left:${erm}%"></i></div>
    </div>`;
  }).join("");
}

// You vs everyone: where each value sits among all people in the data.
let compareAll = false;
function renderCompare(scene) {
  const rank = new Map((scene.importance || []).map((n, i) => [n, i]));
  const rows = scene.deltas.filter((r) => !r.group)
    .sort((a, b) => (rank.get(a.name) ?? 1e9) - (rank.get(b.name) ?? 1e9));
  const shown = compareAll ? rows : rows.slice(0, 6);
  const q = scene.query;
  const who = q.custom || q.from_map ? "You" : "This person";
  el("compare-h").firstChild.textContent = q.from_map ? "How this spot compares " :
    q.custom ? "How you compare " : "How this person compares ";
  el("compare-list").innerHTML = shown.map((r) => {
    const pctl = Math.round(r.pct_x0);
    const where = pctl >= 50 ? `higher than ${pctl}%` : `lower than ${100 - pctl}%`;
    const unit = r.unit ? " " + G.esc(r.unit) : "";
    return `<li class="cmp${r.immutable ? " cmp-fixed" : ""}">
      <div class="cmp-top"><span class="cmp-name">${G.esc(r.label)}` +
      `${r.immutable ? " " + G.LOCK : ""}${r.missing ? ' <span class="miss-mark" title="typical value used">✱</span>' : ""}</span>
        <span class="cmp-val">${fmtVal(r.x0_real, r.integer)}${unit}</span></div>
      <div class="cmp-bar" role="img" aria-label="${G.esc(r.label)}: ${where} of people">
        <i style="left:${Math.min(98, Math.max(0, pctl))}%"></i></div>
      <div class="cmp-txt sub">${where} of people</div></li>`;
  }).join("");
  const more = el("compare-more");
  more.hidden = rows.length <= 6;
  more.textContent = compareAll ? "Show fewer" : `Show all ${rows.length}`;
  el("compare").dataset.who = who;
}
el("compare-more").addEventListener("click", () => {
  compareAll = !compareAll;
  if (lastScene) renderCompare(lastScene);
});

// ---- what would change it: quickest / safest tabs, change cards, what-if, plan

let recoKind = "quick";               // "quick" = this model only, "safe" = every good model
const EASY_SHIFT = 20;                 // rank points; a smaller move counts as "easy"

// The top changes for one model: [{row or group, before, after, unit, shift}].
function topChanges(scene, which, kind, n) {
  const key = kind === "quick" ? which + "_quick" : which;
  const items = [];
  for (const it of displayRows(scene)) {
    if (it.kind === "group") {
      if (it.immutable) continue;
      const members = scene.deltas.filter((x) => x.group && x.group_label === it.label);
      const after = members.find((x) => x[key].cf_real >= 0.5);
      const cat = after ? after.value_label : "none";
      if (cat === it.youCat) continue;
      items.push({ label: it.label, before: it.youCat, after: cat, unit: "", shift: 50,
                   mag: Math.max(...members.map((x) => Math.abs(x[key].delta_std))), group: true });
      continue;
    }
    const r = it.r, d = r[key];
    if (r.immutable || Math.abs(d.delta_std) <= 0.05) continue;
    // A change too small to show (e.g. 1.3 inquiries shown as 1) says nothing.
    if (fmtVal(r.x0_real, r.integer) === fmtVal(d.cf_real, r.integer)) continue;
    items.push({ name: r.name, label: r.label, unit: r.unit || "", integer: r.integer,
                 before: fmtVal(r.x0_real, r.integer), after: fmtVal(d.cf_real, r.integer),
                 afterValue: d.cf_real, up: d.delta_real > 0,
                 shift: Math.abs(d.pct_cf - r.pct_x0), mag: Math.abs(d.delta_std) });
  }
  return items.sort((a, b) => b.mag - a.mag).slice(0, n);
}

function changeCard(c) {
  const easy = c.shift <= EASY_SHIFT;
  const arrow = c.group ? "→" : c.up ? "▲" : "▼";
  return `<li class="chg-card">
    <div class="chg-top"><span class="chg-arrow ${c.group ? "" : c.up ? "up" : "down"}"
      aria-hidden="true">${arrow}</span><b>${G.esc(c.label)}</b>
      <span class="effort ${easy ? "easy" : "hard"}">${easy ? "easy" : "harder"}</span></div>
    <div class="chg-vals">${G.esc(c.before)} → <b>${G.esc(c.after)}</b>
      ${c.unit ? `<span class="sub">${G.esc(c.unit)}</span>` : ""}</div></li>`;
}

function renderRecommend(scene) {
  const [goodName] = scene.class_names;
  const imm = scene.deltas.filter((r) => r.immutable && !r.group).map((r) => r.label);
  el("reco-fixed").innerHTML = imm.map((l) =>
    `<span class="fixed-chip">${G.LOCK} ${G.esc(l)}</span>`).join("");
  for (const t of document.querySelectorAll(".reco-tabs [role=tab]"))
    t.setAttribute("aria-selected", String(t.dataset.kind === recoKind));

  el("reco-lists").innerHTML = ["linear", "mlp"].map((which) => {
    const m = scene.panels[which].metrics;
    const name = which === "linear" ? "Simple model" : "Flexible model";
    if (!m.pred_bad)
      return `<div class="reco-col"><div class="reco-h">${name}</div>
        <p class="reco-ok">✓ Already ${G.esc(goodName)}. Nothing to change.</p></div>`;
    if (!kindOk(scene, which, recoKind))
      return `<div class="reco-col"><div class="reco-h">${name}</div>
        <p class="reco-none">${recoKind === "safe"
          ? `No change you can make works for every good model.
             <button type="button" class="link-btn" data-kind="quick">See the quickest change</button>`
          : "No change within realistic values flips this model."}</p></div>`;
    const cards = topChanges(scene, which, recoKind, 3);
    return `<div class="reco-col"><div class="reco-h">${name}</div>
      <ul class="chg-cards">${cards.map(changeCard).join("") ||
        "<li class='sub'>No single change is enough.</li>"}</ul></div>`;
  }).join("");
  renderPlan(scene);
}

function setRecoKind(kind) {
  recoKind = kind;
  if (lastScene) {
    renderRecommend(lastScene);
    renderChanges(lastScene);
  }
}
for (const t of document.querySelectorAll(".reco-tabs [role=tab]"))
  t.addEventListener("click", () => setRecoKind(t.dataset.kind));
el("reco-lists").addEventListener("click", (e) => {
  const b = e.target.closest("[data-kind]");
  if (b) setRecoKind(b.dataset.kind);
});

// The current person's values in real units (blanks filled with typical values).
function personValues(scene) {
  return Object.fromEntries(scene.deltas.map((r) => [r.name, r.x0_real]));
}

async function predict(values) {
  const resp = await fetch("/api/people", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset: state.dataset, people: [values] }),
  });
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.error || "prediction failed");
  return { person: body.people[0], classNames: body.class_names };
}

function chanceLine(scene, before, after) {
  const bad = G.esc(scene.class_names[1]);
  const b = Math.round(before.p * 100), a = Math.round(after.p * 100);
  const moved = a - b;
  const dir = moved === 0 ? "no change" : `${moved > 0 ? "▲ up" : "▼ down"} ${Math.abs(moved)} points`;
  return `<b>${b}% → ${a}%</b> chance of ${bad} <span class="sub">(${dir} · models say ` +
    `${Math.round(after.lo * 100)}–${Math.round(after.hi * 100)}%)</span>`;
}

// ---- what if: drag a value, the chance and a ghost star update live

let whatifTimer = null, whatifValues = null;

function whatifFeatures(scene) {
  const rank = new Map((scene.importance || []).map((n, i) => [n, i]));
  const meta = new Map(scene.features.map((f) => [f.name, f]));
  return scene.deltas
    .filter((r) => !r.group && !r.immutable && meta.has(r.name))
    .sort((a, b) => (rank.get(a.name) ?? 1e9) - (rank.get(b.name) ?? 1e9))
    .slice(0, 4)
    .map((r) => ({ r, f: meta.get(r.name) }));
}

function renderWhatif(scene) {
  whatifValues = personValues(scene);
  el("whatif-sliders").innerHTML = whatifFeatures(scene).map(({ r, f }) => {
    const lo = Math.min(f.p5 ?? f.min, r.x0_real), hi = Math.max(f.p95 ?? f.max, r.x0_real);
    const step = f.integer ? 1 : (hi - lo) / 100;
    return `<div class="wi-row" data-name="${G.esc(r.name)}" data-int="${f.integer}"
      data-min="${f.min}" data-max="${f.max}">
      <span class="wi-name">${G.esc(r.label)}</span>
      <input type="range" min="${lo}" max="${hi}" step="${step}" value="${r.x0_real}"
             aria-label="${G.esc(r.label)} slider">
      <span class="wi-val"><input type="number" class="wi-num" step="${f.integer ? 1 : "any"}"
             value="${fmtVal(r.x0_real, f.integer).replace(/,/g, "")}" aria-label="${G.esc(r.label)} value">
        ${f.unit ? `<span class="sub">${G.esc(f.unit)}</span>` : ""}</span></div>`;
  }).join("");
  el("whatif-result").innerHTML = `<span class="sub">Drag a slider.</span>`;
  moveGhost(null);
}

// Drag a slider or type in the number box; each keeps the other in step.
el("whatif-sliders").addEventListener("input", (e) => {
  const row = e.target.closest(".wi-row");
  if (!row || !lastScene) return;
  const slider = row.querySelector("input[type=range]"), box = row.querySelector(".wi-num");
  const isInt = row.dataset.int === "true";
  let v;
  if (e.target === slider) {
    v = Number(slider.value);
    box.value = fmtVal(v, isInt).replace(/,/g, "");
  } else {
    if (box.value.trim() === "" || !isFinite(Number(box.value))) return;
    v = Number(box.value);
    // A typed value past the slider's ends stretches the slider to fit.
    if (v < Number(slider.min)) slider.min = v;
    if (v > Number(slider.max)) slider.max = v;
    slider.value = v;
  }
  const out = v < Number(row.dataset.min) || v > Number(row.dataset.max);
  box.classList.toggle("out", out);
  box.title = out ? `Outside the data (${row.dataset.min}–${row.dataset.max})` : "";
  whatifValues[row.dataset.name] = isInt ? Math.round(v) : v;
  clearTimeout(whatifTimer);
  whatifTimer = setTimeout(runWhatif, e.target === slider ? 120 : 350);
});
// Enter in a number box updates right away instead of submitting anything.
el("whatif-sliders").addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || !e.target.classList.contains("wi-num")) return;
  e.preventDefault();
  clearTimeout(whatifTimer);
  runWhatif();
});

async function runWhatif() {
  const scene = lastScene;
  try {
    const { person } = await predict(whatifValues);
    if (scene !== lastScene) return;
    const before = scene.panels.linear.metrics;
    el("whatif-result").innerHTML = "Simple model: " + chanceLine(scene,
      { p: before.p_bad_erm_x0 }, person.linear);
    moveGhost(person);
  } catch (e) {
    el("whatif-result").textContent = "Couldn’t update. Try again.";
  }
}

// A hollow star on the maps shows where the what-if person would sit.
function moveGhost(person) {
  if (!plotsReady) return;
  for (const div of Object.values(plotDivs)) {
    const i = (div.data || []).findIndex((t) => t.name === "what if");
    if (i < 0) continue;
    Plotly.restyle(div, { x: [[person ? person.x : null]], y: [[person ? person.y : null]] }, [i]);
  }
}

el("whatif-reset").addEventListener("click", () => { if (lastScene) renderWhatif(lastScene); });
el("whatif-apply").addEventListener("click", () => {
  if (!whatifValues) return;
  state.custom = { ...whatifValues };
  state.point = null;
  restoreForm();
  refresh();
});

// ---- my plan: tick the changes you'll make, see the result, save it

function planKey(scene) {
  const q = scene.query;
  return `glimpse-plan:${state.dataset}:${q.custom ? "you" : q.id}`;
}

function renderPlan(scene) {
  const noSafe = !kindOk(scene, "linear", recoKind);
  const items = scene.panels.linear.metrics.pred_bad && !noSafe
    ? topChanges(scene, "linear", recoKind, 5) : [];
  let ticked = null;
  try { ticked = JSON.parse(localStorage.getItem(planKey(scene)) || "null"); } catch (e) {}
  el("plan-list").innerHTML = items.length ? items.map((c, i) => {
    const on = ticked ? ticked.includes(c.label) : i < 2;
    return `<li><label class="plan-item"><input type="checkbox" data-i="${i}" ${on ? "checked" : ""}>
      <span><b>${G.esc(c.label)}</b> ${G.esc(c.before)} → <b>${G.esc(c.after)}</b>
      ${c.unit ? G.esc(c.unit) : ""}</span></label></li>`;
  }).join("") : `<li class="sub">${noSafe ? (recoKind === "safe"
    ? "No safe change exists for the simple model. Switch to Quickest change to plan."
    : "No realistic change flips the simple model.")
    : "Nothing to plan: already " + G.esc(scene.class_names[0]) + "."}</li>`;
  el("plan-list").dataset.items = JSON.stringify(items);
  el("plan-save").disabled = !items.length;
  el("plan-msg").textContent = "";
  el("plan-compare").hidden = true;
  updatePlan();
}

function planValues() {
  const items = JSON.parse(el("plan-list").dataset.items || "[]");
  const values = personValues(lastScene), picked = [];
  for (const cb of el("plan-list").querySelectorAll("input:checked")) {
    const c = items[+cb.dataset.i];
    picked.push(c.label);
    if (!c.group) values[c.name] = c.integer ? Math.round(c.afterValue) : c.afterValue;
    else for (const r of lastScene.deltas.filter((x) => x.group_label === c.label))
      values[r.name] = r[recoKind === "quick" ? "linear_quick" : "linear"].cf_real >= 0.5 ? 1 : 0;
  }
  return { values, picked };
}

let planTimer = null;
function updatePlan() {
  if (!lastScene) return;
  const { picked } = planValues();
  if (el("plan-list").querySelector("input")) {
    try { localStorage.setItem(planKey(lastScene), JSON.stringify(picked)); } catch (e) {}
  }
  if (!picked.length) {
    el("plan-result").innerHTML = el("plan-list").querySelector("input")
      ? `<span class="sub">Tick what you’ll change.</span>` : "";
    return;
  }
  clearTimeout(planTimer);
  planTimer = setTimeout(async () => {
    const scene = lastScene;
    try {
      const { person } = await predict(planValues().values);
      if (scene !== lastScene) return;
      el("plan-result").innerHTML = "With this plan: " + chanceLine(scene,
        { p: scene.panels.linear.metrics.p_bad_erm_x0 }, person.linear);
    } catch (e) {
      el("plan-result").textContent = "Couldn’t update. Try again.";
    }
  }, 120);
}
el("plan-list").addEventListener("change", updatePlan);

el("plan-save").addEventListener("click", async () => {
  if (!lastScene) return;
  const { values, picked } = planValues();
  if (!picked.length) { el("plan-msg").textContent = "Tick at least one change."; return; }
  if (!currentUser) { goSignInToSave(values); return; }
  const when = new Date().toLocaleDateString([], { month: "short", day: "numeric" });
  const resp = await fetch("/api/saved", {
    method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
    body: JSON.stringify({ dataset: state.dataset, name: `Plan, ${when}`, values }),
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) { el("plan-msg").textContent = body.error || "Couldn’t save the plan."; return; }
  el("plan-msg").textContent = `Saved “${body.saved.name}”.`;
  const now = encodeYou(personValues(lastScene));
  el("plan-compare").href = `/compare.html?dataset=${encodeURIComponent(state.dataset)}` +
    `&you=${now}&b=${body.saved.id}`;
  el("plan-compare").hidden = false;
  refreshSaved();
});

// Values as "name:value,..." for links (the same format ?you= reads).
function encodeYou(values) {
  return encodeURIComponent(Object.entries(values)
    .filter(([, v]) => v != null).map(([k, v]) => `${k}:${+Number(v).toFixed(4)}`).join(","));
}

// Build rows for the counterfactual comparison.
function displayRows(scene) {
  const items = [], seen = {};
  for (const r of scene.deltas) {
    if (r.group) {
      if (!seen[r.group]) {
        const members = scene.deltas.filter((x) => x.group === r.group);
        const g = groupRow(r.group_label, members);
        seen[r.group] = g;
        items.push(g);
      }
    } else {
      items.push({ kind: "plain", r,
        key: Math.max(Math.abs(r.linear.delta_std), Math.abs(r.mlp.delta_std)) });
    }
  }
  return items;
}

function groupRow(label, members) {
  const active = (val) => {
    const m = members.find((x) => val(x) >= 0.5);
    return m ? m.value_label : "none";
  };
  const youCat = active((x) => x.x0_real);
  const per = {};
  for (const which of ["linear", "mlp", "linear_quick", "mlp_quick"]) {
    const cat = active((x) => x[which].cf_real);
    per[which] = { cat, changed: cat !== youCat,
      mag: Math.max(...members.map((x) => Math.abs(x[which].delta_std))) };
  }
  return { kind: "group", label, youCat, per,
    immutable: members.some((x) => x.immutable),
    missing: members.some((x) => x.missing),
    key: Math.max(...members.map((x) =>
      Math.max(Math.abs(x.linear.delta_std), Math.abs(x.mlp.delta_std)))) };
}

function renderChanges(scene) {
  const rows = displayRows(scene).sort((a, b) => b.key - a.key);
  // Columns follow the "Quickest / Safest" tab; "—" where no safe change exists.
  const col = (which) => (recoKind === "quick" ? which + "_quick" : which);
  const none = (which) => !kindOk(scene, which, recoKind);

  const plainCell = (r, which) => {
    if (r.immutable) return `<td class="fixed">${G.LOCK} can’t change</td>`;
    if (none(which)) return `<td class="same">—</td>`;
    const d = r[col(which)];
    if (Math.abs(d.delta_std) <= 0.02) return `<td class="same">same</td>`;
    const up = d.delta_real > 0, unit = r.unit ? " " + r.unit : "";
    return `<td class="${up ? "up" : "down"}">` +
      `<span class="arrow">${up ? "▲" : "▼"}</span>` +
      `${fmtVal(d.cf_real, r.integer)}${unit}` +
      ` <span class="sub">(${up ? "+" : ""}${fmtVal(d.delta_real, r.integer)})</span></td>`;
  };
  const groupCell = (g, which) => {
    if (g.immutable) return `<td class="fixed">${G.LOCK} can’t change</td>`;
    if (none(which)) return `<td class="same">—</td>`;
    const p = g.per[col(which)];
    if (!p.changed) return `<td class="same">same</td>`;
    return `<td class="up"><span class="arrow">→</span>${esc(p.cat)}</td>`;
  };

  const trs = rows.map((it) => {
    if (it.kind === "group") {
      const miss = it.missing ? ' <span class="miss-mark" title="typical value used">✱</span>' : "";
      return `<tr class="${it.immutable ? "immrow" : ""}">` +
        `<td class="fname-cell">${esc(it.label)}${miss}</td>` +
        `<td class="youval">${esc(it.youCat)}</td>` +
        `${groupCell(it, "linear")}${groupCell(it, "mlp")}</tr>`;
    }
    const r = it.r;
    const miss = r.missing ? ' <span class="miss-mark" title="typical value used">✱</span>' : "";
    const unit = r.unit ? ` <span class="sub">(${r.unit})</span>` : "";
    return `<tr class="${r.immutable ? "immrow" : ""}">` +
      `<td class="fname-cell">${r.label}${miss}${unit}</td>` +
      `<td class="youval">${fmtVal(r.x0_real, r.integer)}</td>` +
      `${plainCell(r, "linear")}${plainCell(r, "mlp")}</tr>`;
  }).join("");

  el("changes-table").innerHTML =
    `<table class="chg"><thead><tr>` +
    `<th>Value</th><th>Now</th>` +
    `<th>After, ${recoKind === "quick" ? "quickest" : "safest"} (simple)</th>` +
    `<th>After, ${recoKind === "quick" ? "quickest" : "safest"} (flexible)</th>` +
    `</tr></thead><tbody>${trs}</tbody></table>`;
}

function metricsText(scene) {
  const lines = [];
  const q = scene.lens.quality;
  lines.push(
    `lens    ${scene.lens.label}  |  recon L1 ${q.recon.toFixed(3)}` +
    `  trustworthiness ${q.trust.toFixed(3)}  roundtrip ${q.rt.toFixed(3)}` +
    `  (held-out 20%; affine lens, roundtrip 0 exactly)`);
  for (const which of ["linear", "mlp"]) {
    const p = scene.panels[which], m = p.metrics;
    lines.push(
      `${which.padEnd(6)}  acc ${p.acc.toFixed(3)}  AUC ${p.auc.toFixed(3)}` +
      `  |  P(bad) person: best ${pct(m.p_bad_best_x0)} · ERM ${pct(m.p_bad_erm_x0)} · worst ${pct(m.p_bad_worst_x0)}` +
      `   robust CF: ERM ${pct(m.p_bad_erm_cf)} → worst ${pct(m.p_bad_worst_cf)}` +
      `  |  robust margin (Cor. 1) ${m.robust_margin_cf >= 0 ? "+" : ""}${m.robust_margin_cf.toFixed(3)}` +
      ` ${m.robust_margin_cf >= 0 ? "✓robust" : "✗NOT robust"}` +
      `  |  cost std ${f3(m.cost_std)}  robust ${f3(m.cost_rob)}`);
    lines.push(
      `        2D dist CF→boundary: ERM ${f3(m.d2_cf_to_erm)}  worst ${f3(m.d2_cf_to_worst)}` +
      `  ${m.worst_closer ? "✓ orange sits closer (as it must)"
                          : "⚠ orange looks FARTHER in projection — 2D reading of the curved boundary is distorted"}` +
      (m.already_robust ? "  |  note: person already robustly good" : ""));
  }
  const a = scene.panels.linear.metrics, b = scene.panels.mlp.metrics;
  lines.push(
    `Δ       robust cost simple ${f3(a.cost_rob)} vs flexible ${f3(b.cost_rob)}` +
    `  |  eps ${scene.eps} fixed — one knob at a time: model, lens, or person`);
  return lines.join("\n");
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// Collapse one-hot columns into one form field.
function formGroups(features) {
  const items = [], seen = {};
  for (const f of features) {
    if (f.group) {
      if (!seen[f.group]) {
        const members = features.filter((x) => x.group === f.group);
        const share = members.reduce((s, m) => s + (m.group_share || 0), 0);
        const g = { type: "group", key: f.group, label: f.group_label,
                    members, baselineShare: Math.max(0, 1 - share) };
        seen[f.group] = g;
        items.push(g);
      }
    } else {
      items.push({ type: "field", f });
    }
  }
  return items;
}

function fieldHTML(f) {
  const unit = f.unit ? ` <span class="unit">(${f.unit})</span>` : "";
  const imm = f.immutable
    ? ` <span class="imm-tag" title="Can’t change, so never recommended">${G.LOCK}</span>`
    : "";
  const hint = f.desc ? " " + G.tip(f.desc) : "";
  return `<label class="you-row" data-min="${f.min}" data-max="${f.max}"
                 data-p5="${f.p5}" data-p95="${f.p95}"
                 data-median="${f.median}" data-int="${f.integer}">
    <span class="fname">${f.label}${unit}${imm}${hint}</span>
    <input type="number" step="${f.integer ? 1 : "any"}" name="${f.name}"
           placeholder="${fmtVal(f.median, f.integer)} typical">
    <span class="fwarn"></span>
  </label>`;
}

function groupHTML(g) {
  const imm = g.members.some((m) => m.immutable)
    ? ` <span class="imm-tag" title="Can’t change, so never recommended">${G.LOCK}</span>`
    : "";
  const hasNone = g.baselineShare > 0.02;
  let modal = "", best = g.baselineShare;
  for (const m of g.members)
    if ((m.group_share || 0) > best) { best = m.group_share; modal = m.name; }
  if (modal === "" && hasNone) modal = "__none__";
  const opts = [`<option value="">typical</option>`];
  if (hasNone) opts.push(`<option value="__none__">none of these</option>`);
  for (const m of g.members)
    opts.push(`<option value="${esc(m.name)}">${esc(m.value_label)}</option>`);
  return `<label class="you-row group-row">
    <span class="fname">${esc(g.label)}${imm}</span>
    <select class="you-group" data-modal="${esc(modal)}">${opts.join("")}</select>
  </label>`;
}

function groupMembers(sel) {
  return [...sel.options].map((o) => o.value).filter((v) => v && v !== "__none__");
}

function buildForm(scene) {
  if (formDataset === state.dataset) return;
  formDataset = state.dataset;
  el("you-fields").innerHTML = formGroups(scene.features)
    .map((it) => (it.type === "group" ? groupHTML(it) : fieldHTML(it.f)))
    .join("");
  for (const inp of el("you-fields").querySelectorAll("input"))
    inp.addEventListener("input", checkRange);
  if (state.custom) restoreForm();
}

function restoreForm() {
  for (const inp of el("you-fields").querySelectorAll("input")) {
    const v = state.custom[inp.name];
    inp.value = v == null ? "" : v;
    inp.dispatchEvent(new Event("input"));
  }
  for (const sel of el("you-fields").querySelectorAll("select.you-group")) {
    const members = groupMembers(sel);
    const vals = members.map((nm) => state.custom[nm]);
    let picked = "";
    if (vals.length && vals.every((v) => v === 0))
      picked = sel.querySelector('option[value="__none__"]') ? "__none__" : "";
    else {
      const one = members.find((nm) => state.custom[nm] === 1);
      if (one) picked = one;
    }
    sel.value = picked;
  }
  el("you-details").open = true;
}

function checkRange(e) {
  const inp = e.target, row = inp.closest(".you-row");
  const warn = row.querySelector(".fwarn");
  const v = inp.value === "" ? null : Number(inp.value);
  const min = +row.dataset.min, max = +row.dataset.max;
  const isInt = row.dataset.int === "true";
  if (v == null || isNaN(v)) { warn.textContent = ""; row.classList.remove("out"); return; }
  if (v < min || v > max) {
    warn.textContent = `outside the data (${fmtVal(min, isInt)}–${fmtVal(max, isInt)})`;
    row.classList.add("out");
  } else { warn.textContent = ""; row.classList.remove("out"); }
}

function readForm() {
  const custom = {};
  for (const inp of el("you-fields").querySelectorAll("input"))
    custom[inp.name] = inp.value === "" ? null : Number(inp.value);
  for (const sel of el("you-fields").querySelectorAll("select.you-group")) {
    const choice = sel.value;
    for (const nm of groupMembers(sel))
      custom[nm] = choice === "" ? null
                 : choice === "__none__" ? 0
                 : (nm === choice ? 1 : 0);
  }
  return custom;
}

function updatePanel(scene) {
  renderLensNote(scene);
  renderLegend(scene);
  renderVerdict(scene);
  renderCompare(scene);
  renderRecommend(scene);
  renderWhatif(scene);
  el("compare-typical").href = `/compare.html?dataset=${encodeURIComponent(state.dataset)}` +
    `&you=${encodeYou(personValues(scene))}`;
  renderChanges(scene);

  el("d-std-lin").textContent = scene.panels.linear.cfs.standard.distance.toFixed(3);
  el("d-ell-lin").textContent = safeOk(scene, "linear")
    ? scene.panels.linear.cfs.ellice.distance.toFixed(3) : "none";
  el("d-std-mlp").textContent = scene.panels.mlp.cfs.standard.distance.toFixed(3);
  el("d-ell-mlp").textContent = safeOk(scene, "mlp")
    ? scene.panels.mlp.cfs.ellice.distance.toFixed(3) : "none";

  const rows = scene.deltas.map((r) =>
    `<tr><td>${r.label}</td><td>${fmtVal(r.x0_real, r.integer)}` +
    `${r.unit ? " " + r.unit : ""}</td>` +
    `<td class="miss">${r.missing ? "imputed" : ""}</td></tr>`).join("");
  el("detail").innerHTML =
    `<table><tr><th>feature</th><th>value</th><th></th></tr>${rows}</table>`;

  el("metrics").textContent = metricsText(scene);
  const q = scene.query;
  el("delta-caption").textContent =
    "Grey = can’t change · ✱ = " + (q.custom ? "left blank, typical value used" : "missing, typical value used");
}

function redrawPlots(scene) {
  const config = { responsive: true, displayModeBar: false };
  for (const which of ["linear", "mlp"])
    Plotly.react(plotDivs[which], buildPanelTraces(scene, which),
                 panelLayout(scene, which), config);
  Plotly.react(deltaDiv, deltaTraces(scene), deltaLayout(), config);
}

async function refresh() {
  loading = true;
  try { await drawScene(); } finally { loading = false; }
}

async function drawScene() {
  Object.values(plotDivs).forEach((d) => d.classList.add("loading"));
  el("busy").textContent = "Loading… the first time can take up to a minute.";

  let resp;
  if (state.point) {
    resp = await fetch("/api/scene", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset: state.dataset, point: state.point }),
    });
  } else if (state.custom) {
    resp = await fetch("/api/scene", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset: state.dataset, custom: state.custom }),
    });
  } else {
    const url = new URL("/api/scene", location.origin);
    url.searchParams.set("dataset", state.dataset);
    if (state.query != null) url.searchParams.set("query", state.query);
    resp = await fetch(url);
  }
  const scene = await resp.json();
  Object.values(plotDivs).forEach((d) => d.classList.remove("loading"));
  el("busy").textContent = "";
  if (scene.error) { el("busy").textContent = "Something went wrong: " + scene.error; return; }
  lastScene = scene;

  if (scene.decoded) {
    state.custom = scene.decoded.values;
    state.point = null;
  }
  if (!scene.query.custom) state.query = scene.query.id;
  const rebuilt = formDataset !== state.dataset;
  buildForm(scene);
  if (scene.decoded && !rebuilt) restoreForm();
  showMapNote(scene);

  const config = { responsive: true, displayModeBar: false };
  const draw = plotsReady ? Plotly.react : Plotly.newPlot;
  for (const which of ["linear", "mlp"])
    await draw(plotDivs[which], buildPanelTraces(scene, which),
               panelLayout(scene, which), config);
  await draw(deltaDiv, deltaTraces(scene), deltaLayout(), config);

  if (!plotsReady) {
    plotsReady = true;
    for (const div of Object.values(plotDivs))
      wireClicks(div);
  }
  updatePanel(scene);
}

// ---- which map: the simple (linear) one, the flexible (MLP) one, or both

function colorbarPanel() {
  return mapView === "linear" ? "linear" : "mlp";
}

function setMapView(view, redraw) {
  if (!["linear", "mlp", "both"].includes(view)) view = "both";
  mapView = view;
  try { localStorage.setItem(VIEW_KEY, view); } catch (e) {}
  el("plots").classList.toggle("single", view !== "both");
  el("cell-linear").hidden = view === "mlp";
  el("cell-mlp").hidden = view === "linear";
  for (const b of el("map-toggle").querySelectorAll("button"))
    b.setAttribute("aria-pressed", String(b.dataset.view === view));
  if (redraw && plotsReady && lastScene) {
    redrawPlots(lastScene);
    for (const div of Object.values(plotDivs))
      if (!div.closest(".plot-cell").hidden) Plotly.Plots.resize(div);
  }
}

el("map-toggle").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-view]");
  if (b) setMapView(b.dataset.view, true);
});
try { setMapView(localStorage.getItem(VIEW_KEY) || "both", false); }
catch (e) { setMapView("both", false); }

// A dot selects that person; anywhere else selects the spot itself, which the
// server turns back into a person through the lens's exact inverse. Clicks are
// read from the mouse event, not Plotly's hover, so every pixel of the plot area
// is clickable and the spot is exact.
const DOT_PX = 4;          // a click this close to a dot's centre picks the dot

function wireClicks(div) {
  let down = null, last = -1;
  div.addEventListener("mousedown", (e) => { down = [e.clientX, e.clientY]; }, true);
  div.addEventListener("click", (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;  // a drag
    if (e.timeStamp - last < 300) return;      // Plotly re-sends the same click
    last = e.timeStamp;
    onClick(div, e);
  });
}

function onClick(div, e) {
  if (loading) return;
  const at = plotPixel(div, e);
  if (!at) return;
  const id = dotAt(div, at);
  if (id != null) {
    state.query = id;
    state.custom = null;
    state.point = null;
  } else {
    const fl = div._fullLayout;
    state.point = [fl.xaxis.p2d(at[0]), fl.yaxis.p2d(at[1])];
    state.query = null;
  }
  refresh();
}

// The click in plot-area pixels, or null outside the plot area.
function plotPixel(div, mouse) {
  const fl = div._fullLayout, svg = div.querySelector(".main-svg");
  if (!fl || !fl.xaxis || !svg) return null;
  const xa = fl.xaxis, ya = fl.yaxis, box = svg.getBoundingClientRect();
  const px = mouse.clientX - box.left - xa._offset;
  const py = mouse.clientY - box.top - ya._offset;
  if (px < 0 || py < 0 || px > xa._length || py > ya._length) return null;
  return [px, py];
}

// The id of the nearest dot within DOT_PX of a plot-area pixel, else null.
function dotAt(div, [px, py]) {
  const xa = div._fullLayout.xaxis, ya = div._fullLayout.yaxis;
  let best = null, bestD = DOT_PX;
  for (const t of div.data) {
    if (t.meta !== "people") continue;
    for (let i = 0; i < t.x.length; i++) {
      const d = Math.hypot(xa.d2p(t.x[i]) - px, ya.d2p(t.y[i]) - py);
      if (d <= bestD) { bestD = d; best = t.customdata[i]; }
    }
  }
  return best;
}

// Share of a change below which the map clearly undersells it.
const OFF_MAP = 0.5;
function offMapNote(scene) {
  const which = mapView === "mlp" ? "mlp" : "linear";
  const m = scene.panels[which].metrics;
  const share = safeOk(scene, which) ? m.safe_on_map : quickOk(scene, which) ? m.quick_on_map : 1;
  return share != null && share < OFF_MAP && m.pred_bad
    ? `<span class="sub">Only ${Math.round(share * 100)}% of this change shows on the map; the rest is in
       values the map can’t draw, so the arrow may look short of the line.</span>` : "";
}

function showMapNote(scene) {
  const note = el("map-note"), d = scene.decoded;
  const off = offMapNote(scene);
  note.hidden = !d && !off;
  if (!d) { note.innerHTML = off; return; }
  const m = scene.panels.linear.metrics, [goodName, badName] = scene.class_names;
  note.innerHTML = `<b>Estimated person at this spot:</b> ` +
    `${G.esc(m.pred_bad ? badName : goodName)} · ${pct(m.p_bad_erm_x0)} chance of ${G.esc(badName)}. ` +
    `<span class="sub">Their numbers are filled in below.</span>` +
    (d.outside.length ? `<br><span class="warn">Outside the data: ${d.outside.map(G.esc).join(", ")}</span>` : "") +
    (off ? "<br>" + off : "");
}

el("dataset").addEventListener("change", async (e) => {
  state.dataset = e.target.value;
  state.query = null; state.custom = null; state.point = null;
  el("save-msg").textContent = "";
  closeSavePanel();
  await refresh();
  refreshSaved();
});
el("you-form").addEventListener("submit", (e) => {
  e.preventDefault();
  state.custom = readForm();
  state.point = null;
  refresh();
});
el("you-typical").addEventListener("click", () => {
  for (const inp of el("you-fields").querySelectorAll("input")) {
    inp.value = inp.closest(".you-row").dataset.median;
    inp.dispatchEvent(new Event("input"));
  }
  for (const sel of el("you-fields").querySelectorAll("select.you-group"))
    sel.value = sel.dataset.modal || "";
});
el("you-clear").addEventListener("click", () => {
  for (const inp of el("you-fields").querySelectorAll("input")) {
    inp.value = "";
    inp.dispatchEvent(new Event("input"));
  }
  for (const sel of el("you-fields").querySelectorAll("select.you-group")) sel.value = "";
  state.custom = null;
  state.point = null;
  refresh();
});

// ---- saving: signed-in users choose which values to keep, under a name

function setSaveButton() {
  el("you-save").textContent = currentUser ? "Save values…" : "Sign in to save";
}

// One item per form field that has a value (a one-hot group counts as one).
function filledItems() {
  const items = [];
  for (const row of el("you-fields").querySelectorAll(".you-row")) {
    const label = row.querySelector(".fname").firstChild.textContent.trim();
    const inp = row.querySelector("input"), sel = row.querySelector("select.you-group");
    if (inp && inp.value !== "") {
      const unit = (row.querySelector(".unit") || {}).textContent || "";
      items.push({ names: [inp.name], label,
                   text: inp.value + (unit ? " " + unit.replace(/[()]/g, "") : "") });
    } else if (sel && sel.value !== "") {
      items.push({ names: groupMembers(sel), label, text: sel.selectedOptions[0].textContent });
    }
  }
  return items;
}

function defaultSaveName() {
  const when = new Date().toLocaleString([], { month: "short", day: "numeric",
                                               hour: "numeric", minute: "2-digit" });
  return (lastScene && lastScene.query.from_map ? "Map spot, " : "My values, ") + when;
}

function updateSaveConfirm() {
  const name = el("save-name").value.trim();
  const clash = savedEntries.some((s) => s.name === name);
  el("save-confirm").textContent = clash ? "Replace" : "Save";
  el("save-confirm").title = clash ? "Replaces your save with the same name" : "";
}

function openSavePanel() {
  const items = filledItems();
  if (!items.length) {
    el("save-msg").textContent = "Enter or pick at least one value first.";
    return;
  }
  panelItems = items;
  el("save-msg").textContent = "";
  el("save-choices").innerHTML = items.map((it, i) =>
    `<label class="save-choice"><input type="checkbox" data-i="${i}" checked>` +
    `<span>${esc(it.label)}</span> <b>${esc(it.text)}</b></label>`).join("");
  el("save-name").value = defaultSaveName();
  updateSaveConfirm();
  el("save-panel").hidden = false;
  el("save-panel").scrollIntoView({ block: "nearest", behavior: "smooth" });
  el("save-name").focus();
  el("save-name").select();
}

function closeSavePanel() {
  el("save-panel").hidden = true;
  panelItems = [];
}

async function confirmSave() {
  const all = readForm(), values = {};
  for (const cb of el("save-choices").querySelectorAll("input:checked"))
    for (const nm of panelItems[+cb.dataset.i].names) values[nm] = all[nm];
  const msg = el("save-msg");
  if (!Object.keys(values).length) {
    msg.textContent = "Tick at least one value to save.";
    return;
  }
  const name = el("save-name").value.trim();
  el("save-confirm").disabled = true;
  try {
    const resp = await fetch("/api/saved", {
      method: "POST", headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ dataset: state.dataset, name, values }),
    });
    const body = await resp.json().catch(() => ({}));
    if (resp.ok) {
      closeSavePanel();
      msg.textContent = `Saved “${body.saved.name}” to your account.`;
      await refreshSaved();
    } else {
      msg.textContent = body.error || "Could not save. Please try again.";
    }
  } catch (e) {
    msg.textContent = "Could not reach the server. Please try again.";
  } finally {
    el("save-confirm").disabled = false;
  }
}

// Plain-language summary of a save, e.g. "Glucose 150 mg/dL · BMI 31.5 kg/m²".
function summarise(values) {
  const meta = Object.fromEntries((lastScene ? lastScene.features : []).map((f) => [f.name, f]));
  const parts = [], groups = {};
  for (const [name, v] of Object.entries(values)) {
    if (v == null) continue;
    const f = meta[name];
    if (f && f.group) {
      if (!(f.group in groups)) groups[f.group] = parts.push(`${f.group_label}: none`) - 1;
      if (v === 1) parts[groups[f.group]] = `${f.group_label}: ${f.value_label}`;
      continue;
    }
    const unit = f && f.unit ? " " + f.unit : "";
    parts.push(`${f ? f.label : name} ${fmtVal(v, f && f.integer && Number.isInteger(v))}${unit}`);
  }
  return parts.join(" · ");
}

function renderSaved() {
  el("saved-list").hidden = !savedEntries.length;
  el("saved-items").innerHTML = savedEntries.map((s, i) =>
    `<li><div class="saved-main"><b>${esc(s.name)}</b>` +
    `<span class="sub">${esc(summarise(s.values))}</span></div>` +
    `<span class="sub saved-when">${new Date(s.updated_at * 1000).toLocaleString()}</span>` +
    `<button type="button" data-load="${i}">Load</button>` +
    `<button type="button" data-del="${i}">Delete</button></li>`).join("");
}

async function refreshSaved() {
  savedEntries = [];
  if (currentUser) {
    try {
      const url = "/api/saved?dataset=" + encodeURIComponent(state.dataset);
      const body = await (await fetch(url, { credentials: "same-origin" })).json();
      savedEntries = body.saved || [];
    } catch (e) {}
  }
  renderSaved();
}

function goSignInToSave(values) {
  // Keep what was typed, sign in, and pick what to save on the way back.
  try {
    sessionStorage.setItem(PENDING_KEY, JSON.stringify({ dataset: state.dataset, values }));
  } catch (e) {}
  location.href = "/login.html?reason=save&next=" +
    encodeURIComponent("/app.html?dataset=" + state.dataset);
}

function takePending() {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    sessionStorage.removeItem(PENDING_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

el("you-save").addEventListener("click", () => {
  if (!currentUser) goSignInToSave(readForm());
  else openSavePanel();
});
el("save-confirm").addEventListener("click", confirmSave);
el("save-cancel").addEventListener("click", closeSavePanel);
el("save-name").addEventListener("input", updateSaveConfirm);
el("save-all").addEventListener("click", () =>
  el("save-choices").querySelectorAll("input").forEach((cb) => { cb.checked = true; }));
el("save-none").addEventListener("click", () =>
  el("save-choices").querySelectorAll("input").forEach((cb) => { cb.checked = false; }));

el("saved-items").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const s = savedEntries[+(b.dataset.load ?? b.dataset.del)];
  if (!s) return;
  if (b.dataset.load != null) {
    state.custom = s.values;
    state.point = null;
    restoreForm();
    el("save-msg").textContent = `Loaded “${s.name}”.`;
    refresh();
    return;
  }
  if (!confirm(`Delete “${s.name}”?`)) return;
  const resp = await fetch("/api/saved?id=" + encodeURIComponent(s.id),
                           { method: "DELETE", credentials: "same-origin" });
  el("save-msg").textContent = resp.ok ? `Deleted “${s.name}”.`
                                       : "Could not delete. Please try again.";
  await refreshSaved();
});


async function showAccount() {
  currentUser = await G.me;
  setSaveButton();
}

async function init() {
  await showAccount();
  const qs = new URLSearchParams(location.search);
  if (qs.has("dataset")) state.dataset = qs.get("dataset");
  if (qs.has("you")) {
    state.custom = {};
    for (const kv of qs.get("you").split(",")) {
      const i = kv.indexOf(":");
      if (i > 0 && isFinite(Number(kv.slice(i + 1))))
        state.custom[kv.slice(0, i)] = Number(kv.slice(i + 1));
    }
  }

  // Back from signing in to save: restore what was typed, then choose what to keep.
  const pending = currentUser ? takePending() : null;
  if (pending) {
    state.dataset = pending.dataset;
    state.custom = pending.values;
  }

  const meta = await (await fetch("/api/datasets")).json();
  el("dataset").innerHTML = meta.datasets
    .map((d) => `<option value="${G.esc(d.key)}">${G.esc(G.topicName(d.key, d.label))}</option>`)
    .join("");
  el("dataset").value = state.dataset;

  await refresh();
  await refreshSaved();
  const openId = Number(qs.get("save"));
  const toOpen = openId && savedEntries.find((e) => e.id === openId);
  if (toOpen) {
    state.custom = toOpen.values;
    state.point = null;
    restoreForm();
    el("save-msg").textContent = `Opened “${toOpen.name}”.`;
    await refresh();
  }
  if (pending) openSavePanel();
  else if (qs.get("enter") === "1") {
    el("you-details").open = true;
    el("you-details").scrollIntoView({ behavior: "smooth", block: "start" });
    const first = el("you-fields").querySelector("input, select");
    if (first) first.focus({ preventScroll: true });
  }
}

// ---- map tools: graph style, find me, reset zoom, most disputed

el("map-tip").innerHTML = G.tip("Click any spot to see the person who would be there. " +
  "Drag a box to zoom in, or use + and −. Double-click resets.");
el("tip-linear").innerHTML = G.tip("A straight-line model. Easy to explain.");
el("tip-mlp").innerHTML = G.tip("A small neural network. Can bend around the data.");
el("compare-tip").innerHTML = G.tip("Where each number sits among everyone in the data. " +
  "Most important first. A lock means it can’t be changed.", "right");
el("reco-tip").innerHTML = G.tip("The smallest changes that flip the result for every " +
  "model that fits the data about as well. Things you can’t change are never suggested.");
el("reco-kind-tip").innerHTML = G.tip("Quickest: the smallest change for this model. " +
  "Safest: a change that works for every model that fits the data about as well.");
el("whatif-tip").innerHTML = G.tip("Drag a value. The chance updates and a hollow star " +
  "shows where you would move on the map.");
el("plan-tip").innerHTML = G.tip("Tick the changes you’ll make. Save the plan to your " +
  "account and compare it with now.", "right");
el("changes-tip").innerHTML = G.tip("Now: your numbers. After: the closest person every " +
  "good model would put on the other side.");

function setGraphStyle(old, redraw) {
  oldGraph = old;
  el("old-graph").checked = old;
  el("disputed-switch").hidden = !old;
  try { localStorage.setItem(GRAPH_KEY, old ? "1" : "0"); } catch (e) {}
  if (redraw && plotsReady && lastScene) {
    redrawPlots(lastScene);
    renderLegend(lastScene);
  }
}
el("old-graph").addEventListener("change", (e) => setGraphStyle(e.target.checked, true));
el("show-disputed").addEventListener("change", (e) => {
  showDisputed = e.target.checked;
  if (plotsReady && lastScene) redrawPlots(lastScene);
});
try { setGraphStyle(localStorage.getItem(GRAPH_KEY) === "1", false); }
catch (e) { setGraphStyle(false, false); }

function visiblePanels() {
  return ["linear", "mlp"].filter((w) => !el("cell-" + w).hidden);
}
el("reset-zoom").addEventListener("click", () => {
  if (!lastScene) return;
  for (const which of visiblePanels()) {
    const [xr, yr] = defaultRanges(lastScene, which);
    Plotly.relayout(plotDivs[which], { "xaxis.range": xr, "yaxis.range": yr });
  }
});
// Zoom in or out around the middle of what's on screen; both axes by the same
// factor, so the map keeps its shape.
const ZOOM_STEP = 0.7;
function zoomBy(factor) {
  if (!plotsReady) return;
  for (const which of visiblePanels()) {
    const fl = plotDivs[which]._fullLayout;
    const scale = (r) => {
      const c = (r[0] + r[1]) / 2, h = (r[1] - r[0]) / 2 * factor;
      return [c - h, c + h];
    };
    Plotly.relayout(plotDivs[which], { "xaxis.range": scale(fl.xaxis.range),
                                       "yaxis.range": scale(fl.yaxis.range) });
  }
}
el("zoom-in").addEventListener("click", () => zoomBy(ZOOM_STEP));
el("zoom-out").addEventListener("click", () => zoomBy(1 / ZOOM_STEP));

el("find-me").addEventListener("click", () => {
  if (!lastScene) return;
  const q = lastScene.query;
  for (const which of visiblePanels()) {
    const fl = plotDivs[which]._fullLayout;
    const wx = fl.xaxis.range[1] - fl.xaxis.range[0], wy = fl.yaxis.range[1] - fl.yaxis.range[0];
    Plotly.relayout(plotDivs[which], { "xaxis.range": [q.x - wx / 2, q.x + wx / 2],
                                       "yaxis.range": [q.y - wy / 2, q.y + wy / 2] });
  }
});

init();
