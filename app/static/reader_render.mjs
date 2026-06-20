const WORD_PATTERN = /[A-Za-z]+(?:'[A-Za-z]+)?/g;

export function buildBlockSegments(block, wordsByIndex) {
  const segments = [];
  let cursor = 0;
  let blockWordOffset = 0;
  for (const match of block.text.matchAll(WORD_PATTERN)) {
    if (match.index > cursor) {
      segments.push({ type: "text", text: block.text.slice(cursor, match.index) });
    }
    const wordIndex = block.word_indexes[blockWordOffset];
    const word = wordsByIndex.get(wordIndex);
    segments.push({
      type: "word",
      text: match[0],
      wordIndex: word.index,
      startMs: word.start_ms,
    });
    cursor = match.index + match[0].length;
    blockWordOffset += 1;
  }
  if (cursor < block.text.length) {
    segments.push({ type: "text", text: block.text.slice(cursor) });
  }
  return segments;
}
