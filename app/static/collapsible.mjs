// Pure state helpers for collapsible cards. No DOM access — callers pass in a
// storage-like object ({ getItem, setItem, removeItem }) so these functions stay
// trivially unit-testable in Node without jsdom.

const PREFIX = "bookamine.card";

/** Build the localStorage key for a card's collapsed flag. */
export function storageKey(cardId) {
  return `${PREFIX}.${cardId}.collapsed`;
}

/** Read whether a card is collapsed. Missing value = expanded (default). */
export function isCollapsed(cardId, storage) {
  return storage.getItem(storageKey(cardId)) === "1";
}

/** Persist the collapsed flag. Removes the key when expanding (falsy = clean state). */
export function setCollapsed(cardId, collapsed, storage) {
  const key = storageKey(cardId);
  if (collapsed) storage.setItem(key, "1");
  else storage.removeItem(key);
}

/** Toggle and persist; returns the new collapsed state. */
export function toggleCollapsed(cardId, storage) {
  const next = !isCollapsed(cardId, storage);
  setCollapsed(cardId, next, storage);
  return next;
}

/** Screen-reader-friendly label for the collapse button. */
export function ariaLabel(title, collapsed) {
  return `${collapsed ? "Expand" : "Collapse"} ${title}`;
}

/**
 * Apply the collapsed visual/ARIA state to a card element and its toggle button.
 * Accepts any objects with `classList.toggle` and `setAttribute` — works with real
 * DOM nodes in the browser and lightweight stubs in tests.
 */
export function applyCollapsedState(cardEl, buttonEl, collapsed) {
  cardEl.classList.toggle("collapsed", collapsed);
  buttonEl.setAttribute("aria-expanded", String(!collapsed));
  buttonEl.setAttribute("aria-label", ariaLabel(buttonEl.dataset.title || "", collapsed));
}
