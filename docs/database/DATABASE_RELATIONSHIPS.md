# DATABASE_RELATIONSHIPS

> Copyright 2024–2026 Jack Zhang. Apache License 2.0；保留 NOTICE 署名。
> 采集日期：2026-09-15；结构来源：实际 PostgreSQL 只读目录；业务语义来源：当前工作区模型、迁移与服务。
> 未读取业务记录。PUBLIC 仅表示字段可经授权业务 DTO 使用，不表示互联网公开或授权直连数据库。

外键来源均为实际 pg_constraint。关系从引用端指向被引用端；N:1 的逆关系是 1:N。1:1 表示至多一条，不保证双方一定存在；nullable 见明细。推断来源统一标为 INFERRED，代码证据与数据库约束严格区分。

| Table A | Column A | Relation | Table B | Column B | Business Meaning | Source | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| action_items | ["created_by"] | N:1 | users | ["id"] | 行动项：创建人用户标识 | FOREIGN_KEY | HIGH |
| action_items | ["issue_id"] | N:1 | issues | ["id"] | 行动项：关联问题标识 | FOREIGN_KEY | HIGH |
| action_items | ["owner_id"] | N:1 | users | ["id"] | 行动项：业务主负责人用户标识（不是创建人） | FOREIGN_KEY | HIGH |
| action_items | ["project_id"] | N:1 | projects | ["id"] | 行动项：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| action_items | ["task_id"] | N:1 | tasks | ["id"] | 行动项：关联执行任务标识 | FOREIGN_KEY | HIGH |
| action_items | ["advice_id"] | N:1 | advice_records | ["id"] | 行动项：产生该行动的建议版本标识 | FOREIGN_KEY | HIGH |
| advice_records | ["decided_by"] | N:1 | users | ["id"] | 建议版本：建议采纳或拒绝的决定人 | FOREIGN_KEY | HIGH |
| advice_records | ["evaluated_by"] | N:1 | users | ["id"] | 建议版本：建议效果评价人 | FOREIGN_KEY | HIGH |
| advice_records | ["generated_by"] | N:1 | users | ["id"] | 建议版本：建议生成请求人用户标识 | FOREIGN_KEY | HIGH |
| advice_records | ["issue_id"] | N:1 | issues | ["id"] | 建议版本：关联问题标识 | FOREIGN_KEY | HIGH |
| advice_records | ["project_id"] | N:1 | projects | ["id"] | 建议版本：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| advice_records | ["proposal_id"] | N:1 | change_proposals | ["id"] | 建议版本：关联计划变更方案标识（字符串主键） | FOREIGN_KEY | HIGH |
| agent_batch_operations | ["user_id"] | N:1 | users | ["id"] | 批量操作：关联用户标识，具体角色见表用途 | FOREIGN_KEY | HIGH |
| agent_command_items | ["plan_id"] | N:1 | agent_command_plans | ["id"] | 指令执行步骤：所属指令执行计划 | FOREIGN_KEY | HIGH |
| agent_command_plans | ["request_id"] | 1:1 | agent_requests | ["id"] | 指令执行计划：助手请求标识 | FOREIGN_KEY | HIGH |
| agent_conversations | ["project_id"] | N:1 | projects | ["id"] | 助手会话：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| agent_conversations | ["user_id"] | N:1 | users | ["id"] | 助手会话：会话所有者，权限隔离键 | FOREIGN_KEY | HIGH |
| agent_memories | ["project_id"] | N:1 | projects | ["id"] | 用户记忆：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| agent_memories | ["user_id"] | N:1 | users | ["id"] | 用户记忆：记忆所有者，权限隔离键 | FOREIGN_KEY | HIGH |
| agent_messages | ["conversation_id"] | N:1 | agent_conversations | ["id"] | 助手消息：所属助手会话 | FOREIGN_KEY | HIGH |
| agent_messages | ["parent_user_message_id"] | N:1 | agent_messages | ["id"] | 助手消息：回答所属的用户消息，不是组织树 | FOREIGN_KEY | HIGH |
| agent_messages | ["regenerated_from_id"] | N:1 | agent_messages | ["id"] | 助手消息：该回答从哪个旧回答重新生成 | FOREIGN_KEY | HIGH |
| agent_messages | ["selected_answer_id"] | N:1 | agent_messages | ["id"] | 助手消息：用户消息当前选择的回答版本 | FOREIGN_KEY | HIGH |
| agent_operations | ["request_id"] | N:1 | agent_requests | ["id"] | 工具写入回执：助手请求标识 | FOREIGN_KEY | HIGH |
| agent_requests | ["assistant_message_id"] | N:1 | agent_messages | ["id"] | 助手请求：请求响应消息标识 | FOREIGN_KEY | HIGH |
| agent_requests | ["conversation_id"] | N:1 | agent_conversations | ["id"] | 助手请求：所属助手会话 | FOREIGN_KEY | HIGH |
| agent_requests | ["user_id"] | N:1 | users | ["id"] | 助手请求：关联用户标识，具体角色见表用途 | FOREIGN_KEY | HIGH |
| agent_requests | ["user_message_id"] | N:1 | agent_messages | ["id"] | 助手请求：请求输入消息标识 | FOREIGN_KEY | HIGH |
| agent_tool_calls | ["conversation_id"] | N:1 | agent_conversations | ["id"] | 工具调用审计：所属助手会话 | FOREIGN_KEY | HIGH |
| agent_tool_calls | ["request_id"] | N:1 | agent_requests | ["id"] | 工具调用审计：助手请求标识 | FOREIGN_KEY | HIGH |
| agent_tool_calls | ["user_id"] | N:1 | users | ["id"] | 工具调用审计：关联用户标识，具体角色见表用途 | FOREIGN_KEY | HIGH |
| ai_runs | ["created_by"] | N:1 | users | ["id"] | 后台 AI 运行：创建人用户标识 | FOREIGN_KEY | HIGH |
| audit_logs | ["user_id"] | N:1 | users | ["id"] | 业务审计日志：业务操作人，可因删除用户而为空 | FOREIGN_KEY | HIGH |
| branch_groups | ["project_id"] | N:1 | projects | ["id"] | 路线决策组：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| branch_groups | ["entry_task_id"] | N:1 | tasks | ["id"] | 路线决策组：路线组入口任务 | FOREIGN_KEY | HIGH |
| branch_groups | ["exit_task_id"] | N:1 | tasks | ["id"] | 路线决策组：路线组出口任务 | FOREIGN_KEY | HIGH |
| branch_options | ["group_id"] | N:1 | branch_groups | ["id"] | 路线选项：路线选项所属决策组 | FOREIGN_KEY | HIGH |
| change_proposals | ["applied_by"] | N:1 | users | ["id"] | 计划变更方案：变更执行人 | FOREIGN_KEY | HIGH |
| change_proposals | ["applied_version_id"] | N:1 | plan_versions | ["id"] | 计划变更方案：执行变更生成的计划快照主键 | FOREIGN_KEY | HIGH |
| change_proposals | ["confirmed_by"] | N:1 | users | ["id"] | 计划变更方案：变更确认人，需与确认上下文绑定 | FOREIGN_KEY | HIGH |
| change_proposals | ["created_by"] | N:1 | users | ["id"] | 计划变更方案：创建人用户标识 | FOREIGN_KEY | HIGH |
| change_proposals | ["project_id"] | N:1 | projects | ["id"] | 计划变更方案：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| daily_project_summaries | ["project_id"] | N:1 | projects | ["id"] | 项目日报：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| issues | ["project_id"] | N:1 | projects | ["id"] | 问题：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| issues | ["reported_by"] | N:1 | users | ["id"] | 问题：问题报告人用户标识 | FOREIGN_KEY | HIGH |
| issues | ["task_id"] | N:1 | tasks | ["id"] | 问题：关联执行任务标识 | FOREIGN_KEY | HIGH |
| milestones | ["owner_id"] | N:1 | users | ["id"] | 里程碑：业务主负责人用户标识（不是创建人） | FOREIGN_KEY | HIGH |
| milestones | ["project_id"] | N:1 | projects | ["id"] | 里程碑：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| notification_events | ["risk_event_id"] | N:1 | risk_events | ["id"] | 通知事件：关联风险事件标识，通知来源之一 | FOREIGN_KEY | HIGH |
| notification_events | ["project_id"] | N:1 | projects | ["id"] | 通知事件：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| notification_events | ["proposal_id"] | N:1 | change_proposals | ["id"] | 通知事件：关联计划变更方案标识（字符串主键） | FOREIGN_KEY | HIGH |
| notification_events | ["recipient_id"] | N:1 | users | ["id"] | 通知事件：通知收件人用户标识 | FOREIGN_KEY | HIGH |
| plan_drafts | ["created_by"] | N:1 | users | ["id"] | 项目计划草案：创建人用户标识 | FOREIGN_KEY | HIGH |
| plan_drafts | ["project_id"] | N:1 | projects | ["id"] | 项目计划草案：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| plan_drafts | ["published_by"] | N:1 | users | ["id"] | 项目计划草案：计划发布人 | FOREIGN_KEY | HIGH |
| plan_versions | ["created_by"] | N:1 | users | ["id"] | 计划快照：创建人用户标识 | FOREIGN_KEY | HIGH |
| plan_versions | ["project_id"] | N:1 | projects | ["id"] | 计划快照：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| progress_updates | ["task_id"] | N:1 | tasks | ["id"] | 进度汇报：关联执行任务标识 | FOREIGN_KEY | HIGH |
| progress_updates | ["user_id"] | N:1 | users | ["id"] | 进度汇报：进度汇报提交人，可能为代报人，不等于任务负责人 | FOREIGN_KEY | HIGH |
| project_members | ["project_id"] | N:1 | projects | ["id"] | 项目成员：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| project_members | ["user_id"] | N:1 | users | ["id"] | 项目成员：关联用户标识，具体角色见表用途 | FOREIGN_KEY | HIGH |
| project_owners | ["project_id"] | N:1 | projects | ["id"] | 项目负责人关系：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| project_owners | ["user_id"] | N:1 | users | ["id"] | 项目负责人关系：关联用户标识，具体角色见表用途 | FOREIGN_KEY | HIGH |
| projects | ["owner_id"] | N:1 | users | ["id"] | 项目：业务主负责人用户标识（不是创建人） | FOREIGN_KEY | HIGH |
| risk_events | ["issue_id"] | N:1 | issues | ["id"] | 风险事件：关联问题标识 | FOREIGN_KEY | HIGH |
| risk_events | ["owner_id"] | N:1 | users | ["id"] | 风险事件：业务主负责人用户标识（不是创建人） | FOREIGN_KEY | HIGH |
| risk_events | ["project_id"] | N:1 | projects | ["id"] | 风险事件：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| risk_events | ["resolved_by"] | N:1 | users | ["id"] | 风险事件：风险关闭操作人 | FOREIGN_KEY | HIGH |
| risk_events | ["task_id"] | N:1 | tasks | ["id"] | 风险事件：关联执行任务标识 | FOREIGN_KEY | HIGH |
| task_groups | ["parent_id"] | N:1 | task_groups | ["id"] | 任务组：父任务组标识；可构成树 | FOREIGN_KEY | HIGH |
| task_groups | ["project_id"] | N:1 | projects | ["id"] | 任务组：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| task_links | ["project_id"] | N:1 | projects | ["id"] | 任务依赖：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| task_links | ["source_id"] | N:1 | tasks | ["id"] | 任务依赖：依赖前驱任务标识 | FOREIGN_KEY | HIGH |
| task_links | ["target_id"] | N:1 | tasks | ["id"] | 任务依赖：依赖后继任务标识 | FOREIGN_KEY | HIGH |
| task_participants | ["task_id"] | N:1 | tasks | ["id"] | 任务参与关系：关联执行任务标识 | FOREIGN_KEY | HIGH |
| task_participants | ["user_id"] | N:1 | users | ["id"] | 任务参与关系：关联用户标识，具体角色见表用途 | FOREIGN_KEY | HIGH |
| tasks | ["branch_option_id"] | N:1 | branch_options | ["id"] | 执行任务：任务所属路线选项 | FOREIGN_KEY | HIGH |
| tasks | ["branch_root_id"] | N:1 | tasks | ["id"] | 执行任务：旧版路线共同根任务标识，不是通用父子任务 | FOREIGN_KEY | HIGH |
| tasks | ["calendar_id"] | N:1 | work_calendars | ["project_id"] | 执行任务：任务工作日历键，指向 work_calendars.project_id（无 calendar.id） | FOREIGN_KEY | HIGH |
| tasks | ["milestone_id"] | N:1 | milestones | ["id"] | 执行任务：任务关联里程碑 | FOREIGN_KEY | HIGH |
| tasks | ["task_group_id"] | N:1 | task_groups | ["id"] | 执行任务：任务所属结构化分组 | FOREIGN_KEY | HIGH |
| tasks | ["owner_id"] | N:1 | users | ["id"] | 执行任务：业务主负责人用户标识（不是创建人） | FOREIGN_KEY | HIGH |
| tasks | ["project_id"] | N:1 | projects | ["id"] | 执行任务：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| work_calendars | ["project_id"] | 1:1 | projects | ["id"] | 项目工作日历：所属或关联项目的内部标识 | FOREIGN_KEY | HIGH |
| agent_batch_items | ["operation_id"] | N:1 | agent_batch_operations | ["operation_id"] | 批次条目按唯一 operation_id 归属批次；无数据库 FK | INFERRED | HIGH |
| agent_conversations | ["summary_message_id"] | N:1 | agent_messages | ["id"] | 滚动摘要覆盖到的消息游标；必须校验消息属于同一会话 | INFERRED | HIGH |
| agent_conversations | ["summary_through_message_id"] | N:1 | agent_messages | ["id"] | 滚动摘要覆盖到的消息游标；必须校验消息属于同一会话 | INFERRED | HIGH |
| branch_groups | ["legacy_root_id"] | 1:1 | tasks | ["id"] | 历史迁移从 tasks.branch_root_id 建立路线决策组；根标识保留而无 FK | INFERRED | HIGH |
| change_proposals | ["project_id", "base_plan_version"] | N:1 | plan_versions | ["project_id", "version"] | 按项目内版本号引用基准计划；不是 plan_versions.id | INFERRED | HIGH |
| agent_batch_items | ["resource_id"] | N:1 | tasks | ["id"] | 当前任务批量创建/更新回执中的资源标识为字符串任务 ID；仅在工具类型白名单分支解析 | INFERRED | HIGH |
| agent_operations | ["request_id", "tool_call_id"] | N:N | agent_tool_calls | ["request_id", "tool_call_id"] | 同请求及模型调用标识可能关联操作回执与调用日志；目标没有唯一约束，不可直接 JOIN 计数 | INFERRED | MEDIUM |

### action_items_created_by_fkey

- 约束：`action_items_created_by_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: action_items_created_by_fkey`；`backend/app/models/action_item.py:37`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### action_items_issue_id_fkey

- 约束：`action_items_issue_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: action_items_issue_id_fkey`；`backend/app/models/action_item.py:37`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### action_items_owner_id_fkey

- 约束：`action_items_owner_id_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: action_items_owner_id_fkey`；`backend/app/models/action_item.py:37`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### action_items_project_id_fkey

- 约束：`action_items_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: action_items_project_id_fkey`；`backend/app/models/action_item.py:37`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### action_items_task_id_fkey

- 约束：`action_items_task_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: action_items_task_id_fkey`；`backend/app/models/action_item.py:37`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_action_items_advice_id

- 约束：`fk_action_items_advice_id`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_action_items_advice_id`；`backend/app/models/action_item.py:37`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### advice_records_decided_by_fkey

- 约束：`advice_records_decided_by_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: advice_records_decided_by_fkey`；`backend/app/models/advice_record.py:50`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### advice_records_evaluated_by_fkey

- 约束：`advice_records_evaluated_by_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: advice_records_evaluated_by_fkey`；`backend/app/models/advice_record.py:50`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### advice_records_generated_by_fkey

- 约束：`advice_records_generated_by_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: advice_records_generated_by_fkey`；`backend/app/models/advice_record.py:50`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### advice_records_issue_id_fkey

- 约束：`advice_records_issue_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: advice_records_issue_id_fkey`；`backend/app/models/advice_record.py:50`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### advice_records_project_id_fkey

- 约束：`advice_records_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: advice_records_project_id_fkey`；`backend/app/models/advice_record.py:50`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### advice_records_proposal_id_fkey

- 约束：`advice_records_proposal_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: advice_records_proposal_id_fkey`；`backend/app/models/advice_record.py:50`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_batch_operations_user_id_fkey

- 约束：`agent_batch_operations_user_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_batch_operations_user_id_fkey`；`backend/app/models/agent_batch.py:18`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_command_items_plan_id_fkey

- 约束：`agent_command_items_plan_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_command_items_plan_id_fkey`；`backend/app/models/agent_command.py:37`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_command_plans_request_id_fkey

- 约束：`agent_command_plans_request_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_command_plans_request_id_fkey`；`backend/app/models/agent_command.py:19`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_conversations_project_id_fkey

- 约束：`agent_conversations_project_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_conversations_project_id_fkey`；`backend/app/models/agent_conversation.py:41`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_conversations_user_id_fkey

- 约束：`agent_conversations_user_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_conversations_user_id_fkey`；`backend/app/models/agent_conversation.py:41`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_memories_project_id_fkey

- 约束：`agent_memories_project_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_memories_project_id_fkey`；`backend/app/models/agent_memory.py:25`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_memories_user_id_fkey

- 约束：`agent_memories_user_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_memories_user_id_fkey`；`backend/app/models/agent_memory.py:25`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_messages_conversation_id_fkey

- 约束：`agent_messages_conversation_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_messages_conversation_id_fkey`；`backend/app/models/agent_conversation.py:88`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_agent_messages_parent_user

- 约束：`fk_agent_messages_parent_user`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_agent_messages_parent_user`；`backend/app/models/agent_conversation.py:88`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_agent_messages_regenerated_from

- 约束：`fk_agent_messages_regenerated_from`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_agent_messages_regenerated_from`；`backend/app/models/agent_conversation.py:88`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_agent_messages_selected_answer

- 约束：`fk_agent_messages_selected_answer`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_agent_messages_selected_answer`；`backend/app/models/agent_conversation.py:88`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_operations_request_id_fkey

- 约束：`agent_operations_request_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_operations_request_id_fkey`；`backend/app/models/agent_request.py:93`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_requests_assistant_message_id_fkey

- 约束：`agent_requests_assistant_message_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_requests_assistant_message_id_fkey`；`backend/app/models/agent_request.py:44`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_requests_conversation_id_fkey

- 约束：`agent_requests_conversation_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_requests_conversation_id_fkey`；`backend/app/models/agent_request.py:44`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_requests_user_id_fkey

- 约束：`agent_requests_user_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_requests_user_id_fkey`；`backend/app/models/agent_request.py:44`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_requests_user_message_id_fkey

- 约束：`agent_requests_user_message_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_requests_user_message_id_fkey`；`backend/app/models/agent_request.py:44`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_tool_calls_conversation_id_fkey

- 约束：`agent_tool_calls_conversation_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_tool_calls_conversation_id_fkey`；`backend/app/models/agent_tool_call.py:18`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_tool_calls_request_id_fkey

- 约束：`agent_tool_calls_request_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_tool_calls_request_id_fkey`；`backend/app/models/agent_tool_call.py:18`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### agent_tool_calls_user_id_fkey

- 约束：`agent_tool_calls_user_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: agent_tool_calls_user_id_fkey`；`backend/app/models/agent_tool_call.py:18`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### ai_runs_created_by_fkey

- 约束：`ai_runs_created_by_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: ai_runs_created_by_fkey`；`backend/app/models/ai_run.py:29`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### audit_logs_user_id_fkey

- 约束：`audit_logs_user_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: audit_logs_user_id_fkey`；`backend/app/models/audit_log.py:13`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### branch_groups_project_id_fkey

- 约束：`branch_groups_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: branch_groups_project_id_fkey`；`backend/app/models/planning.py:101`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_branch_entry

- 约束：`fk_branch_entry`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_branch_entry`；`backend/app/models/planning.py:101`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_branch_exit

- 约束：`fk_branch_exit`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_branch_exit`；`backend/app/models/planning.py:101`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### branch_options_group_id_fkey

- 约束：`branch_options_group_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: branch_options_group_id_fkey`；`backend/app/models/planning.py:117`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### change_proposals_applied_by_fkey

- 约束：`change_proposals_applied_by_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: change_proposals_applied_by_fkey`；`backend/app/models/change_proposal.py:25`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### change_proposals_applied_version_id_fkey

- 约束：`change_proposals_applied_version_id_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: change_proposals_applied_version_id_fkey`；`backend/app/models/change_proposal.py:25`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### change_proposals_confirmed_by_fkey

- 约束：`change_proposals_confirmed_by_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: change_proposals_confirmed_by_fkey`；`backend/app/models/change_proposal.py:25`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### change_proposals_created_by_fkey

- 约束：`change_proposals_created_by_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: change_proposals_created_by_fkey`；`backend/app/models/change_proposal.py:25`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### change_proposals_project_id_fkey

- 约束：`change_proposals_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: change_proposals_project_id_fkey`；`backend/app/models/change_proposal.py:25`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### daily_project_summaries_project_id_fkey

- 约束：`daily_project_summaries_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: daily_project_summaries_project_id_fkey`；`backend/app/models/daily_project_summary.py:14`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### issues_project_id_fkey

- 约束：`issues_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: issues_project_id_fkey`；`backend/app/models/issue.py:31`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### issues_reported_by_fkey

- 约束：`issues_reported_by_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: issues_reported_by_fkey`；`backend/app/models/issue.py:31`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### issues_task_id_fkey

- 约束：`issues_task_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: issues_task_id_fkey`；`backend/app/models/issue.py:31`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### milestones_owner_id_fkey

- 约束：`milestones_owner_id_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: milestones_owner_id_fkey`；`backend/app/models/planning.py:71`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### milestones_project_id_fkey

- 约束：`milestones_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: milestones_project_id_fkey`；`backend/app/models/planning.py:71`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_notification_risk

- 约束：`fk_notification_risk`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_notification_risk`；`backend/app/models/notification.py:41`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### plan_notification_events_project_id_fkey

- 约束：`plan_notification_events_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: plan_notification_events_project_id_fkey`；`backend/app/models/notification.py:41`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### plan_notification_events_proposal_id_fkey

- 约束：`plan_notification_events_proposal_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: plan_notification_events_proposal_id_fkey`；`backend/app/models/notification.py:41`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### plan_notification_events_recipient_id_fkey

- 约束：`plan_notification_events_recipient_id_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: plan_notification_events_recipient_id_fkey`；`backend/app/models/notification.py:41`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### plan_drafts_created_by_fkey

- 约束：`plan_drafts_created_by_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: plan_drafts_created_by_fkey`；`backend/app/models/plan_draft.py:27`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### plan_drafts_project_id_fkey

- 约束：`plan_drafts_project_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: plan_drafts_project_id_fkey`；`backend/app/models/plan_draft.py:27`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### plan_drafts_published_by_fkey

- 约束：`plan_drafts_published_by_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: plan_drafts_published_by_fkey`；`backend/app/models/plan_draft.py:27`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### plan_versions_created_by_fkey

- 约束：`plan_versions_created_by_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: plan_versions_created_by_fkey`；`backend/app/models/planning.py:128`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### plan_versions_project_id_fkey

- 约束：`plan_versions_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: plan_versions_project_id_fkey`；`backend/app/models/planning.py:128`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### progress_updates_task_id_fkey

- 约束：`progress_updates_task_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: progress_updates_task_id_fkey`；`backend/app/models/progress_update.py:13`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### progress_updates_user_id_fkey

- 约束：`progress_updates_user_id_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: progress_updates_user_id_fkey`；`backend/app/models/progress_update.py:13`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### project_members_project_id_fkey

- 约束：`project_members_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: project_members_project_id_fkey`；`backend/app/models/planning.py:25`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### project_members_user_id_fkey

- 约束：`project_members_user_id_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: project_members_user_id_fkey`；`backend/app/models/planning.py:25`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### project_owners_project_id_fkey

- 约束：`project_owners_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: project_owners_project_id_fkey`；`backend/app/models/project.py:33`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### project_owners_user_id_fkey

- 约束：`project_owners_user_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: project_owners_user_id_fkey`；`backend/app/models/project.py:33`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### projects_owner_id_fkey

- 约束：`projects_owner_id_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: projects_owner_id_fkey`；`backend/app/models/project.py:36`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### risk_events_issue_id_fkey

- 约束：`risk_events_issue_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: risk_events_issue_id_fkey`；`backend/app/models/risk_event.py:57`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### risk_events_owner_id_fkey

- 约束：`risk_events_owner_id_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: risk_events_owner_id_fkey`；`backend/app/models/risk_event.py:57`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### risk_events_project_id_fkey

- 约束：`risk_events_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: risk_events_project_id_fkey`；`backend/app/models/risk_event.py:57`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### risk_events_resolved_by_fkey

- 约束：`risk_events_resolved_by_fkey`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: risk_events_resolved_by_fkey`；`backend/app/models/risk_event.py:57`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### risk_events_task_id_fkey

- 约束：`risk_events_task_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: risk_events_task_id_fkey`；`backend/app/models/risk_event.py:57`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### task_groups_parent_id_fkey

- 约束：`task_groups_parent_id_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: task_groups_parent_id_fkey`；`backend/app/models/planning.py:91`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：True。

### task_groups_project_id_fkey

- 约束：`task_groups_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: task_groups_project_id_fkey`；`backend/app/models/planning.py:91`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### task_links_project_id_fkey

- 约束：`task_links_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: task_links_project_id_fkey`；`backend/app/models/task.py:178`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### task_links_source_id_fkey

- 约束：`task_links_source_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: task_links_source_id_fkey`；`backend/app/models/task.py:178`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### task_links_target_id_fkey

- 约束：`task_links_target_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: task_links_target_id_fkey`；`backend/app/models/task.py:178`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### task_participants_task_id_fkey

- 约束：`task_participants_task_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: task_participants_task_id_fkey`；`backend/app/models/planning.py:41`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### task_participants_user_id_fkey

- 约束：`task_participants_user_id_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: task_participants_user_id_fkey`；`backend/app/models/planning.py:41`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_tasks_branch_option_id

- 约束：`fk_tasks_branch_option_id`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_tasks_branch_option_id`；`backend/app/models/task.py:48`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_tasks_branch_root_id

- 约束：`fk_tasks_branch_root_id`；ON DELETE：SET NULL；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_tasks_branch_root_id`；`backend/app/models/task.py:48`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_tasks_calendar_id

- 约束：`fk_tasks_calendar_id`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_tasks_calendar_id`；`backend/app/models/task.py:48`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_tasks_milestone_id

- 约束：`fk_tasks_milestone_id`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_tasks_milestone_id`；`backend/app/models/task.py:48`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### fk_tasks_task_group_id

- 约束：`fk_tasks_task_group_id`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: fk_tasks_task_group_id`；`backend/app/models/task.py:48`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### tasks_owner_id_fkey

- 约束：`tasks_owner_id_fkey`；ON DELETE：RESTRICT；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: tasks_owner_id_fkey`；`backend/app/models/task.py:48`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### tasks_project_id_fkey

- 约束：`tasks_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: tasks_project_id_fkey`；`backend/app/models/task.py:48`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### work_calendars_project_id_fkey

- 约束：`work_calendars_project_id_fkey`；ON DELETE：CASCADE；ON UPDATE：NO ACTION。
- 来源：FOREIGN_KEY；confidence：HIGH；允许已登记服务路径：True。
- 证据：`pg_catalog.pg_constraint: work_calendars_project_id_fkey`；`backend/app/models/planning.py:57`。
- 依据：实际数据库外键；目标唯一性由约束保证。
- 附加条件：每端独立对象权限；递归闭包：False。

### logical_agent_batch_items_operation_id

- 约束：`NONE`；ON DELETE：UNKNOWN；ON UPDATE：UNKNOWN。
- 来源：INFERRED；confidence：HIGH；允许已登记服务路径：True。
- 证据：`backend/app/services/agent_batch.py:490`；`backend/app/models/agent_batch.py`。
- 依据：批次条目按唯一 operation_id 归属批次；无数据库 FK。
- 附加条件：每端独立对象权限；递归闭包：False。

### logical_agent_conversations_summary_message_id

- 约束：`NONE`；ON DELETE：UNKNOWN；ON UPDATE：UNKNOWN。
- 来源：INFERRED；confidence：HIGH；允许已登记服务路径：True。
- 证据：`backend/app/services/conversation.py:1289`。
- 依据：滚动摘要覆盖到的消息游标；必须校验消息属于同一会话。
- 附加条件：agent_messages.conversation_id = agent_conversations.id；递归闭包：False。

### logical_agent_conversations_summary_through_message_id

- 约束：`NONE`；ON DELETE：UNKNOWN；ON UPDATE：UNKNOWN。
- 来源：INFERRED；confidence：HIGH；允许已登记服务路径：True。
- 证据：`backend/app/services/conversation.py:1289`。
- 依据：滚动摘要覆盖到的消息游标；必须校验消息属于同一会话。
- 附加条件：agent_messages.conversation_id = agent_conversations.id；递归闭包：False。

### logical_branch_groups_legacy_root_id

- 约束：`NONE`；ON DELETE：UNKNOWN；ON UPDATE：UNKNOWN。
- 来源：INFERRED；confidence：HIGH；允许已登记服务路径：True。
- 证据：`backend/alembic/versions/20260907_1800_f6a7b8c9d0e1_s1_planning_models.py:198`。
- 依据：历史迁移从 tasks.branch_root_id 建立路线决策组；根标识保留而无 FK。
- 附加条件：tasks.project_id = branch_groups.project_id；递归闭包：False。

### logical_change_proposals_project_id_base_plan_version

- 约束：`NONE`；ON DELETE：UNKNOWN；ON UPDATE：UNKNOWN。
- 来源：INFERRED；confidence：HIGH；允许已登记服务路径：True。
- 证据：`backend/app/services/change_proposal.py:213`；`backend/app/services/change_proposal.py:561`。
- 依据：按项目内版本号引用基准计划；不是 plan_versions.id。
- 附加条件：base_plan_version > 0；递归闭包：False。

### logical_agent_batch_items_resource_id

- 约束：`NONE`；ON DELETE：UNKNOWN；ON UPDATE：UNKNOWN。
- 来源：INFERRED；confidence：HIGH；允许已登记服务路径：False。
- 证据：`backend/app/services/agent_batch.py:300`；`backend/app/services/agent_batch.py:650`。
- 依据：当前任务批量创建/更新回执中的资源标识为字符串任务 ID；仅在工具类型白名单分支解析。
- 附加条件：parent.tool_name IN ('batch_create_tasks','batch_update_tasks'); typed service resolution only；递归闭包：False。

### logical_agent_operations_request_id_tool_call_id

- 约束：`NONE`；ON DELETE：UNKNOWN；ON UPDATE：UNKNOWN。
- 来源：INFERRED；confidence：MEDIUM；允许已登记服务路径：False。
- 证据：`backend/app/models/agent_request.py`；`backend/app/models/agent_tool_call.py`。
- 依据：同请求及模型调用标识可能关联操作回执与调用日志；目标没有唯一约束，不可直接 JOIN 计数。
- 附加条件：每端独立对象权限；递归闭包：False。

## 中间表与多对多

| 中间表 | 实体 A | 关系 | 实体 B | 附加条件 |
| --- | --- | --- | --- | --- |
| project_owners | Project | N:N | User | — |
| project_members | Project | N:N | User | project_members.is_active = true |
| task_participants | Task | N:N | User | role = OWNER / COLLABORATOR / WATCHER 必须区分 |
| task_links | Task | N:N | Task | 有向依赖；link_type 与 lag_days 一并解释 |

## 不可猜测的多态/外部引用

| 位置 | 判别器 | 标识 | 规则 | 证据 |
| --- | --- | --- | --- | --- |
| ai_runs | resource_type | resource_id | 按业务资源类型注册解析器，先验证格式再对象鉴权；UNKNOWN 类型拒绝；不可通用 CAST JOIN | backend/app/api/v1/ai_runs.py:38 |
| audit_logs | resource_type | resource_id | 多态审计引用，不是单一 FK；普通 Agent 禁止直接读取 | backend/app/services/audit.py |
| agent_batch_items | parent batch.tool_name | resource_id | 仅已确认任务批次分支由服务解析，其他工具 UNKNOWN | backend/app/services/agent_batch.py:650 |
| advice_records / risk_events | evidence[].source_type | evidence[].source_id | JSON 证据引用必须逐类型解析、逐对象鉴权，禁止泛化 SQL JOIN | backend/app/models/advice_record.py |

`users.oa_admin_id` / `wechat_user_id` 属于外部系统，本库没有对应目标表；外部约束为 UNKNOWN。`client_request_id`、`client_item_id`、`item_id` 是业务幂等或计划局部键，不是 users/tasks FK。`depends_on` 是同一个 plan 内的 item_id 列表，必须带 plan_id 解析。禁止将所有 `_id` 自动连接到 users。

## 核心与完整 JOIN PATH

### action_items_created_by_fkey

- `action_items.created_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### action_items_issue_id_fkey

- `action_items.issue_id = issues.id`

条件：按对象权限。source_to_target_many_to_one。

### action_items_owner_id_fkey

- `action_items.owner_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### action_items_project_id_fkey

- `action_items.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### action_items_task_id_fkey

- `action_items.task_id = tasks.id`

条件：按对象权限。source_to_target_many_to_one。

### fk_action_items_advice_id

- `action_items.advice_id = advice_records.id`

条件：按对象权限。source_to_target_many_to_one。

### advice_records_decided_by_fkey

- `advice_records.decided_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### advice_records_evaluated_by_fkey

- `advice_records.evaluated_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### advice_records_generated_by_fkey

- `advice_records.generated_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### advice_records_issue_id_fkey

- `advice_records.issue_id = issues.id`

条件：按对象权限。source_to_target_many_to_one。

### advice_records_project_id_fkey

- `advice_records.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### advice_records_proposal_id_fkey

- `advice_records.proposal_id = change_proposals.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_batch_operations_user_id_fkey

- `agent_batch_operations.user_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_command_items_plan_id_fkey

- `agent_command_items.plan_id = agent_command_plans.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_command_plans_request_id_fkey

- `agent_command_plans.request_id = agent_requests.id`

条件：按对象权限。at_most_one。

### agent_conversations_project_id_fkey

- `agent_conversations.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_conversations_user_id_fkey

- `agent_conversations.user_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_memories_project_id_fkey

- `agent_memories.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_memories_user_id_fkey

- `agent_memories.user_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_messages_conversation_id_fkey

- `agent_messages.conversation_id = agent_conversations.id`

条件：按对象权限。source_to_target_many_to_one。

### fk_agent_messages_parent_user

- `child.parent_user_message_id = parent.id`

条件：按对象权限。source_to_target_many_to_one。

### fk_agent_messages_regenerated_from

- `child.regenerated_from_id = parent.id`

条件：按对象权限。source_to_target_many_to_one。

### fk_agent_messages_selected_answer

- `child.selected_answer_id = parent.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_operations_request_id_fkey

- `agent_operations.request_id = agent_requests.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_requests_assistant_message_id_fkey

- `agent_requests.assistant_message_id = agent_messages.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_requests_conversation_id_fkey

- `agent_requests.conversation_id = agent_conversations.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_requests_user_id_fkey

- `agent_requests.user_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_requests_user_message_id_fkey

- `agent_requests.user_message_id = agent_messages.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_tool_calls_conversation_id_fkey

- `agent_tool_calls.conversation_id = agent_conversations.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_tool_calls_request_id_fkey

- `agent_tool_calls.request_id = agent_requests.id`

条件：按对象权限。source_to_target_many_to_one。

### agent_tool_calls_user_id_fkey

- `agent_tool_calls.user_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### ai_runs_created_by_fkey

- `ai_runs.created_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### audit_logs_user_id_fkey

- `audit_logs.user_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### branch_groups_project_id_fkey

- `branch_groups.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### fk_branch_entry

- `branch_groups.entry_task_id = tasks.id`

条件：按对象权限。source_to_target_many_to_one。

### fk_branch_exit

- `branch_groups.exit_task_id = tasks.id`

条件：按对象权限。source_to_target_many_to_one。

### branch_options_group_id_fkey

- `branch_options.group_id = branch_groups.id`

条件：按对象权限。source_to_target_many_to_one。

### change_proposals_applied_by_fkey

- `change_proposals.applied_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### change_proposals_applied_version_id_fkey

- `change_proposals.applied_version_id = plan_versions.id`

条件：按对象权限。source_to_target_many_to_one。

### change_proposals_confirmed_by_fkey

- `change_proposals.confirmed_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### change_proposals_created_by_fkey

- `change_proposals.created_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### change_proposals_project_id_fkey

- `change_proposals.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### daily_project_summaries_project_id_fkey

- `daily_project_summaries.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### issues_project_id_fkey

- `issues.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### issues_reported_by_fkey

- `issues.reported_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### issues_task_id_fkey

- `issues.task_id = tasks.id`

条件：按对象权限。source_to_target_many_to_one。

### milestones_owner_id_fkey

- `milestones.owner_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### milestones_project_id_fkey

- `milestones.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### fk_notification_risk

- `notification_events.risk_event_id = risk_events.id`

条件：按对象权限。source_to_target_many_to_one。

### plan_notification_events_project_id_fkey

- `notification_events.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### plan_notification_events_proposal_id_fkey

- `notification_events.proposal_id = change_proposals.id`

条件：按对象权限。source_to_target_many_to_one。

### plan_notification_events_recipient_id_fkey

- `notification_events.recipient_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### plan_drafts_created_by_fkey

- `plan_drafts.created_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### plan_drafts_project_id_fkey

- `plan_drafts.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### plan_drafts_published_by_fkey

- `plan_drafts.published_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### plan_versions_created_by_fkey

- `plan_versions.created_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### plan_versions_project_id_fkey

- `plan_versions.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### progress_updates_task_id_fkey

- `progress_updates.task_id = tasks.id`

条件：按对象权限。source_to_target_many_to_one。

### progress_updates_user_id_fkey

- `progress_updates.user_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### project_members_project_id_fkey

- `project_members.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### project_members_user_id_fkey

- `project_members.user_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### project_owners_project_id_fkey

- `project_owners.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### project_owners_user_id_fkey

- `project_owners.user_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### projects_owner_id_fkey

- `projects.owner_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### risk_events_issue_id_fkey

- `risk_events.issue_id = issues.id`

条件：按对象权限。source_to_target_many_to_one。

### risk_events_owner_id_fkey

- `risk_events.owner_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### risk_events_project_id_fkey

- `risk_events.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### risk_events_resolved_by_fkey

- `risk_events.resolved_by = users.id`

条件：按对象权限。source_to_target_many_to_one。

### risk_events_task_id_fkey

- `risk_events.task_id = tasks.id`

条件：按对象权限。source_to_target_many_to_one。

### task_groups_parent_id_fkey

- `child.parent_id = parent.id`

条件：按对象权限。source_to_target_many_to_one。

### task_groups_project_id_fkey

- `task_groups.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### task_links_project_id_fkey

- `task_links.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### task_links_source_id_fkey

- `task_links.source_id = tasks.id`

条件：按对象权限。source_to_target_many_to_one。

### task_links_target_id_fkey

- `task_links.target_id = tasks.id`

条件：按对象权限。source_to_target_many_to_one。

### task_participants_task_id_fkey

- `task_participants.task_id = tasks.id`

条件：按对象权限。source_to_target_many_to_one。

### task_participants_user_id_fkey

- `task_participants.user_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### fk_tasks_branch_option_id

- `tasks.branch_option_id = branch_options.id`

条件：按对象权限。source_to_target_many_to_one。

### fk_tasks_branch_root_id

- `child.branch_root_id = parent.id`

条件：按对象权限。source_to_target_many_to_one。

### fk_tasks_calendar_id

- `tasks.calendar_id = work_calendars.project_id`

条件：按对象权限。source_to_target_many_to_one。

### fk_tasks_milestone_id

- `tasks.milestone_id = milestones.id`

条件：按对象权限。source_to_target_many_to_one。

### fk_tasks_task_group_id

- `tasks.task_group_id = task_groups.id`

条件：按对象权限。source_to_target_many_to_one。

### tasks_owner_id_fkey

- `tasks.owner_id = users.id`

条件：按对象权限。source_to_target_many_to_one。

### tasks_project_id_fkey

- `tasks.project_id = projects.id`

条件：按对象权限。source_to_target_many_to_one。

### work_calendars_project_id_fkey

- `work_calendars.project_id = projects.id`

条件：按对象权限。at_most_one。

### logical_agent_batch_items_operation_id

- `agent_batch_items.operation_id = agent_batch_operations.operation_id`

条件：按对象权限。source_to_target_many_to_one。

### logical_agent_conversations_summary_message_id

- `agent_conversations.summary_message_id = agent_messages.id`

条件：agent_messages.conversation_id = agent_conversations.id。source_to_target_many_to_one。

### logical_agent_conversations_summary_through_message_id

- `agent_conversations.summary_through_message_id = agent_messages.id`

条件：agent_messages.conversation_id = agent_conversations.id。source_to_target_many_to_one。

### logical_branch_groups_legacy_root_id

- `branch_groups.legacy_root_id = tasks.id`

条件：tasks.project_id = branch_groups.project_id。at_most_one。

### logical_change_proposals_project_id_base_plan_version

- `change_proposals.project_id = plan_versions.project_id`
- `change_proposals.base_plan_version = plan_versions.version`

条件：base_plan_version > 0。source_to_target_many_to_one。

### Project -> Task

- `projects.id = tasks.project_id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Task -> PrimaryOwner

- `tasks.owner_id = users.id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Project -> Owners

- `projects.id = project_owners.project_id`
- `project_owners.user_id = users.id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Project -> ActiveMembers

- `projects.id = project_members.project_id`
- `project_members.user_id = users.id`

条件：project_members.is_active = true。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Task -> AllOwners

- `tasks.id = task_participants.task_id`
- `task_participants.user_id = users.id`

条件：task_participants.role = 'OWNER'; 与 tasks.owner_id 做集合并集、去重。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Project -> Task -> Progress

- `projects.id = tasks.project_id`
- `tasks.id = progress_updates.task_id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Issue -> Advice -> Action

- `issues.id = advice_records.issue_id`
- `advice_records.id = action_items.advice_id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Project -> Risk -> Notification

- `projects.id = risk_events.project_id`
- `risk_events.id = notification_events.risk_event_id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Project -> Group -> Option -> Task

- `projects.id = branch_groups.project_id`
- `branch_groups.id = branch_options.group_id`
- `branch_options.id = tasks.branch_option_id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### ChangeProposal -> AppliedSnapshot

- `change_proposals.applied_version_id = plan_versions.id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Task -> Calendar

- `tasks.calendar_id = work_calendars.project_id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Project -> Task -> Owner

- `projects.id = tasks.project_id`
- `tasks.owner_id = users.id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Task -> Progress

- `tasks.id = progress_updates.task_id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Project -> Risk

- `projects.id = risk_events.project_id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Notification -> Recipient

- `notification_events.recipient_id = users.id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### Project -> PlanVersion

- `projects.id = plan_versions.project_id`

条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### ScopedTask



条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### ScopedNotification



条件：按对象权限。一对多连接会重复父记录，计数用业务主键去重或 EXISTS。

### TaskDependency -> Endpoints

- `task_links.source_id = predecessor.id`
- `task_links.target_id = successor.id`

条件：task_links.project_id = predecessor.project_id = successor.project_id。每条依赖最多一对端点。

## 自关联与递归

- `task_groups.parent_id → task_groups.id`：真正的分组层级，查询任意深度子树需递归 CTE 或服务树遍历；限制深度、环与项目范围。
- `tasks.branch_root_id → tasks.id`：路线根分组，不是父子执行任务；正常直接查同根，无需无限递归。
- `agent_messages` 三个自 FK：所属问题、重新生成来源、选中答案。普通展示无需递归；追溯重新生成链才需受限递归，始终同会话。
- `task_links` 是有向依赖图，查邻接只需两次任务别名；查传递依赖需递归 CTE 或调度服务图算法，不能把两个 source/target 当树父子。
