const el = (id) => document.getElementById(id);
const THEME_KEY = "glimpse-theme";
const isDark = () => document.documentElement.getAttribute("data-theme") === "dark";

function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(THEME_KEY, t); } catch (e) {}
  el("theme-toggle").textContent = t === "dark" ? "☀ Light" : "☾ Dark";
}
applyTheme(isDark() ? "dark" : "light");
el("theme-toggle").addEventListener("click", () => applyTheme(isDark() ? "light" : "dark"));

//  Only same-site paths, so ?next= cannot send people to another site.
function nextPath() {
  const n = new URLSearchParams(location.search).get("next") || "/";
  return n.startsWith("/") && !n.startsWith("//") ? n : "/";
}

function showTab(which) {
  for (const name of ["login", "register"]) {
    const on = name === which;
    el("tab-" + name).setAttribute("aria-selected", String(on));
    el("form-" + name).hidden = !on;
  }
  el(which + "-email").focus();
}
el("tab-login").addEventListener("click", () => showTab("login"));
el("tab-register").addEventListener("click", () => showTab("register"));

function showSignedIn(user) {
  el("auth-forms").hidden = !!user;
  el("auth-signed-in").hidden = !user;
  if (user) el("signed-in-email").textContent = user.email;
}

async function post(url, data) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
    credentials: "same-origin",
  });
  let body = {};
  try { body = await resp.json(); } catch (e) {}
  return { ok: resp.ok, body };
}

function wireForm(form, url, check) {
  const msg = form.querySelector(".auth-msg");
  const button = form.querySelector(".auth-submit");
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    const problem = check(data);
    msg.textContent = problem || "";
    if (problem) return;
    button.disabled = true;
    try {
      const { ok, body } = await post(url, { email: data.email, password: data.password });
      if (ok) {
        location.href = nextPath();
        return;
      }
      msg.textContent = body.error || "Something went wrong. Please try again.";
    } catch (e) {
      msg.textContent = "Could not reach the server. Please try again.";
    } finally {
      button.disabled = false;
    }
  });
}

wireForm(el("form-login"), "/api/login", (d) =>
  !d.email.trim() || !d.password ? "Enter your email and password." : "");

wireForm(el("form-register"), "/api/register", (d) => {
  if (!d.email.trim()) return "Enter your email.";
  if (d.password.length < 8) return "Use a password of at least 8 characters.";
  if (d.password !== d.confirm) return "The two passwords don’t match.";
  return "";
});

el("sign-out").addEventListener("click", async () => {
  await post("/api/logout");
  showSignedIn(null);
  showTab("login");
});

async function init() {
  const qs = new URLSearchParams(location.search);
  el("auth-reason").hidden = qs.get("reason") !== "save";
  const mode = qs.get("mode");
  showTab(mode === "register" || location.hash === "#register" ? "register" : "login");
  try {
    const me = await (await fetch("/api/me", { credentials: "same-origin" })).json();
    showSignedIn(me.user);
  } catch (e) {}
}
init();
