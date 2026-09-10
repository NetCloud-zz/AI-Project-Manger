"""Report data gaps that make scheduling or forecasting unreliable.

Usage:
    python -m app.scripts.check_data_integrity
    python -m app.scripts.check_data_integrity --project PRJ-1001
    python -m app.scripts.check_data_integrity --json > report.json

Exits with 1 when any BLOCKING finding remains, so a pilot readiness gate can
call it directly. The script only reads; nothing is repaired automatically
because every fix here is a statement of fact that a person has to make.
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.models.project import Project
from app.services.data_integrity import BLOCKING, DataIntegrityService, Finding, summarise


def _print_report(findings: list[Finding]) -> None:
    if not findings:
        print("未发现数据完整性问题。")
        return
    by_project: dict[str, list[Finding]] = {}
    for finding in findings:
        by_project.setdefault(finding.project_code, []).append(finding)
    for code, items in by_project.items():
        print(f"\n项目 {code}")
        for item in sorted(items, key=lambda f: (f.severity != BLOCKING, f.code)):
            marker = "阻断" if item.severity == BLOCKING else "警告"
            print(f"  [{marker}] {item.title}（{item.count}）  {item.code}")
            print(f"         处理：{item.remedy}")
            if item.sample:
                shown = ", ".join(str(value) for value in item.sample)
                more = "" if item.count <= len(item.sample) else " …"
                print(f"         样例：{shown}{more}")
    summary = summarise(findings)
    print(f"\n合计 {summary['total']} 项：阻断 {summary['blocking']}，警告 {summary['warning']}。")
    if summary["projects_with_blocking"]:
        print("存在阻断项的项目：" + ", ".join(summary["projects_with_blocking"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="数据完整性检查")
    parser.add_argument("--project", help="仅检查指定项目编号（project_code）")
    parser.add_argument("--include-closed", action="store_true", help="包含已完成/已取消项目")
    parser.add_argument("--json", action="store_true", help="输出 JSON 便于归档")
    args = parser.parse_args()

    configure_logging()
    with SessionLocal() as db:
        service = DataIntegrityService(db)
        if args.project:
            project = db.scalar(select(Project).where(Project.project_code == args.project))
            if project is None:
                print(f"项目 {args.project} 不存在", file=sys.stderr)
                return 2
            findings = service.check_project(project)
        else:
            findings = service.check_all(include_closed=args.include_closed)

    if args.json:
        print(json.dumps(summarise(findings), ensure_ascii=False, indent=2))
    else:
        _print_report(findings)
    return 1 if any(item.severity == BLOCKING for item in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
