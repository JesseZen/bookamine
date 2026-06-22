import { buildBlockSegments } from "./reader_render.mjs";
import { isCollapsed, toggleCollapsed, applyCollapsedState } from "./collapsible.mjs";

// ─── SVG icons (Lucide path data) ─────────────────────────────────────────────
const ICON_PATHS = {
  palette: '<circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/>',
  keyboard: '<path d="M10 8h.01"/><path d="M12 12h.01"/><path d="M14 8h.01"/><path d="M16 12h.01"/><path d="M18 8h.01"/><path d="M6 8h.01"/><path d="M7 16h10"/><path d="M8 12h.01"/><path d="M2 8a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8z"/>',
  settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3" fill="currentColor" stroke="none"/>',
  pause: '<rect x="14" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/><rect x="6" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/>',
  rewind: '<polygon points="11 19 2 12 11 5 11 19" fill="currentColor" stroke="none"/><polygon points="22 19 13 12 22 5 22 19" fill="currentColor" stroke="none"/>',
  fastforward: '<polygon points="13 19 22 12 13 5 13 19" fill="currentColor" stroke="none"/><polygon points="2 19 11 12 2 5 2 19" fill="currentColor" stroke="none"/>',
  volume2: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
  volume1: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>',
  volumex: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="22" y1="9" x2="16" y2="15"/><line x1="16" y1="9" x2="22" y2="15"/>',
  alarmclock: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2"/><path d="M5 3 2 6"/><path d="m22 6-3-3"/>',
  bookopen: '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
  headphones: '<path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5a9 9 0 0 1 18 0v5a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  chevrondown: '<path d="M6 9l6 6 6-6"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  alerttriangle: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
};

function icon(name, size = 18) {
  const path = ICON_PATHS[name];
  if (!path) return "";
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${path}</svg>`;
}

function initIcons() {
  document.querySelectorAll("[data-icon]").forEach((el) => {
    const name = el.dataset.icon;
    const size = Number(el.dataset.iconSize) || 18;
    el.innerHTML = icon(name, size);
  });
}

// ─── DOM helpers ──────────────────────────────────────────────────────────────
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

// ─── Toast notifications ──────────────────────────────────────────────────────
const toastContainer = $("#toast-container");
function toast(message, type = "info", duration = 4000) {
  const iconMap = { success: "check", error: "alerttriangle", info: "info" };
  const iconName = iconMap[type] || "info";
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.innerHTML = `${icon(iconName, 16)}<span class="toast-msg"></span><div class="toast-progress"><div class="toast-progress-fill"></div></div>`;
  node.querySelector(".toast-msg").textContent = message;
  toastContainer.appendChild(node);
  const fill = node.querySelector(".toast-progress-fill");
  fill.style.transition = `width ${duration}ms linear`;
  requestAnimationFrame(() => { fill.style.width = "0%"; });
  setTimeout(() => {
    node.style.opacity = "0";
    node.style.transform = "translateY(20px)";
    node.style.transition = "all 0.3s ease";
    setTimeout(() => node.remove(), 300);
  }, duration);
}

// ─── DOM construction helpers ─────────────────────────────────────────────────
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "className") node.className = v;
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (k === "attrs") for (const [a, b] of Object.entries(v)) node.setAttribute(a, b);
    else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
    else if (k.startsWith("on") && typeof v === "function") {
      node.addEventListener(k.slice(2).toLowerCase(), v);
    } else if (k === "html") node.innerHTML = v;
    else node[k] = v;
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

function skeleton(className = "skeleton") {
  return el("div", { className });
}

function renderSessionListSkeleton() {
  sessionList.innerHTML = "";
  for (let i = 0; i < 3; i++) {
    sessionList.appendChild(
      el("div", { className: "session-card is-loading" },
        skeleton("skeleton circle"),
        el("div", { className: "skel-col" },
          skeleton("skeleton line-lg"),
          skeleton("skeleton line-sm")
        )
      )
    );
  }
}

function renderReaderSkeleton() {
  readerEl.innerHTML = "";
  readerEl.appendChild(
    el("div", { className: "reader-skeleton" },
      skeleton("skeleton skel-heading"),
      skeleton("skeleton skel-line long"),
      skeleton("skeleton skel-line long"),
      skeleton("skeleton skel-line medium"),
      skeleton("skeleton skel-line long"),
      skeleton("skeleton skel-line short"),
      skeleton("skeleton skel-line long"),
      skeleton("skeleton skel-line medium")
    )
  );
}

function renderErrorBoundary(container, message, detail, onRetry) {
  container.innerHTML = "";
  const boundary = el("div", { className: "error-boundary" },
    el("span", { className: "err-icon", html: icon("alerttriangle", 24) }),
    el("div", { className: "err-body" },
      el("div", { className: "err-title" }, message),
      detail ? el("div", { className: "err-detail" }, detail) : null,
      onRetry ? el("button", { className: "btn small", onClick: onRetry }, "Try again") : null
    )
  );
  container.appendChild(boundary);
}

// ─── State ────────────────────────────────────────────────────────────────────
const state = {
  ebookName: null,
  ebookChapters: null,
  audioChapters: null,
  chapterMappings: null,
  chapterStatuses: null,
  completedChapters: null,
  currentChapterIndex: 0,
  currentActiveWord: null,
  sessionPayload: null,
  sessionId: null,
  audioUploadWs: null,
  eventSource: null,
  pollInterval: null,
  sleepTimer: null,
  sleepTimerEnd: null,
  sleepTimerInterval: null,
  speed: 1.0,
  muted: false,
  savedVolume: 1,
  processingStartedAt: null,
  processingDoneCount: 0,
  elapsedTimer: null,
};

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const ebookFileInput = $("#ebook-file");
const audioFileInput = $("#audio-files");
const uploadEbookSection = $("#upload-ebook-section");
const uploadAudioSection = $("#upload-audio-section");
const ebookResult = $("#ebook-result");
const audioResult = $("#audio-result");
const audioProgressTrack = $("#audio-progress-track");
const audioProgressFill = $("#audio-progress-fill");
const audioProgressPct = $("#audio-progress-pct");
const statusEl = $("#status");
const statusDot = $("#status-dot");
const chapterGridPanel = $("#chapter-grid-panel");
const chapterGrid = $("#chapter-grid");
const progressPanel = $("#progress-panel");
const progressSummary = $("#progress-summary");
const progressElapsed = $("#progress-elapsed");
const progressEta = $("#progress-eta");
const overallProgressFill = $("#overall-progress-fill");
const overallProgressLabel = $("#overall-progress-label");
const chapterStatuses = $("#chapter-statuses");
const readerPanel = $("#reader-panel");
const readerEl = $("#reader");
const chapterMeta = $("#chapter-meta");
const readerTitle = $("#reader-title");
const readerSubtitle = $("#reader-subtitle");
const chapterNav = $("#chapter-nav");
const playerBar = $("#player-bar");
const audio = $("#audio");
const playBtn = $("#play-btn");
const skipBackBtn = $("#skip-back-btn");
const skipFwdBtn = $("#skip-fwd-btn");
const currentTimeEl = $("#current-time");
const durationTimeEl = $("#duration-time");
const playerProgress = $("#player-progress");
const playerProgressFill = $("#player-progress-fill");
const speedBtn = $("#speed-btn");
const speedPanel = $("#speed-panel");
const speedSlider = $("#speed-slider");
const speedPanelValue = $("#speed-panel-value");
const speedPresets = $("#speed-presets");
const volumeSlider = $("#volume-slider");
const volumeIcon = $("#volume-icon");
const sleepTimerBtn = $("#sleep-timer-btn");
const processAllBtn = $("#process-all-btn");
const batchStatus = $("#batch-status");
const useMulticore = $("#use-multicore");
const resumeProcessingBtn = $("#resume-processing-btn");
const clearSessionBtn = $("#clear-session");
const sessionListSection = $("#session-list-section");
const sessionList = $("#session-list");
const newSessionBtn = $("#new-session-btn");
const themeSelectorBtn = $("#theme-selector-btn");
const themeSelectorPopover = $("#theme-selector-popover");
const themeSelectorList = $("#theme-selector-list");
const themeTransitionOverlay = $("#theme-transition-overlay");
const settingsBtn = $("#settings-btn");
const settingsPopover = $("#settings-popover");
const fontSizeSlider = $("#font-size-slider");
const fontFamilyToggle = $("#font-family-toggle");
const highlightToggle = $("#highlight-toggle");
const keyboardHelpBtn = $("#keyboard-help-btn");
const keyboardHelp = $("#keyboard-help");

// ─── Theme system ─────────────────────────────────────────────────────────────
const THEMES = [
  { id: "editorial", name: "Editorial", swatch: "#c06132", metaColor: "#f6f1e8" },
  { id: "midnight", name: "Midnight", swatch: "#e0a842", metaColor: "#14110d" },
  { id: "sepia", name: "Sepia", swatch: "#8b5a2b", metaColor: "#ede0c8" },
];

function updateThemeMeta(themeId) {
  const theme = THEMES.find((t) => t.id === themeId);
  if (!theme) return;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme.metaColor);
}

function renderThemeSwatches(activeTheme) {
  themeSelectorList.innerHTML = "";
  THEMES.forEach((theme) => {
    const btn = el("button", {
      type: "button",
      className: `theme-swatch${theme.id === activeTheme ? " active" : ""}`,
      onClick: () => selectTheme(theme.id),
    },
      el("span", { className: "swatch-color", style: { background: theme.swatch } }),
      el("span", { className: "swatch-name" }, theme.name),
      el("span", { className: "swatch-check", html: icon("check", 16) })
    );
    themeSelectorList.appendChild(btn);
  });
}

function showThemeTransition() {
  themeTransitionOverlay.classList.add("active");
  requestAnimationFrame(() => {
    setTimeout(() => themeTransitionOverlay.classList.remove("active"), 150);
  });
}

function selectTheme(themeId) {
  showThemeTransition();
  document.documentElement.setAttribute("data-theme", themeId);
  localStorage.setItem("bookamine.theme", themeId);
  renderThemeSwatches(themeId);
  updateThemeMeta(themeId);
}

function cycleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "editorial";
  const idx = THEMES.findIndex((t) => t.id === current);
  const next = THEMES[(idx + 1) % THEMES.length];
  selectTheme(next.id);
}

function initThemeSelector() {
  const current = document.documentElement.getAttribute("data-theme") || "editorial";
  renderThemeSwatches(current);
  updateThemeMeta(current);
}

themeSelectorBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const isOpen = !themeSelectorPopover.hidden;
  themeSelectorPopover.hidden = isOpen;
  themeSelectorBtn.setAttribute("aria-expanded", String(!isOpen));
});

document.addEventListener("click", (e) => {
  if (!themeSelectorPopover.contains(e.target) && e.target !== themeSelectorBtn && !themeSelectorBtn.contains(e.target)) {
    themeSelectorPopover.hidden = true;
    themeSelectorBtn.setAttribute("aria-expanded", "false");
  }
});

// ─── Settings ─────────────────────────────────────────────────────────────────
function initSettings() {
  const fontSize = localStorage.getItem("bookamine.fontSize") || "1.15";
  const fontFamily = localStorage.getItem("bookamine.fontFamily") || "serif";
  const highlight = localStorage.getItem("bookamine.highlight") || "warm";
  document.documentElement.style.setProperty("--reader-font-size", `${fontSize}rem`);
  fontSizeSlider.value = fontSize;
  applyFontFamily(fontFamily);
  applyHighlight(highlight);
  fontFamilyToggle.querySelectorAll("button").forEach((b) => {
    b.classList.toggle("active", b.dataset.font === fontFamily);
  });
  highlightToggle.querySelectorAll("button").forEach((b) => {
    b.classList.toggle("active", b.dataset.highlight === highlight);
  });
}

function applyFontFamily(family) {
  const reader = $(".reader-content");
  if (reader) reader.style.fontFamily = family === "sans" ? "var(--reader-font-sans)" : "var(--reader-font-serif)";
}

function applyHighlight(mode) {
  if (mode === "cool") {
    document.documentElement.style.setProperty("--highlight", "rgba(58, 106, 138, 0.25)");
    document.documentElement.style.setProperty("--highlight-active", "rgba(58, 106, 138, 0.5)");
    document.documentElement.style.setProperty("--highlight-underline", "var(--info)");
  } else {
    // Warm: clear overrides so theme defaults apply
    document.documentElement.style.removeProperty("--highlight");
    document.documentElement.style.removeProperty("--highlight-active");
    document.documentElement.style.removeProperty("--highlight-underline");
  }
}

settingsBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  settingsPopover.hidden = !settingsPopover.hidden;
});

document.addEventListener("click", (e) => {
  if (!settingsPopover.contains(e.target) && e.target !== settingsBtn && !settingsBtn.contains(e.target)) {
    settingsPopover.hidden = true;
  }
});

fontSizeSlider.addEventListener("input", () => {
  const val = fontSizeSlider.value;
  document.documentElement.style.setProperty("--reader-font-size", `${val}rem`);
  localStorage.setItem("bookamine.fontSize", val);
});

fontFamilyToggle.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  fontFamilyToggle.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  applyFontFamily(btn.dataset.font);
  localStorage.setItem("bookamine.fontFamily", btn.dataset.font);
});

highlightToggle.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  highlightToggle.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  applyHighlight(btn.dataset.highlight);
  localStorage.setItem("bookamine.highlight", btn.dataset.highlight);
});

// ─── Keyboard shortcuts ───────────────────────────────────────────────────────
keyboardHelpBtn.addEventListener("click", () => {
  keyboardHelp.hidden = !keyboardHelp.hidden;
});

document.addEventListener("click", (e) => {
  if (!keyboardHelp.contains(e.target) && e.target !== keyboardHelpBtn && !keyboardHelpBtn.contains(e.target)) {
    keyboardHelp.hidden = true;
  }
});

document.addEventListener("keydown", (e) => {
  // Don't intercept when typing in inputs
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") {
    return;
  }

  // Number keys 1-9: jump to chapter (only when reader is visible)
  if (/^[1-9]$/.test(e.key) && !readerPanel.hidden) {
    e.preventDefault();
    const targetIdx = Number(e.key) - 1;
    const completed = state.sessionPayload?.completed_chapters || [];
    if (targetIdx < completed.length) {
      goToChapter(targetIdx);
    }
    return;
  }

  switch (e.key) {
    case " ":
      e.preventDefault();
      togglePlay();
      break;
    case "ArrowLeft":
      e.preventDefault();
      skip(-10);
      break;
    case "ArrowRight":
      e.preventDefault();
      skip(10);
      break;
    case "ArrowUp":
      e.preventDefault();
      goToChapter(state.currentChapterIndex - 1);
      break;
    case "ArrowDown":
      e.preventDefault();
      goToChapter(state.currentChapterIndex + 1);
      break;
    case "-":
    case "_":
      e.preventDefault();
      applySpeed(state.speed - 0.25);
      break;
    case "+":
    case "=":
      e.preventDefault();
      applySpeed(state.speed + 0.25);
      break;
    case "m":
    case "M":
      e.preventDefault();
      toggleMute();
      break;
    case "t":
    case "T":
      e.preventDefault();
      cycleTheme();
      break;
    case "?":
      e.preventDefault();
      keyboardHelp.hidden = !keyboardHelp.hidden;
      break;
    case "Escape":
      keyboardHelp.hidden = true;
      settingsPopover.hidden = true;
      speedPanel.hidden = true;
      themeSelectorPopover.hidden = true;
      themeSelectorBtn.setAttribute("aria-expanded", "false");
      break;
  }
});

// ─── Drag and drop ────────────────────────────────────────────────────────────
function setupDragDrop(zone, handler) {
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("dragover");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dragover");
    const files = Array.from(e.dataTransfer.files);
    if (files.length) handler(files);
  });
}

setupDragDrop(uploadEbookSection, (files) => {
  const file = files[0];
  if (!file) return;
  const dt = new DataTransfer();
  dt.items.add(file);
  ebookFileInput.files = dt.files;
  ebookFileInput.dispatchEvent(new Event("change"));
});

setupDragDrop(uploadAudioSection, (files) => {
  const dt = new DataTransfer();
  files.forEach((f) => dt.items.add(f));
  audioFileInput.files = dt.files;
  audioFileInput.dispatchEvent(new Event("change"));
});

// ─── Ebook upload ─────────────────────────────────────────────────────────────
ebookFileInput.addEventListener("change", async () => {
  const file = ebookFileInput.files[0];
  if (!file) return;
  ebookResult.innerHTML = `<span class="spinner"></span><span>Uploading ${file.name}...</span>`;
  ebookResult.style.color = "";
  uploadEbookSection.classList.add("uploading");
  uploadEbookSection.classList.remove("done");
  const formData = new FormData();
  formData.append("ebook", file);
  try {
    const response = await fetch("/sessions/ebook", { method: "POST", body: formData });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(err.detail || "Upload failed");
    }
    const payload = await response.json();
    state.sessionId = payload.session_id;
    state.ebookChapters = payload.ebook_chapters;
    state.audioChapters = payload.audio_chapters;
    ebookResult.innerHTML = `${icon("check", 16)}<span>${file.name} — ${payload.ebook_chapters.length} chapters detected</span>`;
    uploadEbookSection.classList.add("done");
    uploadEbookSection.classList.remove("uploading");
    uploadAudioSection.hidden = false;
    statusEl.textContent = `Ebook uploaded. Now upload audiobook files.`;
    toast("Ebook uploaded successfully", "success");
  } catch (err) {
    ebookResult.innerHTML = `${icon("x", 16)}<span>${err.message}</span>`;
    ebookResult.style.color = "var(--danger)";
    uploadEbookSection.classList.remove("uploading");
    toast(err.message, "error");
  }
});

// ─── Audio upload (WebSocket for progress) ────────────────────────────────────
audioFileInput.addEventListener("change", () => {
  const files = Array.from(audioFileInput.files);
  if (!files.length) return;
  uploadAudioViaWebSocket(files);
});

function uploadAudioViaWebSocket(files) {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${location.host}/ws/sessions/${state.sessionId}/audio-upload`;
  const ws = new WebSocket(wsUrl);
  state.audioUploadWs = ws;

  audioProgressTrack.hidden = false;
  audioProgressPct.hidden = false;
  audioProgressFill.style.width = "0%";
  audioProgressPct.textContent = "0%";
  audioResult.innerHTML = `<span class="spinner"></span><span>Uploading ${files.length} file(s)...</span>`;

  const totalSize = files.reduce((sum, f) => sum + f.size, 0);
  let sent = 0;

  const updatePct = (pct) => {
    audioProgressFill.style.width = `${pct}%`;
    audioProgressPct.textContent = `${Math.round(pct)}%`;
  };

  ws.onopen = async () => {
    for (const file of files) {
      ws.send(JSON.stringify({ type: "start", filename: file.name, size: file.size }));
      const chunkSize = 256 * 1024;
      for (let offset = 0; offset < file.size; offset += chunkSize) {
        const chunk = file.slice(offset, offset + chunkSize);
        const buf = await chunk.arrayBuffer();
        ws.send(buf);
        sent += buf.byteLength;
        updatePct((sent / totalSize) * 100);
      }
      ws.send("__EOF__");
    }
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "progress") {
      updatePct((msg.received / totalSize) * 100);
    } else if (msg.type === "chapters_early") {
      audioResult.innerHTML = `${icon("check", 16)}<span>Detected ${msg.chapters.length} chapters in .m4b</span>`;
    } else if (msg.type === "done") {
      audioResult.innerHTML = `${icon("check", 16)}<span>Upload complete</span>`;
      uploadAudioSection.classList.add("done");
      const payload = msg.payload;
      state.ebookChapters = payload.ebook_chapters;
      state.audioChapters = payload.audio_chapters;
      renderChapterGrid();
      chapterGridPanel.hidden = false;
      statusEl.textContent = `Audio uploaded. Review chapter matches.`;
      statusDot.className = "status-dot";
      toast("Audio uploaded — review chapter matches", "success");
      ws.close();
    } else if (msg.type === "error") {
      audioResult.innerHTML = `${icon("x", 16)}<span>${msg.detail}</span>`;
      audioResult.style.color = "var(--danger)";
      toast(msg.detail, "error");
      ws.close();
    }
  };

  ws.onerror = () => {
    audioResult.innerHTML = `${icon("x", 16)}<span>Connection error</span>`;
    audioResult.style.color = "var(--danger)";
    toast("WebSocket error during upload", "error");
  };
}

// ─── Chapter grid ─────────────────────────────────────────────────────────────
function renderChapterGrid() {
  chapterGrid.innerHTML = "";
  state.ebookChapters.forEach((ebookChapter, idx) => {
    const row = document.createElement("div");
    row.className = "chapter-row";
    const num = document.createElement("div");
    num.className = "chapter-num-circle";
    num.textContent = idx + 1;
    const title = document.createElement("div");
    title.className = "chapter-title";
    title.textContent = ebookChapter.title;
    const info = document.createElement("div");
    info.className = "chapter-row-info";
    info.appendChild(num);
    info.appendChild(title);
    const controls = document.createElement("div");
    controls.className = "chapter-controls";
    const select = document.createElement("select");
    const noneOption = document.createElement("option");
    noneOption.value = "";
    noneOption.textContent = "— Skip —";
    select.appendChild(noneOption);
    state.audioChapters.forEach((audioChapter) => {
      const option = document.createElement("option");
      option.value = audioChapter.index;
      option.textContent = audioChapter.title;
      if (ebookChapter.suggested_audio_chapter_index === audioChapter.index) {
        option.selected = true;
      }
      select.appendChild(option);
    });
    const processBtn = document.createElement("button");
    processBtn.type = "button";
    processBtn.className = "btn small";
    processBtn.textContent = "Process";
    processBtn.addEventListener("click", () => {
      const audioIdx = select.value === "" ? null : Number(select.value);
      processSingleChapter(ebookChapter.index, audioIdx);
    });
    controls.appendChild(select);
    controls.appendChild(processBtn);
    row.appendChild(info);
    row.appendChild(controls);
    chapterGrid.appendChild(row);
  });
}

async function processSingleChapter(ebookChapterIndex, audioChapterIndex) {
  if (audioChapterIndex === null) {
    toast("Skipped chapters can't be processed individually", "info");
    return;
  }
  try {
    await fetch(`/sessions/${state.sessionId}/init-process`, { method: "POST" });
    await fetch(`/sessions/${state.sessionId}/process-chapter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ebook_chapter_index: ebookChapterIndex, audio_chapter_index: audioChapterIndex }),
    });
    toast(`Processing chapter ${ebookChapterIndex + 1}...`, "info");
    startListening();
    progressPanel.hidden = false;
  } catch (err) {
    toast(err.message, "error");
  }
}

// ─── Process all ──────────────────────────────────────────────────────────────
processAllBtn.addEventListener("click", async () => {
  const matches = [];
  $$("#chapter-grid .chapter-row").forEach((row, index) => {
    const select = row.querySelector("select");
    const audioIdx = select.value === "" ? null : Number(select.value);
    matches.push({ ebook_chapter_index: index, audio_chapter_index: audioIdx });
  });
  processAllBtn.disabled = true;
  const originalText = processAllBtn.textContent;
  processAllBtn.innerHTML = '<span class="spinner"></span> Processing...';
  batchStatus.textContent = "Submitting...";
  try {
    const response = await fetch(`/chapter-sessions/${state.sessionId}/mapping`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ matches, multicore: useMulticore.checked }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Failed" }));
      throw new Error(err.detail);
    }
    batchStatus.textContent = "Processing started";
    toast("Processing all chapters...", "success");
    chapterGridPanel.hidden = true;
    progressPanel.hidden = false;
    startListening();
  } catch (err) {
    batchStatus.textContent = "";
    processAllBtn.disabled = false;
    processAllBtn.textContent = originalText;
    toast(err.message, "error");
  }
});

// ─── SSE / Polling ────────────────────────────────────────────────────────────

resumeProcessingBtn.addEventListener("click", async () => {
  if (!state.chapterMappings) return;
  resumeProcessingBtn.disabled = true;
  try {
    const response = await fetch(`/chapter-sessions/${state.sessionId}/mapping`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ matches: state.chapterMappings, multicore: useMulticore.checked }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Failed" }));
      throw new Error(err.detail);
    }
    toast("Processing resumed...", "success");
    startListening();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    resumeProcessingBtn.disabled = false;
  }
});

function startListening() {
  if (state.eventSource) {
    state.eventSource.close();
  }
  try {
    const es = new EventSource(`/sessions/${state.sessionId}/events`);
    state.eventSource = es;
    es.addEventListener("update", (e) => {
      const payload = JSON.parse(e.data);
      handleSessionUpdate(payload);
    });
    es.addEventListener("deleted", () => {
      es.close();
      statusEl.textContent = "Session was deleted";
    });
    es.onerror = () => {
      es.close();
      // Fall back to polling
      startPolling();
    };
  } catch {
    startPolling();
  }
}

function startPolling() {
  if (state.pollInterval) clearInterval(state.pollInterval);
  state.pollInterval = setInterval(async () => {
    try {
      const response = await fetch(`/chapter-sessions/${state.sessionId}`);
      if (!response.ok) {
        clearInterval(state.pollInterval);
        return;
      }
      const payload = await response.json();
      handleSessionUpdate(payload);
      if (["ready", "failed", "failed-partial"].includes(payload.status)) {
        clearInterval(state.pollInterval);
      }
    } catch {
      // ignore
    }
  }, 2000);
}

function handleSessionUpdate(payload) {
  state.sessionPayload = payload;
  state.chapterStatuses = payload.chapter_statuses;
  state.completedChapters = payload.completed_chapters;
  state.chapterMappings = payload.chapter_mappings;
  updateStatusDisplay(payload);
  renderChapterStatuses(payload);
  // Show the reader as soon as completed chapters become available, even
  // mid-processing. Skip if already visible — re-rendering would reset the
  // user's current chapter and audio position. The full re-render happens
  // below when status reaches ready/failed-partial.
  if (readerPanel.hidden && payload.completed_chapters?.length) {
    renderReader(payload);
  }
  if (["ready", "failed-partial"].includes(payload.status)) {
    renderReader(payload);
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    if (state.pollInterval) {
      clearInterval(state.pollInterval);
      state.pollInterval = null;
    }
  } else if (payload.status === "failed") {
    stopElapsedTimer();
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    if (state.pollInterval) {
      clearInterval(state.pollInterval);
      state.pollInterval = null;
    }
  }
}

function updateStatusDisplay(payload) {
  const statusMap = {
    matching: "Matching chapters",
    processing: "Processing chapters",
    ready: "All chapters ready",
    failed: "Processing failed",
    "failed-partial": "Some chapters failed",
    awaiting_audio: "Waiting for audio",
  };
  statusEl.textContent = statusMap[payload.status] || payload.status;
  statusDot.className = "status-dot";
  if (payload.status === "processing") statusDot.classList.add("processing");
  else if (payload.status === "ready") statusDot.classList.add("ready");
  else if (payload.status === "failed" || payload.status === "failed-partial") statusDot.classList.add("failed");
}

function formatElapsed(seconds) {
  if (!isFinite(seconds) || seconds < 0) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function startElapsedTimer() {
  if (state.elapsedTimer) return;
  state.processingStartedAt = Date.now();
  state.processingDoneCount = 0;
  state.elapsedTimer = setInterval(() => {
    if (!state.processingStartedAt) return;
    const elapsed = (Date.now() - state.processingStartedAt) / 1000;
    progressElapsed.innerHTML = `${icon("clock", 14)} ${formatElapsed(elapsed)}`;
    // ETA calculation
    if (state.processingDoneCount > 0 && state.processingDoneCount < state.processingTotalCount) {
      const rate = state.processingDoneCount / elapsed;
      const remaining = state.processingTotalCount - state.processingDoneCount;
      const eta = remaining / rate;
      progressEta.textContent = `~${formatElapsed(eta)} left`;
    } else {
      progressEta.textContent = "";
    }
  }, 1000);
}

function stopElapsedTimer() {
  if (state.elapsedTimer) {
    clearInterval(state.elapsedTimer);
    state.elapsedTimer = null;
  }
  if (state.processingStartedAt) {
    const elapsed = (Date.now() - state.processingStartedAt) / 1000;
    progressElapsed.innerHTML = `${icon("check", 14)} ${formatElapsed(elapsed)}`;
    progressEta.textContent = "";
    state.processingStartedAt = null;
  }
}

function renderChapterStatuses(payload) {
  if (!payload.chapter_statuses) return;
  progressPanel.hidden = false;
  const total = payload.chapter_statuses.length;
  const statuses = payload.chapter_statuses;
  const counts = {
    ready: 0,
    processing: 0,
    pending: 0,
    failed: 0,
    skipped: 0,
    "transcript-only": 0,
  };
  statuses.forEach((s) => {
    if (counts[s.status] !== undefined) counts[s.status] += 1;
  });
  const done = counts.ready + counts["transcript-only"] + counts.skipped + counts.failed;
  const percent = total > 0 ? (done / total) * 100 : 0;

  // Track done count for ETA
  state.processingDoneCount = done;
  state.processingTotalCount = total;

  // Summary text with live counts
  progressSummary.textContent = `${done} / ${total} chapters · ${counts.processing} processing · ${counts.pending} queued`;
  overallProgressFill.style.width = `${percent}%`;
  overallProgressFill.classList.toggle("is-complete", done === total);
  overallProgressLabel.textContent = `${Math.round(percent)}%`;

  // Start/stop elapsed timer based on whether anything is still processing
  if (counts.processing > 0 && !state.elapsedTimer) {
    startElapsedTimer();
  } else if (counts.processing === 0 && counts.pending === 0 && state.elapsedTimer) {
    stopElapsedTimer();
  }

  // Show "Resume Processing" when there are pending chapters but nothing is
  // actively being processed (e.g. after server restart recovered stuck chapters).
  resumeProcessingBtn.hidden = !(counts.processing === 0 && counts.pending > 0);

  chapterStatuses.innerHTML = "";
  statuses.forEach((status, index) => {
    const row = el("div", {
      className: `status-row${status.status === "processing" ? " is-processing" : ""}`,
    });
    const num = el("span", { className: "chapter-num" }, `${index + 1}.`);
    const title = el("div", { className: "status-title" }, status.title);
    const info = el("div", { className: "status-info" }, num, title);
    if (status.reason) {
      info.appendChild(el("div", { className: "status-reason" }, status.reason));
    }
    const actions = el("div", { className: "status-actions" });
    const badge = el("span", { className: `badge ${status.status}` },
      status.status.replace(/-/g, " "));
    actions.appendChild(badge);
    if (status.status === "processing") {
      actions.appendChild(el("span", { className: "spinner" }));
    }
    if (status.status === "failed" || status.status === "transcript-only" || status.status === "processing") {
      actions.appendChild(el("button", {
        type: "button",
        className: "btn small secondary",
        onClick: () => retryChapter(status.ebook_chapter_index),
      }, "Retry"));
    }
    row.append(info, actions);
    chapterStatuses.appendChild(row);
  });
}

async function retryChapter(ebookChapterIndex) {
  try {
    await fetch(`/sessions/${state.sessionId}/retry-chapter/${ebookChapterIndex}`, { method: "POST" });
    toast("Retrying chapter...", "info");
    startListening();
  } catch (err) {
    toast(err.message, "error");
  }
}

// ─── Reader rendering ─────────────────────────────────────────────────────────
function renderReader(payload) {
  // Only dismiss the progress panel + timer when processing is fully done.
  // While still processing, keep both panels visible so the user can read
  // completed chapters while watching the rest finish.
  if (payload.status === "ready") {
    stopElapsedTimer();
    progressPanel.hidden = true;
  }
  chapterGridPanel.hidden = true;
  readerPanel.hidden = false;
  playerBar.hidden = false;

  const completed = payload.completed_chapters || [];
  if (!completed.length) return;

  // Restore last chapter from localStorage
  const savedChapter = localStorage.getItem(`bookamine.${state.sessionId}.chapter`);
  const startIndex = savedChapter !== null ? Math.min(Number(savedChapter), completed.length - 1) : 0;
  state.currentChapterIndex = Math.max(0, startIndex);

  renderChapterNav(completed);
  loadChapter(state.currentChapterIndex);
}

function renderChapterNav(completed) {
  chapterNav.innerHTML = "";
  completed.forEach((chapter, index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chapter-nav-btn";
    if (index === state.currentChapterIndex) btn.classList.add("active");
    // Mark as "read" if there's a saved position
    const savedTime = localStorage.getItem(`bookamine.${state.sessionId}.${index}.time`);
    if (savedTime && Number(savedTime) > 5) {
      btn.style.opacity = "0.6";
    }
    const num = document.createElement("span");
    num.className = "chapter-num";
    num.textContent = index + 1;
    const label = document.createElement("span");
    label.className = "chapter-label";
    label.textContent = chapter.title;
    btn.appendChild(num);
    btn.appendChild(label);
    btn.addEventListener("click", () => goToChapter(index));
    chapterNav.appendChild(btn);
  });
}

function loadChapter(index) {
  const completed = state.sessionPayload?.completed_chapters || [];
  if (index < 0 || index >= completed.length) return;
  state.currentChapterIndex = index;
  state.currentActiveWord = null;
  localStorage.setItem(`bookamine.${state.sessionId}.chapter`, String(index));

  // Update nav
  const navBtns = chapterNav.querySelectorAll(".chapter-nav-btn");
  navBtns.forEach((btn, i) => {
    btn.classList.toggle("active", i === index);
  });
  // Scroll active chapter into view (works for both vertical sidebar and mobile horizontal strip)
  const activeBtn = navBtns[index];
  if (activeBtn) {
    activeBtn.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  const chapter = completed[index];
  readerTitle.textContent = chapter.title;
  readerSubtitle.textContent = `Chapter ${index + 1} of ${completed.length}`;
  const coverageText = chapter.coverage !== null
    ? `${(chapter.coverage * 100).toFixed(0)}% coverage`
    : "transcript only";
  const sourceText = chapter.text_source === "ebook" ? "ebook text" : "transcript";
  chapterMeta.innerHTML = `<span class="meta-badge">${coverageText}</span> · <span>${sourceText}</span>`;

  // Render blocks
  readerEl.innerHTML = "";
  // Chapter title heading inside the reader with decorative accent line
  const heading = document.createElement("h2");
  heading.className = "chapter-heading";
  heading.textContent = chapter.title;
  readerEl.appendChild(heading);

  const wordsByIndex = new Map(chapter.words.map((w) => [w.index, w]));
  chapter.blocks.forEach((block) => {
    const p = document.createElement("p");
    const segments = buildBlockSegments(block, wordsByIndex);
    segments.forEach((token) => {
      if (token.type === "word") {
        const span = document.createElement("span");
        span.className = "word";
        span.dataset.index = token.wordIndex;
        span.dataset.startMs = token.startMs ?? "";
        const wordObj = wordsByIndex.get(token.wordIndex);
        span.dataset.endMs = wordObj?.end_ms ?? "";
        span.textContent = token.text;
        span.addEventListener("click", () => {
          if (token.startMs !== null && token.startMs !== undefined) {
            audio.currentTime = token.startMs / 1000;
            if (audio.paused) audio.play();
          }
        });
        p.appendChild(span);
      } else {
        p.appendChild(document.createTextNode(token.text));
      }
    });
    readerEl.appendChild(p);
  });

  // Fade-in animation
  readerEl.classList.remove("fade-in");
  void readerEl.offsetWidth; // force reflow
  readerEl.classList.add("fade-in");

  // Load audio
  audio.src = chapter.audio_url;
  audio.playbackRate = state.speed;

  // Restore position
  const savedTime = localStorage.getItem(`bookamine.${state.sessionId}.${index}.time`);
  if (savedTime) {
    audio.currentTime = Number(savedTime);
  }
}

function goToChapter(index) {
  const completed = state.sessionPayload?.completed_chapters || [];
  if (index < 0 || index >= completed.length) return;
  loadChapter(index);
  // Scroll reader into view
  readerPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ─── Audio player ─────────────────────────────────────────────────────────────
function togglePlay() {
  if (audio.paused) {
    audio.play();
  } else {
    audio.pause();
  }
}

playBtn.addEventListener("click", togglePlay);

function skip(seconds) {
  audio.currentTime = Math.max(0, Math.min(audio.duration || 0, audio.currentTime + seconds));
}

skipBackBtn.addEventListener("click", () => skip(-10));
skipFwdBtn.addEventListener("click", () => skip(10));

audio.addEventListener("play", () => {
  playBtn.innerHTML = icon("pause");
  playBtn.classList.add("is-playing");
});

audio.addEventListener("pause", () => {
  playBtn.innerHTML = icon("play");
  playBtn.classList.remove("is-playing");
});

audio.addEventListener("loadedmetadata", () => {
  durationTimeEl.textContent = formatTime(audio.duration);
});

audio.addEventListener("timeupdate", () => {
  currentTimeEl.textContent = formatTime(audio.currentTime);
  if (audio.duration) {
    const pct = (audio.currentTime / audio.duration) * 100;
    playerProgressFill.style.width = `${pct}%`;
  }
  // Save position
  localStorage.setItem(`bookamine.${state.sessionId}.${state.currentChapterIndex}.time`, String(audio.currentTime));
  // Highlight current word
  highlightCurrentWord();
  // Auto-advance when chapter ends
  if (audio.ended) {
    goToChapter(state.currentChapterIndex + 1);
  }
});

function highlightCurrentWord() {
  const currentTimeMs = audio.currentTime * 1000;
  let activeEl = null;
  readerEl.querySelectorAll(".word").forEach((el) => {
    const start = Number(el.dataset.startMs);
    const end = Number(el.dataset.endMs);
    if (start <= currentTimeMs && currentTimeMs <= end) {
      el.classList.add("active");
      el.classList.remove("was-active");
      if (!activeEl) activeEl = el;
    } else {
      if (el.classList.contains("active")) {
        // This was active — fade it out
        el.classList.add("was-active");
        el.classList.remove("active");
        const node = el;
        setTimeout(() => node.classList.remove("was-active"), 300);
      }
    }
  });
  // Scroll active word into view
  if (activeEl) {
    const rect = activeEl.getBoundingClientRect();
    const viewportH = window.innerHeight;
    if (rect.top < 100 || rect.bottom > viewportH - 120) {
      activeEl.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }
}

playerProgress.addEventListener("click", (e) => {
  const rect = playerProgress.getBoundingClientRect();
  const pct = (e.clientX - rect.left) / rect.width;
  if (audio.duration) {
    audio.currentTime = pct * audio.duration;
  }
});

// ─── Speed control ────────────────────────────────────────────────────────────
function applySpeed(value) {
  const speed = Math.round(Math.max(0.5, Math.min(4.0, value)) * 100) / 100;
  state.speed = speed;
  audio.playbackRate = speed;
  speedBtn.textContent = `${Number.isInteger(speed * 10) ? speed.toFixed(1) : speed.toFixed(2)}×`;
  speedSlider.value = speed;
  speedPanelValue.textContent = `${Number.isInteger(speed * 10) ? speed.toFixed(1) : speed.toFixed(2)}×`;
  // Update preset active state
  speedPresets.querySelectorAll(".speed-preset").forEach((btn) => {
    btn.classList.toggle("active", Number(btn.dataset.speed) === speed);
  });
}

speedBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  speedPanel.hidden = !speedPanel.hidden;
  if (!speedPanel.hidden) {
    applySpeed(state.speed);
  }
});

// Close panel on outside click
document.addEventListener("click", (e) => {
  if (!speedPanel.hidden && !speedPanel.contains(e.target) && e.target !== speedBtn && !speedBtn.contains(e.target)) {
    speedPanel.hidden = true;
  }
});

// Slider input — real-time update
speedSlider.addEventListener("input", () => {
  applySpeed(Number(speedSlider.value));
});

// Preset buttons
speedPresets.addEventListener("click", (e) => {
  const btn = e.target.closest(".speed-preset");
  if (!btn) return;
  applySpeed(Number(btn.dataset.speed));
});

// ─── Volume ───────────────────────────────────────────────────────────────────
function updateVolumeIcon() {
  const vol = state.muted ? 0 : audio.volume;
  const name = vol === 0 ? "volumex" : vol < 0.5 ? "volume1" : "volume2";
  if (volumeIcon) volumeIcon.innerHTML = icon(name, 18);
}

volumeSlider.addEventListener("input", () => {
  audio.volume = Number(volumeSlider.value);
  state.muted = audio.volume === 0;
  updateVolumeIcon();
});

function toggleMute() {
  if (state.muted) {
    audio.volume = state.savedVolume;
    volumeSlider.value = state.savedVolume;
    state.muted = false;
  } else {
    state.savedVolume = audio.volume;
    audio.volume = 0;
    volumeSlider.value = 0;
    state.muted = true;
  }
  updateVolumeIcon();
}

// ─── Sleep timer ──────────────────────────────────────────────────────────────
const SLEEP_TIMES = [5, 10, 15, 30, 45, 60, null]; // minutes, null = off

function updateSleepTimerDisplay() {
  if (!state.sleepTimerEnd) {
    sleepTimerBtn.innerHTML = icon("alarmclock");
    sleepTimerBtn.title = "Sleep timer";
    sleepTimerBtn.classList.remove("active");
    return;
  }
  const remaining = Math.ceil((state.sleepTimerEnd - Date.now()) / 60000);
  if (remaining <= 0) return;
  sleepTimerBtn.innerHTML = `${icon("alarmclock", 18)}<span class="sleep-time">${remaining}m</span>`;
  sleepTimerBtn.title = `Sleep timer: ${remaining} min remaining`;
  sleepTimerBtn.classList.add("active");
}

sleepTimerBtn.addEventListener("click", () => {
  const current = state.sleepTimerEnd ? Math.ceil((state.sleepTimerEnd - Date.now()) / 60000) : null;
  const currentIdx = SLEEP_TIMES.indexOf(current);
  const nextIdx = (currentIdx + 1) % SLEEP_TIMES.length;
  const next = SLEEP_TIMES[nextIdx];
  if (state.sleepTimer) {
    clearTimeout(state.sleepTimer);
    state.sleepTimer = null;
    state.sleepTimerEnd = null;
  }
  if (state.sleepTimerInterval) {
    clearInterval(state.sleepTimerInterval);
    state.sleepTimerInterval = null;
  }
  if (next !== null) {
    state.sleepTimerEnd = Date.now() + next * 60000;
    state.sleepTimer = setTimeout(() => {
      audio.pause();
      state.sleepTimer = null;
      state.sleepTimerEnd = null;
      if (state.sleepTimerInterval) {
        clearInterval(state.sleepTimerInterval);
        state.sleepTimerInterval = null;
      }
      updateSleepTimerDisplay();
      toast("Sleep timer ended — playback paused", "info");
    }, next * 60000);
    // Update remaining time display every second
    state.sleepTimerInterval = setInterval(updateSleepTimerDisplay, 1000);
    updateSleepTimerDisplay();
    toast(`Sleep timer: ${next} minutes`, "info");
  } else {
    updateSleepTimerDisplay();
    toast("Sleep timer off", "info");
  }
});

// ─── Format time ──────────────────────────────────────────────────────────────
function formatTime(seconds) {
  if (!isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ─── Session list ─────────────────────────────────────────────────────────────
async function loadSessionList() {
  try {
    sessionListSection.hidden = false;
    renderSessionListSkeleton();
    const response = await fetch("/sessions");
    if (!response.ok) {
      sessionList.innerHTML = "";
      renderErrorBoundary(sessionList, "Couldn't load library", `HTTP ${response.status}`, loadSessionList);
      return;
    }
    const data = await response.json();
    if (data.sessions.length === 0) {
      sessionListSection.hidden = true;
      return;
    }
    sessionList.innerHTML = "";
    data.sessions.forEach((session) => {
      const card = el("div", { className: "session-card" });
      const info = el("div", { className: "session-info" },
        el("div", { className: "session-title" }, session.title),
        el("div", { className: "session-meta" },
          `${session.completed_chapter_count}/${session.total_chapter_count} chapters · ${session.status}`)
      );
      const openBtn = el("button", {
        type: "button", className: "btn small",
        onClick: (e) => { e.stopPropagation(); openSession(session.session_id); }
      }, "Open");
      const delBtn = el("button", {
        type: "button", className: "btn small danger",
        onClick: async (e) => {
          e.stopPropagation();
          if (!confirm(`Delete "${session.title}"?`)) return;
          const r = await fetch(`/sessions/${session.session_id}`, { method: "DELETE" });
          if (!r.ok) {
            toast("Failed to delete session", "error");
            return;
          }
          loadSessionList();
          toast("Session deleted", "info");
        }
      }, "Delete");
      const actions = el("div", { className: "status-actions" }, openBtn, delBtn);
      card.append(info, actions);
      card.addEventListener("click", () => openSession(session.session_id));
      sessionList.appendChild(card);
    });
  } catch (err) {
    renderErrorBoundary(sessionList, "Couldn't load library", err.message, loadSessionList);
  }
}

async function openSession(sessionId) {
  try {
    // Show a reader skeleton if we'll be rendering the reader.
    uploadEbookSection.hidden = true;
    uploadAudioSection.hidden = true;
    renderReaderSkeleton();
    const response = await fetch(`/chapter-sessions/${sessionId}`);
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Failed to open session" }));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }
    const payload = await response.json();
    state.sessionId = sessionId;
    state.sessionPayload = payload;
    state.ebookChapters = payload.ebook_chapters;
    state.audioChapters = payload.audio_chapters;
    state.chapterStatuses = payload.chapter_statuses;
    state.completedChapters = payload.completed_chapters;
    state.chapterMappings = payload.chapter_mappings;
    updateStatusDisplay(payload);
    if (payload.status === "matching") {
      renderChapterGrid();
      chapterGridPanel.hidden = false;
    } else {
      if (["processing", "failed-partial"].includes(payload.status)) {
        renderChapterStatuses(payload);
        progressPanel.hidden = false;
        startListening();
      }
      // Show the reader as soon as any chapters are ready, even while
      // the rest are still processing.
      if (payload.completed_chapters?.length) {
        renderReader(payload);
      }
    }
    toast("Session opened", "success");
  } catch (err) {
    renderErrorBoundary(readerEl, "Couldn't open session", err.message, () => openSession(sessionId));
    toast(err.message, "error");
  }
}

newSessionBtn.addEventListener("click", () => {
  location.reload();
});

// ─── Clear session ────────────────────────────────────────────────────────────
clearSessionBtn.addEventListener("click", () => {
  if (state.sessionId && confirm("Delete this session and start over?")) {
    fetch(`/sessions/${state.sessionId}`, { method: "DELETE" }).then(() => location.reload());
  } else if (!state.sessionId) {
    location.reload();
  }
});

// ─── Global error handler ─────────────────────────────────────────────────────
window.addEventListener("error", (e) => {
  console.error("Unhandled error:", e.error);
  toast("An unexpected error occurred", "error");
});

window.addEventListener("unhandledrejection", (e) => {
  console.error("Unhandled promise rejection:", e.reason);
  toast(e.reason?.message || "Network error", "error");
});

// ─── Collapsible cards ───────────────────────────────────────────────────────
function initCollapsibleCards() {
  for (const btn of $$(".card-collapse-btn")) {
    const card = btn.closest(".card");
    if (!card?.id) continue;
    const collapsed = isCollapsed(card.id, localStorage);
    applyCollapsedState(card, btn, collapsed);
    btn.addEventListener("click", () => {
      const next = toggleCollapsed(card.id, localStorage);
      applyCollapsedState(card, btn, next);
    });
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────
initIcons();
initThemeSelector();
initSettings();
initCollapsibleCards();
updateVolumeIcon();
loadSessionList();
