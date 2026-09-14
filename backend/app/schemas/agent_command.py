"""Validated planning protocol. Planning itself never executes a business tool."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Writes that satisfy "create project" / "create tasks" intents.
_PROJECT_WRITE_TOOLS = frozenset({"create_project", "draft_project_plan"})
_TASK_WRITE_TOOLS = frozenset(
    {
        "create_task",
        "batch_create_tasks",
        "draft_project_plan",
        "apply_project_plan",
    }
)
_BATCH_COVERAGE_TOOLS = frozenset(
    {"draft_project_plan", "batch_create_tasks", "batch_update_tasks", "apply_project_plan"}
)

# Fact-finding steps may summarize scattered names/project refs; they must not block writes.
AUXILIARY_QUERY_TOOLS = frozenset(
    {
        "batch_find_users",
        "find_users",
        "get_current_user",
        "get_project",
        "list_projects",
        "get_project_context",
        "search_tasks",
        "query_entities",
        "get_project_progress_overview",
        "list_my_tasks",
        "get_project_risks",
    }
)
# Back-compat alias used by older imports/tests.
_AUXILIARY_QUERY_TOOLS = AUXILIARY_QUERY_TOOLS

_CREATE_PROJECT_INTENT = re.compile(
    r"(?:请)?(?:创建|新建|新增|弄个|建个)\s*项目|立项",
)
_CREATE_TASK_INTENT = re.compile(
    r"(?:请|然后|再)?(?:创建|新建|新增|登记|添加)\s*任务|"
    r"按以下(?:内容)?创建|创建以下任务",
)


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

    @field_validator("items", mode="before")
    @classmethod
    def decode_items(cls, value: Any) -> Any:
        # Some gateways double-encode tool fields. Decode once, then apply all
        # normal list, item, dependency and coverage checks without coercion.
        if isinstance(value, str):
            return json.loads(value)
        return value

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


def _ws_fold(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to a single space; map folded index → original index."""
    folded: list[str] = []
    mapping: list[int] = []
    prev_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if folded and not prev_space:
                folded.append(" ")
                mapping.append(index)
            prev_space = True
            continue
        folded.append(char)
        mapping.append(index)
        prev_space = False
    return "".join(folded), mapping


def locate_source_span(
    source: str, quote: str, preferred_start: int | None = None
) -> tuple[int, int]:
    """Map an item quote onto the authorizing source; allow whitespace-only differences."""
    if preferred_start is not None:
        end = preferred_start + len(quote)
        if preferred_start >= 0 and end <= len(source) and source[preferred_start:end] == quote:
            return preferred_start, end
    start = source.find(quote)
    if start >= 0:
        return start, start + len(quote)

    source_folded, source_map = _ws_fold(source)
    quote_folded, _ = _ws_fold(quote)
    quote_folded = quote_folded.strip()
    if not quote_folded:
        raise ValueError("原文映射不匹配")
    folded_start = source_folded.find(quote_folded)
    if folded_start < 0:
        raise ValueError("原文映射不匹配")
    folded_end = folded_start + len(quote_folded) - 1
    if folded_end >= len(source_map):
        raise ValueError("原文映射不匹配")
    return source_map[folded_start], source_map[folded_end] + 1


def assert_mutation_writes(plan: CommandPlanInput, source: str) -> None:
    """Reject query-only plans when the user clearly asked to create objects."""
    tools = {item.tool for item in plan.items}
    if _CREATE_PROJECT_INTENT.search(source) and not (tools & _PROJECT_WRITE_TOOLS):
        raise ValueError(
            "创建项目指令必须包含 create_project（或 draft_project_plan），"
            "不能只查询负责人或项目列表"
        )
    if _CREATE_TASK_INTENT.search(source) and not (tools & _TASK_WRITE_TOOLS):
        raise ValueError(
            "创建任务指令必须包含 create_task / batch_create_tasks 或 draft_project_plan，"
            "不能只查询或核对"
        )


def locate_auxiliary_evidence(
    source: str, quote: str, preferred_start: int | None = None
) -> tuple[int, int]:
    """Map auxiliary quotes; allow multi-fragment evidence before soft fallback."""
    try:
        return locate_source_span(source, quote, preferred_start)
    except ValueError:
        parts = [part.strip() for part in re.split(r"[,，、;；/\n|]+", quote) if part.strip()]
        for part in parts:
            if len(part) < 2:
                continue
            try:
                return locate_source_span(source, part)
            except ValueError:
                continue
        return (0, 0)


def locate_write_evidence(
    source: str, quote: str, preferred_start: int | None = None
) -> tuple[int, int]:
    """Map write-step quotes; allow multi-fragment matches before failing hard."""
    try:
        return locate_source_span(source, quote, preferred_start)
    except ValueError:
        parts = [part.strip() for part in re.split(r"[,，、;；/\n|]+", quote) if part.strip()]
        for part in parts:
            if len(part) < 2:
                continue
            try:
                return locate_source_span(source, part)
            except ValueError:
                continue
        raise ValueError("原文映射不匹配") from None


def validate_coverage(plan: CommandPlanInput, source: str) -> list[tuple[int, int]]:
    """Validate attribution for writes; auxiliary queries may use soft evidence."""
    if requires_atomic(source) and plan.policy != "atomic":
        raise ValueError("用户要求全成全败，不能使用独立提交策略")
    spans: list[tuple[int, int]] = []
    for item in plan.items:
        if item.tool in _AUXILIARY_QUERY_TOOLS:
            spans.append(locate_auxiliary_evidence(source, item.source_text, item.source_start))
            continue
        try:
            spans.append(locate_write_evidence(source, item.source_text, item.source_start))
        except ValueError as exc:
            raise ValueError(
                f"{item.item_id} 的原文映射不匹配（写入步骤必须能对上用户授权原文）"
            ) from exc
    assert_mutation_writes(plan, source)
    counts = re.findall(
        r"(?:创建|新增|新建)(?:以下|这|共|总共|分别|恰好|正好)?\s*(\d+)\s*(?:个|条|项)?(?:独立)?(?:执行)?(?:的)?任务",
        source,
    )
    created = sum(i.tool == "create_task" for i in plan.items)
    if (
        counts
        and created != sum(int(n) for n in counts)
        and not any(i.tool in _BATCH_COVERAGE_TOOLS for i in plan.items)
    ):
        raise ValueError("任务创建数量与用户明确要求的 N 不一致，尚有遗漏或额外动作")
    return spans


class CommandRetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    item_ids: list[str] = Field(min_length=1, max_length=100)
