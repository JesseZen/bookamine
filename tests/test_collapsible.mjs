import test from "node:test";
import assert from "node:assert/strict";

import {
  storageKey,
  isCollapsed,
  setCollapsed,
  toggleCollapsed,
  ariaLabel,
  applyCollapsedState,
} from "../app/static/collapsible.mjs";

// Minimal localStorage stub: behaves like the real thing for our purposes.
function makeStorage() {
  const store = new Map();
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    _store: store,
  };
}

// Minimal DOM stubs for applyCollapsedState.
function makeStub() {
  const classes = new Set();
  const attrs = new Map();
  return {
    classList: {
      toggle: (cls, force) => {
        if (force === undefined) return classes.delete(cls);
        if (force) classes.add(cls);
        else classes.delete(cls);
        return force;
      },
      contains: (cls) => classes.has(cls),
    },
    setAttribute: (k, v) => attrs.set(k, String(v)),
    getAttribute: (k) => (attrs.has(k) ? attrs.get(k) : null),
    dataset: {},
    _classes: classes,
    _attrs: attrs,
  };
}

// ─── storageKey ──────────────────────────────────────────────────────────────

test("storageKey follows the bookamine.card.<id>.collapsed convention", () => {
  assert.equal(storageKey("reader-panel"), "bookamine.card.reader-panel.collapsed");
  assert.equal(storageKey("a"), "bookamine.card.a.collapsed");
});

// ─── isCollapsed ─────────────────────────────────────────────────────────────

test("isCollapsed returns false when no value is stored (default expanded)", () => {
  const storage = makeStorage();
  assert.equal(isCollapsed("reader-panel", storage), false);
});

test("isCollapsed returns true only when the stored value is '1'", () => {
  const storage = makeStorage();
  storage.setItem(storageKey("reader-panel"), "1");
  assert.equal(isCollapsed("reader-panel", storage), true);
});

test("isCollapsed treats any non-'1' value as expanded", () => {
  const storage = makeStorage();
  storage.setItem(storageKey("x"), "0");
  assert.equal(isCollapsed("x", storage), false);
  storage.setItem(storageKey("x"), "true");
  assert.equal(isCollapsed("x", storage), false);
  storage.setItem(storageKey("x"), "");
  assert.equal(isCollapsed("x", storage), false);
});

// ─── setCollapsed ────────────────────────────────────────────────────────────

test("setCollapsed(true) writes '1' under the storage key", () => {
  const storage = makeStorage();
  setCollapsed("reader-panel", true, storage);
  assert.equal(storage._store.get(storageKey("reader-panel")), "1");
});

test("setCollapsed(false) removes the key so storage stays clean", () => {
  const storage = makeStorage();
  setCollapsed("reader-panel", true, storage);
  setCollapsed("reader-panel", false, storage);
  assert.equal(storage._store.has(storageKey("reader-panel")), false);
});

// ─── toggleCollapsed ─────────────────────────────────────────────────────────

test("toggleCollapsed flips expanded → collapsed and persists", () => {
  const storage = makeStorage();
  const afterFirst = toggleCollapsed("chapter-grid-panel", storage);
  assert.equal(afterFirst, true);
  assert.equal(isCollapsed("chapter-grid-panel", storage), true);
});

test("toggleCollapsed flips collapsed → expanded and clears the key", () => {
  const storage = makeStorage();
  setCollapsed("chapter-grid-panel", true, storage);
  const afterSecond = toggleCollapsed("chapter-grid-panel", storage);
  assert.equal(afterSecond, false);
  assert.equal(isCollapsed("chapter-grid-panel", storage), false);
  assert.equal(storage._store.has(storageKey("chapter-grid-panel")), false);
});

test("toggleCollapsed is idempotent over two full cycles", () => {
  const storage = makeStorage();
  assert.equal(toggleCollapsed("x", storage), true);
  assert.equal(toggleCollapsed("x", storage), false);
  assert.equal(toggleCollapsed("x", storage), true);
  assert.equal(toggleCollapsed("x", storage), false);
});

test("toggleCollapsed keeps each card's state independent", () => {
  const storage = makeStorage();
  toggleCollapsed("a", storage);
  toggleCollapsed("a", storage);
  toggleCollapsed("b", storage);
  assert.equal(isCollapsed("a", storage), false);
  assert.equal(isCollapsed("b", storage), true);
});

// ─── ariaLabel ───────────────────────────────────────────────────────────────

test("ariaLabel says 'Collapse <title>' when expanded", () => {
  assert.equal(ariaLabel("Library", false), "Collapse Library");
});

test("ariaLabel says 'Expand <title>' when collapsed", () => {
  assert.equal(ariaLabel("Library", true), "Expand Library");
});

// ─── applyCollapsedState ─────────────────────────────────────────────────────

test("applyCollapsedState adds 'collapsed' class and sets aria-expanded=false when collapsing", () => {
  const card = makeStub();
  const btn = makeStub();
  btn.dataset.title = "Reader";
  applyCollapsedState(card, btn, true);
  assert.equal(card._classes.has("collapsed"), true);
  assert.equal(btn.getAttribute("aria-expanded"), "false");
  assert.equal(btn.getAttribute("aria-label"), "Expand Reader");
});

test("applyCollapsedState removes 'collapsed' class and sets aria-expanded=true when expanding", () => {
  const card = makeStub();
  const btn = makeStub();
  btn.dataset.title = "Reader";
  card._classes.add("collapsed");
  applyCollapsedState(card, btn, false);
  assert.equal(card._classes.has("collapsed"), false);
  assert.equal(btn.getAttribute("aria-expanded"), "true");
  assert.equal(btn.getAttribute("aria-label"), "Collapse Reader");
});

test("applyCollapsedState handles a missing data-title gracefully", () => {
  const card = makeStub();
  const btn = makeStub(); // no dataset.title
  applyCollapsedState(card, btn, true);
  assert.equal(btn.getAttribute("aria-label"), "Expand ");
});

test("applyCollapsedState is idempotent when called with the same state twice", () => {
  const card = makeStub();
  const btn = makeStub();
  btn.dataset.title = "Progress";
  applyCollapsedState(card, btn, true);
  applyCollapsedState(card, btn, true);
  assert.equal(card._classes.has("collapsed"), true);
  assert.equal(btn.getAttribute("aria-expanded"), "false");
  assert.equal(btn.getAttribute("aria-label"), "Expand Progress");
});

// ─── Round-trip: persist + restore simulates a page refresh ──────────────────

test("state survives a simulated page refresh (storage outlives the DOM)", () => {
  const storage = makeStorage();
  // Simulate user collapsing the reader panel.
  setCollapsed("reader-panel", true, storage);

  // Simulate a fresh page load: new DOM nodes, same storage.
  const card = makeStub();
  const btn = makeStub();
  btn.dataset.title = "Reader";
  const restored = isCollapsed("reader-panel", storage);
  applyCollapsedState(card, btn, restored);

  assert.equal(restored, true);
  assert.equal(card._classes.has("collapsed"), true);
  assert.equal(btn.getAttribute("aria-expanded"), "false");
});
