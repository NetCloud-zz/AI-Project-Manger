#!/usr/bin/env python3
"""Browser acceptance for WEB_UI_UX_IMPROVEMENT_PLAN against local new build."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3010")
USER = os.environ.get("ACCEPT_USER", "admin")
PASS = os.environ.get("ACCEPT_PASS", "Admin@12345")
OUT = Path(__file__).resolve().parents[2] / "docs/assets/uiux-accept-2026-09-14"
OUT.mkdir(parents=True, exist_ok=True)

MEASURE_JS = """
() => {
  const main = document.querySelector('.app-main');
  const pageEl =
    document.querySelector('.page-container') ||
    document.querySelector('.agent-page-wrap') ||
    document.querySelector('.agent-page');
  const agent = document.querySelector('.agent-page');
  const composer = document.querySelector(
    '.agent-composer textarea, .agent-composer .ant-input'
  );
  const tabbar = document.querySelector('.app-tabbar');
  const tabItems = tabbar
    ? tabbar.querySelectorAll('.app-tabbar__item').length
    : 0;
  const mainBox = main && main.getBoundingClientRect();
  const pageBox = pageEl && pageEl.getBoundingClientRect();
  const agentBox = agent && agent.getBoundingClientRect();
  const composerBox = composer && composer.getBoundingClientRect();
  const overflow =
    document.documentElement.scrollWidth - document.documentElement.clientWidth;
  return {
    viewport: { w: window.innerWidth, h: window.innerHeight },
    mainWidth: mainBox ? mainBox.width : null,
    pageWidth: pageBox ? pageBox.width : null,
    pageRatio:
      mainBox && pageBox && mainBox.width > 0
        ? pageBox.width / mainBox.width
        : null,
    agentWidth: agentBox ? agentBox.width : null,
    composerWidth: composerBox ? composerBox.width : null,
    composerHeight: composerBox ? composerBox.height : null,
    tabItems,
    overflowX: overflow,
  };
}
"""


def login(page):
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.get_by_placeholder("admin / lisi / owner").fill(USER)
    page.locator('input[type="password"]').fill(PASS)
    # Ant Design inserts a space between CJK characters in button labels.
    page.locator('button[type="submit"]').click()
    page.wait_for_url("**/my-tasks**", timeout=20000)


def main() -> int:
    results = []
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # AC-14 / AC-03 desktop
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        login(page)
        page.goto(f"{BASE}/projects", wait_until="networkidle")
        m = page.evaluate(MEASURE_JS)
        m["tag"] = "projects-1920"
        results.append(m)
        page.screenshot(path=str(OUT / "projects-1920.png"), full_page=True)
        if m["pageRatio"] is not None and m["pageRatio"] < 0.9:
            failures.append(
                f"AC-14 projects 1920: page/main ratio {m['pageRatio']:.3f} < 0.90"
            )
        if m["overflowX"] > 1:
            failures.append(f"AC-08 projects 1920: overflowX={m['overflowX']}")

        page.goto(f"{BASE}/agent", wait_until="networkidle")
        time.sleep(0.8)
        a = page.evaluate(MEASURE_JS)
        a["tag"] = "agent-1920"
        results.append(a)
        page.screenshot(path=str(OUT / "agent-1920.png"), full_page=False)
        if a["agentWidth"] is not None and a["agentWidth"] <= 1440:
            failures.append(
                f"AC-14 agent 1920: agent width {a['agentWidth']:.0f} still ≤1440"
            )
        if a["composerWidth"] is not None and a["composerWidth"] < 400:
            failures.append(
                f"AC-03 agent 1920: composer too narrow {a['composerWidth']}"
            )
        if a["composerHeight"] is not None and a["composerHeight"] < 60:
            failures.append(
                f"AC-03 agent 1920: composer height {a['composerHeight']} looks single-line"
            )
        context.close()

        # AC-09 mobile
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
        )
        page = context.new_page()
        login(page)
        page.goto(f"{BASE}/agent", wait_until="networkidle")
        time.sleep(0.8)
        m = page.evaluate(MEASURE_JS)
        m["tag"] = "agent-390"
        results.append(m)
        page.screenshot(path=str(OUT / "agent-390.png"), full_page=False)
        if m["tabItems"] and m["tabItems"] != 5:
            failures.append(f"AC-09 mobile tabbar has {m['tabItems']} items (want 5)")
        if m["overflowX"] > 1:
            failures.append(f"AC-08 agent 390: overflowX={m['overflowX']}")
        if m["composerHeight"] is not None and m["composerHeight"] < 48:
            failures.append(f"AC-03 agent 390: composer height {m['composerHeight']}")
        more = page.locator(".app-tabbar__item", has_text="更多")
        if more.count() == 0:
            failures.append("AC-09: 更多 entry missing")
        else:
            more.first.click()
            time.sleep(0.3)
            page.screenshot(path=str(OUT / "agent-390-more.png"), full_page=False)
        context.close()

        # AC-02 / AC-11 project detail
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        login(page)
        page.goto(f"{BASE}/projects", wait_until="networkidle")
        link = page.locator('a[href^="/projects/"]').first
        if link.count() == 0:
            failures.append("AC-02: no project link found")
        else:
            href = link.get_attribute("href") or ""
            if href.rstrip("/") == "/projects" or href.rstrip("/").endswith("/new"):
                # pick a numeric project
                candidates = page.locator('a[href*="/projects/"]').all()
                picked = None
                for c in candidates:
                    h = c.get_attribute("href") or ""
                    if "/projects/" in h and h.rstrip("/").split("/")[-1].isdigit():
                        picked = c
                        break
                if picked is None:
                    failures.append("AC-02: no numeric project link")
                else:
                    picked.click()
            else:
                link.click()
            page.wait_for_url("**/projects/**", timeout=15000)
            time.sleep(1.0)
            header = page.evaluate(
                """() => {
                  const title = document.querySelector('.page-header__title')?.textContent?.trim();
                  const meta = document.querySelector('.page-header__meta')?.textContent?.trim();
                  const actionText = document.querySelector('.page-header__action')?.textContent || '';
                  return { title, meta, actionText };
                }"""
            )
            results.append({"tag": "project-header", **header})
            page.screenshot(path=str(OUT / "project-1440.png"), full_page=True)
            if not any(x in header["actionText"] for x in ("计划资料", "风险", "新建任务")):
                failures.append(
                    f"AC-02: header actions unexpected: {header['actionText']!r}"
                )
            new_task = page.get_by_role("button", name="新建任务")
            if new_task.count() > 0:
                new_task.click()
                time.sleep(0.4)
                if page.get_by_text("负责人 ID").count() > 0:
                    failures.append("AC-11: still showing 负责人 ID")
                if page.get_by_text("负责人", exact=True).count() == 0:
                    failures.append("AC-11: 负责人 label missing")
        context.close()
        browser.close()

    (OUT / "metrics.json").write_text(
        json.dumps({"base": BASE, "results": results, "failures": failures}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"results": results, "failures": failures}, indent=2, ensure_ascii=False))
    if failures:
        print(f"\nACCEPTANCE FAILED: {len(failures)} issue(s)", file=sys.stderr)
        return 1
    print("\nBrowser acceptance checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
