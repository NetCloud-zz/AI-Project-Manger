# 项目专属数据库 Tools 接入

Copyright 2024–2026 Jack Zhang. Apache License 2.0；保留 NOTICE 署名。

## 实现入口

本契约依据本目录的实体、关系、查询规则和工具建议构建，使用项目现有业务服务。

- `backend/app/agents/database_tools.py`：工具定义补充、契约查询、完整 JSON Schema 导出。
- `backend/app/agents/management_tools.py`：统一注册及执行入口，已接入现有助手。
- `backend/app/services/agent_change_policy.py`：修改原因校验与审计。
- AgentScope 和 legacy 共用这些工具；命令规划器也可调用新增查询工具。

交付形式是项目内置 **Tools**，没有新增独立 MCP 网络服务、数据库账号或直连 SQL 接口。
数据库采集文档描述采集时状态；本文说明当前工作区实现。不能根据文档中的表名自由查询或写入。

## 能力

| 类型 | 工具 |
| --- | --- |
| 能力说明 | `get_database_tools` |
| 项目和任务 | `get_project`、`get_task(task_code)`、`search_tasks`、`query_entities` |
| 人员 | `get_current_user`、`batch_find_users` |
| 进度与问题 | `get_task_progress`、`get_project_progress_overview`、已有 Issue / ActionItem / Risk 专用工具 |
| 计划关系 | `get_dependency_graph`、`list_task_branches`、`get_plan_version(project_id, version)` |
| 新增 | 已有项目、任务、里程碑、问题、行动项、进度汇报、计划草案工具 |
| 修改 | 已有项目/任务/问题/行动项修改、改期、分支、草案及变更方案工具 |

`query_entities` 仅允许 task / project / issue / user / milestone / project_member 的字段白名单。
其余对象走专用服务；历史计划只返回版本、类型、原因、创建时间，不返回原始 snapshot。
密码、密钥及内部运行日志不作为业务查询入口；未知工具名拒绝执行。

任务业务编号映射真实 `tasks.task_code`。任务 DTO 的 `owners` / `owner_ids` 包含主负责人和 OWNER 参与者（去重），不包含协作人。负责人过滤匹配全部负责人；兼容标量字段 `owner_id` / `owner_name` 的显示、排序和分组仍表示主负责人，不可用其分组结果回答“所有共同负责人”的统计。
项目进度概览按当前激活分支、非取消的可见任务统计，因此包含已完成任务；时间窗口仅约束近期汇报，不把平均任务完成度称作项目完成度。

## 修改原因

| 操作 | 原因要求 |
| --- | --- |
| `update_project` | 提交 `goal`、`start_date`、`target_date` 时必须有 `change_reason` |
| `update_task` | 提交日期、实际日期、工期、日历、工作流、任务分组时必须有 `change_reason` |
| `reschedule_task` | 必须有 `change_reason`，包括按 offset_days 改期 |
| `update_action_item` | 提交 `due_date` 时必须有 `change_reason` |
| `batch_update_tasks` | 修改工作流需每项 `change_reason`；仅支持名称、主负责人、工作流，其他字段拒绝，避免静默忽略 |
| 分支创建/切换、变更方案 | 必须有 `reason` |
| `update_project_plan_draft` | 完整草案替换统一要求 `change_reason`，包括尚未发布的草案 |

原因去除首尾空白后为 2–2000 字。提交敏感字段即要求原因，包括清空和重复提交相同值。初始创建日期无需修改原因，普通状态/进度更新不额外要求原因。系统自动生成的完成时间仍由原有状态服务维护。

原因必须来自用户，助手缺少信息时追问，不得编造。原因校验是服务端硬约束；来源真实性由对话授权和助手提示共同约束，程序不能证明自然语言原因是否真实。项目、任务、行动项和草案修改原因与业务写入同事务写入 `audit_logs`，原服务继续记录前后快照；分支及变更方案沿用已有原因记录。

仅支持增、查、改，不提供删除工具或 SQL。写操作保留当前用户 RBAC、显式请求授权、已有幂等与版本校验。原因不替代授权。影响其他任务排期时仍走预览 → 方案 → 用户确认卡片 → 执行，草案发布保留现有流程。

`review_project_plan_draft` / `validate_project_plan` 会保存审查结果，已归类为 WRITE，在只读重答中禁止执行。

## 后端接入示例

```python
from app.agents.database_tools import export_database_tool_definitions
from app.agents.management_tools import ManagementToolExecutor

# 可序列化为 JSON，供外部适配层加载；不包含业务数据或数据库连接信息。
contract = export_database_tool_definitions()

# actor 必须来自认证依赖，allow_writes 必须来自服务端当前请求的授权判定。
executor = ManagementToolExecutor(
    db, actor, allow_writes=authorized_write,
    agent_request_id=request_id, source_message=user_message,
)
result = executor.execute_result("get_task", {"task_code": "T20260915-001"})
```

不能接受模型传入 actor、数据库连接或 allow_writes。外部 MCP 如需接入，应在认证后的适配层调用同一执行器，不直接执行定义中的 SQL（本工具没有 SQL 参数）。定义文件本身不授予权限。

## 验证与启用

```bash
cd backend
.venv/bin/python -m pytest tests/test_database_tools.py
```

无需数据库迁移。源码方式运行需重启后端；Compose 需按部署技能重建使用后端源码的镜像后再启用。工作区测试不会自动部署，也不修改业务数据库。
