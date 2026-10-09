/**
 * Acceptance helpers for WEB_UI_UX_IMPROVEMENT_PLAN (static checks).
 * Run: npx --yes tsx scripts/accept-uiux-static.ts
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

import {
  buildAnswerPreview,
  isLongAssistantAnswer,
  splitMarkdownBlocks,
} from "../lib/answer-preview";

const root = path.resolve(__dirname, "..");

function read(rel: string): string {
  return fs.readFileSync(path.join(root, rel), "utf8");
}

function mustInclude(rel: string, needles: string[], label: string) {
  const text = read(rel);
  for (const needle of needles) {
    assert.ok(text.includes(needle), `${label}: missing ${JSON.stringify(needle)} in ${rel}`);
  }
}

function mustNotInclude(rel: string, needles: string[], label: string) {
  const text = read(rel);
  for (const needle of needles) {
    assert.ok(!text.includes(needle), `${label}: unexpected ${JSON.stringify(needle)} in ${rel}`);
  }
}

// AC-01: answer preview / long collapse
{
  const short = "短答一行即可。";
  assert.equal(isLongAssistantAnswer(short), false);

  const longLines = Array.from({ length: 20 }, (_, i) => `第 ${i + 1} 段说明。`).join("\n\n");
  assert.equal(isLongAssistantAnswer(longLines), true);
  const preview = buildAnswerPreview(longLines);
  assert.ok(preview.remainingBlocks > 0, "long answer should leave remaining blocks");
  assert.ok(preview.preview.length < longLines.length, "preview shorter than full");

  const withTable =
    "前言\n\n" +
    Array.from({ length: 5 }, () => "| a | b |\n| - | - |\n| 1 | 2 |").join("\n\n");
  const blocks = splitMarkdownBlocks(withTable);
  assert.ok(blocks.length >= 2);
  console.log("AC-01 static: answer-preview OK");
}

// AC-03 / AC-14 layout contracts
{
  mustNotInclude(
    "app/globals.css",
    ["--app-page-max-width: 1600px", "max-width: 1440px", "max-width:1600px"],
    "AC-14",
  );
  mustInclude("app/globals.css", ["--app-page-max-width: 100%", "agent-composer"], "AC-03/14");
  mustInclude(
    "components/agent/AgentComposer.tsx",
    ["agent-composer", "Enter 发送", "Shift+Enter"],
    "AC-03",
  );
  console.log("AC-03/14 static: layout/composer OK");
}

// AC-06/07 focus & scroll hooks present
{
  mustInclude(
    "app/agent/page.tsx",
    ["stickToBottomRef", "sentSnapshotRef", "maybeRestoreComposerFocus", "AgentComposer"],
    "AC-04/06/07",
  );
  const agent = read("app/agent/page.tsx");
  assert.ok(
    !/scrollToBottom\(true\)[\s\S]{0,80}finally/.test(agent) ||
      agent.includes("scrollToBottom(false)"),
    "AC-07: terminal scroll should not unconditionally force",
  );
  console.log("AC-04/06/07 static: composer focus/scroll markers OK");
}

// AC-08/02 buttons not link-styled for manage actions
{
  mustNotInclude(
    "components/project/ProjectManagePanel.tsx",
    ['type="link"'],
    "AC-02/05",
  );
  mustInclude("components/project/ProjectForecastCard.tsx", ["重新加载", "去排期预览"], "AC-02/05");
  console.log("AC-02/05 static: button semantics OK");
}

// AC-09 mobile nav <= 5
{
  mustInclude(
    "lib/navigation.ts",
    ["getMobilePrimaryNav", "MORE_NAV_ITEM", "getMobileMoreNav"],
    "AC-09",
  );
  const nav = read("lib/navigation.ts");
  assert.ok(
    /return \[TASKS, PROJECTS, AGENT, NOTIFICATIONS, MORE_NAV_ITEM\]/.test(nav),
    "AC-09: primary mobile nav must be five items",
  );
  console.log("AC-09 static: mobile nav OK");
}

// AC-10/11 project detail resilience
{
  mustInclude(
    "app/projects/[id]/page.tsx",
    [
      "fetchAssignableUsers",
      "tasksError",
      "progressError",
      "summaryTimedOut",
      "compact",
      "选择负责人",
    ],
    "AC-10/11",
  );
  mustInclude("components/project/ProjectForecastCard.tsx", ["重新加载"], "AC-11");
  console.log("AC-10/11 static: project detail OK");
}

// AC-01 command plan / advice disclosure
{
  mustInclude(
    "components/agent/CommandPlanCard.tsx",
    ["ExplanationDisclosure", "successItems", "notableItems"],
    "AC-01",
  );
  mustInclude(
    "components/risk/AdviceCard.tsx",
    ["ExplanationDisclosure", "previewActions"],
    "AC-01",
  );
  mustInclude(
    "components/agent/MarkdownRenderer.tsx",
    ["md-link--internal", "md-link--external", "isInternalHref"],
    "AC-01/14 links",
  );
  console.log("AC-01 disclosure/links OK");
}

console.log("\nAll static acceptance checks passed.");
