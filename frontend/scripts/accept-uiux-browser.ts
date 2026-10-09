/**
 * Browser acceptance for WEB_UI_UX_IMPROVEMENT_PLAN against the local new build.
 * Usage: BASE_URL=http://127.0.0.1:3010 npx playwright test --config=scripts/accept-uiux.playwright.config.ts
 * Or run this file with: BASE_URL=http://127.0.0.1:3010 npx --yes tsx scripts/accept-uiux-browser.ts
 */
import { chromium, type Page } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:3010";
const USER = process.env.ACCEPT_USER ?? "admin";
const PASS = process.env.ACCEPT_PASS ?? "Admin@12345";
const outDir = path.resolve(__dirname, "../../docs/assets/uiux-accept-2026-09-14");

async function login(page: Page) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await page.getByPlaceholder("admin / lisi / owner").fill(USER);
  await page.locator('input[type="password"]').fill(PASS);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL(/\/(my-tasks|projects|agent|$)/, { timeout: 20_000 });
}

async function measureShell(page: Page, label: string) {
  return page.evaluate((tag) => {
    const main = document.querySelector(".app-main") as HTMLElement | null;
    const pageEl =
      (document.querySelector(".page-container") as HTMLElement | null) ??
      (document.querySelector(".agent-page-wrap") as HTMLElement | null) ??
      (document.querySelector(".agent-page") as HTMLElement | null);
    const agent = document.querySelector(".agent-page") as HTMLElement | null;
    const composer = document.querySelector(
      ".agent-composer textarea, .agent-composer .ant-input",
    ) as HTMLElement | null;
    const tabbar = document.querySelector(".app-tabbar") as HTMLElement | null;
    const tabItems = tabbar
      ? Array.from(tabbar.querySelectorAll(".app-tabbar__item")).length
      : 0;
    const mainBox = main?.getBoundingClientRect();
    const pageBox = pageEl?.getBoundingClientRect();
    const agentBox = agent?.getBoundingClientRect();
    const composerBox = composer?.getBoundingClientRect();
    const overflow =
      document.documentElement.scrollWidth - document.documentElement.clientWidth;
    return {
      tag,
      viewport: { w: window.innerWidth, h: window.innerHeight },
      mainWidth: mainBox?.width ?? null,
      pageWidth: pageBox?.width ?? null,
      pageRatio:
        mainBox && pageBox && mainBox.width > 0 ? pageBox.width / mainBox.width : null,
      agentWidth: agentBox?.width ?? null,
      composerWidth: composerBox?.width ?? null,
      composerHeight: composerBox?.height ?? null,
      tabItems,
      overflowX: overflow,
    };
  }, label);
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const results: unknown[] = [];
  const failures: string[] = [];

  try {
    // AC-14 large desktop layout
    {
      const context = await browser.newContext({
        viewport: { width: 1920, height: 1080 },
      });
      const page = await context.newPage();
      await login(page);
      await page.goto(`${BASE}/projects`, { waitUntil: "networkidle" });
      const m = await measureShell(page, "projects-1920");
      results.push(m);
      await page.screenshot({
        path: path.join(outDir, "projects-1920.png"),
        fullPage: true,
      });
      if (m.pageRatio != null && m.pageRatio < 0.9) {
        failures.push(
          `AC-14 projects 1920: page/main ratio ${m.pageRatio.toFixed(3)} < 0.90`,
        );
      }
      if (m.overflowX > 1) {
        failures.push(`AC-08 projects 1920: overflowX=${m.overflowX}`);
      }

      await page.goto(`${BASE}/agent`, { waitUntil: "networkidle" });
      await page.waitForTimeout(800);
      const a = await measureShell(page, "agent-1920");
      results.push(a);
      await page.screenshot({
        path: path.join(outDir, "agent-1920.png"),
        fullPage: false,
      });
      if (a.agentWidth != null && a.agentWidth > 0 && a.agentWidth < 1500) {
        // Old cap was 1440; new build should grow on 1920 (~1680 content).
        // Allow some chrome: require > 1440.
        failures.push(
          `AC-14 agent 1920: agent width ${a.agentWidth.toFixed(0)} still looks capped (≤1440 expected old)`,
        );
      }
      if (a.composerWidth != null && a.agentWidth != null) {
        const ratio = a.composerWidth / a.agentWidth;
        // composer is inside main column; just ensure it's reasonably wide
        if (a.composerWidth < 400) {
          failures.push(`AC-03 agent 1920: composer too narrow ${a.composerWidth}`);
        }
        results.push({ composerToAgent: ratio });
      }
      if (a.composerHeight != null && a.composerHeight < 60) {
        failures.push(
          `AC-03 agent 1920: composer height ${a.composerHeight} suggests single-line input`,
        );
      }
      await context.close();
    }

    // AC-09 / AC-03 mobile
    {
      const context = await browser.newContext({
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      });
      const page = await context.newPage();
      await login(page);
      await page.goto(`${BASE}/agent`, { waitUntil: "networkidle" });
      await page.waitForTimeout(800);
      const m = await measureShell(page, "agent-390");
      results.push(m);
      await page.screenshot({
        path: path.join(outDir, "agent-390.png"),
        fullPage: false,
      });
      if (m.tabItems > 0 && m.tabItems > 5) {
        failures.push(`AC-09 mobile tabbar has ${m.tabItems} items (>5)`);
      }
      if (m.tabItems > 0 && m.tabItems < 5) {
        failures.push(`AC-09 mobile tabbar has ${m.tabItems} items (<5 primary)`);
      }
      if (m.overflowX > 1) {
        failures.push(`AC-08 agent 390: overflowX=${m.overflowX}`);
      }
      // Composer should be multi-line-ish on mobile (minRows 2)
      if (m.composerHeight != null && m.composerHeight < 48) {
        failures.push(`AC-03 agent 390: composer height ${m.composerHeight}`);
      }

      // Check more drawer exists
      const more = page.getByRole("button", { name: /更多/ }).or(
        page.locator('.app-tabbar__item', { hasText: "更多" }),
      );
      assert.ok((await more.count()) > 0, "AC-09: 更多 entry missing");
      await more.first().click();
      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(outDir, "agent-390-more.png"),
        fullPage: false,
      });
      await context.close();
    }

    // AC-02 / AC-10 project detail header order (use first project link)
    {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
      });
      const page = await context.newPage();
      await login(page);
      await page.goto(`${BASE}/projects`, { waitUntil: "networkidle" });
      const link = page.locator('a[href^="/projects/"]').first();
      if ((await link.count()) === 0) {
        failures.push("AC-02: no project link found to open detail");
      } else {
        await link.click();
        await page.waitForURL(/\/projects\/\d+/, { timeout: 15_000 });
        await page.waitForTimeout(1000);
        const header = await page.evaluate(() => {
          const title = document.querySelector(".page-header__title")?.textContent?.trim();
          const meta = document.querySelector(".page-header__meta")?.textContent?.trim();
          const actionText = document.querySelector(".page-header__action")?.textContent ?? "";
          const hasOwnerSelectLabel = Array.from(
            document.querySelectorAll("label, .ant-form-item-label"),
          ).some((el) => (el.textContent ?? "").includes("负责人"));
          return { title, meta, actionText, hasOwnerSelectLabel };
        });
        results.push({ projectHeader: header });
        await page.screenshot({
          path: path.join(outDir, "project-1440.png"),
          fullPage: true,
        });
        if (header.meta && header.title && header.meta.includes(header.title)) {
          // title should be name, meta code — if equal something wrong
        }
        if (!/计划资料|风险|新建任务/.test(header.actionText)) {
          failures.push(
            `AC-02/09: page header actions missing expected entries: ${header.actionText}`,
          );
        }
        // Open new task form if button exists
        const newTask = page.getByRole("button", { name: "新建任务" });
        if ((await newTask.count()) > 0) {
          await newTask.click();
          await page.waitForTimeout(400);
          const ownerIdLabel = page.getByText("负责人 ID");
          if ((await ownerIdLabel.count()) > 0) {
            failures.push("AC-11: still showing 负责人 ID instead of Select");
          }
          const ownerLabel = page.getByText("负责人", { exact: true });
          if ((await ownerLabel.count()) === 0) {
            failures.push("AC-11: 负责人 select label missing");
          }
        }
      }
      await context.close();
    }
  } finally {
    await browser.close();
  }

  fs.writeFileSync(
    path.join(outDir, "metrics.json"),
    JSON.stringify({ base: BASE, results, failures }, null, 2),
  );

  console.log(JSON.stringify({ results, failures }, null, 2));
  if (failures.length) {
    console.error(`\nACCEPTANCE FAILED: ${failures.length} issue(s)`);
    process.exit(1);
  }
  console.log("\nBrowser acceptance checks passed.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
