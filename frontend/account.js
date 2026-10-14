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

  let datasets = [];
  try { datasets = (await (await fetch("/api/datasets")).json()).datasets; } catch (e) {}
  el("acct-saves").innerHTML = datasets.map((d) => {
    const n = user.saves[d.key] || 0;
    return `<li>${G.icon(d.key)}<span class="acct-topic">${G.esc(G.topicName(d.key, d.label))}</span>
      <span class="sub">${n === 0 ? "no saves" : n === 1 ? "1 save" : n + " saves"}</span>
      <a href="/app.html?dataset=${encodeURIComponent(d.key)}&enter=1">${n ? "Open" : "Start"}</a></li>`;
  }).join("");

  if (new URLSearchParams(location.search).get("reset") === "1")
    notice("New password saved. You’re signed in.");
  el("account").hidden = false;
}
init();
