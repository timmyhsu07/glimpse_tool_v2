// Sign in, create an account, forgot password, and set a new password.
const el = (id) => document.getElementById(id);
const FORMS = ["login", "register", "forgot", "reset"];

//  Only same-site paths, so ?next= cannot send people to another site.
function nextPath() {
  const n = new URLSearchParams(location.search).get("next") || "/app.html";
  return n.startsWith("/") && !n.startsWith("//") ? n : "/app.html";
}

function resetToken() {
  const m = location.hash.match(/^#reset=([\w-]+)$/);
  return m ? m[1] : null;
}

function showForm(which) {
  for (const name of FORMS) el("form-" + name).hidden = name !== which;
  const tabs = which === "login" || which === "register";
  document.querySelector(".auth-tabs").hidden = !tabs;
  for (const name of ["login", "register"])
    el("tab-" + name).setAttribute("aria-selected", String(name === which));
  const first = el("form-" + which).querySelector("input");
  if (first) first.focus();
}
el("tab-login").addEventListener("click", () => showForm("login"));
el("tab-register").addEventListener("click", () => showForm("register"));
el("go-forgot").addEventListener("click", () => {
  el("forgot-email").value = el("login-email").value;
  showForm("forgot");
});
for (const b of document.querySelectorAll("[data-back]"))
  b.addEventListener("click", () => showForm("login"));

for (const b of document.querySelectorAll(".pw-show")) {
  b.addEventListener("click", () => {
    const inp = el(b.getAttribute("aria-controls"));
    const show = inp.type === "password";
    inp.type = show ? "text" : "password";
    b.textContent = show ? "Hide" : "Show";
  });
}

// The shared testing account shown next to the form.
el("wip-fill").addEventListener("click", () => {
  showForm("login");
  el("login-email").value = "test@ex.com";
  el("login-password").value = "test123";
  el("form-login").querySelector(".auth-submit").focus();
});

function showSignedIn(user) {
  el("wip-account").hidden = !!user;
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

function wireForm(name, url, check, done, payload) {
  const form = el("form-" + name);
  const msg = form.querySelector(".auth-msg");
  const button = form.querySelector(".auth-submit");
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    const problem = check(data);
    msg.textContent = problem || "";
    msg.classList.remove("ok");
    if (problem) return;
    button.disabled = true;
    try {
      const { ok, body } = await post(url, payload ? payload(data) : data);
      if (ok) done(body, msg);
      else msg.textContent = body.error || "Something went wrong. Please try again.";
    } catch (e) {
      msg.textContent = "Could not reach the server. Please try again.";
    } finally {
      button.disabled = false;
    }
  });
}

const goNext = () => { location.href = nextPath(); };
const newPassword = (d) => {
  if (d.password.length < 8) return "Use at least 8 characters.";
  if (d.password !== d.confirm) return "The two passwords don’t match.";
  return "";
};

wireForm("login", "/api/login", (d) =>
  !d.email.trim() || !d.password ? "Enter your email and password." : "", goNext);

wireForm("register", "/api/register", (d) =>
  !d.email.trim() ? "Enter your email." : newPassword(d), goNext);

wireForm("forgot", "/api/forgot", (d) => (!d.email.trim() ? "Enter your email." : ""),
  (body, msg) => {
    msg.textContent = body.message;
    msg.classList.add("ok");
  });

wireForm("reset", "/api/reset", newPassword, () => {
  history.replaceState(null, "", location.pathname);
  location.href = "/account.html?reset=1";
}, (d) => ({ token: resetToken(), password: d.password }));

el("sign-out").addEventListener("click", async () => {
  await post("/api/logout");
  showSignedIn(null);
  showForm("login");
});

async function init() {
  const qs = new URLSearchParams(location.search);
  el("auth-reason").hidden = qs.get("reason") !== "save";
  if (resetToken()) {
    showForm("reset");
    return;
  }
  if (location.hash === "#forgot") {       // also for signed-in people who forgot it
    showForm("forgot");
    return;
  }
  const mode = qs.get("mode");
  showForm(mode === "register" || location.hash === "#register" ? "register" : "login");
  showSignedIn(await window.GLIMPSE.me);
}
init();

// A reset link opened on an already-open sign-in page only changes the hash.
window.addEventListener("hashchange", () => {
  if (resetToken()) {
    showSignedIn(null);
    showForm("reset");
  } else if (location.hash === "#forgot") {
    showSignedIn(null);
    showForm("forgot");
  }
});
