# AGENT_DATABASE_GUIDE

> Copyright 2024–2026 Jack Zhang. Apache License 2.0；保留 NOTICE 署名。
> 采集日期：2026-09-15；结构来源：实际 PostgreSQL 只读目录；业务语义来源：当前工作区模型、迁移与服务。
> 未读取业务记录。PUBLIC 仅表示字段可经授权业务 DTO 使用，不表示互联网公开或授权直连数据库。

这是建议的受控语义契约，不是新增数据库权限，也未修改现有运行时代码。建议加载顺序：AGENT_QUERY_RULES → 本指南 → 目标实体 YAML 分片 → 已登记 Tool schema。完整字典与索引详情供维护人员使用，避免每次对话加载全部内部字段。

当前工作区的可执行工具接入与修正说明见 [项目专属数据库 Tools](PROJECT_DATABASE_TOOLS.md)。下文保留采集时快照；task_code 映射、共同负责人过滤、审查工具写分类以该接入说明和运行时代码为准。

## 业务实体与查询能力

| 实体 | 主表 | 含义/粒度 | 读取 |
| --- | --- | --- | --- |
| ActionItem | action_items | 一条记录代表有负责人和期限的跟进事项，可关联问题、任务及建议 | SCOPED_DTO_ONLY |
| AdviceRecord | advice_records | 一条记录代表一个问题的一版建议及证据、采纳决定和效果评价 | SCOPED_DTO_ONLY |
| AgentBatchItem | agent_batch_items | 一条记录代表批量操作中一个 client_item_id 对应的执行回执 | DENY_GENERAL_QUERY |
| AgentBatchOperation | agent_batch_operations | 一条记录代表某用户一次带幂等标识的批量工具调用 | DENY_GENERAL_QUERY |
| AgentCommandItem | agent_command_items | 一条记录代表命令计划中的一个有序步骤及依赖、结果 | DENY_GENERAL_QUERY |
| AgentCommandPlan | agent_command_plans | 一条记录代表一个助手请求对应的一份结构化命令计划 | DENY_GENERAL_QUERY |
| AgentConversation | agent_conversations | 一条记录代表某用户的一段对话及可选绑定项目 | DENY_GENERAL_QUERY |
| AgentMemory | agent_memories | 一条记录代表某用户的一条偏好、指令或固定上下文；不是动态业务事实 | DENY_GENERAL_QUERY |
| AgentMessage | agent_messages | 一条记录代表一个会话中的一条消息或一个回答版本 | DENY_GENERAL_QUERY |
| AgentOperation | agent_operations | 一条记录代表一个助手请求内一次有副作用工具动作的回执 | DENY_GENERAL_QUERY |
| AgentRequest | agent_requests | 一条记录代表用户在会话中的一次带幂等标识的发送请求 | DENY_GENERAL_QUERY |
| AgentToolCall | agent_tool_calls | 一条记录代表一次读或写工具调用及耗时、结果摘要 | DENY_GENERAL_QUERY |
| AIRun | ai_runs | 一条记录代表某业务资源的一次后台 AI 作业 | DENY_GENERAL_QUERY |
| AuditLog | audit_logs | 一条记录代表一次业务变更的操作人与前后快照 | DENY_GENERAL_QUERY |
| BranchGroup | branch_groups | 一条记录代表一个项目中一组互斥执行路线的决策点 | SCOPED_DTO_ONLY |
| BranchOption | branch_options | 一条记录代表某路线决策组中的一个候选选项 | SCOPED_DTO_ONLY |
| ChangeProposal | change_proposals | 一条记录代表一个经预览、校验、确认及执行的计划变更方案 | SCOPED_DTO_ONLY |
| DailyProjectSummary | daily_project_summaries | 一条记录代表一个项目在一个业务日期的 AI 汇总 | SCOPED_DTO_ONLY |
| Issue | issues | 一条记录代表一个项目级或任务级问题 | SCOPED_DTO_ONLY |
| Milestone | milestones | 一条记录代表一个项目中的验收或交付节点 | SCOPED_DTO_ONLY |
| NotificationEvent | notification_events | 一条记录代表某业务事件向某收件人在某渠道的一次通知意图 | SCOPED_DTO_ONLY |
| PlanDraft | plan_drafts | 一条记录代表尚未发布的结构化项目计划，发布后关联项目 | SCOPED_DTO_ONLY |
| PlanVersion | plan_versions | 一条记录代表一个项目的一个不可直接修改的历史计划版本 | SCOPED_DTO_ONLY |
| ProgressUpdate | progress_updates | 一条记录代表某用户向某任务提交的一次原始汇报及异步分析结果 | SCOPED_DTO_ONLY |
| ProjectMember | project_members | 一条记录代表一个项目与一个用户的成员关系及有效性 | SCOPED_DTO_ONLY |
| ProjectOwner | project_owners | 一条记录代表一个项目与一个共同负责人的关联 | SCOPED_DTO_ONLY |
| Project | projects | 一条记录代表一个项目的当前目标、计划日期及主负责人 | SCOPED_DTO_ONLY |
| RiskEvent | risk_events | 一条记录代表一个项目中由 dedupe_key 标识的可重复开启风险事实 | SCOPED_DTO_ONLY |
| TaskGroup | task_groups | 一条记录代表一个项目中的一个可嵌套任务分组节点 | SCOPED_DTO_ONLY |
| TaskDependency | task_links | 一条记录代表同一项目中两个任务之间的一条有方向依赖 | SCOPED_DTO_ONLY |
| TaskParticipant | task_participants | 一条记录代表一个任务与一个用户的单一参与角色；OWNER 为共同负责人 | SCOPED_DTO_ONLY |
| Task | tasks | 一条记录代表一个执行任务的当前计划、实际执行信息及状态 | SCOPED_DTO_ONLY |
| User | users | 一条记录代表一个本地用户账号及角色；外部身份仅映射 | SCOPED_DTO_ONLY |
| WorkCalendar | work_calendars | 一条记录代表一个项目的一份版本化工作日历，以 project_id 为主键 | SCOPED_DTO_ONLY |

工作流 `tasks.work_stream` 是文本维度，不是独立 WorkStream 表；结构化树是 TaskGroup。Issue、RiskEvent、AdviceRecord、ActionItem 分别表示问题、检测风险、建议版本、落实行动，不能合并理解。ProjectOwner / ProjectMember / TaskParticipant 是有角色语义的关联实体。

## 当前已经实现的 Query DSL

只支持 task / project / issue / user / milestone / project_member；其他实体必须走专用工具或待实现 Query Service。实体字段建议不代表现有 DSL 已经支持。

### task

| 逻辑字段 | 当前代码属性路径 |
| --- | --- |
| task_id | id |
| id | id |
| task_code | id |
| task_name | task_name |
| title | task_name |
| project_id | project_id |
| project_code | project.project_code |
| work_stream | work_stream |
| status | status |
| progress | progress_percent |
| progress_percent | progress_percent |
| start_date | start_date |
| target_date | due_date |
| due_date | due_date |
| planned_due_date | due_date |
| risk_level | ai_risk_level |
| owner_id | owner_id |
| owner_name | owner.name |
| created_at | created_at |
| is_overdue | __computed__ |
| days_overdue | __computed__ |

### project

| 逻辑字段 | 当前代码属性路径 |
| --- | --- |
| project_id | id |
| id | id |
| project_code | project_code |
| project_name | project_name |
| status | status |
| risk_level | risk_level |
| owner_id | owner_id |
| start_date | start_date |
| target_date | target_date |

### issue

| 逻辑字段 | 当前代码属性路径 |
| --- | --- |
| issue_id | id |
| id | id |
| project_id | project_id |
| task_id | task_id |
| title | title |
| status | status |
| severity | severity |

### user

| 逻辑字段 | 当前代码属性路径 |
| --- | --- |
| id | id |
| name | name |
| username | username |
| department | department |
| role | role |
| status | status |

### milestone

| 逻辑字段 | 当前代码属性路径 |
| --- | --- |
| id | id |
| project_id | project_id |
| name | name |
| target_date | target_date |
| status | status |
| owner_id | owner_id |

### project_member

| 逻辑字段 | 当前代码属性路径 |
| --- | --- |
| project_id | project_id |
| user_id | user_id |
| role | role |
| is_active | is_active |
| user_name | user_name |
| project_code | project_code |

**阻断映射：** task_code 当前错误映射为 id，修复前禁止通过该别名查询。owner_name/owner_id 当前只覆盖主负责人；完整“负责”查询必须在服务中实现主负责人与 OWNER 并集。

DSL 当前支持 eq/ne/in/not_in/gt/gte/lt/lte/before/after/between/contains/is_null；默认 limit=50，最大 200，offset>=0。contains 是应用层字符串匹配，没有数据库全文索引保障。日期由 BusinessClock 解释；group_by/聚合须按类型收紧，不对 ID 求和/平均，不把 enum 字符串自然顺序当业务优先级。

## DATA_SCOPE_RULES

没有 tenant_id/organization_id/workspace_id；department 是文本。不能宣称有数据库多租户隔离。普通查询以当前认证用户身份执行；ADMIN/EXECUTIVE 的广域读来自应用角色，EXECUTIVE 没有写权限。

| 表 | 必须应用的范围 | 禁止绕过 |
| --- | --- | --- |
| action_items | can_view_action_item(db, actor, item) | 是 |
| advice_records | RiskEventService/AdviceService 过滤项目与具体任务/问题证据；不可原样返回 evidence JSON | 是 |
| agent_batch_items | DENY_GENERAL_AGENT_QUERY | 是 |
| agent_batch_operations | DENY_GENERAL_AGENT_QUERY | 是 |
| agent_command_items | DENY_GENERAL_AGENT_QUERY | 是 |
| agent_command_plans | DENY_GENERAL_AGENT_QUERY | 是 |
| agent_conversations | DENY_GENERAL_AGENT_QUERY | 是 |
| agent_memories | DENY_GENERAL_AGENT_QUERY | 是 |
| agent_messages | DENY_GENERAL_AGENT_QUERY | 是 |
| agent_operations | DENY_GENERAL_AGENT_QUERY | 是 |
| agent_requests | DENY_GENERAL_AGENT_QUERY | 是 |
| agent_tool_calls | DENY_GENERAL_AGENT_QUERY | 是 |
| ai_runs | DENY_GENERAL_AGENT_QUERY | 是 |
| alembic_version | DENY_GENERAL_AGENT_QUERY | 是 |
| audit_logs | DENY_GENERAL_AGENT_QUERY | 是 |
| branch_groups | 保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在 | 是 |
| branch_options | 保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在 | 是 |
| change_proposals | 保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在 | 是 |
| daily_project_summaries | 保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在 | 是 |
| issues | can_view_issue(db, actor, issue) | 是 |
| milestones | 父项目 can_view_project；用户 DTO 最小披露 | 是 |
| notification_events | 本人 recipient_id；方案通知管理列表走 NotificationDeliveryService 专项权限 | 是 |
| plan_drafts | ACTIVE 的 ADMIN/PROJECT_OWNER 角色；仅 created_by=actor.id 或 ADMIN；调用 PlanDraftService._draft | 是 |
| plan_versions | 保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在 | 是 |
| progress_updates | 先 can_view_task，再查询该任务汇报 | 是 |
| project_members | 父项目 can_view_project；用户 DTO 最小披露 | 是 |
| project_owners | 父项目 can_view_project；用户 DTO 最小披露 | 是 |
| projects | can_view_project(db, actor, project) | 是 |
| risk_events | RiskEventService/AdviceService 过滤项目与具体任务/问题证据；不可原样返回 evidence JSON | 是 |
| task_groups | 保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在 | 是 |
| task_links | 父项目可见且 source/target 任务分别可见 | 是 |
| task_participants | 任务可见，用户 DTO 最小披露 | 是 |
| tasks | can_view_task(db, actor, task) | 是 |
| users | 已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围 | 是 |
| work_calendars | 保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在 | 是 |

### 权限关键区别

- can_view_project：ADMIN/EXECUTIVE、项目主/共同负责人、有效成员、在项目负责某任务者。
- can_view_task：ADMIN/EXECUTIVE；参与者需有效项目成员；MEMBER 另可通过主负责人或 OWNER 参与关系访问；PROJECT_OWNER 角色按项目负责人判断；其他分支以 permissions.py 为准。不能仅凭项目可见就读取全部任务。
- can_view_full_project：ADMIN/EXECUTIVE 或有项目修改权限者。生成摘要、完整计划及快照可能包含隐藏任务，不可按普通项目可见权限整包披露。
- 当前用户目录查询返回全部 ACTIVE 用户的最小字段；若部署要求按组织隔离人员，需要额外产品规则，现状没有此保证。
- 会话、记忆、请求与操作日志不可借 project_id 分享给同项目成员；应沿 user_id/conversation_id/request_id 检查所有者。

## 默认过滤与软删除

| 对象 | 规则 |
| --- | --- |
| tasks | {"current_execution": "is_active_branch = true AND status IN ('TODO','IN_PROGRESS')", "all_history": "不附加执行中筛选；仍应用对象权限", "note": "不同工具当前行为不一致，不能把当前执行筛选当成软删除"} |
| users | {"directory": "status = 'ACTIVE'", "note": "停用不是删除；历史负责人可显示最小 DTO"} |
| project_members | {"current_members": "is_active = true", "note": "失效成员不授予权限，现有 query_entities 可返回失效关系"} |
| agent_conversations | {"note": "ARCHIVED 是归档，不等于删除"} |

本库未观察到通用 deleted_at/is_deleted。默认当前记忆过滤 `agent_memories.is_active=true`，并匹配本人 user_id；成员授权要求 `project_members.is_active=true`。CANCELLED、INACTIVE、ARCHIVED、非激活路线各有含义，不统一视为“已删除”。查询全部历史任务时可含取消或非当前路线，但不能绕过对象权限。

## 字段可见性与查询能力（逐实体）

### ActionItem

- display_fields：title, due_date, status
- filters：title, due_date, status, priority, completed_at, created_at, updated_at
- service 内部定位：id, project_id, task_id, issue_id, owner_id
- sort：title, due_date, completed_at, created_at, updated_at
- aggregation：{"due_date": ["count_non_null", "min", "max"], "status": ["count", "group_by"], "priority": ["count", "group_by"], "completed_at": ["count_non_null", "min", "max"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：title；非 PostgreSQL 全文能力。
- SENSITIVE：description；需受控摘录。
- HIDDEN：无；完全禁止。

### AdviceRecord

- display_fields：status
- filters：status, decided_at, decision_note, outcome, issue_resolved, outcome_note, evaluated_at, created_at, updated_at
- service 内部定位：id, issue_id, project_id
- sort：decided_at, evaluated_at, created_at, updated_at
- aggregation：{"status": ["count", "group_by"], "decided_at": ["count_non_null", "min", "max"], "outcome": ["count", "group_by"], "evaluated_at": ["count_non_null", "min", "max"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：content, evidence, coverage；需受控摘录。
- HIDDEN：无；完全禁止。

### AgentBatchItem

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：error_message, payload；需受控摘录。
- HIDDEN：无；完全禁止。

### AgentBatchOperation

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id, user_id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：details；需受控摘录。
- HIDDEN：无；完全禁止。

### AgentCommandItem

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：source_text, arguments, result；需受控摘录。
- HIDDEN：无；完全禁止。

### AgentCommandPlan

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：source, error, planning_details；需受控摘录。
- HIDDEN：lease_token；完全禁止。

### AgentConversation

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id, user_id, project_id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### AgentMemory

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id, user_id, project_id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：content；需受控摘录。
- HIDDEN：无；完全禁止。

### AgentMessage

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：content, tool_calls, tool_results, cards；需受控摘录。
- HIDDEN：无；完全禁止。

### AgentOperation

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：result_json；需受控摘录。
- HIDDEN：无；完全禁止。

### AgentRequest

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id, user_id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：content_preview；需受控摘录。
- HIDDEN：无；完全禁止。

### AgentToolCall

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id, user_id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：arguments_json, result_summary；需受控摘录。
- HIDDEN：无；完全禁止。

### AIRun

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### AuditLog

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：id, user_id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：old_value, new_value, ip_address；需受控摘录。
- HIDDEN：无；完全禁止。

### BranchGroup

- display_fields：name
- filters：name, created_at, updated_at
- service 内部定位：id, project_id
- sort：name, created_at, updated_at
- aggregation：{"created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：name；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### BranchOption

- display_fields：name
- filters：name, is_selected, created_at, updated_at
- service 内部定位：id
- sort：name, created_at, updated_at
- aggregation：{"created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：name；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### ChangeProposal

- display_fields：status
- filters：status, reason, base_plan_version, confirmed_at, expires_at, applied_at, created_at, updated_at
- service 内部定位：id, project_id
- sort：base_plan_version, confirmed_at, expires_at, applied_at, created_at, updated_at
- aggregation：{"status": ["count", "group_by"], "confirmed_at": ["count_non_null", "min", "max"], "expires_at": ["count_non_null", "min", "max"], "applied_at": ["count_non_null", "min", "max"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：request, source, preview, diff, result, failure_reason；需受控摘录。
- HIDDEN：snapshot_token；完全禁止。

### DailyProjectSummary

- display_fields：无通用显示字段
- filters：summary_date, summary, risk_summary, next_action, management_attention, created_at, updated_at
- service 内部定位：id, project_id
- sort：summary_date, created_at, updated_at
- aggregation：{"summary_date": ["count_non_null", "min", "max"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：summary；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### Issue

- display_fields：title, status
- filters：title, severity, status, suggested_solution, resolved_at, created_at, updated_at
- service 内部定位：id, project_id, task_id
- sort：title, resolved_at, created_at, updated_at
- aggregation：{"severity": ["count", "group_by"], "status": ["count", "group_by"], "resolved_at": ["count_non_null", "min", "max"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：title；非 PostgreSQL 全文能力。
- SENSITIVE：description；需受控摘录。
- HIDDEN：无；完全禁止。

### Milestone

- display_fields：name, target_date, status
- filters：name, deliverable, acceptance_criteria, target_date, status, achieved_date, created_at, updated_at
- service 内部定位：id, project_id, owner_id
- sort：name, target_date, achieved_date, created_at, updated_at
- aggregation：{"target_date": ["count_non_null", "min", "max"], "status": ["count", "group_by"], "achieved_date": ["count_non_null", "min", "max"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：name；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### NotificationEvent

- display_fields：status
- filters：status, attempts, created_at, updated_at, event_type, channel, next_attempt_at, sent_at, delivery_uncertain, acknowledged_at
- service 内部定位：id, project_id
- sort：attempts, created_at, updated_at, next_attempt_at, sent_at, acknowledged_at
- aggregation：{"status": ["count", "group_by"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"], "next_attempt_at": ["count_non_null", "min", "max"], "sent_at": ["count_non_null", "min", "max"], "acknowledged_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：payload, last_error；需受控摘录。
- HIDDEN：无；完全禁止。

### PlanDraft

- display_fields：title, status
- filters：title, status, published_at, created_at, updated_at
- service 内部定位：id, project_id
- sort：title, published_at, created_at, updated_at
- aggregation：{"status": ["count", "group_by"], "published_at": ["count_non_null", "min", "max"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：title；非 PostgreSQL 全文能力。
- SENSITIVE：content, review, result, failure_reason；需受控摘录。
- HIDDEN：无；完全禁止。

### PlanVersion

- display_fields：无通用显示字段
- filters：kind, reason, created_at, updated_at
- service 内部定位：id, project_id
- sort：created_at, updated_at
- aggregation：{"created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：snapshot；需受控摘录。
- HIDDEN：无；完全禁止。

### ProgressUpdate

- display_fields：progress_percent
- filters：summary, progress_percent, ai_status, risk_detected, ai_analysis_failed, created_at, updated_at
- service 内部定位：id, task_id, user_id
- sort：progress_percent, created_at, updated_at
- aggregation：{"progress_percent": ["count_non_null", "min", "max", "avg"], "ai_status": ["count", "group_by"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：summary；非 PostgreSQL 全文能力。
- SENSITIVE：raw_content；需受控摘录。
- HIDDEN：无；完全禁止。

### ProjectMember

- display_fields：无通用显示字段
- filters：role, receive_notifications, is_active, created_at, updated_at
- service 内部定位：project_id, user_id
- sort：created_at, updated_at
- aggregation：{"role": ["count", "group_by"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### ProjectOwner

- display_fields：无通用显示字段
- filters：无通用筛选
- service 内部定位：project_id, user_id
- sort：无
- aggregation：{}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### Project

- display_fields：project_code, project_name, target_date, status
- filters：project_code, project_name, goal, target_date, status, risk_level, created_at, updated_at, start_date
- service 内部定位：id, owner_id
- sort：project_code, project_name, target_date, created_at, updated_at, start_date
- aggregation：{"target_date": ["count_non_null", "min", "max"], "status": ["count", "group_by"], "risk_level": ["count", "group_by"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"], "start_date": ["count_non_null", "min", "max"]}
- 文本搜索候选：project_code, project_name, goal；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### RiskEvent

- display_fields：status, title
- filters：event_type, level, status, title, cause, impact_date, impact_days, first_seen_at, last_seen_at, resolved_at, resolution, created_at, updated_at
- service 内部定位：id, project_id, task_id, issue_id, owner_id
- sort：title, impact_date, impact_days, first_seen_at, last_seen_at, resolved_at, created_at, updated_at
- aggregation：{"event_type": ["count", "group_by"], "level": ["count", "group_by"], "status": ["count", "group_by"], "impact_date": ["count_non_null", "min", "max"], "impact_days": ["count_non_null", "min", "max", "avg"], "first_seen_at": ["count_non_null", "min", "max"], "last_seen_at": ["count_non_null", "min", "max"], "resolved_at": ["count_non_null", "min", "max"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：title；非 PostgreSQL 全文能力。
- SENSITIVE：evidence；需受控摘录。
- HIDDEN：无；完全禁止。

### TaskGroup

- display_fields：name
- filters：name, created_at, updated_at
- service 内部定位：id, project_id
- sort：name, created_at, updated_at
- aggregation：{"created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：name；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### TaskDependency

- display_fields：无通用显示字段
- filters：link_type, created_at, updated_at, lag_days
- service 内部定位：id, project_id
- sort：created_at, updated_at, lag_days
- aggregation：{"link_type": ["count", "group_by"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"], "lag_days": ["count_non_null", "min", "max", "avg"]}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### TaskParticipant

- display_fields：无通用显示字段
- filters：role, created_at, updated_at
- service 内部定位：task_id, user_id
- sort：created_at, updated_at
- aggregation：{"role": ["count", "group_by"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：无；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

### Task

- display_fields：task_name, due_date, status, progress_percent, task_code
- filters：task_name, due_date, status, ai_status, ai_risk_level, completed_at, created_at, updated_at, start_date, progress_percent, work_stream, branch_label, is_active_branch, deliverable, acceptance_criteria, planned_duration_days, remaining_duration_days, actual_start_date, actual_finish_date, earliest_start_date, fixed_start_date, fixed_due_date, task_code
- service 内部定位：id, project_id, owner_id, milestone_id, task_group_id
- sort：task_name, due_date, completed_at, created_at, updated_at, start_date, progress_percent, planned_duration_days, remaining_duration_days, actual_start_date, actual_finish_date, earliest_start_date, fixed_start_date, fixed_due_date, task_code
- aggregation：{"due_date": ["count_non_null", "min", "max"], "status": ["count", "group_by"], "ai_status": ["count", "group_by"], "ai_risk_level": ["count", "group_by"], "completed_at": ["count_non_null", "min", "max"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"], "start_date": ["count_non_null", "min", "max"], "progress_percent": ["count_non_null", "min", "max", "avg"], "work_stream": ["count", "group_by"], "planned_duration_days": ["count_non_null", "min", "max", "avg"], "remaining_duration_days": ["count_non_null", "min", "max", "avg"], "actual_start_date": ["count_non_null", "min", "max"], "actual_finish_date": ["count_non_null", "min", "max"], "earliest_start_date": ["count_non_null", "min", "max"], "fixed_start_date": ["count_non_null", "min", "max"], "fixed_due_date": ["count_non_null", "min", "max"]}
- 文本搜索候选：task_name, work_stream, task_code；非 PostgreSQL 全文能力。
- SENSITIVE：description；需受控摘录。
- HIDDEN：无；完全禁止。

### User

- display_fields：name, status
- filters：name, username, department, role, status, created_at, updated_at
- service 内部定位：id
- sort：name, created_at, updated_at
- aggregation：{"department": ["count", "group_by"], "role": ["count", "group_by"], "status": ["count", "group_by"], "created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：name；非 PostgreSQL 全文能力。
- SENSITIVE：email, mobile, wechat_user_id, oa_admin_id；需受控摘录。
- HIDDEN：password_hash；完全禁止。

### WorkCalendar

- display_fields：name
- filters：name, timezone, weekdays, exceptions, created_at, updated_at
- service 内部定位：project_id
- sort：name, created_at, updated_at
- aggregation：{"created_at": ["count_non_null", "min", "max"], "updated_at": ["count_non_null", "min", "max"]}
- 文本搜索候选：name；非 PostgreSQL 全文能力。
- SENSITIVE：无；需受控摘录。
- HIDDEN：无；完全禁止。

INTERNAL 审计标识、版本和内部计数不能当作普通自然语言统计维度。所有 JSON 嵌套成员须独立白名单；HIDDEN 的 lease_token/snapshot_token 即使位于返回载荷中也要剥离。

## 自然语言别名

| 字段 | 别名 |
| --- | --- |
| action_items.id | ["id", "记录主键"] |
| action_items.project_id | ["project_id", "所属或关联项目的内部标识"] |
| action_items.task_id | ["task_id", "关联执行任务标识"] |
| action_items.issue_id | ["issue_id", "关联问题标识"] |
| action_items.owner_id | ["owner_id", "业务主负责人用户标识（不是创建人）"] |
| action_items.created_by | ["created_by", "创建人用户标识"] |
| action_items.title | ["title", "该业务对象的标题"] |
| action_items.due_date | ["due_date", "任务或行动项计划截止日期"] |
| action_items.status | ["status", "该对象状态；必须使用本表状态字典"] |
| action_items.priority | ["priority", "行动项优先级"] |
| action_items.completed_at | ["completed_at", "对象完成事件时间"] |
| action_items.created_at | ["created_at", "记录创建时间"] |
| action_items.updated_at | ["updated_at", "记录最后更新时间"] |
| action_items.advice_id | ["advice_id", "产生该行动的建议版本标识"] |
| advice_records.id | ["id", "记录主键"] |
| advice_records.issue_id | ["issue_id", "关联问题标识"] |
| advice_records.project_id | ["project_id", "所属或关联项目的内部标识"] |
| advice_records.version | ["version", "版本计数"] |
| advice_records.status | ["status", "该对象状态；必须使用本表状态字典"] |
| advice_records.context_digest | ["context_digest", "生成建议时上下文指纹"] |
| advice_records.model | ["model", "生成或分析所用模型标识"] |
| advice_records.generated_by | ["generated_by", "建议生成请求人用户标识"] |
| advice_records.decided_by | ["decided_by", "建议采纳或拒绝的决定人"] |
| advice_records.decided_at | ["decided_at", "建议决策时间"] |
| advice_records.decision_note | ["decision_note", "采纳或拒绝原因"] |
| advice_records.proposal_id | ["proposal_id", "关联计划变更方案标识（字符串主键）"] |
| advice_records.outcome | ["outcome", "建议效果枚举"] |
| advice_records.issue_resolved | ["issue_resolved", "评价时记录的问题是否已解决"] |
| advice_records.outcome_note | ["outcome_note", "建议效果说明"] |
| advice_records.evaluated_by | ["evaluated_by", "建议效果评价人"] |
| advice_records.evaluated_at | ["evaluated_at", "建议效果评价时间"] |
| advice_records.created_at | ["created_at", "记录创建时间"] |
| advice_records.updated_at | ["updated_at", "记录最后更新时间"] |
| agent_batch_items.id | ["id", "记录主键"] |
| agent_batch_items.operation_id | ["operation_id", "幂等操作标识"] |
| agent_batch_items.client_item_id | ["client_item_id", "批次内客户端条目幂等键"] |
| agent_batch_items.status | ["status", "该对象状态；必须使用本表状态字典"] |
| agent_batch_items.resource_id | ["resource_id", "多态业务资源标识"] |
| agent_batch_items.error_code | ["error_code", "结构化错误码"] |
| agent_batch_items.created_at | ["created_at", "记录创建时间"] |
| agent_batch_items.updated_at | ["updated_at", "记录最后更新时间"] |
| agent_batch_operations.id | ["id", "记录主键"] |
| agent_batch_operations.operation_id | ["operation_id", "幂等操作标识"] |
| agent_batch_operations.user_id | ["user_id", "关联用户标识"] |
| agent_batch_operations.tool_name | ["tool_name", "已注册结构化工具名"] |
| agent_batch_operations.status | ["status", "该对象状态；必须使用本表状态字典"] |
| agent_batch_operations.expected_count | ["expected_count", "预期条目数"] |
| agent_batch_operations.created_at | ["created_at", "记录创建时间"] |
| agent_batch_operations.updated_at | ["updated_at", "记录最后更新时间"] |
| agent_command_items.id | ["id", "记录主键"] |
| agent_command_items.plan_id | ["plan_id", "所属指令执行计划"] |
| agent_command_items.item_id | ["item_id", "同一命令计划内的逻辑步骤标识"] |
| agent_command_items.ordinal | ["ordinal", "步骤排序序号"] |
| agent_command_items.tool | ["tool", "该步骤的结构化工具名"] |
| agent_command_items.source_start | ["source_start", "授权原文片段起始偏移"] |
| agent_command_items.source_end | ["source_end", "授权原文片段结束偏移"] |
| agent_command_items.depends_on | ["depends_on", "同计划内依赖步骤 item_id 列表"] |
| agent_command_items.state | ["state", "指令条目执行状态；不是任务状态"] |
| agent_command_items.attempts | ["attempts", "执行或投递尝试次数"] |
| agent_command_items.created_at | ["created_at", "记录创建时间"] |
| agent_command_items.updated_at | ["updated_at", "记录最后更新时间"] |
| agent_command_plans.id | ["id", "记录主键"] |
| agent_command_plans.request_id | ["request_id", "助手请求标识"] |
| agent_command_plans.policy | ["policy", "命令计划事务策略"] |
| agent_command_plans.status | ["status", "该对象状态；必须使用本表状态字典"] |
| agent_command_plans.expected_count | ["expected_count", "预期条目数"] |
| agent_command_plans.revision | ["revision", "草案或方案内容修订号"] |
| agent_command_plans.lease_until | ["lease_until", "命令计划执行租约到期时间"] |
| agent_command_plans.created_at | ["created_at", "记录创建时间"] |
| agent_command_plans.updated_at | ["updated_at", "记录最后更新时间"] |
| agent_conversations.id | ["id", "记录主键"] |
| agent_conversations.user_id | ["user_id", "会话所有者"] |
| agent_conversations.title | ["title", "该业务对象的标题"] |
| agent_conversations.status | ["status", "该对象状态；必须使用本表状态字典"] |
| agent_conversations.project_id | ["project_id", "所属或关联项目的内部标识"] |
| agent_conversations.last_message_at | ["last_message_at", "会话最近消息时间"] |
| agent_conversations.summary | ["summary", "业务或会话摘要；AI 摘要不等于原始事实"] |
| agent_conversations.summary_updated_at | ["summary_updated_at", "会话滚动摘要更新时间"] |
| agent_conversations.summary_message_id | ["summary_message_id", "旧滚动摘要覆盖到的消息标识"] |
| agent_conversations.created_at | ["created_at", "记录创建时间"] |
| agent_conversations.updated_at | ["updated_at", "记录最后更新时间"] |
| agent_conversations.summary_through_message_id | ["summary_through_message_id", "滚动摘要覆盖到的最后消息标识"] |
| agent_memories.id | ["id", "记录主键"] |
| agent_memories.user_id | ["user_id", "记忆所有者"] |
| agent_memories.scope | ["scope", "用户记忆作用域 USER/PROJECT"] |
| agent_memories.memory_type | ["memory_type", "用户记忆内容类别"] |
| agent_memories.project_id | ["project_id", "所属或关联项目的内部标识"] |
| agent_memories.is_active | ["is_active", "上下文有效性标志；成员有效性或记忆启用"] |
| agent_memories.created_at | ["created_at", "记录创建时间"] |
| agent_memories.updated_at | ["updated_at", "记录最后更新时间"] |
| agent_messages.id | ["id", "记录主键"] |
| agent_messages.conversation_id | ["conversation_id", "所属助手会话"] |
| agent_messages.role | ["role", "当前表上下文中的角色"] |
| agent_messages.status | ["status", "该对象状态；必须使用本表状态字典"] |
| agent_messages.model | ["model", "生成或分析所用模型标识"] |
| agent_messages.created_at | ["created_at", "记录创建时间"] |
| agent_messages.completed_at | ["completed_at", "对象完成事件时间"] |
| agent_messages.parent_user_message_id | ["parent_user_message_id", "回答所属的用户消息"] |
| agent_messages.regenerated_from_id | ["regenerated_from_id", "该回答从哪个旧回答重新生成"] |
| agent_messages.answer_version | ["answer_version", "同一用户问题下的回答版本号"] |
| agent_messages.selected_answer_id | ["selected_answer_id", "用户消息当前选择的回答版本"] |
| agent_messages.association_status | ["association_status", "回答与用户消息绑定状态"] |
| agent_operations.id | ["id", "记录主键"] |
| agent_operations.operation_id | ["operation_id", "幂等操作标识"] |
| agent_operations.request_id | ["request_id", "助手请求标识"] |
| agent_operations.tool_name | ["tool_name", "已注册结构化工具名"] |
| agent_operations.args_digest | ["args_digest", "工具参数指纹"] |
| agent_operations.status | ["status", "该对象状态；必须使用本表状态字典"] |
| agent_operations.tool_call_id | ["tool_call_id", "模型工具调用标识"] |
| agent_operations.created_at | ["created_at", "记录创建时间"] |
| agent_requests.id | ["id", "记录主键"] |
| agent_requests.user_id | ["user_id", "关联用户标识"] |
| agent_requests.conversation_id | ["conversation_id", "所属助手会话"] |
| agent_requests.client_request_id | ["client_request_id", "会话内客户端发送幂等键"] |
| agent_requests.content_digest | ["content_digest", "请求原文指纹"] |
| agent_requests.status | ["status", "该对象状态；必须使用本表状态字典"] |
| agent_requests.user_message_id | ["user_message_id", "请求输入消息标识"] |
| agent_requests.assistant_message_id | ["assistant_message_id", "请求响应消息标识"] |
| agent_requests.error_code | ["error_code", "结构化错误码"] |
| agent_requests.completed_at | ["completed_at", "对象完成事件时间"] |
| agent_requests.created_at | ["created_at", "记录创建时间"] |
| agent_requests.updated_at | ["updated_at", "记录最后更新时间"] |
| agent_requests.cancel_requested | ["cancel_requested", "用户已请求取消生成"] |
| agent_requests.heartbeat_at | ["heartbeat_at", "生成请求最近存活心跳"] |
| agent_tool_calls.id | ["id", "记录主键"] |
| agent_tool_calls.request_id | ["request_id", "助手请求标识"] |
| agent_tool_calls.conversation_id | ["conversation_id", "所属助手会话"] |
| agent_tool_calls.user_id | ["user_id", "关联用户标识"] |
| agent_tool_calls.tool_name | ["tool_name", "已注册结构化工具名"] |
| agent_tool_calls.risk_level | ["risk_level", "项目风险等级或工具风险分类"] |
| agent_tool_calls.tool_call_id | ["tool_call_id", "模型工具调用标识"] |
| agent_tool_calls.success | ["success", "工具调用是否成功"] |
| agent_tool_calls.error_code | ["error_code", "结构化错误码"] |
| agent_tool_calls.duration_ms | ["duration_ms", "工具调用耗时毫秒"] |
| agent_tool_calls.created_at | ["created_at", "记录创建时间"] |
| ai_runs.id | ["id", "记录主键"] |
| ai_runs.run_type | ["run_type", "后台 AI 作业类型"] |
| ai_runs.resource_type | ["resource_type", "多态资源类型判别器"] |
| ai_runs.resource_id | ["resource_id", "多态业务资源标识"] |
| ai_runs.status | ["status", "该对象状态；必须使用本表状态字典"] |
| ai_runs.model | ["model", "生成或分析所用模型标识"] |
| ai_runs.error_code | ["error_code", "结构化错误码"] |
| ai_runs.user_message | ["user_message", "可呈现的作业状态说明"] |
| ai_runs.created_by | ["created_by", "创建人用户标识"] |
| ai_runs.created_at | ["created_at", "记录创建时间"] |
| ai_runs.started_at | ["started_at", "后台 AI 作业实际开始时间"] |
| ai_runs.completed_at | ["completed_at", "对象完成事件时间"] |
| alembic_version.version_num | ["version_num", "Alembic 已应用迁移版本字符串"] |
| audit_logs.id | ["id", "记录主键"] |
| audit_logs.user_id | ["user_id", "业务操作人"] |
| audit_logs.action | ["action", "业务审计动作名"] |
| audit_logs.resource_type | ["resource_type", "多态资源类型判别器"] |
| audit_logs.resource_id | ["resource_id", "多态业务资源标识"] |
| audit_logs.created_at | ["created_at", "记录创建时间"] |
| branch_groups.id | ["id", "记录主键"] |
| branch_groups.project_id | ["project_id", "所属或关联项目的内部标识"] |
| branch_groups.name | ["name", "该业务对象的显示名称"] |
| branch_groups.legacy_root_id | ["legacy_root_id", "迁移时保留的旧版分支根任务标识"] |
| branch_groups.entry_task_id | ["entry_task_id", "路线组入口任务"] |
| branch_groups.exit_task_id | ["exit_task_id", "路线组出口任务"] |
| branch_groups.created_at | ["created_at", "记录创建时间"] |
| branch_groups.updated_at | ["updated_at", "记录最后更新时间"] |
| branch_options.id | ["id", "记录主键"] |
| branch_options.group_id | ["group_id", "路线选项所属决策组"] |
| branch_options.name | ["name", "该业务对象的显示名称"] |
| branch_options.is_selected | ["is_selected", "路线选项是否被选中"] |
| branch_options.created_at | ["created_at", "记录创建时间"] |
| branch_options.updated_at | ["updated_at", "记录最后更新时间"] |
| change_proposals.id | ["id", "记录主键"] |
| change_proposals.project_id | ["project_id", "所属或关联项目的内部标识"] |
| change_proposals.created_by | ["created_by", "创建人用户标识"] |
| change_proposals.status | ["status", "该对象状态；必须使用本表状态字典"] |
| change_proposals.revision | ["revision", "草案或方案内容修订号"] |
| change_proposals.reason | ["reason", "业务变更或计划快照原因"] |
| change_proposals.create_key | ["create_key", "创建幂等键"] |
| change_proposals.create_hash | ["create_hash", "创建参数指纹"] |
| change_proposals.digest | ["digest", "审核内容摘要"] |
| change_proposals.base_plan_version | ["base_plan_version", "项目范围内基准 plan_versions.version；0 表示尚无版本"] |
| change_proposals.confirmed_by | ["confirmed_by", "变更确认人"] |
| change_proposals.confirmed_at | ["confirmed_at", "方案确认时间"] |
| change_proposals.expires_at | ["expires_at", "方案校验/确认有效期截止时间"] |
| change_proposals.applied_by | ["applied_by", "变更执行人"] |
| change_proposals.applied_at | ["applied_at", "方案执行时间"] |
| change_proposals.applied_version_id | ["applied_version_id", "执行变更生成的计划快照主键"] |
| change_proposals.apply_key | ["apply_key", "执行幂等键"] |
| change_proposals.created_at | ["created_at", "记录创建时间"] |
| change_proposals.updated_at | ["updated_at", "记录最后更新时间"] |
| daily_project_summaries.id | ["id", "记录主键"] |
| daily_project_summaries.project_id | ["project_id", "所属或关联项目的内部标识"] |
| daily_project_summaries.summary_date | ["summary_date", "日报对应的业务日期"] |
| daily_project_summaries.summary | ["summary", "业务或会话摘要；AI 摘要不等于原始事实"] |
| daily_project_summaries.risk_summary | ["risk_summary", "项目日报风险摘要（AI 参考）"] |
| daily_project_summaries.next_action | ["next_action", "日报下一步行动建议"] |
| daily_project_summaries.management_attention | ["management_attention", "日报管理关注事项"] |
| daily_project_summaries.created_at | ["created_at", "记录创建时间"] |
| daily_project_summaries.updated_at | ["updated_at", "记录最后更新时间"] |
| issues.id | ["id", "记录主键"] |
| issues.project_id | ["project_id", "所属或关联项目的内部标识"] |
| issues.task_id | ["task_id", "关联执行任务标识"] |
| issues.reported_by | ["reported_by", "问题报告人用户标识"] |
| issues.title | ["title", "该业务对象的标题"] |
| issues.severity | ["severity", "问题严重程度"] |
| issues.status | ["status", "该对象状态；必须使用本表状态字典"] |
| issues.suggested_solution | ["suggested_solution", "问题最新建议文本"] |
| issues.resolved_at | ["resolved_at", "问题或风险解决时间"] |
| issues.created_at | ["created_at", "记录创建时间"] |
| issues.updated_at | ["updated_at", "记录最后更新时间"] |
| milestones.id | ["id", "记录主键"] |
| milestones.project_id | ["project_id", "所属或关联项目的内部标识"] |
| milestones.name | ["name", "该业务对象的显示名称"] |
| milestones.deliverable | ["deliverable", "预期交付物"] |
| milestones.acceptance_criteria | ["acceptance_criteria", "交付验收标准"] |
| milestones.target_date | ["target_date", "项目或里程碑目标日期"] |
| milestones.owner_id | ["owner_id", "业务主负责人用户标识（不是创建人）"] |
| milestones.status | ["status", "该对象状态；必须使用本表状态字典"] |
| milestones.achieved_date | ["achieved_date", "里程碑实际达成日期"] |
| milestones.created_at | ["created_at", "记录创建时间"] |
| milestones.updated_at | ["updated_at", "记录最后更新时间"] |
| notification_events.id | ["id", "记录主键"] |
| notification_events.proposal_id | ["proposal_id", "关联计划变更方案标识（字符串主键）"] |
| notification_events.project_id | ["project_id", "所属或关联项目的内部标识"] |
| notification_events.recipient_id | ["recipient_id", "通知收件人用户标识"] |
| notification_events.status | ["status", "该对象状态；必须使用本表状态字典"] |
| notification_events.attempts | ["attempts", "执行或投递尝试次数"] |
| notification_events.created_at | ["created_at", "记录创建时间"] |
| notification_events.updated_at | ["updated_at", "记录最后更新时间"] |
| notification_events.event_type | ["event_type", "风险或通知事件种类"] |
| notification_events.channel | ["channel", "通知投递渠道"] |
| notification_events.next_attempt_at | ["next_attempt_at", "下一次通知重试时间"] |
| notification_events.sent_at | ["sent_at", "渠道接受通知时间"] |
| notification_events.delivery_uncertain | ["delivery_uncertain", "渠道超时导致投递结果不确定"] |
| notification_events.acknowledged_at | ["acknowledged_at", "收件人在系统确认知悉时间"] |
| notification_events.dedupe_key | ["dedupe_key", "业务事件去重标识"] |
| notification_events.risk_event_id | ["risk_event_id", "关联风险事件标识"] |
| plan_drafts.id | ["id", "记录主键"] |
| plan_drafts.created_by | ["created_by", "创建人用户标识"] |
| plan_drafts.title | ["title", "该业务对象的标题"] |
| plan_drafts.status | ["status", "该对象状态；必须使用本表状态字典"] |
| plan_drafts.revision | ["revision", "草案或方案内容修订号"] |
| plan_drafts.digest | ["digest", "审核内容摘要"] |
| plan_drafts.create_key | ["create_key", "创建幂等键"] |
| plan_drafts.publish_key | ["publish_key", "发布幂等键"] |
| plan_drafts.project_id | ["project_id", "所属或关联项目的内部标识"] |
| plan_drafts.published_by | ["published_by", "计划发布人"] |
| plan_drafts.published_at | ["published_at", "计划发布完成时间"] |
| plan_drafts.created_at | ["created_at", "记录创建时间"] |
| plan_drafts.updated_at | ["updated_at", "记录最后更新时间"] |
| plan_versions.id | ["id", "记录主键"] |
| plan_versions.project_id | ["project_id", "所属或关联项目的内部标识"] |
| plan_versions.version | ["version", "项目内唯一的计划版本序号"] |
| plan_versions.kind | ["kind", "计划快照种类"] |
| plan_versions.reason | ["reason", "业务变更或计划快照原因"] |
| plan_versions.created_by | ["created_by", "创建人用户标识"] |
| plan_versions.created_at | ["created_at", "记录创建时间"] |
| plan_versions.updated_at | ["updated_at", "记录最后更新时间"] |
| progress_updates.id | ["id", "记录主键"] |
| progress_updates.task_id | ["task_id", "关联执行任务标识"] |
| progress_updates.user_id | ["user_id", "进度汇报提交人"] |
| progress_updates.summary | ["summary", "业务或会话摘要；AI 摘要不等于原始事实"] |
| progress_updates.progress_percent | ["progress_percent", "完成百分比"] |
| progress_updates.ai_status | ["ai_status", "AI 分析给出的状态参考"] |
| progress_updates.risk_detected | ["risk_detected", "本次 AI 分析是否识别风险；NULL 为未知"] |
| progress_updates.ai_analysis_failed | ["ai_analysis_failed", "本次异步 AI 分析失败标志"] |
| progress_updates.created_at | ["汇报提交时间"] |
| progress_updates.updated_at | ["updated_at", "记录最后更新时间"] |
| project_members.project_id | ["project_id", "所属或关联项目的内部标识"] |
| project_members.user_id | ["user_id", "关联用户标识"] |
| project_members.role | ["role", "当前表上下文中的角色"] |
| project_members.receive_notifications | ["receive_notifications", "成员是否订阅通知"] |
| project_members.is_active | ["is_active", "上下文有效性标志；成员有效性或记忆启用"] |
| project_members.created_at | ["created_at", "记录创建时间"] |
| project_members.updated_at | ["updated_at", "记录最后更新时间"] |
| project_owners.project_id | ["project_id", "所属或关联项目的内部标识"] |
| project_owners.user_id | ["user_id", "关联用户标识"] |
| projects.id | ["id", "记录主键"] |
| projects.project_code | ["项目编号", "项目代码", "project code"] |
| projects.project_name | ["project_name", "项目业务名称"] |
| projects.goal | ["goal", "项目目标"] |
| projects.owner_id | ["owner_id", "业务主负责人用户标识（不是创建人）"] |
| projects.target_date | ["项目目标日期", "项目截止日期"] |
| projects.status | ["status", "该对象状态；必须使用本表状态字典"] |
| projects.risk_level | ["risk_level", "项目风险等级或工具风险分类"] |
| projects.created_at | ["created_at", "记录创建时间"] |
| projects.updated_at | ["updated_at", "记录最后更新时间"] |
| projects.start_date | ["start_date", "计划开始日期"] |
| risk_events.id | ["id", "记录主键"] |
| risk_events.project_id | ["project_id", "所属或关联项目的内部标识"] |
| risk_events.task_id | ["task_id", "关联执行任务标识"] |
| risk_events.issue_id | ["issue_id", "关联问题标识"] |
| risk_events.event_type | ["event_type", "风险或通知事件种类"] |
| risk_events.dedupe_key | ["dedupe_key", "业务事件去重标识"] |
| risk_events.level | ["level", "风险事件等级"] |
| risk_events.status | ["status", "该对象状态；必须使用本表状态字典"] |
| risk_events.title | ["title", "该业务对象的标题"] |
| risk_events.cause | ["cause", "风险检测触发原因"] |
| risk_events.impact_date | ["impact_date", "风险影响日期"] |
| risk_events.impact_days | ["impact_days", "预计/事实影响天数"] |
| risk_events.owner_id | ["owner_id", "业务主负责人用户标识（不是创建人）"] |
| risk_events.first_seen_at | ["first_seen_at", "风险首次被识别时间"] |
| risk_events.last_seen_at | ["last_seen_at", "风险最近仍被识别时间"] |
| risk_events.resolved_at | ["resolved_at", "问题或风险解决时间"] |
| risk_events.resolution | ["resolution", "风险关闭原因"] |
| risk_events.resolved_by | ["resolved_by", "风险关闭操作人"] |
| risk_events.created_at | ["created_at", "记录创建时间"] |
| risk_events.updated_at | ["updated_at", "记录最后更新时间"] |
| task_groups.id | ["id", "记录主键"] |
| task_groups.project_id | ["project_id", "所属或关联项目的内部标识"] |
| task_groups.name | ["name", "该业务对象的显示名称"] |
| task_groups.parent_id | ["parent_id", "父任务组标识；可构成树"] |
| task_groups.created_at | ["created_at", "记录创建时间"] |
| task_groups.updated_at | ["updated_at", "记录最后更新时间"] |
| task_links.id | ["id", "记录主键"] |
| task_links.project_id | ["project_id", "所属或关联项目的内部标识"] |
| task_links.source_id | ["source_id", "依赖前驱任务标识"] |
| task_links.target_id | ["target_id", "依赖后继任务标识"] |
| task_links.link_type | ["link_type", "任务依赖端点类型"] |
| task_links.created_at | ["created_at", "记录创建时间"] |
| task_links.updated_at | ["updated_at", "记录最后更新时间"] |
| task_links.lag_days | ["lag_days", "依赖等待天数"] |
| task_participants.task_id | ["task_id", "关联执行任务标识"] |
| task_participants.user_id | ["共同负责人", "任务负责人", "责任人", "owner", "assignee", "协作人", "观察者"] |
| task_participants.role | ["role", "当前表上下文中的角色"] |
| task_participants.created_at | ["created_at", "记录创建时间"] |
| task_participants.updated_at | ["updated_at", "记录最后更新时间"] |
| tasks.id | ["id", "记录主键"] |
| tasks.project_id | ["project_id", "所属或关联项目的内部标识"] |
| tasks.task_name | ["任务名称", "任务标题", "task title"] |
| tasks.owner_id | ["主负责人", "主要责任人", "primary owner"] |
| tasks.due_date | ["任务截止日期", "任务目标日期", "计划完成日期"] |
| tasks.status | ["status", "该对象状态；必须使用本表状态字典"] |
| tasks.ai_status | ["ai_status", "AI 分析给出的状态参考"] |
| tasks.ai_risk_level | ["ai_risk_level", "任务 AI 风险参考等级"] |
| tasks.completed_at | ["completed_at", "对象完成事件时间"] |
| tasks.created_at | ["created_at", "记录创建时间"] |
| tasks.updated_at | ["updated_at", "记录最后更新时间"] |
| tasks.start_date | ["start_date", "计划开始日期"] |
| tasks.progress_percent | ["任务完成度", "任务进度百分比"] |
| tasks.work_stream | ["工作流", "工作线", "work stream"] |
| tasks.branch_root_id | ["branch_root_id", "旧版路线共同根任务标识"] |
| tasks.branch_label | ["branch_label", "旧版路线标签"] |
| tasks.is_active_branch | ["is_active_branch", "是否当前激活路线"] |
| tasks.risk_context_changed_at | ["risk_context_changed_at", "计划或问题变化导致风险证据失效的时间边界"] |
| tasks.deliverable | ["deliverable", "预期交付物"] |
| tasks.acceptance_criteria | ["acceptance_criteria", "交付验收标准"] |
| tasks.planned_duration_days | ["planned_duration_days", "计划工期天数"] |
| tasks.remaining_duration_days | ["remaining_duration_days", "剩余工期天数"] |
| tasks.actual_start_date | ["actual_start_date", "任务实际开始日期"] |
| tasks.actual_finish_date | ["actual_finish_date", "任务实际结束日期"] |
| tasks.earliest_start_date | ["earliest_start_date", "排期约束：最早允许开始日期"] |
| tasks.fixed_start_date | ["fixed_start_date", "排期约束：固定开始日期"] |
| tasks.fixed_due_date | ["fixed_due_date", "排期约束：固定截止日期"] |
| tasks.branch_suspended_status | ["branch_suspended_status", "路线停用前保留的任务状态"] |
| tasks.calendar_id | ["calendar_id", "任务工作日历键"] |
| tasks.milestone_id | ["milestone_id", "任务关联里程碑"] |
| tasks.task_group_id | ["任务组", "结构化分组"] |
| tasks.branch_option_id | ["branch_option_id", "任务所属路线选项"] |
| tasks.version | ["version", "任务乐观锁版本"] |
| tasks.task_code | ["任务编号", "任务代码", "task code"] |
| users.id | ["id", "记录主键"] |
| users.name | ["name", "用户显示姓名"] |
| users.username | ["username", "用户登录名"] |
| users.department | ["department", "用户部门文本"] |
| users.role | ["role", "当前表上下文中的角色"] |
| users.status | ["status", "该对象状态；必须使用本表状态字典"] |
| users.created_at | ["created_at", "记录创建时间"] |
| users.updated_at | ["updated_at", "记录最后更新时间"] |
| work_calendars.project_id | ["project_id", "所属或关联项目的内部标识"] |
| work_calendars.name | ["name", "该业务对象的显示名称"] |
| work_calendars.timezone | ["timezone", "日历或业务时区名称"] |
| work_calendars.weekdays | ["weekdays", "工作日编号列表"] |
| work_calendars.exceptions | ["exceptions", "特殊日期到是否工作日的映射"] |
| work_calendars.version | ["version", "版本计数"] |
| work_calendars.created_at | ["created_at", "记录创建时间"] |
| work_calendars.updated_at | ["updated_at", "记录最后更新时间"] |

“负责人”需要先区分项目/任务/行动项；任务负责人默认包括主负责人和 OWNER；协作人必须加 role=COLLABORATOR，观察者是 WATCHER。updated_by/creator_id 等示例字段在本库不存在，禁止发明。

## JOIN PATH

以下为核心路径，所有外键与确认的逻辑路径完整清单见 DATABASE_RELATIONSHIPS / JSON。

### Project -> Task

- `projects.id = tasks.project_id`

### Task -> PrimaryOwner

- `tasks.owner_id = users.id`

### Project -> Owners

- `projects.id = project_owners.project_id`
- `project_owners.user_id = users.id`

### Project -> ActiveMembers

- `projects.id = project_members.project_id`
- `project_members.user_id = users.id`

### Task -> AllOwners

- `tasks.id = task_participants.task_id`
- `task_participants.user_id = users.id`

### Project -> Task -> Progress

- `projects.id = tasks.project_id`
- `tasks.id = progress_updates.task_id`

### Issue -> Advice -> Action

- `issues.id = advice_records.issue_id`
- `advice_records.id = action_items.advice_id`

### Project -> Risk -> Notification

- `projects.id = risk_events.project_id`
- `risk_events.id = notification_events.risk_event_id`

### Project -> Group -> Option -> Task

- `projects.id = branch_groups.project_id`
- `branch_groups.id = branch_options.group_id`
- `branch_options.id = tasks.branch_option_id`

### ChangeProposal -> AppliedSnapshot

- `change_proposals.applied_version_id = plan_versions.id`

### Task -> Calendar

- `tasks.calendar_id = work_calendars.project_id`

### Project -> Task -> Owner

- `projects.id = tasks.project_id`
- `tasks.owner_id = users.id`

### Task -> Progress

- `tasks.id = progress_updates.task_id`

### Project -> Risk

- `projects.id = risk_events.project_id`

### Notification -> Recipient

- `notification_events.recipient_id = users.id`

### Project -> PlanVersion

- `projects.id = plan_versions.project_id`

### ScopedTask



### ScopedNotification



### TaskDependency -> Endpoints

- `task_links.source_id = predecessor.id`
- `task_links.target_id = successor.id`

Task → AllOwners 附加 role=OWNER，结果与主负责人做并集；Project → ActiveMembers 附加 is_active=true。N:N JOIN 后聚合任务时用去重业务主键或 EXISTS。不能把汇报数、负责人数量乘积当任务数。自引用需要表别名；task_groups 任意深度子树 requires_recursive_cte=true，限制深度并检测环。tasks.branch_root_id 为路线根，不代表无限级父子任务。

## 常见业务查询 Intent

| Intent | 用户问题 | 表 | 已登记路径 | 筛选 | Tool | 语义 |
| --- | --- | --- | --- | --- | --- | --- |
| list_project_tasks | 查看某项目所有任务 | ["projects", "tasks"] | Project -> Task | ["project_code"] | search_tasks | 全量必须遍历分页；历史与当前执行范围显式区分 |
| list_tasks_by_owner | 查看某负责人任务 | ["users", "tasks", "task_participants"] | Task -> AllOwners | ["owner identity"] | search_tasks | 姓名先消歧；完整负责人为主负责人与 OWNER 参与关系并集；当前工具过滤需修复 |
| get_project_progress | 查看项目进度 | ["projects", "tasks", "progress_updates", "issues"] | Project -> Task -> Progress | ["project_code", "days"] | get_project_progress_overview | 没有 projects.progress；不以 AVG(tasks.progress_percent) 代表项目进度；当前 completed 计数缺陷见风险 |
| get_task_progress | 查看任务汇报 | ["tasks", "progress_updates"] | Task -> Progress | ["task identity"] | get_task_progress | 任务当前百分比与每次 AI 分析百分比分列；按 created_at,id 排序 |
| list_overdue_tasks | 查询延期未完成任务 | ["tasks"] | ScopedTask | ["due_date < business_today", "status", "is_active_branch"] | query_tasks | 已超期是日期事实，AI DELAYED 为分析标签，不混用；NULL due_date 为未知 |
| count_tasks_by_status | 按状态统计任务 | ["tasks"] | ScopedTask | ["project_code"] | query_entities | 只聚合可见任务，按主键去重；未知百分比不按 0 处理 |
| get_dependency_graph | 查看前后置任务 | ["task_links", "tasks"] | TaskDependency -> Endpoints | ["project_code"] | get_dependency_graph | 两个任务别名；跨项目和环检测走 SchedulingService；闭包需要递归或服务图算法 |
| get_issue_followup | 查看问题建议与行动 | ["issues", "advice_records", "action_items"] | Issue -> Advice -> Action | ["issue_id"] | get_issue_advice | 最新建议不替代历史版本；建议不是事实，证据逐资源鉴权 |
| list_project_risks | 查看项目风险 | ["projects", "risk_events"] | Project -> Risk | ["project_code", "status", "event_type"] | list_risk_events | 风险事实、预测、信息缺失区分 |
| get_notifications | 查看通知是否已读 | ["notification_events"] | ScopedNotification | ["recipient=current_actor"] | get_notification_status | SENT 仅渠道接受；ACKNOWLEDGED 才是系统确认 |
| get_plan_snapshot | 查看历史计划 | ["plan_versions", "projects"] | Project -> PlanVersion | ["project_id", "version"] | get_plan_version | 建议新增；不是直接读取完整 snapshot JSON |
| list_current_members | 查看项目成员 | ["projects", "project_members", "users"] | Project -> ActiveMembers | ["project_code"] | query_entities | 成员不等于项目负责人；默认 is_active=true |

### 进度、风险与事实口径

数据库没有 projects.progress 字段，也没有明确授权用任务平均百分比代表项目完成度。tasks.progress_percent 是任务当前快照；progress_updates.progress_percent 是某次 AI 汇报分析值；两者不能自动等同。ProgressService.submit_progress 先写原文，AI 后台补充分析；缺值表示未知。get_project_progress_overview 按近期 N×24 小时的汇报与查询时任务状态汇总，但当前 completed 恒零问题必须先修复。日报是带 summary_date 的 AI 总结，不替代当前任务事实；风险预测来自 SchedulingService，不能凭任务平均进度推算完成日期。

## 状态字典

全部 PostgreSQL 原生枚举数量为 0。CODE_ENUM 是应用枚举；CHECK_CONSTRAINT 是实际数据库约束；partial code dictionary 不保证枚举完整，未登记状态应返回 UNKNOWN。不同实体相同字符串可能含义不同。

### action_items.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/action_item.py:37`。

| 值 | 中文含义 |
| --- | --- |
| OPEN | 开放 |
| IN_PROGRESS | 进行中 |
| DONE | 已完成 |
| CANCELLED | 已取消 |

### action_items.priority

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/action_item.py:37`。

| 值 | 中文含义 |
| --- | --- |
| LOW | 低 |
| MEDIUM | 中 |
| HIGH | 高 |
| URGENT | 紧急 |

### advice_records.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/advice_record.py:50`。

| 值 | 中文含义 |
| --- | --- |
| PROPOSED | 建议待决策 |
| ADOPTED | 已采纳 |
| REJECTED | 已拒绝 |
| SUPERSEDED | 被新版替代 |

### advice_records.outcome

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/advice_record.py:50`。

| 值 | 中文含义 |
| --- | --- |
| EFFECTIVE | 有效 |
| PARTIAL | 部分有效/部分成功（按实体） |
| INEFFECTIVE | 无效 |

### agent_conversations.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/agent_conversation.py:41`。

| 值 | 中文含义 |
| --- | --- |
| ACTIVE | 启用/进行中（按实体） |
| ARCHIVED | 归档 |

### agent_memories.scope

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/agent_memory.py:25`。

| 值 | 中文含义 |
| --- | --- |
| USER | 用户 |
| PROJECT | 项目范围 |

### agent_memories.memory_type

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/agent_memory.py:25`。

| 值 | 中文含义 |
| --- | --- |
| PREFERENCE | 偏好 |
| INSTRUCTION | 显式指令 |
| PINNED_CONTEXT | 固定上下文 |

### agent_messages.role

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/agent_conversation.py:88`。

| 值 | 中文含义 |
| --- | --- |
| USER | 用户 |
| ASSISTANT | 助手 |
| SYSTEM | 系统 |

### agent_messages.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/agent_conversation.py:88`。

| 值 | 中文含义 |
| --- | --- |
| PENDING | 等待 |
| STREAMING | 生成中 |
| COMPLETED | 已完成 |
| FAILED | 失败 |
| STOPPED | 已停止 |
| INTERRUPTED | 已中断 |

### agent_messages.association_status

来源：CODE_REFERENCE；完整定义：True；证据：`backend/app/models/agent_conversation.py:88`。

| 值 | 中文含义 |
| --- | --- |
| NORMAL | 正常 |
| LEGACY | 历史绑定未知 |

### agent_operations.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/agent_request.py:93`。

| 值 | 中文含义 |
| --- | --- |
| SUCCEEDED | 成功 |
| FAILED | 失败 |

### agent_requests.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/agent_request.py:44`。

| 值 | 中文含义 |
| --- | --- |
| ACCEPTED | 已接收 |
| RUNNING | 执行中 |
| COMPLETED | 已完成 |
| FAILED | 失败 |
| STOPPED | 已停止 |
| INTERRUPTED | 已中断 |

### ai_runs.run_type

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/ai_run.py:29`。

| 值 | 中文含义 |
| --- | --- |
| PROGRESS_ANALYSIS | 进度分析 |
| ISSUE_ADVICE | 问题建议生成 |
| DAILY_SUMMARY | 日报生成 |
| CONVERSATION_SUMMARY | 会话摘要 |

### ai_runs.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/ai_run.py:29`。

| 值 | 中文含义 |
| --- | --- |
| QUEUED | 排队中 |
| RUNNING | 执行中 |
| SUCCEEDED | 成功 |
| FAILED | 失败 |
| DISABLED | 未启用 |

### change_proposals.status

来源：CHECK_CONSTRAINT；完整定义：True；证据：`backend/app/models/change_proposal.py:25`。

| 值 | 中文含义 |
| --- | --- |
| DRAFT | 草稿 |
| VALIDATED | 已验证 |
| CONFIRMED | 已确认 |
| APPLIED | 已执行 |
| REJECTED | 已拒绝 |
| EXPIRED | 已过期 |
| FAILED | 失败 |

### issues.severity

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/issue.py:31`。

| 值 | 中文含义 |
| --- | --- |
| LOW | 低 |
| MEDIUM | 中 |
| HIGH | 高 |
| CRITICAL | 严重 |

### issues.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/issue.py:31`。

| 值 | 中文含义 |
| --- | --- |
| OPEN | 开放 |
| IN_PROGRESS | 进行中 |
| RESOLVED | 已解决 |

### milestones.status

来源：CHECK_CONSTRAINT；完整定义：True；证据：`backend/app/models/planning.py:71`。

| 值 | 中文含义 |
| --- | --- |
| PLANNED | 已计划 |
| ACHIEVED | 已达成 |
| CANCELLED | 已取消 |

### notification_events.status

来源：CHECK_CONSTRAINT；完整定义：True；证据：`backend/app/models/notification.py:41`。

| 值 | 中文含义 |
| --- | --- |
| QUEUED | 排队中 |
| SENT | 渠道已接受 |
| FAILED | 失败 |
| ACKNOWLEDGED | 本人已确认 |

### plan_drafts.status

来源：CHECK_CONSTRAINT；完整定义：True；证据：`backend/app/models/plan_draft.py:27`。

| 值 | 中文含义 |
| --- | --- |
| DRAFT | 草稿 |
| REVIEWED | 已审阅 |
| PUBLISHED | 已发布 |
| DISCARDED | 已废弃 |
| FAILED | 失败 |

### progress_updates.ai_status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/progress_update.py:13`。

| 值 | 中文含义 |
| --- | --- |
| ON_TRACK | 按计划 |
| AT_RISK | 存在风险 |
| DELAYED | 延期 |

### project_members.role

来源：CHECK_CONSTRAINT；完整定义：True；证据：`backend/app/models/planning.py:25`。

| 值 | 中文含义 |
| --- | --- |
| CONTRIBUTOR | 贡献成员 |
| OBSERVER | 观察成员 |

### projects.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/project.py:36`。

| 值 | 中文含义 |
| --- | --- |
| PLANNING | 规划中 |
| ACTIVE | 启用/进行中（按实体） |
| COMPLETED | 已完成 |
| CANCELLED | 已取消 |

### projects.risk_level

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/project.py:36`。

| 值 | 中文含义 |
| --- | --- |
| NORMAL | 正常 |
| AT_RISK | 存在风险 |
| DELAYED | 延期 |

### risk_events.event_type

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/risk_event.py:57`。

| 值 | 中文含义 |
| --- | --- |
| OVERDUE | 已超期事实 |
| FORECAST_DELAY | 预测延期 |
| ISSUE | 问题触发 |
| MISSING_DATA | 资料缺失 |

### risk_events.level

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/risk_event.py:57`。

| 值 | 中文含义 |
| --- | --- |
| AT_RISK | 存在风险 |
| DELAYED | 延期 |

### risk_events.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/risk_event.py:57`。

| 值 | 中文含义 |
| --- | --- |
| OPEN | 开放 |
| RESOLVED | 已解决 |

### task_links.link_type

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/task.py:178`。

| 值 | 中文含义 |
| --- | --- |
| FINISH_TO_START | 前驱完成后后继开始 |
| START_TO_START | 前驱开始后后继开始 |
| FINISH_TO_FINISH | 前驱完成后后继完成 |
| START_TO_FINISH | 前驱开始后后继完成 |

### task_participants.role

来源：CHECK_CONSTRAINT；完整定义：True；证据：`backend/app/models/planning.py:41`。

| 值 | 中文含义 |
| --- | --- |
| COLLABORATOR | 协作人 |
| WATCHER | 关注人 |
| OWNER | 共同负责人 |

### tasks.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/task.py:48`。

| 值 | 中文含义 |
| --- | --- |
| TODO | 未开始 |
| IN_PROGRESS | 进行中 |
| COMPLETED | 已完成 |
| CANCELLED | 已取消 |

### tasks.ai_status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/task.py:48`。

| 值 | 中文含义 |
| --- | --- |
| ON_TRACK | 按计划 |
| AT_RISK | 存在风险 |
| DELAYED | 延期 |

### tasks.ai_risk_level

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/task.py:48`。

| 值 | 中文含义 |
| --- | --- |
| ON_TRACK | 按计划 |
| AT_RISK | 存在风险 |
| DELAYED | 延期 |

### users.role

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/user.py:26`。

| 值 | 中文含义 |
| --- | --- |
| ADMIN | 管理员 |
| EXECUTIVE | 管理层只读 |
| PROJECT_OWNER | 项目负责人角色 |
| MEMBER | 成员角色 |

### users.status

来源：CODE_ENUM；完整定义：True；证据：`backend/app/models/user.py:26`。

| 值 | 中文含义 |
| --- | --- |
| ACTIVE | 启用/进行中（按实体） |
| INACTIVE | 停用 |

### agent_command_plans.status

来源：CODE_REFERENCE；完整定义：False；证据：`backend/app/services/agent_commands.py`。

| 值 | 中文含义 |
| --- | --- |
| COMPLETED | 已完成 |
| FAILED | 失败 |
| PARTIAL | 部分有效/部分成功（按实体） |
| PAUSED | 暂停 |
| PENDING | 等待 |
| PLANNING | 规划中 |
| PLANNING_FAILED | 规划失败 |
| SUCCEEDED | 成功 |

### agent_command_items.state

来源：CODE_REFERENCE；完整定义：False；证据：`backend/app/services/agent_commands.py`。

| 值 | 中文含义 |
| --- | --- |
| BLOCKED | UNKNOWN |
| FAILED | 失败 |
| PENDING | 等待 |
| ROLLED_BACK | UNKNOWN |
| RUNNING | 执行中 |
| SUCCEEDED | 成功 |
| UNKNOWN | 提交结果未知 |

### agent_batch_operations.status

来源：CODE_REFERENCE；完整定义：False；证据：`backend/app/services/agent_batch.py`。

| 值 | 中文含义 |
| --- | --- |
| FAILED | 失败 |
| PENDING | 等待 |
| VALIDATION_FAILED | 校验失败 |

### agent_batch_items.status

来源：CODE_REFERENCE；完整定义：False；证据：`backend/app/services/agent_batch.py`。

| 值 | 中文含义 |
| --- | --- |
| FAILED | 失败 |
| PENDING | 等待 |
| VALIDATION_FAILED | 校验失败 |

### notification_events.event_type

来源：CODE_REFERENCE；完整定义：False；证据：`backend/app/models/notification.py:41`。

| 值 | 中文含义 |
| --- | --- |
| PLAN_CHANGE | 计划变更通知 |
| RISK_OPENED | 风险开启通知 |
| RISK_ESCALATED | 风险升级通知 |
| RISK_RESOLVED | 风险关闭通知 |

### plan_versions.kind

来源：CODE_REFERENCE；完整定义：False；证据：`backend/app/models/planning.py:128`。

| 值 | 中文含义 |
| --- | --- |
| SNAPSHOT | 计划快照 |

### agent_command_plans.policy

来源：CODE_REFERENCE；完整定义：False；证据：`backend/app/models/agent_command.py:19`。

| 值 | 中文含义 |
| --- | --- |
| independent | 步骤独立执行 |
| atomic | 支持范围内整批原子执行 |

## 已确认的状态转换片段

### change_proposals

证据：`backend/app/services/change_proposal.py:549`；非完整转换矩阵。这不是完整转换矩阵；编辑会清除旧确认；APPLIED 不可直接撤销

| 起点 | 终点 | 条件 |
| --- | --- | --- |
| ["DRAFT", "VALIDATED", "FAILED"] | VALIDATED | validate 且 candidate.feasible=true；生成 digest |
| ["DRAFT", "VALIDATED", "FAILED"] | DRAFT | validate 不可行；digest=null |
| ["VALIDATED"] | CONFIRMED | revision/digest 匹配、当前用户确认、未过期且指纹一致 |
| ["CONFIRMED"] | APPLIED | 通过 Business Service 重验、锁定、执行成功 |
| ["VALIDATED", "CONFIRMED"] | EXPIRED | 超过有效期、跨业务日或上下文变化 |
| ["CONFIRMED"] | FAILED | 执行失败 |

### plan_drafts

证据：`backend/app/services/plan_draft.py:154`；非完整转换矩阵。review 会更新记录，不能归类为只读

| 起点 | 终点 | 条件 |
| --- | --- | --- |
| ["DRAFT"] | REVIEWED | review 无 blocking 并生成 digest |
| ["REVIEWED"] | PUBLISHED | 发布权限、版本、确认及幂等验证 |

### risk_events

证据：`backend/app/services/risk_event.py:426`；非完整转换矩阵。

| 起点 | 终点 | 条件 |
| --- | --- | --- |
| ["OPEN"] | RESOLVED | 检测条件消失或授权业务关闭 |
| ["RESOLVED"] | OPEN | 确定性检测器再次识别同一 dedupe_key |

### tasks

证据：`backend/app/services/task.py:320`；非完整转换矩阵。代码没有简单 TODO→IN_PROGRESS→COMPLETED 强制矩阵；授权状态更新还受实际日期及排期约束。设为 COMPLETED 写 completed_at，从完成改回其他状态清空它；路线切换可暂存并恢复状态。不能宣称任意转换均被允许。

| 起点 | 终点 | 条件 |
| --- | --- | --- |

## 日期与审计语义

| 字段 | 含义 |
| --- | --- |
| action_items.due_date | 行动项：任务或行动项计划截止日期 |
| action_items.completed_at | 行动项：对象完成事件时间，具体为任务完成或请求/消息/作业结束 |
| action_items.created_at | 行动项：记录创建时间，不是计划开始或汇报涵盖日期 |
| action_items.updated_at | 行动项：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| advice_records.decided_at | 建议版本：建议决策时间 |
| advice_records.evaluated_at | 建议版本：建议效果评价时间 |
| advice_records.created_at | 建议版本：记录创建时间，不是计划开始或汇报涵盖日期 |
| advice_records.updated_at | 建议版本：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| agent_batch_items.created_at | 批量操作条目：记录创建时间，不是计划开始或汇报涵盖日期 |
| agent_batch_items.updated_at | 批量操作条目：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| agent_batch_operations.created_at | 批量操作：记录创建时间，不是计划开始或汇报涵盖日期 |
| agent_batch_operations.updated_at | 批量操作：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| agent_command_items.created_at | 指令执行步骤：记录创建时间，不是计划开始或汇报涵盖日期 |
| agent_command_items.updated_at | 指令执行步骤：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| agent_command_plans.lease_until | 指令执行计划：命令计划执行租约到期时间 |
| agent_command_plans.created_at | 指令执行计划：记录创建时间，不是计划开始或汇报涵盖日期 |
| agent_command_plans.updated_at | 指令执行计划：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| agent_conversations.last_message_at | 助手会话：会话最近消息时间 |
| agent_conversations.summary_updated_at | 助手会话：会话滚动摘要更新时间 |
| agent_conversations.created_at | 助手会话：记录创建时间，不是计划开始或汇报涵盖日期 |
| agent_conversations.updated_at | 助手会话：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| agent_memories.created_at | 用户记忆：记录创建时间，不是计划开始或汇报涵盖日期 |
| agent_memories.updated_at | 用户记忆：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| agent_messages.created_at | 助手消息：记录创建时间，不是计划开始或汇报涵盖日期 |
| agent_messages.completed_at | 助手消息：对象完成事件时间，具体为任务完成或请求/消息/作业结束 |
| agent_operations.created_at | 工具写入回执：记录创建时间，不是计划开始或汇报涵盖日期 |
| agent_requests.completed_at | 助手请求：对象完成事件时间，具体为任务完成或请求/消息/作业结束 |
| agent_requests.created_at | 助手请求：记录创建时间，不是计划开始或汇报涵盖日期 |
| agent_requests.updated_at | 助手请求：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| agent_requests.heartbeat_at | 助手请求：生成请求最近存活心跳 |
| agent_tool_calls.created_at | 工具调用审计：记录创建时间，不是计划开始或汇报涵盖日期 |
| ai_runs.created_at | 后台 AI 运行：记录创建时间，不是计划开始或汇报涵盖日期 |
| ai_runs.started_at | 后台 AI 运行：后台 AI 作业实际开始时间 |
| ai_runs.completed_at | 后台 AI 运行：对象完成事件时间，具体为任务完成或请求/消息/作业结束 |
| audit_logs.created_at | 业务审计日志：记录创建时间，不是计划开始或汇报涵盖日期 |
| branch_groups.created_at | 路线决策组：记录创建时间，不是计划开始或汇报涵盖日期 |
| branch_groups.updated_at | 路线决策组：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| branch_options.created_at | 路线选项：记录创建时间，不是计划开始或汇报涵盖日期 |
| branch_options.updated_at | 路线选项：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| change_proposals.confirmed_at | 计划变更方案：方案确认时间 |
| change_proposals.expires_at | 计划变更方案：方案校验/确认有效期截止时间 |
| change_proposals.applied_at | 计划变更方案：方案执行时间 |
| change_proposals.created_at | 计划变更方案：记录创建时间，不是计划开始或汇报涵盖日期 |
| change_proposals.updated_at | 计划变更方案：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| daily_project_summaries.summary_date | 项目日报：日报对应的业务日期，不是生成日期 |
| daily_project_summaries.created_at | 项目日报：记录创建时间，不是计划开始或汇报涵盖日期 |
| daily_project_summaries.updated_at | 项目日报：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| issues.resolved_at | 问题：问题或风险解决时间 |
| issues.created_at | 问题：记录创建时间，不是计划开始或汇报涵盖日期 |
| issues.updated_at | 问题：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| milestones.target_date | 里程碑：项目或里程碑目标日期 |
| milestones.achieved_date | 里程碑：里程碑实际达成日期 |
| milestones.created_at | 里程碑：记录创建时间，不是计划开始或汇报涵盖日期 |
| milestones.updated_at | 里程碑：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| notification_events.created_at | 通知事件：记录创建时间，不是计划开始或汇报涵盖日期 |
| notification_events.updated_at | 通知事件：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| notification_events.next_attempt_at | 通知事件：下一次通知重试时间 |
| notification_events.sent_at | 通知事件：渠道接受通知时间，不代表阅读 |
| notification_events.acknowledged_at | 通知事件：收件人在系统确认知悉时间 |
| plan_drafts.published_at | 项目计划草案：计划发布完成时间 |
| plan_drafts.created_at | 项目计划草案：记录创建时间，不是计划开始或汇报涵盖日期 |
| plan_drafts.updated_at | 项目计划草案：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| plan_versions.created_at | 计划快照：记录创建时间，不是计划开始或汇报涵盖日期 |
| plan_versions.updated_at | 计划快照：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| progress_updates.created_at | 进度汇报：记录创建时间，不是计划开始或汇报涵盖日期 |
| progress_updates.updated_at | 进度汇报：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| project_members.created_at | 项目成员：记录创建时间，不是计划开始或汇报涵盖日期 |
| project_members.updated_at | 项目成员：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| projects.target_date | 项目：项目或里程碑目标日期 |
| projects.created_at | 项目：记录创建时间，不是计划开始或汇报涵盖日期 |
| projects.updated_at | 项目：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| projects.start_date | 项目：计划开始日期 |
| risk_events.impact_date | 风险事件：风险影响日期，依风险类型为截止或预测日期 |
| risk_events.first_seen_at | 风险事件：风险首次被识别时间 |
| risk_events.last_seen_at | 风险事件：风险最近仍被识别时间 |
| risk_events.resolved_at | 风险事件：问题或风险解决时间 |
| risk_events.created_at | 风险事件：记录创建时间，不是计划开始或汇报涵盖日期 |
| risk_events.updated_at | 风险事件：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| task_groups.created_at | 任务组：记录创建时间，不是计划开始或汇报涵盖日期 |
| task_groups.updated_at | 任务组：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| task_links.created_at | 任务依赖：记录创建时间，不是计划开始或汇报涵盖日期 |
| task_links.updated_at | 任务依赖：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| task_participants.created_at | 任务参与关系：记录创建时间，不是计划开始或汇报涵盖日期 |
| task_participants.updated_at | 任务参与关系：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| tasks.due_date | 执行任务：任务或行动项计划截止日期 |
| tasks.completed_at | 执行任务：对象完成事件时间，具体为任务完成或请求/消息/作业结束 |
| tasks.created_at | 执行任务：记录创建时间，不是计划开始或汇报涵盖日期 |
| tasks.updated_at | 执行任务：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| tasks.start_date | 执行任务：计划开始日期 |
| tasks.risk_context_changed_at | 执行任务：计划或问题变化导致风险证据失效的时间边界 |
| tasks.actual_start_date | 执行任务：任务实际开始日期 |
| tasks.actual_finish_date | 执行任务：任务实际结束日期 |
| tasks.earliest_start_date | 执行任务：排期约束：最早允许开始日期 |
| tasks.fixed_start_date | 执行任务：排期约束：固定开始日期 |
| tasks.fixed_due_date | 执行任务：排期约束：固定截止日期 |
| users.created_at | 用户：记录创建时间，不是计划开始或汇报涵盖日期 |
| users.updated_at | 用户：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |
| work_calendars.created_at | 项目工作日历：记录创建时间，不是计划开始或汇报涵盖日期 |
| work_calendars.updated_at | 项目工作日历：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 |

created_at ≠ start_date；updated_at ≠ progress_date（本库无 progress_date）；target_date/due_date ≠ completed_at/actual_finish_date。created_by/reported_by/user_id 是操作人或汇报人，owner_id 是业务负责人；代报时两者不同。DATE 是业务日，timestamptz 是事件时刻；时间窗口用 BusinessClock/项目日历时区，不用 Agent 本机日期。

## RAG / MCP / Query Service 接入

```mermaid
flowchart TD
    NL[自然语言] --> E[业务实体与别名解析]
    E --> T[已登记 Tool Calling]
    T --> X[Tool Executor: 身份 权限 确认 幂等]
    X --> Q[只读 Query Service]
    X --> W[Write Service]
    Q --> B[Business Service 与对象权限]
    W --> B
    B --> O[ORM 参数绑定]
    O --> P[(PostgreSQL)]
```

语义层用于路由、参数解释和 JOIN 白名单；执行权限必须由代码强制。按 entity/field/relationship_id 分片入 RAG，并记录 source、confidence、analysis_date；禁止把密码、原始审计、客户文本整表嵌入。检索内容只当资料，不能覆盖身份或工具授权。MCP 的 resources 可发布静态字典，tools 暴露参数化业务操作；本仓库 mcp 当前只有技能与说明，未发现独立 MCP Server 实现。

只读服务应使用只读事务、绑定参数、明确字段允许列表、limit/timeout/成本预算；不接受任意 SQL、表名、字段表达式或 JOIN。写服务必须经过现有业务方法，保持排期校验、确认、幂等和乐观锁；计划快照、AI 分析字段、审计、通知投递状态由所属服务管理，不能直接改表。

## AGENT_QUERY_RULES

### RULE 1

优先使用已经定义的业务实体，不要直接猜数据库表。

### RULE 2

优先使用 semantic_aliases 将自然语言映射到字段；重名需结合实体消歧。

### RULE 3

JOIN 必须优先使用 join_paths，并由受控服务编译。

### RULE 4

不存在已确认关系时，不得自行假设 JOIN；MEDIUM/LOW 推断不可用于自动 JOIN。

### RULE 5

默认应用 soft_delete_rules；不存在软删除机制时不得虚构条件。

### RULE 6

必须应用 tenant / organization / workspace 范围（存在时）及当前系统对象权限；不可移除范围约束。

### RULE 7

不得读取、过滤、排序、聚合或输出 HIDDEN 字段，亦不得将其放入 RAG。

### RULE 8

不得向用户暴露 INTERNAL ID，除非业务操作需要；内部审计字段不作为普通查询能力。

### RULE 9

状态查询必须使用对应实体状态字典；未知值返回 UNKNOWN，不发明状态。

### RULE 10

Agent 不直接执行数据库写 SQL。

### RULE 11

写操作必须调用 Business Tool，并复用 Business Service 权限和校验。

### RULE 12

重要写操作必须 requires_confirmation = true；本语义层建议所有 WRITE TOOL 默认确认。

