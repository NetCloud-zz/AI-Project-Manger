"""Permission-scoped entity resolution and non-LLM guards for ambiguous mutations."""

from __future__ import annotations

import re
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import can_view_project, can_view_task
from app.models.project import Project
from app.models.task import Task
from app.models.user import User, UserStatus
from app.services.exceptions import DomainValidationError


class EntityResolutionError(DomainValidationError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "AMBIGUOUS_ENTITY",
        candidates: list[dict[str, Any]] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.candidates = candidates or []


def unique_candidate(rows: list[Any], kind: str) -> Any:
    if not rows:
        raise EntityResolutionError(f"未找到可访问的{kind}", code="NOT_FOUND")
    if len(rows) != 1:
        raise EntityResolutionError(
            f"有多个匹配的{kind}，请选择明确编号",
            candidates=[
                {
                    "id": r.id,
                    "name": getattr(
                        r, "task_name", getattr(r, "project_name", getattr(r, "name", ""))
                    ),
                }
                for r in rows[:20]
            ],
        )
    return rows[0]


def resolve_owner(db: Session, name: str) -> User:
    rows = list(
        db.scalars(select(User).where(User.status == UserStatus.ACTIVE, User.name == name.strip()))
    )
    # Do not silently assign a partial-name match: explicit selection is needed.
    return unique_candidate(rows, "负责人")


def resolve_arguments(
    db: Session,
    actor: User,
    tool: str,
    arguments: dict[str, Any],
    *,
    source_message: str | None = None,
) -> dict[str, Any]:
    args = dict(arguments)
    if tool == "search_tasks" and args.get("owner_name"):
        owner = resolve_owner(db, str(args["owner_name"]))
        if args.get("owner_id") and int(args["owner_id"]) != owner.id:
            raise EntityResolutionError("负责人名称与 ID 不一致", code="INVALID_ARGUMENTS")
        args["owner_id"], args["owner_scope"] = owner.id, "user"
    if (
        args.get("owner_name")
        and not args.get("owner_id")
        and tool.startswith(("create_", "update_"))
    ):
        from app.core.owner_labels import is_pending_owner_label

        if is_pending_owner_label(str(args["owner_name"])):
            # Keep unassigned; create_task / update_task treat missing owner_id as TBD.
            args.pop("owner_name", None)
            if tool.startswith("update_"):
                args["owner_id"] = None
        else:
            args["owner_id"] = resolve_owner(db, str(args["owner_name"])).id
            args.pop("owner_name", None)
    if args.get("task_id") and args.get("target_task_name"):
        task = db.get(Task, int(args["task_id"]))
        if task is None or not can_view_task(db, actor, task):
            raise EntityResolutionError("未找到可访问的任务", code="NOT_FOUND")
        if task.task_name != str(args["target_task_name"]).strip():
            raise EntityResolutionError(
                "任务名称与 ID 不一致，未执行修改", code="INVALID_ARGUMENTS"
            )
    if (
        args.get("project_name")
        and not args.get("project_id")
        and not args.get("project_code")
        and tool != "create_project"
    ):
        rows = [
            p
            for p in db.scalars(select(Project).where(Project.project_name == args["project_name"]))
            if can_view_project(db, actor, p)
        ]
        args["project_id"] = unique_candidate(rows, "项目").id
        args.pop("project_name")
    task_name = args.get("target_task_name")
    if not args.get("task_id") and tool in {"update_task", "get_task_progress", "submit_progress"}:
        task_name = task_name or args.get("task_name")
        inferred_name = False
        if not task_name and source_message:
            task_name = extract_task_name_hint(source_message)
            if task_name:
                inferred_name = True
                args["target_task_name"] = task_name
        if task_name:
            stmt = select(Task).where(Task.task_name == str(task_name).strip())
            if args.get("project_id"):
                stmt = stmt.where(Task.project_id == int(args["project_id"]))
            elif args.get("project_code"):
                stmt = stmt.join(Project).where(
                    Project.project_code == str(args["project_code"]).strip().upper()
                )
            matched_tasks = [task for task in db.scalars(stmt) if can_view_task(db, actor, task)]
            args["task_id"] = unique_candidate(matched_tasks, "任务").id
            # Drop resolved name so update_task does not rename the task.
            if tool == "update_task" and (
                inferred_name or "task_name" not in arguments or arguments.get("task_name") is None
            ):
                args.pop("task_name", None)
    if args.get("task_id") and (args.get("project_id") or args.get("project_code")):
        task = db.get(Task, int(args["task_id"]))
        if task is None or not can_view_task(db, actor, task):
            raise EntityResolutionError("未找到可访问的任务", code="NOT_FOUND")
        if args.get("project_id") and task.project_id != int(args["project_id"]):
            raise EntityResolutionError("任务不属于指定项目", code="INVALID_ARGUMENTS")
        if (
            args.get("project_code")
            and task.project.project_code != str(args["project_code"]).strip().upper()
        ):
            raise EntityResolutionError("任务不属于指定项目", code="INVALID_ARGUMENTS")
    args.pop("target_task_name", None)
    if "new_task_name" in args:
        args["task_name"] = args.pop("new_task_name")
    return args


_TASK_NAME_HINT = re.compile(
    r"(?:把|将|查|看)?\s*[「\"“]?(.+?)[」\"”]?\s*(?:的)?(?:完成度|进度|截止|日期|状态)"
)


def extract_task_name_hint(source: str) -> str | None:
    match = _TASK_NAME_HINT.search(source)
    if not match:
        return None
    name = match.group(1).strip()
    return name or None


_VAGUE = re.compile(
    r"往前推|推(?:进|动)?一点|宽松(?:一?些|一点)?|稍微|高一点|低一点|差不多|随便|看着办|酌情|尽快安排"
)
_MUTATION = re.compile(
    r"(?:"
    r"创建|新增|新建|登记|记录|提交|更新|修改|设置|设为|改为|改成|调整|分配|指派|取消|延期|改期|"
    r"完成度.*(?:改|调)|往前推|推进一点|宽松|"
    # Natural create / execute phrasing (exploratory NL-01).
    r"弄个|弄一个|弄起来|建个|建一个|帮我建|现在就建|立项|起草(?:计划|草案)?|"
    r"确认创建|确认执行|就按你说的(?:建好|建|办|做|弄)?|按你说的(?:建好|办|执行)|"
    r"就这么办|执行吧"
    r")"
)
_CONFIRMATION = re.compile(
    r"(?:"
    r"确认创建|确认执行|现在就建|现在就创建|"
    r"好啊?[，,。！!\s]*弄起来|弄起来吧|"
    r"就按你说的|按你说的(?:建|办|做|弄|执行)|"
    r"就这么办|执行吧|可以执行|可以建"
    r")"
)
# Soft affirmatives only inherit a prior create turn — never authorize alone.
_WEAK_CONFIRMATION = re.compile(
    r"(?:"
    r"^(?:好的?|可以了|行|OK|ok|嗯)[。！!？?\s]*$|"
    r"行[，,。！!\s]+(?:就|按)"
    r")"
)
# Status checks must not inherit write authorization (exploratory NL-05).
_STATUS_QUERY = re.compile(
    r"(?:"
    r"(?:有没有|是否|到底).{0,16}(?:建|创建|弄|落库)|"
    r"(?:建|创建)好了吗|"
    r"创建成功了吗|"
    r"落库了吗|"
    r"有没有建好"
    r")"
)
# Only cancel writes for clear read-only / discussion framing.
# "不要创建其它任务" must NOT cancel an explicit create-N request.
_READ_ONLY_INTENT = re.compile(
    r"(?:"
    r"(?:只是|仅仅)讨论|"
    r"不要执行|"
    r"不(?:要|用)进行任何(?:写入|修改|创建|操作)|"
    r"明确不要创建[、,，\s]*不要修改|"
    r"不要创建[、,，\s]*不要修改[、,，\s]*不要删除|"
    r"只(?:读|查询)(?:[，。]|$)|"
    r"(?:先算了|算了).{0,8}别(?:建|创建|弄)|"
    r"别建了|不要建了|别创建了"
    r")"
)
_FRESH_FACTS = re.compile(
    r"最近(?:进展|怎么样)|进展如何|顺不顺利|是否顺利|最需要关注|还好吗|当前风险|总体进度|做得怎么样"
)


def is_status_query(source: str) -> bool:
    return bool(_STATUS_QUERY.search(source))


def is_confirmation(source: str) -> bool:
    return bool(_CONFIRMATION.search(source))


def is_weak_confirmation(source: str) -> bool:
    return bool(_WEAK_CONFIRMATION.search(source.strip()))


def has_mutation_intent(source: str) -> bool:
    if is_status_query(source):
        return False
    if not (_MUTATION.search(source) or is_confirmation(source)):
        return False
    if not _READ_ONLY_INTENT.search(source):
        return True
    # Conflicting framing: explicit create-N still authorizes writes.
    return bool(
        re.search(
            r"(?:创建|新增|新建|弄个|建个)(?:以下|这|共|总共|分别|恰好|正好)?\s*\d+\s*(?:个|条|项)",
            source,
        )
    )


AssistantIntent = Literal[
    "mutation",
    "status",
    "discussion",
    "confirmation",
    "weak_confirmation",
    "general",
]


def classify_assistant_intent(message: str) -> AssistantIntent:
    """Route signal only — does not by itself authorize writes."""
    if is_status_query(message):
        return "status"
    if is_weak_confirmation(message) and not has_mutation_intent(message):
        return "weak_confirmation"
    if is_confirmation(message) and has_mutation_intent(message):
        return "confirmation"
    if has_mutation_intent(message):
        return "mutation"
    if _READ_ONLY_INTENT.search(message):
        return "discussion"
    if is_confirmation(message):
        return "confirmation"
    return "general"


def resolve_write_authorization(
    message: str,
    prior_user_messages: list[str] | None = None,
) -> str | None:
    """Return authorizing text for writes, or None when writes must not run.

    Intent classification selects a path; this function alone decides write
    authorization. Status and discussion never authorize. Weak confirmations
    only inherit an earlier mutation turn.
    """
    intent = classify_assistant_intent(message)
    if intent in {"status", "discussion"}:
        return None
    if intent in {"mutation", "confirmation"} and has_mutation_intent(message):
        return message
    if intent == "weak_confirmation" or (
        intent == "confirmation" and not has_mutation_intent(message)
    ):
        for prior in reversed(prior_user_messages or []):
            if prior and has_mutation_intent(prior) and not is_status_query(prior):
                return prior
        return None
    if has_mutation_intent(message):
        return message
    return None


def authorization_source(
    message: str,
    prior_user_messages: list[str] | None = None,
) -> str:
    """Text used by mutation guard / coverage (never invents authorization)."""
    return resolve_write_authorization(message, prior_user_messages) or message


def plan_coverage_source(
    message: str,
    prior_user_messages: list[str] | None = None,
) -> str:
    """Source used to validate write-step ``source_text`` attribution.

    Confirmations authorize writes but usually omit the original task body.
    Prefer the richest prior mutation turn so planners can map stage/task quotes
    onto the earlier create instruction instead of the short confirm sentence.
    """
    intent = classify_assistant_intent(message)
    if intent in {"confirmation", "weak_confirmation"}:
        candidates: list[str] = []
        for prior in prior_user_messages or []:
            if not prior or is_status_query(prior) or not has_mutation_intent(prior):
                continue
            # Skip other short confirm phrases; keep detailed create instructions.
            if (
                classify_assistant_intent(prior) == "confirmation"
                and len(prior.strip()) < 160
            ):
                continue
            candidates.append(prior)
        if candidates:
            return max(candidates, key=len)
    return authorization_source(message, prior_user_messages)


def writes_authorized(
    message: str,
    prior_user_messages: list[str] | None = None,
) -> bool:
    return resolve_write_authorization(message, prior_user_messages) is not None


def requires_fresh_facts(source: str) -> bool:
    """Manager-style status questions must re-query; do not reuse prior reply text."""
    return bool(_FRESH_FACTS.search(source))


def should_use_command_plan(source: str) -> bool:
    """Durable command executor for writes and multi-step compound instructions.

    ``source`` is typically ``authorization_source(...)``. Routing uses intent
    signals on that text; tool RBAC and ``guard_mutation`` still enforce writes.
    """
    if has_mutation_intent(source):
        return True
    if is_status_query(source):
        return False
    return is_compound_instruction(source)


def is_compound_instruction(source: str) -> bool:
    """Three or more action verbs: route through the durable planner even for reads."""
    verbs = len(re.findall(r"创建|更新|修改|查询|列出|查一下|再建|登记|再查|弄个|建个", source))
    return verbs >= 3


def guard_mutation(
    source: str | None,
    tool: str,
    args: dict[str, Any],
    *,
    authorized: bool | None = None,
) -> None:
    """Hard block guessed values in vague edits, even when the LLM proposes numbers.

    ``authorized`` carries an explicit per-turn verdict (hybrid intent mode);
    ``None`` falls back to the regex mutation check on ``source``.
    """
    if source is None:
        return
    allowed = has_mutation_intent(source) if authorized is None else authorized
    if not allowed:
        raise EntityResolutionError(
            "当前消息未授权业务写入，请明确需要执行的操作", code="CONFIRMATION_REQUIRED"
        )
    if tool.startswith("update_") and _VAGUE.search(source):
        sensitive = {
            "progress_percent",
            "due_date",
            "start_date",
            "target_date",
            "owner_id",
            "owner_name",
            "status",
        }
        for field in sensitive & args.keys():
            value = args[field]
            if field == "progress_percent" and re.search(
                rf"(?<!\d){re.escape(str(value))}\s*[%％]", source
            ):
                continue
            if field.endswith("date") and isinstance(value, str) and value in source:
                continue
            raise EntityResolutionError(
                "修改幅度不明确，请指定完成度、日期或负责人；不会猜测写入",
                code="CONFIRMATION_REQUIRED",
            )
