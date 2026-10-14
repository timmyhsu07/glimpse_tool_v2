// Shared by every page: theme, top navigation, topic names, "?" tips.
(function () {
  const THEME_KEY = "glimpse-theme";
  const $ = (id) => document.getElementById(id);

  const TOPICS = {
    pima: { name: "Diabetes", line: "Would a model flag diabetes?",
            icon: '<path d="M12 3c3.5 4.6 6 8 6 11a6 6 0 0 1-12 0c0-3 2.5-6.4 6-11z"/>' },
    heloc: { name: "Credit", line: "Would a lender call you a good risk?",
             icon: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M3 10h18M7 15h4"/>' },
    cancer: { name: "Breast cancer", line: "Would a model call a tumor malignant?",
              icon: '<path d="M12 3c-2 0-3.5 1.5-3.5 3.5 0 2 1.5 4 3.5 6.5 2-2.5 3.5-4.5 3.5-6.5C15.5 4.5 14 3 12 3z"/><path d="M10.5 11 6.5 21M13.5 11l4 10"/>' },
  };
  const topicName = (key, fallback) => (TOPICS[key] ? TOPICS[key].name : fallback || key);
  const icon = (key) =>
    `<svg class="topic-icon" viewBox="0 0 24 24" aria-hidden="true">${(TOPICS[key] || {}).icon || ""}</svg>`;

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // A "?" that shows a short explanation on hover, focus or tap.
  const tip = (text, align) =>
    `<button type="button" class="tip${align === "right" ? " tip-r" : ""}" ` +
    `aria-label="${esc(text)}" data-tip="${esc(text)}">?</button>`;

  const LOCK = '<svg class="lock" viewBox="0 0 24 24" aria-hidden="true">' +
    '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';

  const isDark = () => document.documentElement.getAttribute("data-theme") === "dark";

  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem(THEME_KEY, t); } catch (e) {}
    const btn = $("theme-toggle");
    if (btn) btn.textContent = t === "dark" ? "☀ Light" : "☾ Dark";
    document.dispatchEvent(new CustomEvent("glimpse-theme", { detail: t }));
  }

  // Signed-in state, fetched once per page.
  const me = fetch("/api/me", { credentials: "same-origin" })
    .then((r) => r.json()).then((b) => b.user || null).catch(() => null);

  function markNav() {
    const page = document.body.dataset.page;
    for (const a of document.querySelectorAll("#nav a")) {
      if (a.dataset.page === page) a.setAttribute("aria-current", "page");
    }
    const link = $("account-link");
    if (!link) return;
    me.then((user) => {
      if (user) {
        link.textContent = "My account";
        link.href = "/account.html";
      } else {
        link.textContent = "Sign in";
        link.href = "/login.html?next=" + encodeURIComponent(location.pathname + location.search);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(isDark() ? "dark" : "light");
    const btn = $("theme-toggle");
    if (btn) btn.addEventListener("click", () => applyTheme(isDark() ? "light" : "dark"));
    markNav();
  });

  window.GLIMPSE = { TOPICS, topicName, icon, tip, esc, LOCK, isDark, me };
})();
