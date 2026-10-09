# 数据库维护资料入口

Copyright 2024–2026 Jack Zhang. Apache License 2.0；保留 NOTICE 署名。

此目录把本项目数据库详情接入 `mcp` 的开发技能。完整资料保存在 `docs/database`，下面的链接和 [resources.json](resources.json) 指向同一份文件。JSON 是仓库文件索引，不是已注册的 MCP resources，也不提供数据库连接或执行权限。

## 按任务读取

| 需要了解什么 | 资料 | 使用方式 |
| --- | --- | --- |
| 全库概览、规模、模块 | [DATABASE_OVERVIEW.md](../../docs/database/DATABASE_OVERVIEW.md) | 先读架构概述；规模数字是采集快照 |
| 某张表的字段、类型、空值、默认值、索引 | [DATABASE_DICTIONARY.md](../../docs/database/DATABASE_DICTIONARY.md) | 按 `public.tasks` 等表名搜索 |
| 外键、关系方向、JOIN 路径与证据 | [DATABASE_RELATIONSHIPS.md](../../docs/database/DATABASE_RELATIONSHIPS.md) | 区分已确认外键与推断关系 |
| 模块关系图 | [DATABASE_ER.md](../../docs/database/DATABASE_ER.md) | 按业务模块阅读 Mermaid 图 |
| 机器可读完整结构 | [database_schema.json](../../docs/database/database_schema.json) | 提取目标表及相邻依赖，勿整份塞入业务对话 |
| 实体、字段别名、状态、权限和时间口径 | [AGENT_DATABASE_GUIDE.md](../../docs/database/AGENT_DATABASE_GUIDE.md) | 与当前工具契约交叉核对 |
| 机器可读语义层 | [agent_semantic_layer.yaml](../../docs/database/agent_semantic_layer.yaml) | 按实体读取；建议字段不是运行时白名单 |
| 查询限制 | [AGENT_QUERY_RULES.md](../../docs/database/AGENT_QUERY_RULES.md) | 修改查询、DTO 或工具前阅读 |
| 采集时的工具现状及建议 | [AGENT_TOOLS.md](../../docs/database/AGENT_TOOLS.md) | 其中 PROPOSED 不表示已经实现 |
| 当前工作区工具接入及原因规则 | [PROJECT_DATABASE_TOOLS.md](../../docs/database/PROJECT_DATABASE_TOOLS.md) | 助手开发优先核对这一份和实际代码 |
| 结构漂移与已知问题 | [DATABASE_RISKS.md](../../docs/database/DATABASE_RISKS.md) | 逐项复核是否仍存在，不能把旧风险直接当现状 |

结构文档标注的采集日期为 **2026-09-15**。本次只建立文件关联，未重新采集数据库；不要把文件修改时间当作数据库验证时间。

## 数据库模块到代码的定位

以下为采集快照中的 35 张表（含迁移表）的维护导航。具体字段、关系与约束以链接的完整字典及迁移为依据。

| 模块 | 表 | 主要模型 / 服务（仓库根目录相对路径） |
| --- | --- | --- |
| 人员和项目 | `users`, `projects`, `project_owners`, `project_members` | `backend/app/models/user.py`, `project.py`, `planning.py`；`backend/app/services/user.py`, `project.py` |
| 任务执行与关系 | `tasks`, `task_participants`, `task_links`, `task_groups`, `milestones`, `work_calendars`, `branch_groups`, `branch_options` | `backend/app/models/task.py`, `planning.py`；`backend/app/services/task.py`, `task_link.py`, `planning.py`, `scheduling.py` |
| 计划草案与历史 | `plan_drafts`, `change_proposals`, `plan_versions` | `backend/app/models/plan_draft.py`, `change_proposal.py`, `planning.py`；同名服务及 `schedule_guard.py` |
| 汇报和跟进 | `progress_updates`, `daily_project_summaries`, `issues`, `risk_events`, `advice_records`, `action_items` | 对应模型；`backend/app/services/progress.py`, `daily_summary.py`, `issue.py`, `risk_event.py`, `advice.py`, `action_item.py` |
| 通知 | `notification_events` | `backend/app/models/notification.py`；`backend/app/services/notification_delivery.py` |
| 助手运行 | `agent_conversations`, `agent_messages`, `agent_memories`, `agent_requests`, `agent_operations`, `agent_command_plans`, `agent_command_items`, `agent_batch_operations`, `agent_batch_items`, `agent_tool_calls` | `backend/app/models/agent_*.py`；`backend/app/services/conversation.py`, `memory.py`, `agent_commands.py`, `agent_batch.py`, `agent_idempotency.py` |
| 后台和审计 | `ai_runs`, `audit_logs` | `backend/app/models/ai_run.py`, `audit_log.py`；`backend/app/services/ai_run.py`, `audit.py` |
| 迁移记录 | `alembic_version` | `backend/alembic/versions/`；属于迁移管理，不是业务工具查询实体 |

## 修改前必须区分的语义

- 项目方向对应 `projects.goal`；`tasks.work_stream` 是文本维度，`task_groups` 是树形分组，备选任务分支与 `branch_groups` / `branch_options` 路线选择也有不同服务入口。
- 项目共同负责人、有效项目成员、任务 OWNER、任务 COLLABORATOR 是不同关系；项目可见不等于全部任务或历史快照可见。
- 当前代码的 `task_code` 映射真实业务编号；旧采集文档中映射为 `id` 的内容不能照搬。负责人过滤包含主负责人和 OWNER，标量负责人分组仍只表示主负责人。
- `review_project_plan_draft` 与 `validate_project_plan` 会保存审查结果，当前必须按写操作处理。当前进度概览包含激活分支中的已完成任务；详见工具接入说明。
- Issue、RiskEvent、AdviceRecord、ActionItem 分别表示问题、风险事件、建议版本、落实行动；预测日期不等于承诺日期。
- 当前没有通用租户键或通用软删除字段；不得自行假定 tenant、deleted_at 或 RLS 保障。取消、失效和非激活分支分别按业务语义处理。

## 后续改动同步流程

1. 从目标表/实体定位字段、外键、状态和读写服务，检查相关权限及旧风险的当前状态。
2. 修改业务代码时同步 schema、DTO、工具参数、查询白名单、提示词及必要测试。日期、方向、分支等修改继续要求用户提供原因并审计，详见 `agent_change_policy.py`。
3. 确需改变数据库结构时，在该开发任务范围内编写并审查 Alembic migration，检查升级兼容性和单一 head。文档维护任务不执行 migration；业务助手不提供 DDL、SQL 或删除能力。
4. 结构变更部署后，按任务需要通过只读目录元数据核对数据库；不要采集业务行、口令、连接串、内网地址或客户数据。未经重新采集的结构数字继续标注为旧快照；代码预期结构应标注“待迁移/待验证”。
5. 字段/约束变更同步字典及 JSON，关系变更同步关系文档与 ER 图，语义变更同步指南及 YAML，工具变更同步接入说明；新增/移动资料时更新本目录资源索引。版本变更说明只写入 `docs/releases/`。

## 运行时入口

- [工具定义与导出](../../backend/app/agents/database_tools.py)：`export_database_tool_definitions()` 返回当前代码的完整工具 schema；不把一份过期导出当运行时事实。
- [统一执行器](../../backend/app/agents/management_tools.py)：`ManagementToolExecutor`，身份和写授权由可信请求上下文提供。
- [修改原因规则](../../backend/app/services/agent_change_policy.py)、[对象权限](../../backend/app/core/permissions.py)、[字段白名单](../../backend/app/agents/query/fields.py)。

这些资料服务于后续项目开发。业务助手仍只通过受控工具新增、查询、修改已有业务实体；读取这些文件不会新建数据库对象。
