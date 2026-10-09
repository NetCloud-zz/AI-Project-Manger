# DATABASE_RISKS

> Copyright 2024–2026 Jack Zhang. Apache License 2.0；保留 NOTICE 署名。
> 采集日期：2026-09-15；结构来源：实际 PostgreSQL 只读目录；业务语义来源：当前工作区模型、迁移与服务。
> 未读取业务记录。PUBLIC 仅表示字段可经授权业务 DTO 使用，不表示互联网公开或授权直连数据库。

本文件只提出建议，不修改结构或数据。HIGH 表示需要优先评估，不表示已经发生数据泄露或线上事故。代码缺陷由静态路径确认，未执行有副作用工具。没有采样业务记录，孤儿、重复、真实大表和循环实例均为 UNKNOWN。

| ID | 级别 | 问题 | 已观察证据 | 建议 |
| --- | --- | --- | --- | --- |
| R01 | HIGH | 读工具实际写库 | review_project_plan_draft、validate_project_plan 未列入 WRITE_TOOLS，但调用 review 更新 status/review/digest，flush/audit 后 commit。 | 从只读工具集合移除，重新分类为 WRITE；或拆出 inspect 的纯只读能力；执行器按实际副作用拒绝只读会话。 |
| R02 | HIGH | 任务编号语义漂移 | 实际 tasks.task_code 为可空唯一业务编号，Query DSL TASK_QUERY_FIELDS 却把 task_code 映射到 id。 | 修正映射并明确历史空编号策略；在修复前拒绝该 DSL 别名，使用经验证的业务编号解析服务。 |
| R03 | HIGH | 多人负责人查询可能漏报 | 权限代码支持主负责人及 task_participants.OWNER，但查询白名单 owner_name/owner_id 仅访问 task.owner；多个查询路径也仅比较主负责人。 | 主负责人、共同负责人、协作人分别定义；“负责的任务”使用主负责人与 OWNER 集合并集并去重。 |
| R04 | HIGH | 进度概览 completed 统计恒零 | get_project_progress_overview 先以 is_execution_active 只保留 TODO/IN_PROGRESS，随后统计 COMPLETED，因此 completed 永远为零。 | 明确统计分母；分开全部可见任务、当前执行任务及已完成任务，不输出虚假的完成数。 |
| R05 | HIGH | 没有数据库级行隔离 | 所有观察表 rls_enabled=false，pg_policies 为空；无 tenant_id/organization_id/workspace_id。当前安全边界是应用对象权限。 | Query Service 强制注入 actor 和对象范围；多租户需求出现时再设计租户键和 RLS；不能把 department 当隔离键。 |
| R06 | MEDIUM | 两处 ORM 与实际 NULL 约束漂移 | advice_records.evidence、risk_events.evidence：实际可为 NULL，ORM 声明不可为空。 | 先只读核验存量，再制定一致的 NULL/空数组语义与迁移；当前 DTO 必须兼容 NULL。 |
| R07 | MEDIUM | 外键缺少可用前导索引 | 31 条外键没有以全部 FK 列开头的有效非部分索引；复合 PK 的第二列不能单独算作前导索引。 | 结合实际流量评估用户反查、任务分组和引用删除检查索引；仅建议，不创建索引。 |
| R08 | HIGH | 独立外键不能保证同项目/同会话 | task_links 的 source/target/project、tasks 的 calendar/milestone/group/option、消息自引用等独立 FK 并不保证对象处于相同范围。 | 保留并全面复用服务的一致性校验；后续评估复合 FK；本次未抽样，不能断言已有跨范围坏数据。 |
| R09 | MEDIUM | 缺失逻辑外键及多态引用 | batch_items.operation_id、摘要游标、legacy_root_id、基准版本缺显式 FK；resource_id/evidence 是多态引用。 | 为稳定关系评估约束；多态引用通过类型注册解析器验证，禁止无判别器 CAST JOIN。 |
| R10 | MEDIUM | 应用枚举多数无数据库 CHECK | 原生 PostgreSQL enum 为 0，模型 native_enum=False；tasks.status 等仅代码枚举，无实际 CHECK。直接绕过服务可写入未知状态。 | 按业务状态字典校验所有入口；审查迁移后再补 CHECK；不要将未观察到的 distinct 值当作已知合法值。 |
| R11 | MEDIUM | JSON/自由文本可能携带敏感数据 | 会话、执行参数、审计前后值、计划快照、通知和证据 JSON 可包含用户输入、私人信息或内部标识。 | 采用嵌套 DTO 允许列表、对象级证据授权、长度限制和保留期；拒绝通用 JSON 投影或整表 RAG。 |
| R12 | MEDIUM | 应用内查询计算限制规模与正确性 | _visible_tasks 遍历可见项目/任务；apply_query 在 Python 中筛选排序聚合。limit 只限制结果页，不能限制扫描工作量；多排序方向沿用第一项 direction。 | 受控 ORM 查询下推范围、过滤与聚合；限制复杂度和执行时间，补充多方向排序契约。 |
| R13 | MEDIUM | 生命周期过滤不统一 | 任务路线停用、用户停用、会话归档、记忆停用含义不同；query_entities 与 search_tasks 默认当前执行筛选也不同。 | 显式提供 current/history 范围；没有统一 soft delete 时禁止自动加删除条件。 |
| R14 | MEDIUM | 分支单选、负责人镜像及层级无环依赖服务 | 无部分唯一索引保证每组仅一个 is_selected=true；project.owner_id 与 project_owners、task.owner_id 与 OWNER 参与者的同步不是单靠 FK 保证；parent_id 自 FK 不防环。 | 评估部分唯一约束、并发锁和完整性检查；需要业务数据核验，不能声称当前已有重复/循环。 |
| R15 | MEDIUM | 类型与时间语义易误判 | plan_drafts/change_proposals 主键为 varchar(36)，不是 PostgreSQL UUID；resource_id 为字符串多态键；created_at 和 updated_at 不是实际执行日期。 | 按物理类型绑定参数；明确计划/实际/事件时间；updated_at 的 ORM onupdate 不保证其他写入口自动更新。 |
| R17 | HIGH | 通知汇总未复用收件人范围 | get_notification_status 按 proposal_id 查询时 events 已按权限过滤，但 summary 随后调用不含 actor 参数的 status_summary，统计整个方案的通知。普通收件人可能获知其他人的汇总投递状态。 | summary 应对同一已授权事件集合统计；跨收件人的汇总仅在明确管理权限下返回。 |
| R16 | MEDIUM | 注释与状态契约不足 | 数据库 COMMENT 缺失，内部命令状态字符串未用 CHECK/Enum 定义完整契约；应用默认值通常不是 DB default。 | 以版本化语义层补充维护；状态机器只登记代码确认边；未来另行授权迁移补 COMMENT。 |

## R01 · 读工具实际写库

级别：HIGH。review_project_plan_draft、validate_project_plan 未列入 WRITE_TOOLS，但调用 review 更新 status/review/digest，flush/audit 后 commit。

证据：backend/app/agents/management_tools.py；backend/app/services/management_planning.py:329；backend/app/services/plan_draft.py:154。

建议：从只读工具集合移除，重新分类为 WRITE；或拆出 inspect 的纯只读能力；执行器按实际副作用拒绝只读会话。

## R02 · 任务编号语义漂移

级别：HIGH。实际 tasks.task_code 为可空唯一业务编号，Query DSL TASK_QUERY_FIELDS 却把 task_code 映射到 id。

证据：backend/app/agents/query/fields.py:11；backend/app/models/task.py:75。

建议：修正映射并明确历史空编号策略；在修复前拒绝该 DSL 别名，使用经验证的业务编号解析服务。

## R03 · 多人负责人查询可能漏报

级别：HIGH。权限代码支持主负责人及 task_participants.OWNER，但查询白名单 owner_name/owner_id 仅访问 task.owner；多个查询路径也仅比较主负责人。

证据：backend/app/core/permissions.py:41；backend/app/services/management_query.py:947；backend/app/agents/query/fields.py。

建议：主负责人、共同负责人、协作人分别定义；“负责的任务”使用主负责人与 OWNER 集合并集并去重。

## R04 · 进度概览 completed 统计恒零

级别：HIGH。get_project_progress_overview 先以 is_execution_active 只保留 TODO/IN_PROGRESS，随后统计 COMPLETED，因此 completed 永远为零。

证据：backend/app/services/management_query.py:234；backend/app/services/management_query.py:254；backend/app/models/task.py。

建议：明确统计分母；分开全部可见任务、当前执行任务及已完成任务，不输出虚假的完成数。

## R05 · 没有数据库级行隔离

级别：HIGH。所有观察表 rls_enabled=false，pg_policies 为空；无 tenant_id/organization_id/workspace_id。当前安全边界是应用对象权限。

证据：pg_class.relrowsecurity；pg_policies；backend/app/core/permissions.py。

建议：Query Service 强制注入 actor 和对象范围；多租户需求出现时再设计租户键和 RLS；不能把 department 当隔离键。

## R06 · 两处 ORM 与实际 NULL 约束漂移

级别：MEDIUM。advice_records.evidence、risk_events.evidence：实际可为 NULL，ORM 声明不可为空。

证据：实际 pg_attribute 与 backend/app/models/advice_record.py / risk_event.py。

建议：先只读核验存量，再制定一致的 NULL/空数组语义与迁移；当前 DTO 必须兼容 NULL。

## R07 · 外键缺少可用前导索引

级别：MEDIUM。31 条外键没有以全部 FK 列开头的有效非部分索引；复合 PK 的第二列不能单独算作前导索引。

证据：pg_index；详见本文件完整清单。

建议：结合实际流量评估用户反查、任务分组和引用删除检查索引；仅建议，不创建索引。

## R08 · 独立外键不能保证同项目/同会话

级别：HIGH。task_links 的 source/target/project、tasks 的 calendar/milestone/group/option、消息自引用等独立 FK 并不保证对象处于相同范围。

证据：实际 FK 定义；backend/app/services/task.py；backend/app/services/planning.py。

建议：保留并全面复用服务的一致性校验；后续评估复合 FK；本次未抽样，不能断言已有跨范围坏数据。

## R09 · 缺失逻辑外键及多态引用

级别：MEDIUM。batch_items.operation_id、摘要游标、legacy_root_id、基准版本缺显式 FK；resource_id/evidence 是多态引用。

证据：DATABASE_RELATIONSHIPS.md 推断证据。

建议：为稳定关系评估约束；多态引用通过类型注册解析器验证，禁止无判别器 CAST JOIN。

## R10 · 应用枚举多数无数据库 CHECK

级别：MEDIUM。原生 PostgreSQL enum 为 0，模型 native_enum=False；tasks.status 等仅代码枚举，无实际 CHECK。直接绕过服务可写入未知状态。

证据：模型 Enum、实际 pg_constraint。

建议：按业务状态字典校验所有入口；审查迁移后再补 CHECK；不要将未观察到的 distinct 值当作已知合法值。

## R11 · JSON/自由文本可能携带敏感数据

级别：MEDIUM。会话、执行参数、审计前后值、计划快照、通知和证据 JSON 可包含用户输入、私人信息或内部标识。

证据：完整字段字典；backend/app/models/agent_tool_call.py；audit_log.py。

建议：采用嵌套 DTO 允许列表、对象级证据授权、长度限制和保留期；拒绝通用 JSON 投影或整表 RAG。

## R12 · 应用内查询计算限制规模与正确性

级别：MEDIUM。_visible_tasks 遍历可见项目/任务；apply_query 在 Python 中筛选排序聚合。limit 只限制结果页，不能限制扫描工作量；多排序方向沿用第一项 direction。

证据：backend/app/services/management_query.py:707；backend/app/agents/query/builder.py。

建议：受控 ORM 查询下推范围、过滤与聚合；限制复杂度和执行时间，补充多方向排序契约。

## R13 · 生命周期过滤不统一

级别：MEDIUM。任务路线停用、用户停用、会话归档、记忆停用含义不同；query_entities 与 search_tasks 默认当前执行筛选也不同。

证据：backend/app/models/task.py；backend/app/services/management_query.py；memory.py。

建议：显式提供 current/history 范围；没有统一 soft delete 时禁止自动加删除条件。

## R14 · 分支单选、负责人镜像及层级无环依赖服务

级别：MEDIUM。无部分唯一索引保证每组仅一个 is_selected=true；project.owner_id 与 project_owners、task.owner_id 与 OWNER 参与者的同步不是单靠 FK 保证；parent_id 自 FK 不防环。

证据：实际唯一索引；backend/app/models/project.py；planning.py；task.py。

建议：评估部分唯一约束、并发锁和完整性检查；需要业务数据核验，不能声称当前已有重复/循环。

## R15 · 类型与时间语义易误判

级别：MEDIUM。plan_drafts/change_proposals 主键为 varchar(36)，不是 PostgreSQL UUID；resource_id 为字符串多态键；created_at 和 updated_at 不是实际执行日期。

证据：实际列类型；backend/app/models/base.py。

建议：按物理类型绑定参数；明确计划/实际/事件时间；updated_at 的 ORM onupdate 不保证其他写入口自动更新。

## R17 · 通知汇总未复用收件人范围

级别：HIGH。get_notification_status 按 proposal_id 查询时 events 已按权限过滤，但 summary 随后调用不含 actor 参数的 status_summary，统计整个方案的通知。普通收件人可能获知其他人的汇总投递状态。

证据：backend/app/services/management_planning.py:647；backend/app/services/notification_delivery.py:316。

建议：summary 应对同一已授权事件集合统计；跨收件人的汇总仅在明确管理权限下返回。

## R16 · 注释与状态契约不足

级别：MEDIUM。数据库 COMMENT 缺失，内部命令状态字符串未用 CHECK/Enum 定义完整契约；应用默认值通常不是 DB default。

证据：pg_description/pg_constraint；backend/app/services/agent_commands.py。

建议：以版本化语义层补充维护；状态机器只登记代码确认边；未来另行授权迁移补 COMMENT。

## 无前导索引的外键（完整清单）

仅检查有效、非部分且前导列匹配的索引；这是保守结构判断，不等于已发生慢查询。不会自动创建索引。

| 表 | FK 列 | 目标 | 约束 |
| --- | --- | --- | --- |
| advice_records | ["decided_by"] | users | advice_records_decided_by_fkey |
| advice_records | ["evaluated_by"] | users | advice_records_evaluated_by_fkey |
| advice_records | ["generated_by"] | users | advice_records_generated_by_fkey |
| advice_records | ["proposal_id"] | change_proposals | advice_records_proposal_id_fkey |
| agent_batch_operations | ["user_id"] | users | agent_batch_operations_user_id_fkey |
| agent_messages | ["regenerated_from_id"] | agent_messages | fk_agent_messages_regenerated_from |
| agent_messages | ["selected_answer_id"] | agent_messages | fk_agent_messages_selected_answer |
| agent_requests | ["assistant_message_id"] | agent_messages | agent_requests_assistant_message_id_fkey |
| agent_requests | ["user_message_id"] | agent_messages | agent_requests_user_message_id_fkey |
| agent_tool_calls | ["user_id"] | users | agent_tool_calls_user_id_fkey |
| ai_runs | ["created_by"] | users | ai_runs_created_by_fkey |
| branch_groups | ["entry_task_id"] | tasks | fk_branch_entry |
| branch_groups | ["exit_task_id"] | tasks | fk_branch_exit |
| change_proposals | ["applied_by"] | users | change_proposals_applied_by_fkey |
| change_proposals | ["applied_version_id"] | plan_versions | change_proposals_applied_version_id_fkey |
| change_proposals | ["confirmed_by"] | users | change_proposals_confirmed_by_fkey |
| change_proposals | ["created_by"] | users | change_proposals_created_by_fkey |
| milestones | ["owner_id"] | users | milestones_owner_id_fkey |
| plan_drafts | ["project_id"] | projects | plan_drafts_project_id_fkey |
| plan_drafts | ["published_by"] | users | plan_drafts_published_by_fkey |
| plan_versions | ["created_by"] | users | plan_versions_created_by_fkey |
| project_members | ["user_id"] | users | project_members_user_id_fkey |
| risk_events | ["issue_id"] | issues | risk_events_issue_id_fkey |
| risk_events | ["owner_id"] | users | risk_events_owner_id_fkey |
| risk_events | ["resolved_by"] | users | risk_events_resolved_by_fkey |
| task_groups | ["parent_id"] | task_groups | task_groups_parent_id_fkey |
| task_participants | ["user_id"] | users | task_participants_user_id_fkey |
| tasks | ["branch_option_id"] | branch_options | fk_tasks_branch_option_id |
| tasks | ["calendar_id"] | work_calendars | fk_tasks_calendar_id |
| tasks | ["milestone_id"] | milestones | fk_tasks_milestone_id |
| tasks | ["task_group_id"] | task_groups | fk_tasks_task_group_id |

## 高频筛选候选

| 字段 | 索引成员 | 前导索引 | 说明 |
| --- | --- | --- | --- |
| tasks.project_id | ["ix_tasks_project_id", "ix_tasks_work_stream"] | ["ix_tasks_project_id", "ix_tasks_work_stream"] | 项目任务列表 |
| tasks.owner_id | ["ix_tasks_owner_id"] | ["ix_tasks_owner_id"] | 主负责人；另需参与表用户反查 |
| tasks.status | [] | [] | 项目+状态候选复合索引，按负载验证 |
| tasks.due_date | [] | [] | 当前任务到期窗口，评估项目/日期或部分索引 |
| tasks.created_at | [] | [] | 创建时间查询 |
| progress_updates.created_at | [] | [] | 最近汇报，评估 task_id+created_at+id |
| project_members.user_id | ["project_members_pkey"] | [] | 用户反查成员关系，复合 PK 第二列 |
| task_participants.user_id | ["task_participants_pkey"] | [] | 多人负责人和协作任务反查 |
| notification_events.next_attempt_at | [] | [] | worker 队列扫描，结合 status 评估 |

## 异常检查覆盖与 UNKNOWN

| 检查 | 结论 |
| --- | --- |
| 缺少主键 | 本次观察的 35 张表均有主键 |
| 重复表/重复字段/冗余关联 | 未确认物理重复；project_owners 与 project_members、task.owner_id 与 task_participants 业务职责不同，不可直接删除 |
| VARCHAR 存 JSON/日期/数字 | 核心日期使用 DATE/timestamptz，JSON 使用 JSON/JSONB；未读取数据，字符串字段内容 UNKNOWN。varchar(36) ID / resource_id 为明确字符串设计 |
| 孤立表 | alembic_version 是有意独立维护表；无 FK 的逻辑引用已登记；记录级孤儿 UNKNOWN |
| 超大 TEXT/JSON | 存在无数据库长度上限的 TEXT/JSON；实际大小与增长量 UNKNOWN |
| 时间类型混用 | {'timestamp with time zone': 85}；DATE 与 timestamptz 混用是业务日期与事件时间分工 |
| magic number | 状态主要字符串；没有证据表明 status=0/1/2；运行时 DISTINCT 未查询 |
| 枚举 | 0 原生枚举，代码枚举和 CHECK 字典分别记录 |
| 索引方法 | {"btree": 129} |
| 部分/表达式/全文索引 | 完整定义见 database_schema.json；本次没有 GIN/GiST/BRIN/全文专用索引 |
| 结构漂移 | [{"table": "advice_records", "column": "evidence", "property": "nullable", "database": true, "orm": false, "evidence": "backend/app/models/advice_record.py:50"}, {"table": "risk_events", "column": "evidence", "property": "nullable", "database": true, "orm": false, "evidence": "backend/app/models/risk_event.py:57"}] |
| ORM CHECK 未在实际数据库出现 | [] |
| 恶意 SQL Tool | 对 backend/app/agents 和 mcp 检索 execute_sql/run_sql/query_database/raw_query/database_execute，未发现可调用万能 SQL 工具；技能文本中的禁止示例不算实现 |
| 只读语义例外 | R01 两个读分类工具存在实际写入路径，必须处理 |

