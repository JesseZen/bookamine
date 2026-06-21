import { buildBlockSegments } from "./reader_render.mjs";

const ebookFileInput = document.querySelector("#ebook-file");
const audioFileInput = document.querySelector("#audio-files");
const uploadEbookSection = document.querySelector("#upload-ebook-section");
const uploadAudioSection = document.querySelector("#upload-audio-section");
const ebookResult = document.querySelector("#ebook-result");
const audioResult = document.querySelector("#audio-result");
const audioProgress = document.querySelector("#audio-progress");
const status = document.querySelector("#status");
const clearSessionButton = document.querySelector("#clear-session");
const chapterGridPanel = document.querySelector("#chapter-grid-panel");
const chapterGrid = document.querySelector("#chapter-grid");
const processAllBtn = document.querySelector("#process-all-btn");
const batchStatus = document.querySelector("#batch-status");
const multicoreCheckbox = document.querySelector("#use-multicore");
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

ebookFileInput?.addEventListener("change", async () => {
  const file = ebookFileInput.files[0];
  if (!file) {
    return;
  }
  ebookResult.textContent = "Parsing ebook...";
  const body = new FormData();
  body.append("ebook", file);
  const response = await fetch("/sessions/ebook", { method: "POST", body });
  const payload = await response.json();
  if (!response.ok) {
    ebookResult.textContent = payload.detail;
    return;
  }
  state.sessionId = payload.session_id;
  window.history.replaceState(null, "", `/?session_id=${payload.session_id}`);
  uploadEbookSection.classList.add("done");
  ebookResult.textContent = `✓ Detected ${payload.ebook_chapters.length} ebook chapters`;
  uploadAudioSection.hidden = false;
  audioFileInput.focus();
});

audioFileInput?.addEventListener("change", () => {
  const files = audioFileInput.files;
  if (!files || files.length === 0 || !state.sessionId) {
    return;
  }
  if (files.length === 1) {
    uploadViaWebSocket(files[0]);
  } else {
    uploadViaHttp(files);
  }
});

function uploadViaWebSocket(file) {
  audioFileInput.disabled = true;
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${location.host}/ws/sessions/${state.sessionId}/audio-upload`;
  const ws = new WebSocket(wsUrl);
  ws.onopen = async () => {
    ws.send(JSON.stringify({ filename: file.name }));
    const chunkSize = 256 * 1024;
    let offset = 0;
    while (offset < file.size) {
      const end = Math.min(offset + chunkSize, file.size);
      const buffer = await file.slice(offset, end).arrayBuffer();
      ws.send(buffer);
      offset = end;
    }
    ws.send(new TextEncoder().encode("__EOF__"));
  };
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "progress") {
      audioProgress.hidden = false;
      audioProgress.value = msg.received;
      audioProgress.max = file.size;
      const pct = Math.round((msg.received / file.size) * 100);
      if (pct >= 100) {
        audioResult.textContent = "File received, finalizing on server...";
      } else {
        audioResult.textContent = `Uploading... ${pct}%`;
      }
    } else if (msg.type === "chapters_early") {
      audioResult.textContent = `✓ Detected ${msg.chapters.length} audio chapters early! (upload continues...)`;
    } else if (msg.type === "done") {
      audioProgress.hidden = true;
      uploadAudioSection.classList.add("done");
      audioResult.textContent = `✓ Detected ${msg.payload.audio_chapters.length} audio chapters`;
      audioFileInput.disabled = false;
      loadSessionFromPayload(msg.payload);
    } else if (msg.type === "error") {
      audioFileInput.disabled = false;
      audioResult.textContent = msg.detail;
    }
  };
  ws.onerror = () => {
    audioResult.textContent = "WebSocket unavailable, trying HTTP upload...";
    audioFileInput.disabled = false;
    uploadViaHttp(audioFileInput.files);
  };
  audioResult.textContent = "Connecting for streaming upload...";
  audioProgress.hidden = false;
  audioProgress.value = 0;
}

function uploadViaHttp(files) {
  const body = new FormData();
  for (const file of files) {
    body.append("audio_files", file);
  }
  audioFileInput.disabled = true;
  const xhr = new XMLHttpRequest();
  xhr.open("POST", `/sessions/${state.sessionId}/audio`);
  xhr.upload.addEventListener("progress", (event) => {
    if (event.lengthComputable) {
      audioProgress.hidden = false;
      audioProgress.value = event.loaded;
      audioProgress.max = event.total;
      const pct = Math.round((event.loaded / event.total) * 100);
      if (pct >= 100) {
        audioResult.textContent = "Upload received, detecting chapters on server...";
      } else {
        audioResult.textContent = `Uploading... ${pct}%`;
      }
    }
  });
  xhr.addEventListener("load", () => {
    audioFileInput.disabled = false;
    if (xhr.status >= 200 && xhr.status < 300) {
      const payload = JSON.parse(xhr.responseText);
      audioProgress.hidden = true;
      uploadAudioSection.classList.add("done");
      audioResult.textContent = `✓ Detected ${payload.audio_chapters.length} audio chapters`;
      loadSessionFromPayload(payload);
    } else {
      let detail = "Upload failed.";
      try {
        detail = JSON.parse(xhr.responseText).detail || detail;
      } catch (_) { /* ignore */ }
      audioResult.textContent = detail;
    }
  });
  xhr.addEventListener("error", () => {
    audioFileInput.disabled = false;
    audioResult.textContent = "Upload failed.";
  });
  audioResult.textContent = "Uploading audiobook...";
  audioProgress.hidden = false;
  audioProgress.value = 0;
  xhr.send(body);
}

if (initialSessionId) {
  status.textContent = "Loading existing session...";
  loadSession(initialSessionId);
}

clearSessionButton?.addEventListener("click", () => {
  resetSessionState("Select an ebook file to begin.");
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

processAllBtn?.addEventListener("click", async () => {
  if (!state.sessionId) {
    return;
  }
  processAllBtn.disabled = true;
  const multicore = multicoreCheckbox?.checked ?? false;
  batchStatus.textContent = "Initializing...";
  const initResp = await fetch(`/sessions/${state.sessionId}/init-process`, { method: "POST" });
  const initPayload = await initResp.json();
  if (!initResp.ok) {
    batchStatus.textContent = initPayload.detail;
    processAllBtn.disabled = false;
    return;
  }
  const pending = initPayload.chapter_statuses.filter((s) => s.status === "pending");
  if (pending.length === 0) {
    batchStatus.textContent = "No chapters to process.";
    processAllBtn.disabled = false;
    return;
  }
  if (multicore) {
    for (const s of pending) {
      fetch(`/sessions/${state.sessionId}/process-chapter`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ebook_chapter_index: s.ebook_chapter_index,
          audio_chapter_index: s.audio_chapter_index,
        }),
      });
    }
  } else {
    processRemainingSequential(initPayload);
  }
  await loadSession(state.sessionId);
});

async function processRemainingSequential(initPayload) {
  const pending = initPayload.chapter_statuses.filter((s) => s.status === "pending");
  for (const s of pending) {
    batchStatus.textContent = `Processing ${s.title}...`;
    await fetch(`/sessions/${state.sessionId}/process-chapter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ebook_chapter_index: s.ebook_chapter_index,
        audio_chapter_index: s.audio_chapter_index,
      }),
    });
    await loadSession(state.sessionId);
  }
  batchStatus.textContent = "All chapters processed.";
  processAllBtn.disabled = false;
}

chapterGrid?.addEventListener("click", async (event) => {
  const processBtn = event.target.closest("[data-action='process-chapter']");
  if (!processBtn || !state.sessionId) {
    return;
  }
  processBtn.disabled = true;
  const ebookIdx = Number(processBtn.dataset.ebookIndex);
  const select = chapterGrid.querySelector(`[data-ebook-index="${ebookIdx}"]`);
  const audioIdx = select ? Number(select.value) : null;
  if (audioIdx === null || isNaN(audioIdx)) {
    processBtn.disabled = false;
    return;
  }
  await fetch(`/sessions/${state.sessionId}/process-chapter`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ebook_chapter_index: ebookIdx,
      audio_chapter_index: audioIdx,
    }),
  });
  await loadSession(state.sessionId);
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
  loadSessionFromPayload(payload);
}

function loadSessionFromPayload(payload) {
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

function resetSessionState(statusText = "Select an ebook file to begin.") {
  if (state.pollTimer !== null) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
  state.activeIndex = null;
  state.currentChapterIndex = null;
  state.sessionId = null;
  state.session = null;
  state.words = [];
  ebookFileInput.value = "";
  audioFileInput.value = "";
  audioFileInput.disabled = false;
  uploadEbookSection.classList.remove("done");
  uploadAudioSection.classList.add("done");
  uploadAudioSection.hidden = true;
  ebookResult.textContent = "";
  audioResult.textContent = "";
  audioProgress.hidden = true;
  chapterGrid.innerHTML = "";
  chapterStatuses.innerHTML = "";
  chapterNav.innerHTML = "";
  chapterTitle.textContent = "";
  reader.innerHTML = "";
  chapterGridPanel.hidden = true;
  progressPanel.hidden = true;
  readerPanel.hidden = true;
  processAllBtn.disabled = false;
  batchStatus.textContent = "";
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  status.textContent = statusText;
  window.history.replaceState(null, "", "/");
}

function renderSession(payload) {
  renderChapterGrid(payload);
  renderProgressPanel(payload);
  renderReaderPanel(payload);
  if (payload.status === "awaiting_audio") {
    status.textContent = "Ebook parsed. Select an audiobook file.";
    return;
  }
  if (payload.status === "matching") {
    status.textContent = "Adjust chapter matches below, then process individually or all at once.";
    return;
  }
  if (payload.status === "processing") {
    const readableCount = (payload.chapter_statuses || []).filter((chapter) =>
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

function renderChapterGrid(payload) {
  const showGrid =
    payload.status === "matching" || payload.status === "processing" ||
    payload.status === "ready" || payload.status === "failed-partial";
  chapterGridPanel.hidden = !showGrid;
  if (!showGrid) {
    return;
  }
  const chapterStatusesMap = new Map(
    (payload.chapter_statuses || []).map((s) => [s.ebook_chapter_index, s])
  );
  chapterGrid.innerHTML = "";
  for (const ebookChapter of payload.ebook_chapters || []) {
    const row = document.createElement("div");
    row.className = "chapter-row";
    const label = document.createElement("div");
    label.textContent = ebookChapter.title;
    label.style.fontWeight = "600";
    const controls = document.createElement("div");
    controls.className = "chapter-controls";
    const select = document.createElement("select");
    select.dataset.ebookIndex = String(ebookChapter.index);
    const skipOption = document.createElement("option");
    skipOption.value = "";
    skipOption.textContent = "Skip";
    select.append(skipOption);
    for (const audioChapter of payload.audio_chapters || []) {
      const option = document.createElement("option");
      option.value = String(audioChapter.index);
      option.textContent = audioChapter.title;
      select.append(option);
    }
    const chapterStatus = chapterStatusesMap.get(ebookChapter.index);
    if (chapterStatus) {
      select.value =
        chapterStatus.audio_chapter_index !== null && chapterStatus.audio_chapter_index !== undefined
          ? String(chapterStatus.audio_chapter_index)
          : "";
      select.disabled = true;
      const badge = document.createElement("span");
      badge.className = `chapter-status-badge ${chapterStatus.status}`;
      badge.textContent = chapterStatus.status;
      controls.append(select, badge);
    } else {
      if (ebookChapter.suggested_audio_chapter_index !== null) {
        select.value = String(ebookChapter.suggested_audio_chapter_index);
      }
      const processBtn = document.createElement("button");
      processBtn.type = "button";
      processBtn.className = "small";
      processBtn.dataset.action = "process-chapter";
      processBtn.dataset.ebookIndex = String(ebookChapter.index);
      processBtn.textContent = "Process";
      controls.append(select, processBtn);
    }
    row.append(label, controls);
    chapterGrid.append(row);
  }
}

function renderProgressPanel(payload) {
  const chapterStateList = payload.chapter_statuses ?? [];
  progressPanel.hidden = chapterStateList.length === 0;
  chapterStatuses.innerHTML = "";
  for (const chapterStatus of chapterStateList) {
    const row = document.createElement("div");
    row.className = "chapter-row";
    row.style.animation = "none";
    row.style.opacity = "1";
    row.style.transform = "none";
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
