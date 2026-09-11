"""Validated planning protocol. Planning itself never executes a business tool."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CommandItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    tool: str = Field(min_length=1, max_length=100)
    source_text: str = Field(min_length=1)
    source_start: int | None = Field(default=None, ge=0)
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class CommandPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: Literal["independent", "atomic"] = "independent"
    # Legacy model-generated counts are accepted but never trusted as an oracle.
    expected_count: int | None = Field(default=None, ge=0)
    items: list[CommandItemInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def ignore_legacy_count(cls, value: Any) -> Any:
        if isinstance(value, dict) and "expected_count" in value:
            return {**value, "expected_count": None}
        return value

    @model_validator(mode="after")
    def graph_valid(self) -> CommandPlanInput:
        self.expected_count = len(self.items)
        ids = [i.item_id for i in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("item_id 不得重复")
        graph = {i.item_id: set(i.depends_on) for i in self.items}
        for item in self.items:
            if not graph[item.item_id] <= set(ids) or item.item_id in graph[item.item_id]:
                raise ValueError("依赖引用不存在或指向自己")
            for ref in references(item.arguments):
                if ref.split(".")[0] not in graph[item.item_id]:
                    raise ValueError("结果引用必须在 depends_on 中声明")
        visited: set[str] = set()
        while len(visited) < len(graph):
            ready = {key for key, deps in graph.items() if key not in visited and deps <= visited}
            if not ready:
                raise ValueError("指令依赖有环")
            visited |= ready
        return self


def references(value: Any) -> list[str]:
    if isinstance(value, dict):
        if "$ref" in value:
            if set(value) != {"$ref"} or not isinstance(value["$ref"], str):
                raise ValueError('引用格式必须为 {"$ref": "item_id.field.path"}')
            return [value["$ref"]]
        return [ref for v in value.values() for ref in references(v)]
    if isinstance(value, list):
        return [ref for v in value for ref in references(v)]
    return []


def requires_atomic(source: str) -> bool:
    return bool(
        re.search(
            r"要么|全成全败|全部成功.*(?:否则|才)|全部回滚|一个也不|原子(?:批次|执行)", source
        )
    )


def validate_coverage(plan: CommandPlanInput, source: str) -> list[tuple[int, int]]:
    """Exact quotes plus declared counts/numbered requirements; never guess missing items."""
    if requires_atomic(source) and plan.policy != "atomic":
        raise ValueError("用户要求全成全败，不能使用独立提交策略")
    spans = []
    for item in plan.items:
        start = (
            item.source_start if item.source_start is not None else source.find(item.source_text)
        )
        end = start + len(item.source_text)
        if start < 0 or source[start:end] != item.source_text:
            raise ValueError(f"{item.item_id} 的原文映射不匹配")
        spans.append((start, end))
    counts = re.findall(
        r"(?:创建|新增|新建)(?:以下|这|共|总共|分别|恰好|正好)?\s*(\d+)\s*(?:个|条|项)?(?:独立)?(?:执行)?(?:的)?任务",
        source,
    )
    batch_tools = {"draft_project_plan", "batch_create_tasks", "batch_update_tasks", "apply_project_plan"}
    created = sum(i.tool == "create_task" for i in plan.items)
    if counts and created != sum(int(n) for n in counts) and not any(
        i.tool in batch_tools for i in plan.items
    ):
        raise ValueError("任务创建数量与用户明确要求的 N 不一致，尚有遗漏或额外动作")
    # One numbered requirement needs its own mapped item. Quoting the whole
    # request once must not conceal omitted lines or duplicate one line N times.
    # A single batch tool may cover many numbered lines.
    requirements = source_requirements(source)
    if requirements and any(item.tool in batch_tools for item in plan.items):
        covered = set()
        for item, (start, end) in zip(plan.items, spans, strict=True):
            if item.tool not in batch_tools:
                continue
            for index, req in enumerate(requirements):
                if start <= req["start"] and end >= req["end"]:
                    covered.add(index)
        if len(covered) == len(requirements):
            return spans
    matched: dict[int, int] = {}

    def assign(index: int, visited: set[int]) -> bool:
        requirement = requirements[index]
        for item_index, (start, end) in enumerate(spans):
            if sum(start <= r["start"] and end >= r["end"] for r in requirements) != 1:
                continue
            if item_index in visited or not (
                start <= requirement["end"] and end >= requirement["start"]
            ):
                continue
            # Require the complete numbered content, not a shared word.
            if not (start <= requirement["start"] and end >= requirement["end"]):
                continue
            visited.add(item_index)
            if item_index not in matched or assign(matched[item_index], visited):
                matched[item_index] = index
                return True
        return False

    missing = [
        r["requirement_id"] for index, r in enumerate(requirements) if not assign(index, set())
    ]
    if missing:
        raise ValueError("编号指令缺少独立执行项：" + "、".join(missing))
    return spans


def source_requirements(source: str) -> list[dict[str, Any]]:
    return [
        {
            "requirement_id": f"r{index}",
            "text": match.group(1),
            "start": match.start(1),
            "end": match.end(1),
        }
        for index, match in enumerate(
            re.finditer(r"(?m)^[ \t]*(?:\d+[.、）)]|[-*])[ \t]*(\S[^\n]*)", source), 1
        )
    ]


def missing_source_fields(source: str) -> list[str]:
    """Task owners marked TBD may stay empty; project still needs a real owner/code."""
    from app.core.owner_labels import has_project_pending_owner_line

    questions = []
    if has_project_pending_owner_line(source):
        questions.append("请补充项目负责人")
    # Accept: explicit 项目编号/代码, PRJ-1001 style, or code-like token in 项目：NLRP3 …
    if re.search(r"(?m)^\s*项目[：:]", source) and not re.search(
        r"(?m)^\s*项目(?:编号|代码)[：:][ \t]*[A-Za-z0-9][A-Za-z0-9_-]*"
        r"|^\s*项目[：:][^\n]*\b[A-Z][A-Z0-9]*-\d+\b"
        r"|^\s*项目[：:][ \t]*[A-Za-z][A-Za-z0-9_-]{1,31}\b",
        source,
    ):
        questions.append("请提供新项目的唯一项目代码（例如 PRJ-1001）")
    return questions


class CommandRetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    item_ids: list[str] = Field(min_length=1, max_length=100)
