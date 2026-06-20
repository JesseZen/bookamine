import test from "node:test";
import assert from "node:assert/strict";

import { buildBlockSegments } from "../app/static/reader_render.mjs";

test("buildBlockSegments preserves punctuation around ebook words", () => {
  const block = {
    text: "\"Hello,\" don't stop.",
    word_indexes: [0, 1, 2],
  };
  const wordsByIndex = new Map([
    [0, { index: 0, start_ms: 0 }],
    [1, { index: 1, start_ms: 250 }],
    [2, { index: 2, start_ms: 500 }],
  ]);

  assert.deepEqual(buildBlockSegments(block, wordsByIndex), [
    { type: "text", text: "\"" },
    { type: "word", text: "Hello", wordIndex: 0, startMs: 0 },
    { type: "text", text: ",\" " },
    { type: "word", text: "don't", wordIndex: 1, startMs: 250 },
    { type: "text", text: " " },
    { type: "word", text: "stop", wordIndex: 2, startMs: 500 },
    { type: "text", text: "." },
  ]);
});

test("buildBlockSegments keeps repeated words in order", () => {
  const block = {
    text: "Go, go!",
    word_indexes: [0, 1],
  };
  const wordsByIndex = new Map([
    [0, { index: 0, start_ms: 0 }],
    [1, { index: 1, start_ms: 300 }],
  ]);

  assert.deepEqual(buildBlockSegments(block, wordsByIndex), [
    { type: "word", text: "Go", wordIndex: 0, startMs: 0 },
    { type: "text", text: ", " },
    { type: "word", text: "go", wordIndex: 1, startMs: 300 },
    { type: "text", text: "!" },
  ]);
});
