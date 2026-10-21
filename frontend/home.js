// Home: pick a topic, then enter your numbers or try an example person.
const G = window.GLIMPSE;
const TOPIC_KEY = "glimpse-topic";

function choose(key) {
  for (const card of document.querySelectorAll(".topic-card")) {
    const on = card.dataset.key === key;
    card.setAttribute("aria-checked", String(on));
    card.tabIndex = on ? 0 : -1;
  }
  document.getElementById("go-enter").href = `/app.html?dataset=${key}&enter=1`;
  document.getElementById("go-example").href = `/app.html?dataset=${key}`;
  try { localStorage.setItem(TOPIC_KEY, key); } catch (e) {}
}

async function init() {
  let datasets = [];
  try {
    datasets = (await (await fetch("/api/datasets")).json()).datasets;
  } catch (e) {
    datasets = Object.keys(G.TOPICS).map((key) => ({ key, label: G.topicName(key) }));
  }
  const box = document.getElementById("topics");
  box.innerHTML = datasets.map((d) => {
    const t = G.TOPICS[d.key] || {};
    return `<button type="button" class="topic-card" role="radio" data-key="${G.esc(d.key)}"
      aria-checked="false">${G.icon(d.key)}
      <span class="topic-name">${G.esc(G.topicName(d.key, d.label))}</span>
      <span class="topic-line">${G.esc(t.line || d.label)}</span></button>`;
  }).join("");
  box.addEventListener("click", (e) => {
    const card = e.target.closest(".topic-card");
    if (card) choose(card.dataset.key);
  });
  box.addEventListener("keydown", (e) => {
    if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(e.key)) return;
    const cards = [...box.querySelectorAll(".topic-card")];
    const i = cards.findIndex((c) => c.getAttribute("aria-checked") === "true");
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1;
    const next = cards[(i + step + cards.length) % cards.length];
    choose(next.dataset.key);
    next.focus();
    e.preventDefault();
  });
  let saved = null;
  try { saved = localStorage.getItem(TOPIC_KEY); } catch (e) {}
  choose(datasets.some((d) => d.key === saved) ? saved : datasets[0].key);
}
document.getElementById("diff-tip").innerHTML = G.tip("Many different models fit the same " +
  "data about equally well. Researchers call this group the Rashomon set. Most counterfactual " +
  "tools explain just one model from it; GLIMPSE takes the whole set into account.");
init();
