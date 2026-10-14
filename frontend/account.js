// My account: details, saves per topic, change password, delete account.
const G = window.GLIMPSE;
const el = (id) => document.getElementById(id);

async function post(url, data) {
  const resp = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}), credentials: "same-origin",
  });
  let body = {};
  try { body = await resp.json(); } catch (e) {}
  return { ok: resp.ok, body };
}

function notice(text) {
  el("account-notice").textContent = text;
  el("account-notice").hidden = !text;
}

function wire(form, url, check, done) {
  const msg = form.querySelector(".auth-msg"), button = form.querySelector(".auth-submit");
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    const problem = check(data);
    msg.textContent = problem || "";
    if (problem) return;
    button.disabled = true;
    try {
      const { ok, body } = await post(url, data);
      if (ok) done(body);
      else msg.textContent = body.error || "Something went wrong. Please try again.";
    } catch (e) {
      msg.textContent = "Could not reach the server. Please try again.";
    } finally {
      button.disabled = false;
    }
  });
}

wire(el("form-password"), "/api/account/password", (d) => {
  if (!d.current) return "Enter your current password.";
  if (d.new.length < 8) return "Use at least 8 characters.";
  if (d.new !== d.confirm) return "The two new passwords don’t match.";
  return "";
}, () => {
  el("form-password").reset();
  notice("Password changed.");
  window.scrollTo({ top: 0, behavior: "smooth" });
});

wire(el("form-delete"), "/api/account/delete", (d) => {
  if (!d.password) return "Enter your password.";
  if (!el("del-confirm").checked) return "Tick the box to confirm.";
  return "";
}, () => { location.href = "/"; });

el("acct-signout").addEventListener("click", async () => {
  await post("/api/logout");
  location.href = "/";
});

async function init() {
  if (!(await G.me)) {
    location.replace("/login.html?next=" + encodeURIComponent("/account.html"));
    return;
  }
  const resp = await fetch("/api/account", { credentials: "same-origin" });
  if (resp.status === 401) {
    location.replace("/login.html?next=" + encodeURIComponent("/account.html"));
    return;
  }
  const { user } = await resp.json();
  el("acct-email").textContent = user.email;
  el("acct-since").textContent = new Date(user.created_at * 1000)
    .toLocaleDateString([], { year: "numeric", month: "long", day: "numeric" });
  el("acct-forgot").href = "/login.html?mode=login#forgot";

  await renderSaves();

  if (new URLSearchParams(location.search).get("reset") === "1")
    notice("New password saved. You’re signed in.");
  el("account").hidden = false;
}
init();

// ---- saves: cards with a mini verdict, a timeline per topic, rename / compare / delete

let datasets = [];

const day = (t) => new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });

async function predictAll(dataset, list) {
  const r = await fetch("/api/people", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset, people: list.map((s) => s.values) }),
  });
  if (!r.ok) throw new Error("predict failed");
  return r.json();
}

function saveCard(s, person, names) {
  const m = person.linear, bad = m.p >= 0.5;
  const lo = Math.round(m.lo * 100), hi = Math.round(m.hi * 100), p = Math.round(m.p * 100);
  return `<li class="save-card ${bad ? "bad" : "good"}" data-id="${s.id}">
    <div class="sc-head"><b class="sc-name">${G.esc(s.name)}</b><span class="sub">${day(s.updated_at)}</span></div>
    <div class="sc-verdict"><span class="sc-pred">${G.esc(bad ? names[1] : names[0])}</span>
      <span>${p}% <span class="sub">· ${lo}–${hi}%</span></span></div>
    <div class="vbar" role="img" aria-label="${lo} to ${hi} percent, best guess ${p}">
      <span style="left:${lo}%;right:${100 - hi}%"></span><i style="left:${p}%"></i></div>
    <div class="sc-actions">
      <a href="/app.html?dataset=${encodeURIComponent(s.dataset)}&save=${s.id}">Open</a>
      <button type="button" data-act="rename">Rename</button>
      <a href="/compare.html?dataset=${encodeURIComponent(s.dataset)}&a=${s.id}">Compare</a>
      <button type="button" data-act="delete">Delete</button>
    </div></li>`;
}

// Chance over time for one topic: one line, the 50% mark dashed.
function timeline(list, people, badName) {
  if (list.length < 2) return "";
  const pts = list.map((s, i) => ({ s, p: people[i].linear.p })).sort((a, b) => a.s.updated_at - b.s.updated_at);
  const W = 600, H = 150, L = 34, R = 12, T = 12, B = 26;
  const t0 = pts[0].s.updated_at, t1 = pts[pts.length - 1].s.updated_at;
  const x = (pt, i) => L + (W - L - R) * (t1 > t0 ? (pt.s.updated_at - t0) / (t1 - t0) : i / (pts.length - 1));
  const y = (p) => T + (H - T - B) * (1 - p);
  const line = pts.map((pt, i) => `${x(pt, i).toFixed(1)},${y(pt.p).toFixed(1)}`).join(" ");
  const first = pts[0], last = pts[pts.length - 1];
  // Saves from one day are told apart by time.
  const oneDay = day(t0) === day(t1);
  const when = (t) => oneDay
    ? new Date(t * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : day(t);
  return `<figure class="timeline">
    <figcaption>Chance of ${G.esc(badName)} over time:
      <b>${Math.round(first.p * 100)}%</b> (${when(first.s.updated_at)}) →
      <b>${Math.round(last.p * 100)}%</b> (${when(last.s.updated_at)})</figcaption>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Chance of ${G.esc(badName)} for each save, oldest to newest">
      <line class="tl-axis" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/>
      <line class="tl-mid" x1="${L}" x2="${W - R}" y1="${y(0.5)}" y2="${y(0.5)}"/>
      <text class="tl-lab" x="${L - 6}" y="${y(1) + 4}" text-anchor="end">100%</text>
      <text class="tl-lab" x="${L - 6}" y="${y(0.5) + 4}" text-anchor="end">50%</text>
      <text class="tl-lab" x="${L - 6}" y="${y(0) + 4}" text-anchor="end">0%</text>
      <polyline class="tl-line" points="${line}"/>
      ${pts.map((pt, i) => `<circle class="tl-dot" cx="${x(pt, i).toFixed(1)}" cy="${y(pt.p).toFixed(1)}" r="5">
        <title>${G.esc(pt.s.name)} · ${when(pt.s.updated_at)} · ${Math.round(pt.p * 100)}%</title></circle>`).join("")}
      <text class="tl-lab" x="${L}" y="${H - 6}">${when(t0)}</text>
      <text class="tl-lab" x="${W - R}" y="${H - 6}" text-anchor="end">${when(t1)}</text>
    </svg></figure>`;
}

let allSaves = [];
let pending = null;              // { id, timer }: a delete that can still be undone

async function renderSaves() {
  if (!datasets.length) {
    try { datasets = (await (await fetch("/api/datasets")).json()).datasets; } catch (e) {}
  }
  try {
    allSaves = (await (await fetch("/api/saved", { credentials: "same-origin" })).json()).saved || [];
  } catch (e) { allSaves = []; }
  if (pending) allSaves = allSaves.filter((s) => s.id !== pending.id);
  const blocks = await Promise.all(datasets.map(async (d) => {
    const list = allSaves.filter((s) => s.dataset === d.key).sort((a, b) => b.updated_at - a.updated_at);
    const head = `<div class="ts-head">${G.icon(d.key)}<span class="acct-topic">${G.esc(G.topicName(d.key, d.label))}</span>
      <span class="sub">${list.length === 0 ? "no saves" : list.length === 1 ? "1 save" : list.length + " saves"}</span>
      <a href="/app.html?dataset=${encodeURIComponent(d.key)}&enter=1">${list.length ? "New" : "Start"}</a></div>`;
    if (!list.length) return `<section class="topic-saves">${head}</section>`;
    let out;
    try { out = await predictAll(d.key, list); } catch (e) {
      return `<section class="topic-saves">${head}<p class="warn">Couldn’t load these saves.</p></section>`;
    }
    return `<section class="topic-saves">${head}
      ${timeline(list, out.people, out.class_names[1])}
      <ul class="save-cards">${list.map((s, i) => saveCard(s, out.people[i], out.class_names)).join("")}</ul></section>`;
  }));
  el("acct-saves").innerHTML = blocks.join("");
}

// Rename in place, delete with undo.
el("acct-saves").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const card = btn.closest(".save-card"), id = Number(card.dataset.id);
  const save = allSaves.find((s) => s.id === id);
  if (!save) return;
  if (btn.dataset.act === "rename") {
    const name = card.querySelector(".sc-name");
    const form = document.createElement("form");
    form.className = "sc-rename";
    form.innerHTML = `<input maxlength="60" aria-label="New name"><button type="submit">Save</button>
      <button type="button" data-cancel>Cancel</button>`;
    form.querySelector("input").value = save.name;
    name.replaceWith(form);
    form.querySelector("input").select();
    form.querySelector("[data-cancel]").onclick = () => form.replaceWith(name);
    form.onsubmit = async (ev) => {
      ev.preventDefault();
      const { ok, body } = await post("/api/saved/rename", { id, name: form.querySelector("input").value });
      if (!ok) { toast(body.error || "Couldn’t rename."); return; }
      save.name = body.name;
      name.textContent = body.name;
      form.replaceWith(name);
    };
    return;
  }
  // Hide it now and delete after the Undo window, so Undo restores it exactly.
  finishDelete();
  pending = { id, timer: setTimeout(finishDelete, UNDO_MS) };
  await renderSaves();
  toast(`Deleted “${save.name}”.`, async () => {
    clearTimeout(pending.timer);
    pending = null;
    await renderSaves();
    toast(`Restored “${save.name}”.`);
  });
});

const UNDO_MS = 8000;
function finishDelete() {
  if (!pending) return;
  clearTimeout(pending.timer);
  fetch("/api/saved?id=" + pending.id, { method: "DELETE", credentials: "same-origin", keepalive: true });
  pending = null;
}
// Leaving the page during the Undo window still deletes.
window.addEventListener("pagehide", finishDelete);

let toastTimer = null;
function toast(text, undo) {
  const t = el("toast");
  t.innerHTML = G.esc(text) + (undo ? ` <button type="button">Undo</button>` : "");
  t.hidden = false;
  if (undo) t.querySelector("button").onclick = () => { t.hidden = true; undo(); };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, undo ? UNDO_MS : 3000);
}
