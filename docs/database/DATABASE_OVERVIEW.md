# DATABASE_OVERVIEW

> Copyright 2024–2026 Jack Zhang. Apache License 2.0；保留 NOTICE 署名。
> 采集日期：2026-09-15；结构来源：实际 PostgreSQL 只读目录；业务语义来源：当前工作区模型、迁移与服务。
> 未读取业务记录。PUBLIC 仅表示字段可经授权业务 DTO 使用，不表示互联网公开或授权直连数据库。

## 阅读入口

| 文件 | 用途 |
| --- | --- |
| [DATABASE_DICTIONARY.md](DATABASE_DICTIONARY.md) | 逐表、逐字段完整字典和索引 |
| [DATABASE_RELATIONSHIPS.md](DATABASE_RELATIONSHIPS.md) | 全部外键、推断关系、证据及 JOIN 路径 |
| [DATABASE_ER.md](DATABASE_ER.md) | 按业务模块划分的 Mermaid ER 图 |
| [AGENT_DATABASE_GUIDE.md](AGENT_DATABASE_GUIDE.md) | 实体、别名、状态、时间、权限和查询口径 |
| [AGENT_TOOLS.md](AGENT_TOOLS.md) | 现有工具与建议权限、参数、DTO、服务 |
| [database_schema.json](database_schema.json) | 完整机器可读模型 |
| [agent_semantic_layer.yaml](agent_semantic_layer.yaml) | 供 Agent/MCP/RAG 加载的语义层 |
| [AGENT_QUERY_RULES.md](AGENT_QUERY_RULES.md) | 12 条强制查询规则 |
| [DATABASE_RISKS.md](DATABASE_RISKS.md) | 风险与待修复事项 |

## Database Architecture Summary（1000 字以内）

这是面向多行业的 AI 项目管理系统，以 PostgreSQL 保存项目、任务、人员、计划、进度和风险事实。核心关系是 Project→Task，人员通过主负责人和多对多参与关系关联项目及任务。任务既有文本工作流，也有树形任务组、里程碑、工作日历、依赖边及互斥路线。当前计划位于任务等业务表，历史版本保存在 plan_versions；草案和变更方案通过校验、确认和执行流程进入当前计划。

进度原文与异步 AI 分析分开；问题、确定性风险事件、建议版本和行动项形成跟进闭环。日报和 AI 输出提供参考，不替代业务事实。通知使用事务型待投递事件；发送成功不等于用户已读。助手运行另有会话、消息版本、请求、命令步骤、批量幂等回执、调用审计及后台作业记录。

数据库集中于 public，无原生枚举、视图或分区，也没有租户键及 RLS。权限依赖当前用户角色、项目成员/负责人及任务参与关系。语义层应把自然语言映射到业务对象和受控工具，再由业务服务执行权限、计划校验、并发控制和数据库访问。本次仅采集目录元数据，不修改数据库、不读取业务内容；无法证明的记录级完整性明确为 UNKNOWN。

## 实际数据库规模

| 项目 | 结果 |
| --- | --- |
| PostgreSQL 版本 | 16.15 |
| database name | project_agent |
| 事务只读 | on |
| business_schema_count | 1 |
| table_count | 35 |
| business_table_count | 34 |
| view_count | 0 |
| materialized_view_count | 0 |
| partitioned_table_count | 0 |
| partition_count | 0 |
| enum_count | 0 |
| foreign_key_count | 84 |
| index_count | 129 |
| sequence_count | 28 |
| column_count | 423 |
| code_state_dictionary_count | 41 |
| schema | ["public"] |
| extensions | [{"name": "plpgsql", "version": "1.0"}] |
| 独立 custom types | [] |
| RLS policies | [] |

统计口径：业务 schema 排除 pg_catalog、information_schema、pg_toast 等系统 schema；35 张表包含 1 张 alembic_version，34 张属于应用。129 个索引包含 PK/UNIQUE 自动索引，不能再与唯一约束数相加。系统表行复合类型与自动数组类型不算独立 custom type。reltuples 为估计，不是精确数据量；未提供总记录数。

## Schema、对象与序列

| schema | 对象 | 类别 |
| --- | --- | --- |
| public | action_items | table |
| public | action_items_id_seq | sequence |
| public | advice_records | table |
| public | advice_records_id_seq | sequence |
| public | agent_batch_items | table |
| public | agent_batch_items_id_seq | sequence |
| public | agent_batch_operations | table |
| public | agent_batch_operations_id_seq | sequence |
| public | agent_command_items | table |
| public | agent_command_items_id_seq | sequence |
| public | agent_command_plans | table |
| public | agent_command_plans_id_seq | sequence |
| public | agent_conversations | table |
| public | agent_conversations_id_seq | sequence |
| public | agent_memories | table |
| public | agent_memories_id_seq | sequence |
| public | agent_messages | table |
| public | agent_messages_id_seq | sequence |
| public | agent_operations | table |
| public | agent_operations_id_seq | sequence |
| public | agent_requests | table |
| public | agent_requests_id_seq | sequence |
| public | agent_tool_calls | table |
| public | agent_tool_calls_id_seq | sequence |
| public | ai_runs | table |
| public | ai_runs_id_seq | sequence |
| public | alembic_version | table |
| public | audit_logs | table |
| public | audit_logs_id_seq | sequence |
| public | branch_groups | table |
| public | branch_groups_id_seq | sequence |
| public | branch_options | table |
| public | branch_options_id_seq | sequence |
| public | change_proposals | table |
| public | daily_project_summaries | table |
| public | daily_project_summaries_id_seq | sequence |
| public | issues | table |
| public | issues_id_seq | sequence |
| public | milestones | table |
| public | milestones_id_seq | sequence |
| public | notification_events | table |
| public | plan_drafts | table |
| public | plan_notification_events_id_seq | sequence |
| public | plan_versions | table |
| public | plan_versions_id_seq | sequence |
| public | progress_updates | table |
| public | progress_updates_id_seq | sequence |
| public | project_members | table |
| public | project_owners | table |
| public | projects | table |
| public | projects_id_seq | sequence |
| public | risk_events | table |
| public | risk_events_id_seq | sequence |
| public | task_groups | table |
| public | task_groups_id_seq | sequence |
| public | task_links | table |
| public | task_links_id_seq | sequence |
| public | task_participants | table |
| public | tasks | table |
| public | tasks_id_seq | sequence |
| public | users | table |
| public | users_id_seq | sequence |
| public | work_calendars | table |

本次没有视图、物化视图、分区表、分区子表、独立用户类型或原生 enum。序列与 SERIAL 默认表达式对应关系见字典，不执行 nextval/setval。

## 核心业务模块

| 模块 | 表 |
| --- | --- |
| agent_runtime | ["agent_batch_items", "agent_batch_operations", "agent_command_items", "agent_command_plans", "agent_conversations", "agent_memories", "agent_messages", "agent_operations", "agent_requests", "agent_tool_calls", "ai_runs"] |
| audit | ["audit_logs"] |
| execution | ["daily_project_summaries", "progress_updates", "tasks"] |
| identity | ["project_members", "project_owners", "task_participants", "users"] |
| maintenance | ["alembic_version"] |
| notification | ["notification_events"] |
| planning | ["branch_groups", "branch_options", "change_proposals", "milestones", "plan_drafts", "plan_versions", "task_groups", "task_links", "work_calendars"] |
| project_management | ["projects"] |
| risk | ["action_items", "advice_records", "issues", "risk_events"] |

## Core Entities（30 项）

| 实体 | 主表 | 说明 |
| --- | --- | --- |
| ActionItem | action_items | 有负责人和期限的跟进事项，可关联问题、任务及建议 |
| AdviceRecord | advice_records | 一个问题的一版建议及证据、采纳决定和效果评价 |
| AgentBatchOperation | agent_batch_operations | 某用户一次带幂等标识的批量工具调用 |
| AgentCommandPlan | agent_command_plans | 一个助手请求对应的一份结构化命令计划 |
| AgentConversation | agent_conversations | 某用户的一段对话及可选绑定项目 |
| AgentMemory | agent_memories | 某用户的一条偏好、指令或固定上下文；不是动态业务事实 |
| AgentMessage | agent_messages | 一个会话中的一条消息或一个回答版本 |
| AgentRequest | agent_requests | 用户在会话中的一次带幂等标识的发送请求 |
| AIRun | ai_runs | 某业务资源的一次后台 AI 作业 |
| AuditLog | audit_logs | 一次业务变更的操作人与前后快照 |
| BranchGroup | branch_groups | 一个项目中一组互斥执行路线的决策点 |
| BranchOption | branch_options | 某路线决策组中的一个候选选项 |
| ChangeProposal | change_proposals | 一个经预览、校验、确认及执行的计划变更方案 |
| DailyProjectSummary | daily_project_summaries | 一个项目在一个业务日期的 AI 汇总 |
| Issue | issues | 一个项目级或任务级问题 |
| Milestone | milestones | 一个项目中的验收或交付节点 |
| NotificationEvent | notification_events | 某业务事件向某收件人在某渠道的一次通知意图 |
| PlanDraft | plan_drafts | 尚未发布的结构化项目计划，发布后关联项目 |
| PlanVersion | plan_versions | 一个项目的一个不可直接修改的历史计划版本 |
| ProgressUpdate | progress_updates | 某用户向某任务提交的一次原始汇报及异步分析结果 |
| ProjectMember | project_members | 一个项目与一个用户的成员关系及有效性 |
| ProjectOwner | project_owners | 一个项目与一个共同负责人的关联 |
| Project | projects | 一个项目的当前目标、计划日期及主负责人 |
| RiskEvent | risk_events | 一个项目中由 dedupe_key 标识的可重复开启风险事实 |
| TaskGroup | task_groups | 一个项目中的一个可嵌套任务分组节点 |
| TaskDependency | task_links | 同一项目中两个任务之间的一条有方向依赖 |
| TaskParticipant | task_participants | 一个任务与一个用户的单一参与角色；OWNER 为共同负责人 |
| Task | tasks | 一个执行任务的当前计划、实际执行信息及状态 |
| User | users | 一个本地用户账号及角色；外部身份仅映射 |
| WorkCalendar | work_calendars | 一个项目的一份版本化工作日历，以 project_id 为主键 |

## Core Relationships

- Project 1:N Task；Project N:N User 分别通过 project_owners（负责人）及 project_members（成员）。
- Task N:N User 通过 task_participants，并保留主 owner_id；OWNER 与 COLLABORATOR 不同。
- Task 1:N ProgressUpdate；Project/Task 1:N Issue；Issue 1:N AdviceRecord；AdviceRecord 1:N ActionItem。
- Project 1:N RiskEvent；RiskEvent 或 ChangeProposal 1:N NotificationEvent，每条通知只有一个来源。
- Project 1:0..1 WorkCalendar；Task.calendar_id 指向日历 project_id。
- TaskGroup 自关联层级；TaskLink 是 Task 到 Task 的有向依赖边。
- Project→BranchGroup→BranchOption→Task 表达互斥路线；旧 branch_root_id 仍保留。
- Project 1:N PlanVersion；ChangeProposal 使用项目内 version 引用基准，使用 applied_version_id 引用执行结果。
- AgentConversation 1:N AgentMessage / AgentRequest；AgentRequest 1:0..1 AgentCommandPlan→AgentCommandItem。
- AgentBatchOperation 与 AgentBatchItem 通过 operation_id 逻辑关联，无 FK；摘要消息游标同样没有 FK。

## Recommended Agent Architecture

`Agent → Tool Calling → Tool Executor → Query / Write Service → Business Service → ORM → PostgreSQL`。

采用这条现有架构的强化路线：对象权限、多人负责人、计划可行性、版本和幂等已在业务层；LLM 直连 SQL 无法安全复现这些规则。语义层是字段与关系允许列表，业务服务仍是事实与权限执行边界。MCP 可包装已有结构化工具，RAG 只索引静态语义及经授权摘录。不要新增万能 SQL Tool。

## Top Risks（17 项）

| ID | 级别 | 优先事项 |
| --- | --- | --- |
| R01 | HIGH | 读工具实际写库 |
| R02 | HIGH | 任务编号语义漂移 |
| R03 | HIGH | 多人负责人查询可能漏报 |
| R04 | HIGH | 进度概览 completed 统计恒零 |
| R05 | HIGH | 没有数据库级行隔离 |
| R06 | MEDIUM | 两处 ORM 与实际 NULL 约束漂移 |
| R07 | MEDIUM | 外键缺少可用前导索引 |
| R08 | HIGH | 独立外键不能保证同项目/同会话 |
| R09 | MEDIUM | 缺失逻辑外键及多态引用 |
| R10 | MEDIUM | 应用枚举多数无数据库 CHECK |
| R11 | MEDIUM | JSON/自由文本可能携带敏感数据 |
| R12 | MEDIUM | 应用内查询计算限制规模与正确性 |
| R13 | MEDIUM | 生命周期过滤不统一 |
| R14 | MEDIUM | 分支单选、负责人镜像及层级无环依赖服务 |
| R15 | MEDIUM | 类型与时间语义易误判 |
| R17 | HIGH | 通知汇总未复用收件人范围 |
| R16 | MEDIUM | 注释与状态契约不足 |

具体证据、影响范围和索引清单见 [DATABASE_RISKS.md](DATABASE_RISKS.md)。本次仅报告，未实施修复。

## Recommended Tools（第一阶段 28 项）

`get_current_user`, `batch_find_users`, `list_projects`, `get_project`, `get_task`, `search_tasks`, `query_entities`, `get_task_progress`, `get_project_progress_overview`, `get_dependency_graph`, `list_open_issues`, `list_action_items`, `list_risk_events`, `get_issue_evidence`, `get_issue_advice`, `get_notification_status`, `get_plan_version`, `create_task`, `batch_create_tasks`, `assign_task`, `change_task_status`, `submit_progress`, `create_issue`, `create_action_item`, `preview_change`, `propose_change`, `draft_project_plan`, `review_project_plan_draft`。

读/写/管理分类、参数及所需权限见 [AGENT_TOOLS.md](AGENT_TOOLS.md)。所有建议写工具 requires_confirmation=true，计划发布/执行保留人工确认边界。

## 证据边界与结构漂移

| 表 | 字段 | 属性 | 实际 DB | ORM |
| --- | --- | --- | --- | --- |
| advice_records | evidence | nullable | 是 | 否 |
| risk_events | evidence | nullable | 是 | 否 |

目录采集通过现有后端连接，连接选项强制 default_transaction_read_only=on、statement_timeout=15000、lock_timeout=2000；目录结果确认 transaction_read_only=on。未调用业务 API、未运行迁移、未执行有副作用的工具，也未运行 EXPLAIN ANALYZE。已应用 Alembic revision、实际 DISTINCT、孤儿/重复记录及真实行数为 UNKNOWN。

业务语义对照当前工作区（包含用户未提交改动），不是已部署代码的一致性认证。当前数据库有 84 条实际 FK；本报告同时登记 7 条推断关系，可信度与附加条件逐条记录。HIGH 推断仍不等于数据库约束。

## 产物校验

JSON 与 YAML 已通过解析及交叉一致性校验；35 张表、423 个字段与只读目录逐项对应；84 条 FK、7 条推断关系的源/目标列、全部别名及 JOIN 路径通过引用检查。HIDDEN 字段查询建议全部关闭，所有建议 WRITE 工具要求确认，12 条查询规则在两种机器格式中保持一致。Markdown 代码块及 ER 的 84 条物理关系已检查；未运行浏览器 Mermaid 渲染。
