"""Evaluation case loading and placeholder rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MODES = frozenset({"intent", "agent"})


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    role: str
    prompt: str
    history: tuple[str, ...] = ()
    expect: dict[str, Any] = field(default_factory=dict)
    modes: frozenset[str] = MODES
    tags: tuple[str, ...] = ()

    def render(self, values: dict[str, Any]) -> EvalCase:
        return EvalCase(
            id=self.id,
            role=self.role,
            prompt=_fill(self.prompt, values),
            history=tuple(_fill(item, values) for item in self.history),
            expect=self.expect,
            modes=self.modes,
            tags=self.tags,
        )


def _fill(text: str, values: dict[str, Any]) -> str:
    out = text
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def _normalize_expect(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept the original OPT-11 keys alongside the current schema."""
    expect = dict(raw or {})
    if "mutation" in expect and "writes" not in expect:
        expect["writes"] = expect.pop("mutation")
    if "create_task_count" in expect:
        expect.setdefault("created", {})["task"] = expect.pop("create_task_count")
    if "min_persisted_tasks" in expect:
        expect.setdefault("min_created", {})["task"] = expect.pop("min_persisted_tasks")
    if expect.pop("task_count_unchanged", False):
        expect.setdefault("unchanged", []).append("task")
    expect.pop("policy", None)
    return expect


def load_cases(paths: list[Path]) -> list[EvalCase]:
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for path in paths:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for raw in payload.get("cases") or []:
            case_id = str(raw["id"])
            if case_id in seen:
                raise ValueError(f"Duplicate eval case id: {case_id}")
            seen.add(case_id)
            modes = frozenset(raw.get("modes") or MODES)
            if not modes <= MODES:
                raise ValueError(f"{case_id}: unknown modes {sorted(modes - MODES)}")
            cases.append(
                EvalCase(
                    id=case_id,
                    role=str(raw.get("role") or "PROJECT_OWNER"),
                    prompt=str(raw["prompt"]).strip(),
                    history=tuple(str(item).strip() for item in raw.get("history") or []),
                    expect=_normalize_expect(raw.get("expect") or {}),
                    modes=modes,
                    tags=tuple(raw.get("tags") or ()),
                )
            )
    return cases


def repair_fixture_cases(path: Path, layouts: list[str] | None = None) -> list[EvalCase]:
    """Render the 24-task + 1-milestone acceptance fixture into agent-mode cases."""
    fixture = yaml.safe_load(path.read_text(encoding="utf-8"))
    code = fixture["project_code"]
    groups = fixture["groups"]
    milestone = fixture["milestone"]
    expect = {
        "writes": True,
        "created": {
            "task": fixture["expect"]["task_count"],
            "milestone": fixture["expect"]["milestone_count"],
        },
    }
    chosen = layouts or [item["id"] for item in fixture.get("layouts") or []]
    renderers = {
        "markdown": _render_markdown,
        "flattened": lambda g, m: _render_markdown(g, m).replace("\n", " "),
        "prose": _render_prose,
        "table": _render_table,
        "json_text": _render_json,
    }
    cases = []
    for layout in chosen:
        body = renderers[layout](groups, milestone)
        cases.append(
            EvalCase(
                id=f"REPAIR24-{layout}",
                role="PROJECT_OWNER",
                prompt=f"在项目 {code} 中按以下清单创建任务和里程碑：\n{body}",
                expect=expect,
                modes=frozenset({"agent"}),
                tags=("repair24", layout),
            )
        )
    return cases


def _task_line(task: dict[str, Any]) -> str:
    parts = [task["name"], f"负责人 {task.get('owner_name') or '待定'}"]
    if task.get("collaborator_names"):
        parts.append("协作 " + "、".join(task["collaborator_names"]))
    if task.get("planned_duration_days"):
        parts.append(f"工期 {task['planned_duration_days']} 天")
    if task.get("start_date"):
        parts.append(f"开始 {task['start_date']}")
    if task.get("due_date"):
        parts.append(f"截止 {task['due_date']}")
    return " —— ".join(parts)


def _milestone_line(milestone: dict[str, Any]) -> str:
    return (
        f"里程碑：{milestone['name']}，目标日期 {milestone['target_date']}，"
        f"负责人 {milestone['owner_name']}"
    )


def _render_markdown(groups: list[dict[str, Any]], milestone: dict[str, Any]) -> str:
    lines: list[str] = []
    for group in groups:
        lines.append(f"## {group['work_stream']}")
        lines += [f"{index}. {_task_line(task)}" for index, task in enumerate(group["tasks"], 1)]
    lines.append(_milestone_line(milestone))
    return "\n".join(lines)


def _render_prose(groups: list[dict[str, Any]], milestone: dict[str, Any]) -> str:
    paragraphs = []
    for group in groups:
        items = "；".join(_task_line(task).replace(" —— ", "，") for task in group["tasks"])
        paragraphs.append(f"{group['work_stream']}包括：{items}。")
    paragraphs.append(_milestone_line(milestone) + "。")
    return "\n".join(paragraphs)


def _render_table(groups: list[dict[str, Any]], milestone: dict[str, Any]) -> str:
    rows = [
        "| 阶段 | 任务 | 负责人 | 协作 | 工期(天) | 开始 | 截止 |",
        "|---|---|---|---|---|---|---|",
    ]
    for group in groups:
        for task in group["tasks"]:
            rows.append(
                "| {ws} | {name} | {owner} | {collab} | {days} | {start} | {due} |".format(
                    ws=group["work_stream"],
                    name=task["name"],
                    owner=task.get("owner_name") or "待定",
                    collab="、".join(task.get("collaborator_names") or []),
                    days=task.get("planned_duration_days") or "",
                    start=task.get("start_date") or "",
                    due=task.get("due_date") or "",
                )
            )
    return "\n".join(rows) + "\n" + _milestone_line(milestone)


def _render_json(groups: list[dict[str, Any]], milestone: dict[str, Any]) -> str:
    return json.dumps({"groups": groups, "milestone": milestone}, ensure_ascii=False, indent=2)
