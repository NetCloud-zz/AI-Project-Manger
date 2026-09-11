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
    expected_count: int = Field(ge=1, le=100)
    items: list[CommandItemInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def graph_valid(self) -> CommandPlanInput:
        if self.expected_count != len(self.items):
            raise ValueError("expected_count 必须等于完整步骤清单数量")
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
    if counts and sum(int(n) for n in counts) != sum(i.tool == "create_task" for i in plan.items):
        raise ValueError("任务创建数量与用户明确要求的 N 不一致，尚有遗漏或额外动作")
    # Numbered lines must all be represented, even if the planner omits an inconvenient item.
    for match in re.finditer(r"(?m)^\s*(?:\d+[.、）)]|[-*])\s*(\S.*)$", source):
        a, b = match.span(1)
        if not any(start < b and end > a for start, end in spans):
            raise ValueError("有编号指令没有对应执行项")
    return spans


class CommandRetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    item_ids: list[str] = Field(min_length=1, max_length=100)
