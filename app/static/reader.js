import { buildBlockSegments } from "./reader_render.mjs";

const form = document.querySelector("#upload-form");
const status = document.querySelector("#status");
const clearSessionButton = document.querySelector("#clear-session");
const matchingPanel = document.querySelector("#matching-panel");
const matchingForm = document.querySelector("#matching-form");
const matchingList = document.querySelector("#matching-list");
const progressPanel = document.querySelector("#progress-panel");
const chapterStatuses = document.querySelector("#chapter-statuses");
const readerPanel = document.querySelector("#reader-panel");
const chapterNav = document.querySelector("#chapter-nav");
const chapterTitle = document.querySelector("#chapter-title");
const audio = document.querySelector("#audio");
const reader = document.querySelector("#reader");

const state = {
  activeIndex: null,
  currentChapterIndex: null,
  pollTimer: null,
  sessionId: null,
  session: null,
  words: [],
};

const searchParams = new URLSearchParams(window.location.search);
const initialSessionId = searchParams.get("session_id");

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = new FormData(form);
  status.textContent = "Uploading files...";
  const response = await fetch("/chapter-sessions", { method: "POST", body });
  const payload = await response.json();
  window.history.replaceState(null, "", `/?session_id=${payload.session_id}`);
  await loadSession(payload.session_id);
});

if (initialSessionId) {
  status.textContent = "Loading existing session...";
  loadSession(initialSessionId);
}

clearSessionButton?.addEventListener("click", () => {
  resetSessionState();
});

audio?.addEventListener("timeupdate", () => {
  const activeIndex = findWordForTime(state.words, Math.round(audio.currentTime * 1000));
  setActiveWord(activeIndex);
});

reader?.addEventListener("click", (event) => {
  const target = event.target.closest("[data-start-ms]");
  if (!target) {
    return;
  }
  audio.currentTime = Number(target.dataset.startMs) / 1000;
  audio.play();
  setActiveWord(Number(target.dataset.wordIndex));
});

matchingForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.sessionId || !state.session) {
    return;
  }
  const matches = state.session.ebook_chapters.map((chapter) => ({
    ebook_chapter_index: chapter.index,
    audio_chapter_index: readAudioChapterSelection(chapter.index),
  }));
  status.textContent = "Saving chapter mapping...";
  const response = await fetch(`/chapter-sessions/${state.sessionId}/mapping`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matches }),
  });
  const payload = await response.json();
  if (!response.ok) {
    status.textContent = payload.detail;
    return;
  }
  await loadSession(payload.session_id);
});

async function loadSession(sessionId) {
  state.sessionId = sessionId;
  const response = await fetch(`/chapter-sessions/${sessionId}`);
  const payload = await response.json();
  if (state.sessionId !== sessionId) {
    return;
  }
  if (!response.ok) {
    resetSessionState(payload.detail ?? "Session not found.");
    return;
  }
  state.session = payload;
  renderSession(payload);
  schedulePoll(payload);
}

function schedulePoll(payload) {
  if (state.pollTimer !== null) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
  if (payload.status === "processing") {
    state.pollTimer = window.setTimeout(() => loadSession(state.sessionId), 700);
  }
}

function resetSessionState(statusText = "Waiting for upload.") {
  if (state.pollTimer !== null) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
  state.activeIndex = null;
  state.currentChapterIndex = null;
  state.sessionId = null;
  state.session = null;
  state.words = [];
  form?.reset();
  matchingList.innerHTML = "";
  chapterStatuses.innerHTML = "";
  chapterNav.innerHTML = "";
  chapterTitle.textContent = "";
  reader.innerHTML = "";
  matchingPanel.hidden = true;
  progressPanel.hidden = true;
  readerPanel.hidden = true;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  status.textContent = statusText;
  window.history.replaceState(null, "", "/");
}

function renderSession(payload) {
  renderMatchingPanel(payload);
  renderProgressPanel(payload);
  renderReaderPanel(payload);
  if (payload.status === "matching") {
    status.textContent = "Match each ebook chapter to one audio chapter, or skip chapters with no matching audio.";
    return;
  }
  if (payload.status === "processing") {
    const readableCount = payload.chapter_statuses.filter((chapter) =>
      ["ready", "transcript-only"].includes(chapter.status)
    ).length;
    status.textContent = `Processing chapters... ${readableCount}/${payload.chapter_statuses.length} readable.`;
    return;
  }
  if (payload.status === "failed-partial") {
    status.textContent = "Some chapters failed, but completed chapters are still readable.";
    return;
  }
  if (payload.status === "failed") {
    status.textContent = "Chapter processing failed.";
    return;
  }
  status.textContent = `Ready. ${payload.completed_chapters?.length ?? 0} chapters available.`;
}

function renderMatchingPanel(payload) {
  const isMatching = payload.status === "matching";
  matchingPanel.hidden = !isMatching;
  if (!isMatching) {
    return;
  }
  matchingList.innerHTML = "";
  for (const ebookChapter of payload.ebook_chapters) {
    const row = document.createElement("div");
    row.className = "chapter-row";
    const label = document.createElement("label");
    label.textContent = ebookChapter.title;
    const select = document.createElement("select");
    select.dataset.ebookIndex = String(ebookChapter.index);
    const skipOption = document.createElement("option");
    skipOption.value = "";
    skipOption.textContent = "Skip";
    if (ebookChapter.suggested_audio_chapter_index === null) {
      skipOption.selected = true;
    }
    select.append(skipOption);
    for (const audioChapter of payload.audio_chapters) {
      const option = document.createElement("option");
      option.value = String(audioChapter.index);
      option.textContent = audioChapter.title;
      if (audioChapter.index === ebookChapter.suggested_audio_chapter_index) {
        option.selected = true;
      }
      select.append(option);
    }
    row.append(label, select);
    matchingList.append(row);
  }
}

function readAudioChapterSelection(ebookChapterIndex) {
  const value = matchingForm.querySelector(`[data-ebook-index="${ebookChapterIndex}"]`)?.value ?? "";
  if (value === "") {
    return null;
  }
  return Number(value);
}

function renderProgressPanel(payload) {
  const chapterStateList = payload.chapter_statuses ?? [];
  progressPanel.hidden = chapterStateList.length === 0;
  chapterStatuses.innerHTML = "";
  for (const chapterStatus of chapterStateList) {
    const row = document.createElement("div");
    row.className = "chapter-row";
    row.textContent = `${chapterStatus.title}: ${chapterStatus.status}`;
    if (chapterStatus.reason) {
      const reason = document.createElement("div");
      reason.className = "muted";
      reason.textContent = chapterStatus.reason;
      row.append(reason);
    }
    chapterStatuses.append(row);
  }
}

function renderReaderPanel(payload) {
  const completedChapters = payload.completed_chapters ?? [];
  readerPanel.hidden = completedChapters.length === 0;
  chapterNav.innerHTML = "";
  if (completedChapters.length === 0) {
    state.words = [];
    reader.innerHTML = "";
    chapterTitle.textContent = "";
    return;
  }
  const currentChapter =
    completedChapters.find((chapter) => chapter.chapter_index === state.currentChapterIndex) ??
    completedChapters[0];
  state.currentChapterIndex = currentChapter.chapter_index;
  for (const chapter of completedChapters) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = chapter.title;
    if (chapter.chapter_index === state.currentChapterIndex) {
      button.classList.add("active");
    }
    button.addEventListener("click", () => {
      state.currentChapterIndex = chapter.chapter_index;
      renderReaderPanel(payload);
    });
    chapterNav.append(button);
  }
  renderChapter(currentChapter);
}

function renderChapter(chapter) {
  state.words = chapter.words;
  state.activeIndex = null;
  if (!audio.src.endsWith(chapter.audio_url)) {
    audio.src = chapter.audio_url;
  }
  chapterTitle.textContent =
    chapter.text_source === "transcript"
      ? `${chapter.title} • Transcript mode`
      : `${chapter.title} • Alignment coverage ${(chapter.coverage * 100).toFixed(0)}%`;
  reader.innerHTML = "";
  const wordsByIndex = new Map(chapter.words.map((word) => [word.index, word]));
  for (const block of chapter.blocks) {
    const paragraph = document.createElement("p");
    for (const segment of buildBlockSegments(block, wordsByIndex)) {
      if (segment.type === "text") {
        paragraph.append(document.createTextNode(segment.text));
        continue;
      }
      const span = document.createElement("span");
      span.className = "word";
      span.dataset.wordIndex = String(segment.wordIndex);
      if (segment.startMs !== null) {
        span.dataset.startMs = String(segment.startMs);
      }
      span.textContent = segment.text;
      paragraph.append(span);
    }
    reader.append(paragraph);
  }
}

function findWordForTime(words, currentMs) {
  let bestIndex = null;
  for (const word of words) {
    if (word.start_ms === null || word.end_ms === null) {
      continue;
    }
    if (currentMs >= word.start_ms && currentMs <= word.end_ms) {
      bestIndex = word.index;
    }
  }
  return bestIndex;
}

function setActiveWord(index) {
  if (index === null || index === state.activeIndex) {
    return;
  }
  const previous = reader.querySelector(".word.active");
  previous?.classList.remove("active");
  const next = reader.querySelector(`[data-word-index="${index}"]`);
  next?.classList.add("active");
  next?.scrollIntoView({ block: "center", behavior: "smooth" });
  state.activeIndex = index;
}
