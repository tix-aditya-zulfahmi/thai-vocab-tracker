const DIR_LABELS = { th2id: "ไทย → Arti", id2th: "Arti → ไทย", mixed: "Campur" };
const PROMPT_TAG = { th2id: "Apa artinya?", id2th: "Apa bahasa Thai-nya?" };
const RING_CIRC = 2 * Math.PI * 52; // matches r=52 in the SVG

const state = {
  direction: "th2id",
  card: null,
  answered: false,
  shownAt: 0,
  session: { total: 0, correct: 0, wrong: 0, streak: 0, best: 0, missed: [] },
};

const $ = (id) => document.getElementById(id);

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

function renderStatsSession() {
  $("statCorrect").textContent = state.session.correct;
  $("statWrong").textContent = state.session.wrong;
  $("statStreak").textContent = state.session.streak;
}

async function refreshProgress() {
  try {
    const { progress, due } = await api("/api/progress");
    if (state.direction === "mixed") {
      $("statDue").textContent = (due.th2id || 0) + (due.id2th || 0);
      $("statMastered").textContent =
        (progress.th2id?.mastered || 0) + (progress.id2th?.mastered || 0);
    } else {
      $("statDue").textContent = due[state.direction] ?? "–";
      $("statMastered").textContent = progress[state.direction]?.mastered ?? "–";
    }
  } catch (e) { /* non-fatal */ }
}

function renderPips(box) {
  const wrap = $("pips");
  wrap.innerHTML = "";
  for (let i = 1; i <= 5; i++) {
    const pip = document.createElement("span");
    pip.className = "pip" + (i <= box ? " on" : "") + (box >= 5 && i <= box ? " mastered" : "");
    wrap.appendChild(pip);
  }
}

async function loadCard() {
  $("afterthought").hidden = true;
  $("cardActions").hidden = true;
  $("options").innerHTML = "";
  $("prompt").textContent = "…";
  state.answered = false;

  const card = await api(`/api/next?direction=${state.direction}`);
  if (card.done) {
    $("card").hidden = true;
    $("done").hidden = false;
    return;
  }
  $("card").hidden = false;
  $("done").hidden = true;
  state.card = card;

  const isThaiPrompt = card.direction === "th2id";
  $("dirPill").textContent = DIR_LABELS[card.direction];
  $("promptTag").textContent = PROMPT_TAG[card.direction];
  renderPips(card.box);

  const promptEl = $("prompt");
  promptEl.textContent = card.prompt;
  promptEl.classList.toggle("is-thai", isThaiPrompt);

  const optWrap = $("options");
  card.options.forEach((opt, i) => {
    const btn = document.createElement("button");
    btn.className = "opt" + (isThaiPrompt ? "" : " is-thai"); // options are Thai when prompt is ID
    btn.style.animationDelay = `${i * 45}ms`;
    btn.innerHTML = `<span class="badge">${i + 1}</span>`;
    btn.appendChild(document.createTextNode(opt.text));
    btn.dataset.vocabId = opt.vocab_id;
    btn.addEventListener("click", () => choose(opt.vocab_id, btn));
    optWrap.appendChild(btn);
  });

  // replay deal animation
  const cardEl = $("card");
  cardEl.classList.remove("dealt");
  void cardEl.offsetWidth;
  cardEl.classList.add("dealt");

  state.shownAt = performance.now();
}

function renderReveal(r) {
  let html = `<div class="r-head"><span class="r-thai">${r.thai}</span>`;
  if (r.romanization) html += `<span class="r-roman">${r.romanization}</span>`;
  if (r.tone) html += `<span class="r-tone">${r.tone}</span>`;
  html += `</div><div class="r-meaning">${r.meaning || ""}</div>`;
  if (r.notes) html += `<span class="r-note">${r.notes}</span>`;
  $("reveal").innerHTML = html;
}

function renderExample(ex) {
  const el = $("example");
  if (!ex) { el.hidden = true; return; }
  let html = `<div class="ex-label">Contoh kalimat</div>`;
  html += `<div class="ex-thai">${ex.thai}</div>`;
  if (ex.romanization) html += `<div class="ex-roman">${ex.romanization}</div>`;
  if (ex.meaning) html += `<div class="ex-meaning">${ex.meaning}</div>`;
  if (Array.isArray(ex.breakdown) && ex.breakdown.length) {
    html += `<div class="breakdown">`;
    ex.breakdown.forEach((w) => {
      html += `<div class="bd-row"><span class="bd-thai">${w.thai || ""}</span>` +
              `<span class="bd-roman">${w.roman || ""}</span>` +
              `<span class="bd-arti">${w.arti || ""}</span></div>`;
    });
    html += `</div>`;
  }
  el.innerHTML = html;
  el.hidden = false;
}

async function choose(chosenId, btn) {
  if (state.answered) return;
  state.answered = true;
  const responseMs = Math.round(performance.now() - state.shownAt);

  const result = await api("/api/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      vocab_id: state.card.vocab_id,
      direction: state.card.direction,
      chosen_vocab_id: chosenId,
      response_ms: responseMs,
    }),
  });

  document.querySelectorAll(".opt").forEach((b) => {
    b.disabled = true;
    const vid = Number(b.dataset.vocabId);
    if (vid === result.correct_vocab_id) b.classList.add("correct");
    else if (b === btn) b.classList.add("wrong");
    else b.classList.add("dim");
  });

  const s = state.session;
  s.total++;
  if (result.is_correct) { s.correct++; s.streak++; s.best = Math.max(s.best, s.streak); }
  else {
    s.wrong++; s.streak = 0;
    s.missed.push({ thai: result.reveal.thai, roman: result.reveal.romanization, arti: result.reveal.meaning });
  }
  renderStatsSession();
  renderPips(result.state.box);

  renderReveal(result.reveal);
  renderExample(result.example);
  $("afterthought").hidden = false;

  $("cardActions").hidden = false;
  $("nextBtn").focus();
  refreshProgress();
}

function setDirection(dir) {
  state.direction = dir;
  document.querySelectorAll("#dirToggle button").forEach((b) =>
    b.classList.toggle("active", b.dataset.dir === dir)
  );
  refreshProgress();
  loadCard();
}

function endSession() {
  const s = state.session;
  const acc = s.total ? Math.round((s.correct / s.total) * 100) : 0;
  $("sumTotal").textContent = s.total;
  $("sumCorrect").textContent = s.correct;
  $("sumWrong").textContent = s.wrong;
  $("sumBest").textContent = s.best;
  $("sumAcc").textContent = acc + "%";

  const miss = $("summaryMiss");
  if (s.missed.length) {
    let html = `<h3>Perlu diulang (${s.missed.length})</h3><ul>`;
    s.missed.forEach((m) => {
      html += `<li><span class="m-thai">${m.thai}</span> ` +
              `<span class="m-roman">${m.roman || ""}</span> — ` +
              `<span class="m-arti">${m.arti || ""}</span></li>`;
    });
    html += `</ul>`;
    miss.innerHTML = html;
  } else {
    miss.innerHTML = s.total ? `<div class="clean">Tidak ada yang meleset. Mantap!</div>` : "";
  }

  $("summary").hidden = false;
  // animate ring after paint
  const ring = $("ringFg");
  ring.style.strokeDashoffset = RING_CIRC;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    ring.style.strokeDashoffset = RING_CIRC * (1 - acc / 100);
  }));
}

function closeSummary() { $("summary").hidden = true; }

function restartSession() {
  state.session = { total: 0, correct: 0, wrong: 0, streak: 0, best: 0, missed: [] };
  renderStatsSession();
  $("summary").hidden = true;
  refreshProgress();
  loadCard();
}

// Thai font mode (easy = looped/beginner, hard = loopless display). Persisted.
function applyFontMode(mode) {
  document.body.classList.toggle("font-hard", mode === "hard");
  document.querySelectorAll("#fontToggle button").forEach((b) =>
    b.classList.toggle("active", b.dataset.font === mode)
  );
}
function setFontMode(mode) {
  try { localStorage.setItem("thaiFontMode", mode); } catch (e) {}
  applyFontMode(mode);
}
function initFontMode() {
  let mode = "easy";
  try { mode = localStorage.getItem("thaiFontMode") || "easy"; } catch (e) {}
  applyFontMode(mode);
}

// Controls
document.querySelectorAll("#dirToggle button").forEach((b) =>
  b.addEventListener("click", () => setDirection(b.dataset.dir))
);
document.querySelectorAll("#fontToggle button").forEach((b) =>
  b.addEventListener("click", () => setFontMode(b.dataset.font))
);
$("nextBtn").addEventListener("click", loadCard);
$("endBtn").addEventListener("click", endSession);
$("restartBtn").addEventListener("click", restartSession);
$("summaryClose").addEventListener("click", closeSummary);

document.addEventListener("keydown", (e) => {
  if (!$("summary").hidden) { if (e.key === "Escape") closeSummary(); return; }
  if (!state.answered && /^[1-4]$/.test(e.key)) {
    const btn = document.querySelectorAll(".opt")[Number(e.key) - 1];
    if (btn) btn.click();
  } else if (state.answered && (e.key === "Enter" || e.key === " ")) {
    e.preventDefault();
    loadCard();
  }
});

// Boot
initFontMode();
refreshProgress();
loadCard();
