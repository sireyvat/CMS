/**
 * quiz.js — Telegram Mini App client for the secure daily quiz.
 *
 * SECURITY NOTE (read this before modifying):
 * This file is NOT the trust boundary. Every value here (the timer, the
 * "is this really the student" check) is advisory/UX only. The backend
 * independently re-verifies Telegram's initData on every single request
 * and independently enforces the 15-minute deadline using its own clock
 * (app/routers/quiz.py). Never add client-side-only logic that a modified
 * or replayed request could bypass — assume this JS is fully visible and
 * editable by the student.
 */
(function () {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    if (tg.disableVerticalSwipes) tg.disableVerticalSwipes(); // reduce accidental/careless swipe-to-close
    if (tg.enableClosingConfirmation) tg.enableClosingConfirmation();
  }
  const initData = tg?.initData || "";

  const screens = {
    loading: document.getElementById("loading"),
    denied: document.getElementById("denied"),
    quiz: document.getElementById("quiz"),
    finished: document.getElementById("finished"),
    locked: document.getElementById("locked"),
  };
  function show(name) {
    Object.values(screens).forEach((el) => el.classList.add("hidden"));
    screens[name].classList.remove("hidden");
  }

  const state = {
    sessionId: null,
    questions: [],
    index: 0,
    deadlineMs: null,
    clockOffsetMs: 0, // serverNow - clientNow, so we never trust the device clock alone
    answered: false,
    locked: false,
    timerInterval: null,
    currentAudio: null,
  };

  const API = ""; // same-origin

  async function api(path, body) {
    const res = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      keepalive: true, // important for the autosubmit beacon fired on tab-hide/unload
    });
    return { ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) };
  }

  // ---------------------------------------------------------------------
  // 1. Access control + quiz start
  // ---------------------------------------------------------------------
  async function startQuiz() {
    if (!initData) {
      showDenied("This quiz must be opened from inside Telegram.");
      return;
    }
    const { ok, status, data } = await api("/api/quiz/access", { init_data: initData });
    if (!ok) {
      showDenied(data.detail || "Access denied.");
      return;
    }
    if (data.status && data.status !== "in_progress") {
      finishScreen(data.status, data.score ?? 0);
      return;
    }

    state.sessionId = data.session_id;
    state.questions = data.questions;
    state.deadlineMs = Date.parse(data.deadline_at);
    state.clockOffsetMs = Date.parse(data.server_time) - Date.now();

    show("quiz");
    startTimer();
    renderQuestion();
    attachAntiCheatListeners();
  }

  function showDenied(message) {
    document.getElementById("denied-message").textContent = message;
    show("denied");
  }

  function finishScreen(status, score) {
    const titleEl = document.getElementById("finished-title");
    const scoreEl = document.getElementById("finished-score");
    if (status === "auto_submitted") {
      titleEl.textContent = "🔒 Locked — Cheating Detected";
    } else if (status === "expired") {
      titleEl.textContent = "⏰ Time's Up";
    } else {
      titleEl.textContent = "✅ Quiz Complete!";
    }
    scoreEl.textContent = `Score: ${score}`;
    show("finished");
    stopTimer();
  }

  // ---------------------------------------------------------------------
  // 2. Server-synced countdown (never trust the local clock alone)
  // ---------------------------------------------------------------------
  function correctedNow() {
    return Date.now() + state.clockOffsetMs;
  }

  function startTimer() {
    const timerEl = document.getElementById("timer");
    state.timerInterval = setInterval(() => {
      const remainingMs = state.deadlineMs - correctedNow();
      if (remainingMs <= 0) {
        clearInterval(state.timerInterval);
        timerEl.textContent = "00:00";
        onTimeExpired();
        return;
      }
      const totalSeconds = Math.floor(remainingMs / 1000);
      const m = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
      const s = String(totalSeconds % 60).padStart(2, "0");
      timerEl.textContent = `${m}:${s}`;
      timerEl.classList.toggle("warning", totalSeconds <= 60);
    }, 250);
  }
  function stopTimer() {
    if (state.timerInterval) clearInterval(state.timerInterval);
  }

  async function onTimeExpired() {
    const { data } = await api("/api/quiz/submit", { init_data: initData, session_id: state.sessionId });
    finishScreen("expired", data.score ?? 0);
  }

  // ---------------------------------------------------------------------
  // 3. Question rendering
  // ---------------------------------------------------------------------
  function renderQuestion() {
    const q = state.questions[state.index];
    document.getElementById("progress").textContent = `Question ${state.index + 1}/${state.questions.length}`;
    document.getElementById("feedback").classList.add("hidden");
    document.getElementById("next-btn").classList.add("hidden");
    state.answered = false;

    const card = document.getElementById("question-card");
    card.innerHTML = "";

    const badge = document.createElement("div");
    badge.className = "section-badge";
    badge.textContent = q.section;
    card.appendChild(badge);

    const qText = document.createElement("div");
    qText.className = "q-text";
    qText.textContent = q.question_text;
    card.appendChild(qText);

    if (q.section === "mcq" && q.options) {
      const wrap = document.createElement("div");
      wrap.className = "options";
      q.options.forEach((opt) => {
        const btn = document.createElement("button");
        btn.className = "option-btn";
        btn.textContent = opt;
        btn.onclick = () => selectOption(btn, opt);
        wrap.appendChild(btn);
      });
      card.appendChild(wrap);
    } else if (q.section === "listening") {
      const row = document.createElement("div");
      row.className = "audio-row";
      const playBtn = document.createElement("button");
      playBtn.className = "play-btn";
      playBtn.textContent = "▶";
      playBtn.onclick = () => playAudio(q.id);
      row.appendChild(playBtn);
      card.appendChild(row);
      appendTextInput(card, q);
    } else {
      appendTextInput(card, q);
    }
  }

  function appendTextInput(card, q) {
    const input = document.createElement("input");
    input.type = "text";
    input.className = "answer-input";
    input.placeholder = "Type your answer…";
    input.autocomplete = "off";
    input.autocapitalize = "off";
    input.spellcheck = false;
    input.onkeydown = (e) => {
      if (e.key === "Enter" && input.value.trim()) submitAnswer(q.id, input.value.trim());
    };
    card.appendChild(input);

    const submitBtn = document.createElement("button");
    submitBtn.className = "btn-primary";
    submitBtn.style.marginTop = "12px";
    submitBtn.textContent = "Submit Answer";
    submitBtn.onclick = () => {
      if (input.value.trim()) submitAnswer(q.id, input.value.trim());
    };
    card.appendChild(submitBtn);
  }

  function selectOption(btn, value) {
    document.querySelectorAll(".option-btn").forEach((b) => b.classList.remove("selected"));
    btn.classList.add("selected");
    submitAnswer(state.questions[state.index].id, value);
  }

  async function playAudio(questionId) {
    if (state.currentAudio) state.currentAudio.pause();
    const audio = new Audio(`/api/quiz/audio/${questionId}`);
    state.currentAudio = audio;
    audio.play().catch(() => {});
  }

  async function submitAnswer(questionId, answer) {
    if (state.answered || state.locked) return;
    state.answered = true;
    const { ok, data } = await api("/api/quiz/answer", {
      init_data: initData, session_id: state.sessionId, question_id: questionId, answer,
    });
    if (!ok) return; // session expired/invalid mid-question — deadline handler will take over

    const fb = document.getElementById("feedback");
    fb.textContent = data.is_correct ? `✅ Correct! +${data.points} pts` : "❌ Not quite.";
    fb.className = `feedback ${data.is_correct ? "correct" : "incorrect"}`;
    fb.classList.remove("hidden");

    const nextBtn = document.getElementById("next-btn");
    nextBtn.classList.remove("hidden");
    nextBtn.onclick = () => {
      state.index += 1;
      if (state.index >= state.questions.length) {
        finalSubmit();
      } else {
        renderQuestion();
      }
    };
  }

  async function finalSubmit() {
    const { data } = await api("/api/quiz/submit", { init_data: initData, session_id: state.sessionId });
    finishScreen("submitted", data.score ?? 0);
  }

  // ---------------------------------------------------------------------
  // 4. Anti-cheating: focus-loss / visibility detection -> instant lockout
  // ---------------------------------------------------------------------
  let autoSubmitSent = false;
  async function triggerLockout(reason) {
    if (autoSubmitSent || state.locked || !state.sessionId) return;
    autoSubmitSent = true;
    state.locked = true;
    stopTimer();
    // fetch keepalive=true so this still fires even as the tab is being hidden/unloaded
    await api("/api/quiz/autosubmit", { init_data: initData, session_id: state.sessionId, reason });
    show("locked");
  }

  function attachAntiCheatListeners() {
    // Fires on tab switch, app minimize, screen lock, switching to another Telegram chat, etc.
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") triggerLockout("visibility_hidden");
    });
    // Fires when the WebView loses OS-level focus (covers cases visibilitychange misses on some platforms)
    window.addEventListener("blur", () => triggerLockout("window_blur"));
    window.addEventListener("pagehide", () => triggerLockout("page_hide"));

    // Best-effort deterrents only (see quiz.css header comment — cannot truly block
    // screenshots/recording; no web platform exposes that capability to JS).
    document.addEventListener("contextmenu", (e) => e.preventDefault());
    document.addEventListener("copy", (e) => e.preventDefault());
    document.addEventListener("keydown", (e) => {
      // Attempt to discourage the obvious desktop-browser devtools/print-screen shortcuts.
      // Purely cosmetic on mobile Telegram clients, where this JS doesn't run in a normal browser chrome.
      const blockedCombos =
        e.key === "PrintScreen" ||
        (e.ctrlKey && e.shiftKey && ["I", "J", "C"].includes(e.key)) ||
        e.key === "F12";
      if (blockedCombos) e.preventDefault();
    });
  }

  startQuiz();
})();
