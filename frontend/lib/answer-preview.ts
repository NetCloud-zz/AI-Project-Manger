/**
 * Helpers for collapsing long assistant Markdown without mid-block cuts.
 */

const LONG_CHAR_THRESHOLD = 800;
const LONG_LINE_THRESHOLD = 12;
const PREVIEW_CHAR_BUDGET = 520;

export function isLongAssistantAnswer(content: string): boolean {
  const nonEmptyLines = content.split("\n").filter((line) => line.trim()).length;
  return content.length > LONG_CHAR_THRESHOLD || nonEmptyLines > LONG_LINE_THRESHOLD;
}

function isTableOrFenceBlock(block: string): boolean {
  const trimmed = block.trimStart();
  return trimmed.startsWith("|") || trimmed.startsWith("```") || trimmed.startsWith("~~~");
}

/** Split Markdown into blocks on blank lines; keep fences/tables intact. */
export function splitMarkdownBlocks(content: string): string[] {
  const normalized = content.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];
  const blocks: string[] = [];
  let current: string[] = [];
  let inFence = false;

  for (const line of normalized.split("\n")) {
    if (/^(`{3,}|~{3,})/.test(line.trimStart())) {
      inFence = !inFence;
      current.push(line);
      continue;
    }
    if (!inFence && line.trim() === "" && current.length > 0) {
      blocks.push(current.join("\n"));
      current = [];
      continue;
    }
    current.push(line);
  }
  if (current.length > 0) blocks.push(current.join("\n"));
  return blocks;
}

export function buildAnswerPreview(content: string): {
  preview: string;
  remainingBlocks: number;
} {
  const blocks = splitMarkdownBlocks(content);
  if (blocks.length <= 1 && !isLongAssistantAnswer(content)) {
    return { preview: content, remainingBlocks: 0 };
  }

  const chosen: string[] = [];
  let chars = 0;
  for (const block of blocks) {
    const nextLen = block.length + (chosen.length ? 2 : 0);
    if (chosen.length > 0 && chars + nextLen > PREVIEW_CHAR_BUDGET) {
      // Prefer not to start a large table/fence in the preview if budget is gone.
      if (isTableOrFenceBlock(block) && block.length > 200) break;
      if (chars >= PREVIEW_CHAR_BUDGET * 0.6) break;
    }
    // Cap preview depth so long answers with many short paragraphs still collapse.
    if (chosen.length >= 4 && isLongAssistantAnswer(content)) break;
    chosen.push(block);
    chars += nextLen;
    if (chars >= PREVIEW_CHAR_BUDGET && chosen.length >= 1) break;
  }

  if (chosen.length === 0 && blocks[0]) {
    chosen.push(blocks[0]);
  }

  // If the whole answer is long but still fit the budget, keep roughly half.
  if (
    isLongAssistantAnswer(content) &&
    chosen.length === blocks.length &&
    blocks.length > 1
  ) {
    const keep = Math.max(1, Math.ceil(blocks.length / 2));
    return {
      preview: blocks.slice(0, keep).join("\n\n"),
      remainingBlocks: blocks.length - keep,
    };
  }

  const remainingBlocks = Math.max(0, blocks.length - chosen.length);
  return {
    preview: chosen.join("\n\n"),
    remainingBlocks,
  };
}
