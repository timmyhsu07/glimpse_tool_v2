

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
let mapView = "both";

const pct = (v) => (v * 100).toFixed(0) + "%";
const f3 = (v) => (v == null ? "  n/a" : v.toFixed(3));

function fmtVal(v, integer) {
  if (v == null || isNaN(v)) return "—";
  if (integer) return (Math.round(v) + 0).toLocaleString();
  const a = Math.abs(v);
  return (Number(v.toFixed(a >= 100 ? 0 : a >= 10 ? 1 : 2)) + 0)
    .toString();
}
const ordinal = (n) => {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

const THEME_KEY = "glimpse-theme";
const isDark = () =>
  document.documentElement.getAttribute("data-theme") === "dark";

function themeColors() {
  return isDark()
    ? { paper: "#1c2027", plot: "#1c2027", font: "#e6e6ea",
        legendBg: "rgba(28,32,39,0.82)", legendBorder: "#333a45", zero: "#8a8f99" }
    : { paper: "#ffffff", plot: "#ffffff", font: "#222222",
        legendBg: "rgba(255,255,255,0.75)", legendBorder: "#cccccc", zero: "#888888" };
}

function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(THEME_KEY, t); } catch (e) {}
  const btn = el("theme-toggle");
  if (btn) btn.textContent = t === "dark" ? "☀ Light" : "☾ Dark";
  if (plotsReady && lastScene) redrawPlots(lastScene);
}

function initTheme() {
  let t = null;
  try {
    const q = new URLSearchParams(location.search).get("theme");
    t = (q === "dark" || q === "light") ? q : localStorage.getItem(THEME_KEY);
  } catch (e) {}
  if (t !== "dark" && t !== "light")
    t = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  applyTheme(t);
}

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
    hovertemplate: `${name}<br>cost %{text}<extra></extra>`, text: [pt.distance],
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
    opacity: 0.9, hoverinfo: "none", showscale: which === colorbarPanel(),
    colorbar: { title: { text: "P(bad)", side: "right", font: { color: tc.font } },
                tickfont: { color: tc.font },
                thickness: 12, len: 0.9, x: 1.02 },
  });

  traces.push(...polyTraces(panel.fan, COLORS.fan, 1, 0.14,
                            "equally-good models", legend));

  const groups = [
    { c: 0, color: COLORS.good, label: scene.class_names[0] },
    { c: 1, color: COLORS.bad, label: scene.class_names[1] },
  ];
  for (const g of groups) {
    const sel = scene.points.filter((p) => p.outcome === g.c);
    traces.push({
      type: "scatter", mode: "markers",
      x: sel.map((p) => p.x), y: sel.map((p) => p.y),
      customdata: sel.map((p) => p.id), meta: "people",
      marker: { size: 5, color: g.color, opacity: 0.55,
                line: { color: "white", width: 0.3 } },
      name: g.label, showlegend: legend,
      hovertemplate: `person #%{customdata}<extra></extra>`,
    });
  }

  traces.push(...polyTraces(panel.boundary, COLORS.boundary, 2.6, 1,
                            "decision boundary", legend));
  traces.push(...polyTraces(panel.worst, COLORS.worst, 2.4, 0.95,
                            "harshest equally-good model", legend));

  const q = scene.query, cf = panel.cfs;
  const qName = q.from_map ? "the spot you picked"
              : q.custom ? "you (entered)" : `person #${q.id}`;
  traces.push({
    type: "scatter", mode: "markers", x: [q.x], y: [q.y],
    marker: { size: q.custom ? 15 : 12,
              color: q.custom ? COLORS.you : COLORS.query,
              symbol: "star", opacity: 0.95, line: { color: "#000", width: 0.7 } },
    name: "person", showlegend: false, customdata: [q.id],
    hovertemplate: `${qName}<extra></extra>`,
  });
  traces.push(markerTrace(cf.standard, COLORS.std, "quick change", "x", 9));
  traces.push(markerTrace(cf.ellice, COLORS.ell, "robust change", "square", 9));
  return traces;
}

// Axis ranges. Both axes use constrain "domain", so Plotly keeps equal scale by
// shrinking the plot area, never by changing these ranges. A map click keeps the
// current view: the star lands under the pointer and the map does not shift.
function viewRanges(div, scene, which) {
  const fl = div._fullLayout;
  if (scene.query.from_map && fl && fl.xaxis && div.dataset.view === scene.dataset)
    return [fl.xaxis.range.slice(), fl.yaxis.range.slice()];
  div.dataset.view = scene.dataset;
  const q = scene.query, cf = scene.panels[which].cfs;
  const xs = [scene.bounds.x[0], scene.bounds.x[1], q.x, cf.ellice.x];
  const ys = [scene.bounds.y[0], scene.bounds.y[1], q.y, cf.ellice.y];
  const grow = (lo, hi) => [lo - 0.03 * (hi - lo), hi + 0.03 * (hi - lo)];
  return [grow(Math.min(...xs), Math.max(...xs)), grow(Math.min(...ys), Math.max(...ys))];
}

function panelLayout(scene, which) {
  const q = scene.query, cf = scene.panels[which].cfs;
  const [xr, yr] = viewRanges(plotDivs[which], scene, which);
  const axis = scene.lens.is_linear ? ["PC1", "PC2"] : ["z₁", "z₂"];
  const tc = themeColors();
  return {
    paper_bgcolor: tc.paper, plot_bgcolor: tc.plot, font: { color: tc.font },
    margin: { l: 42, r: which === "mlp" ? 4 : 10, t: 6, b: 36 },
    xaxis: { title: axis[0], range: xr, zeroline: false, constrain: "domain",
             color: tc.font },
    yaxis: { title: axis[1], range: yr, zeroline: false, constrain: "domain",
             scaleanchor: "x", scaleratio: 1, color: tc.font },
    legend: { x: 0.02, y: 0.98, bgcolor: tc.legendBg,
              font: { size: 10, color: tc.font }, bordercolor: tc.legendBorder,
              borderwidth: 1 },
    showlegend: false, hovermode: "closest",
    // a dot is only picked when the pointer is on it; anywhere else is a spot
    hoverdistance: DOT_PX,
    // keep the user's zoom while clicking around the same dataset
    uirevision: scene.dataset,
    annotations: [{
      x: cf.ellice.x, y: cf.ellice.y, ax: q.x, ay: q.y,
      xref: "x", yref: "y", axref: "x", ayref: "y",
      showarrow: true, arrowhead: 3, arrowsize: 1.2, arrowwidth: 1.6,
      arrowcolor: "#111", opacity: 0.85, text: "",
    }],
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
      r.immutable ? " · held fixed (immutable)" : "",
    ]),
    hovertemplate:
      "%{y}: %{customdata[0]} → %{customdata[1]} (real units)<br>" +
      "percentile %{customdata[2]} → %{customdata[3]}%{customdata[4]}" +
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
    xaxis: { title: "Δ = change − you  (standardized units)", color: tc.font,
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
  el("maps-sub").textContent =
    "ECLIPSE view — a linear model’s boundary is an exact straight line here";
}

function renderLegend(scene) {
  const [g, b] = scene.class_names;
  el("legend").innerHTML = [
    `<li><span class="sw" style="background:#aaffaa"></span> good side` +
      ` <span class="sw" style="background:#ffaaff"></span> bad side` +
      ` <span class="sub">(background = the model’s P(${b}))</span></li>`,
    `<li><span class="dot" style="background:${COLORS.good}"></span> ${g}` +
      ` &nbsp;<span class="dot" style="background:${COLORS.bad}"></span> ${b}` +
      ` <span class="sub">(each dot is a person)</span></li>`,
    `<li><span class="sw line" style="background:${COLORS.boundary}"></span>` +
      ` decision boundary</li>`,
    `<li><span class="sw line" style="background:${COLORS.fan}"></span>` +
      ` equally-good models (sampled “Rashomon” fan)</li>`,
    `<li><span class="sw line" style="background:${COLORS.worst}"></span>` +
      ` harshest equally-good model</li>`,
    `<li>★ person, ✕ = quick change, ▪ = robust change</li>`,
  ].join("");
}

function renderVerdict(scene) {
  const q = scene.query;
  const who = q.from_map ? "The person at this spot" : q.custom ? "You" : `This person`;
  const [goodName, badName] = scene.class_names;
  const lm = scene.panels.linear.metrics;
  const predName = lm.pred_bad ? badName : goodName;
  el("verdict").className = lm.pred_bad ? "bad" : "good";

  const uncertain = lm.p_bad_best_x0 < 0.5 && lm.p_bad_worst_x0 > 0.5;
  el("verdict-headline").innerHTML =
    `${who} would be predicted <b>${predName}</b>` +
    (uncertain
      ? ` — but it’s a close call: equally-good models disagree.`
      : `.`);

  el("verdict-models").innerHTML = ["linear", "mlp"].map((which) => {
    const m = scene.panels[which].metrics;
    const name = which === "linear" ? "Simple model" : "Flexible model";
    const lo = Math.round(m.p_bad_best_x0 * 100);
    const hi = Math.round(m.p_bad_worst_x0 * 100);
    const erm = Math.round(m.p_bad_erm_x0 * 100);
    const side = m.pred_bad ? badName : goodName;
    return `<div class="vmodel ${m.pred_bad ? "bad" : "good"}">
      <div class="vlabel">${name}</div>
      <div class="vpred">${side}</div>
      <div class="vrange">chance of “${badName}”:
        <b>${lo}–${hi}%</b> <span class="sub">(best guess ${erm}%)</span></div>
      <div class="vbar"><span style="left:${lo}%;right:${100 - hi}%"></span>
        <i style="left:${erm}%"></i></div>
      <div class="sub vexpl">range = every model that fits the data equally well</div>
    </div>`;
  }).join("");
}

function renderRecommend(scene) {
  const [goodName, badName] = scene.class_names;
  const anyBad = scene.panels.linear.metrics.pred_bad ||
                 scene.panels.mlp.metrics.pred_bad;
  const imm = scene.deltas.filter((r) => r.immutable).map((r) => r.label);
  el("reco-note").textContent = (anyBad && imm.length)
    ? `Held fixed because they can’t realistically be changed: ${imm.join(", ")}.`
    : "";

  el("reco-lists").innerHTML = ["linear", "mlp"].map((which) => {
    const m = scene.panels[which].metrics;
    const name = which === "linear" ? "Simple model" : "Flexible model";
    if (!m.pred_bad) {
      return `<div class="reco-col"><div class="reco-h">${name}</div>
        <p class="reco-ok">Already on the “${goodName}” side — nothing needs
        to change.</p></div>`;
    }
    // Show meaningful mutable changes, with at least three when available.
    const magOf = (it) => it.kind === "group"
      ? it.per[which].mag : Math.abs(it.r[which].delta_std);
    const ranked = displayRows(scene)
      .filter((it) => !(it.kind === "group" ? it.immutable : it.r.immutable))
      .sort((a, b) => magOf(b) - magOf(a));
    const strong = ranked.filter((it) => magOf(it) > 0.05);
    const rows = (strong.length >= 2 ? strong : ranked.slice(0, 3)).slice(0, 5);
    const items = rows.map((it) => {
      if (it.kind === "group") {
        const p = it.per[which];
        if (!p.changed) return "";
        return `<li class="up"><span class="arrow">→</span>
          <b>Set ${esc(it.label)} to “${esc(p.cat)}”</b>
          <span class="sub">(currently “${esc(it.youCat)}”)</span></li>`;
      }
      const r = it.r, d = r[which];
      const up = d.delta_real > 0;
      const unit = r.unit ? " " + r.unit : "";
      return `<li class="${up ? "up" : "down"}">
        <span class="arrow">${up ? "▲" : "▼"}</span>
        <b>${up ? "Raise" : "Lower"} ${r.label}</b>
        from ${fmtVal(r.x0_real, r.integer)} to
        <b>${fmtVal(d.cf_real, r.integer)}${unit}</b>
        <span class="sub">(${ordinal(Math.round(r.pct_x0))} →
        ${ordinal(Math.round(d.pct_cf))} percentile)</span></li>`;
    }).filter(Boolean).join("");
    return `<div class="reco-col">
      <div class="reco-h">${name}
        <span class="sub">smallest robust change to reach “${goodName}”</span></div>
      <ul class="reco">${items ||
        "<li class='sub'>no single-feature change is enough on its own</li>"}</ul>
    </div>`;
  }).join("");
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
  for (const which of ["linear", "mlp"]) {
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
  el("changes-good").textContent = scene.class_names[0];

  const rows = displayRows(scene).sort((a, b) => b.key - a.key);

  const plainCell = (r, which) => {
    if (r.immutable) return `<td class="fixed">held fixed</td>`;
    const d = r[which];
    if (Math.abs(d.delta_std) <= 0.02) return `<td class="same">no change</td>`;
    const up = d.delta_real > 0, unit = r.unit ? " " + r.unit : "";
    return `<td class="${up ? "up" : "down"}">` +
      `<span class="arrow">${up ? "▲" : "▼"}</span>` +
      `${fmtVal(d.cf_real, r.integer)}${unit}` +
      ` <span class="sub">(${up ? "+" : ""}${fmtVal(d.delta_real, r.integer)})</span></td>`;
  };
  const groupCell = (g, which) => {
    if (g.immutable) return `<td class="fixed">held fixed</td>`;
    const p = g.per[which];
    if (!p.changed) return `<td class="same">no change</td>`;
    return `<td class="up"><span class="arrow">→</span>${esc(p.cat)}</td>`;
  };

  const trs = rows.map((it) => {
    if (it.kind === "group") {
      const miss = it.missing ? ' <span class="miss-mark" title="imputed">✱</span>' : "";
      return `<tr class="${it.immutable ? "immrow" : ""}">` +
        `<td class="fname-cell">${esc(it.label)}${miss}</td>` +
        `<td class="youval">${esc(it.youCat)}</td>` +
        `${groupCell(it, "linear")}${groupCell(it, "mlp")}</tr>`;
    }
    const r = it.r;
    const miss = r.missing ? ' <span class="miss-mark" title="imputed">✱</span>' : "";
    const unit = r.unit ? ` <span class="sub">(${r.unit})</span>` : "";
    return `<tr class="${r.immutable ? "immrow" : ""}">` +
      `<td class="fname-cell">${r.label}${miss}${unit}</td>` +
      `<td class="youval">${fmtVal(r.x0_real, r.integer)}</td>` +
      `${plainCell(r, "linear")}${plainCell(r, "mlp")}</tr>`;
  }).join("");

  el("changes-table").innerHTML =
    `<table class="chg"><thead><tr>` +
    `<th>Feature</th><th>You</th>` +
    `<th>Simple model →</th><th>Flexible model →</th>` +
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
    ? ` <span class="imm-tag" title="won’t be changed by recommendations">fixed</span>`
    : "";
  const hint = f.desc ? `<span class="fhint">${f.desc}</span>` : "";
  return `<label class="you-row" data-min="${f.min}" data-max="${f.max}"
                 data-p5="${f.p5}" data-p95="${f.p95}"
                 data-median="${f.median}" data-int="${f.integer}">
    <span class="fname">${f.label}${unit}${imm}</span>
    ${hint}
    <input type="number" step="${f.integer ? 1 : "any"}" name="${f.name}"
           placeholder="typical ${fmtVal(f.median, f.integer)}">
    <span class="fwarn"></span>
  </label>`;
}

function groupHTML(g) {
  const imm = g.members.some((m) => m.immutable)
    ? ` <span class="imm-tag" title="won’t be changed by recommendations">fixed</span>`
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
  renderRecommend(scene);
  renderChanges(scene);

  el("sub-linear").textContent = "straight-line boundary";

  el("d-std-lin").textContent = scene.panels.linear.cfs.standard.distance.toFixed(3);
  el("d-ell-lin").textContent = scene.panels.linear.cfs.ellice.distance.toFixed(3);
  el("d-std-mlp").textContent = scene.panels.mlp.cfs.standard.distance.toFixed(3);
  el("d-ell-mlp").textContent = scene.panels.mlp.cfs.ellice.distance.toFixed(3);

  const rows = scene.deltas.map((r) =>
    `<tr><td>${r.label}</td><td>${fmtVal(r.x0_real, r.integer)}` +
    `${r.unit ? " " + r.unit : ""}</td>` +
    `<td class="miss">${r.missing ? "imputed" : ""}</td></tr>`).join("");
  el("detail").innerHTML =
    `<table><tr><th>feature</th><th>value</th><th></th></tr>${rows}</table>`;

  el("metrics").textContent = metricsText(scene);
  const q = scene.query;
  el("delta-caption").textContent =
    "grey bars = immutable features (held fixed in the search); " +
    (q.custom ? "✱ = left blank in the form (imputed)."
              : "✱ = missing in the data (imputed).");
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
  el("busy").textContent =
    "  computing… (first use of a dataset fits its map: up to ~1 min)";

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
  if (scene.error) { el("lens-note").textContent = "error: " + scene.error; return; }
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

function showMapNote(scene) {
  const note = el("map-note"), d = scene.decoded;
  note.hidden = !d;
  if (!d) return;
  let text = "Showing the person the map places exactly at the spot you " +
             "clicked. Their values are filled in below.";
  if (d.outside.length)
    text += ` ${d.outside.length === 1 ? "One value falls" : d.outside.length + " values fall"}` +
            ` outside anything in the data (${d.outside.join(", ")}), so this` +
            " spot is beyond the people the models learned from.";
  note.textContent = text;
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
    encodeURIComponent("/?dataset=" + state.dataset);
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

initTheme();
el("theme-toggle").addEventListener("click", () =>
  applyTheme(isDark() ? "light" : "dark"));

async function showAccount() {
  try {
    const me = await (await fetch("/api/me", { credentials: "same-origin" })).json();
    currentUser = me.user || null;
    setSaveButton();
    if (!me.user) return;
    const link = el("account-link");
    link.textContent = "";
    const who = document.createElement("span");
    who.className = "sub";
    who.textContent = me.user.email;
    link.append(who, "Account");
  } catch (e) {}
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
    .map((d) => `<option value="${d.key}">${d.label}</option>`).join("");
  el("dataset").value = state.dataset;

  await refresh();
  await refreshSaved();
  if (pending) openSavePanel();
}

init();
