# AGENT_TOOLS

> Copyright 2024–2026 Jack Zhang. Apache License 2.0；保留 NOTICE 署名。
> 采集日期：2026-09-15；结构来源：实际 PostgreSQL 只读目录；业务语义来源：当前工作区模型、迁移与服务。
> 未读取业务记录。PUBLIC 仅表示字段可经授权业务 DTO 使用，不表示互联网公开或授权直连数据库。

当前清单从 MANAGEMENT_TOOLS 参数 schema 读取；`current_registry_operation` 与建议 `operation` 分开。所有建议 WRITE 默认 requires_confirmation=true；不会因文档列出工具而授权当前 Agent 执行。返回字段为建议的最小 DTO，并非现有返回体的完整复刻。底层表是主要业务表及相关表，未声称覆盖所有审计/异步副作用。完整参数 JSON Schema 存于 database_schema.json 和 YAML。

## 第一阶段优先清单（28 项）

`get_current_user`, `batch_find_users`, `list_projects`, `get_project`, `get_task`, `search_tasks`, `query_entities`, `get_task_progress`, `get_project_progress_overview`, `get_dependency_graph`, `list_open_issues`, `list_action_items`, `list_risk_events`, `get_issue_evidence`, `get_issue_advice`, `get_notification_status`, `get_plan_version`, `create_task`, `batch_create_tasks`, `assign_task`, `change_task_status`, `submit_progress`, `create_issue`, `create_action_item`, `preview_change`, `propose_change`, `draft_project_plan`, `review_project_plan_draft`。

先修复 task_code、多负责人、进度统计与伪只读工具，再接入工具路由。get_task/get_plan_version 为建议新增，其余复用/收紧现有能力；review_project_plan_draft 必须按 WRITE 分类。

## READ TOOL

| Tool | Entity | 现状 | 必填参数 | 可选参数 | 返回 DTO | Permission / Scope | Service | Tables | 确认 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| get_current_user | User | EXISTING_TOOL | [] | [] | ["name", "username", "department"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["users"] | 否 |
| list_projects | Project | EXISTING_TOOL | [] | [] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["projects", "users", "project_owners"] | 否 |
| get_project | Project | EXISTING_TOOL | [] | ["project_id", "project_code"] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["projects", "users", "project_owners"] | 否 |
| search_tasks | Task | EXISTING_TOOL | [] | ["project_id", "project_code", "owner_scope", "owner_id", "date_preset", "due_from", "due_to", "status", "keyword", "include_inactive", "limit", "cursor", "owner_name", "statuses", "progress_min", "progress_max", "overdue"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["tasks", "projects", "users", "task_participants"] | 否 |
| query_tasks | Task | EXISTING_TOOL | [] | ["filters", "sort", "group_by", "aggregates", "limit", "offset"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["tasks", "projects", "users", "task_participants"] | 否 |
| search_projects | Project | EXISTING_TOOL | [] | ["filters", "sort", "limit", "offset"] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["projects", "users", "project_owners"] | 否 |
| search_issues | Issue | EXISTING_TOOL | [] | ["filters", "sort", "limit", "offset"] | ["title", "status", "severity", "description_excerpt"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["issues", "projects", "tasks"] | 否 |
| list_my_tasks | Task | EXISTING_TOOL | [] | ["project_id", "project_code", "date_preset", "due_from", "due_to", "status", "keyword", "limit", "cursor"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["tasks", "projects", "users", "task_participants"] | 否 |
| list_project_tasks | Task | EXISTING_TOOL | [] | ["project_id", "project_code", "owner_name"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["tasks", "projects", "users", "task_participants"] | 否 |
| get_task_progress | Task | EXISTING_TOOL | [] | ["task_id", "project_code", "target_task_name", "project_id"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["tasks", "progress_updates", "users"] | 否 |
| list_delayed_tasks | Task | EXISTING_TOOL | [] | ["project_id"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["tasks", "projects", "users", "task_participants"] | 否 |
| list_at_risk_tasks | Task | EXISTING_TOOL | [] | ["project_id"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["tasks", "projects", "users", "task_participants"] | 否 |
| list_open_issues | Issue | EXISTING_TOOL | [] | ["project_id", "task_id"] | ["title", "status", "severity", "description_excerpt"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["issues", "projects", "tasks"] | 否 |
| list_action_items | ActionItem | EXISTING_TOOL | [] | ["project_id", "project_code", "owner_name", "issue_id", "open_only"] | ["title", "status", "priority", "owner_display", "due_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["action_items", "projects", "users", "issues"] | 否 |
| get_management_attention_items | Project | EXISTING_TOOL | [] | [] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["projects", "tasks", "issues", "action_items", "progress_updates"] | 否 |
| find_users | User | EXISTING_TOOL | [] | ["query", "names", "limit"] | ["name", "username", "department"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["users"] | 否 |
| batch_find_users | User | EXISTING_TOOL | ["names"] | [] | ["name", "username", "department"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | AgentBatchService | ["users"] | 否 |
| query_entities | Task | EXISTING_TOOL | ["entity"] | ["filters", "fields", "order_by", "sort", "group_by", "aggregates", "limit", "offset"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["tasks", "projects", "issues", "users", "milestones", "project_members"] | 否 |
| list_task_branches | Project | EXISTING_TOOL | ["task_id"] | [] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["projects", "tasks", "branch_groups", "branch_options"] | 否 |
| get_project_context | Project | EXISTING_TOOL | [] | ["project_id", "project_code"] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementPlanningService | ["projects", "tasks", "task_links", "project_members", "task_participants", "work_calendars", "milestones", "task_groups", "branch_groups", "branch_options", "plan_versions"] | 否 |
| get_dependency_graph | Project | EXISTING_TOOL | [] | ["project_id", "project_code"] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementPlanningService | ["projects", "tasks", "task_links", "task_groups", "branch_groups", "branch_options", "work_calendars"] | 否 |
| get_project_plan_draft | PlanDraft | EXISTING_TOOL | [] | ["draft_id"] | ["title", "status", "revision", "review_summary"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementPlanningService | ["plan_drafts"] | 否 |
| preview_change | Project | EXISTING_TOOL | [] | ["project_id", "project_code", "changes", "links", "selections", "project_target_date"] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementPlanningService | ["projects", "tasks", "task_links", "work_calendars"] | 否 |
| get_change_proposal | ChangeProposal | EXISTING_TOOL | [] | ["project_id", "project_code", "proposal_id"] | ["status", "revision", "diff_summary", "expires_at"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementPlanningService | ["change_proposals", "projects", "tasks", "task_links", "plan_versions", "notification_events"] | 否 |
| get_notification_status | NotificationEvent | EXISTING_TOOL | [] | ["proposal_id", "status", "limit"] | ["status", "channel", "sent_at", "acknowledged_at", "delivery_uncertain"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementPlanningService | ["notification_events", "users", "projects", "change_proposals"] | 否 |
| list_risk_events | RiskEvent | EXISTING_TOOL | [] | ["project_id", "project_code", "status", "event_type", "limit"] | ["title", "event_type", "level", "status", "cause", "impact_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementPlanningService | ["risk_events", "tasks", "issues", "projects"] | 否 |
| get_issue_evidence | Issue | EXISTING_TOOL | ["issue_id"] | [] | ["title", "status", "severity", "description_excerpt"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementPlanningService | ["issues", "tasks", "progress_updates", "risk_events", "advice_records"] | 否 |
| get_issue_advice | Issue | EXISTING_TOOL | ["issue_id"] | [] | ["title", "status", "severity", "description_excerpt"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementPlanningService | ["issues", "advice_records"] | 否 |
| get_project_progress_overview | Project | EXISTING_TOOL | [] | ["project_id", "project_code", "days"] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 已认证 + 所有对象读取权限；先过滤再分页、聚合 | ManagementQueryService | ["projects", "tasks", "progress_updates", "issues"] | 否 |
| get_task | Task | PROPOSED_NOT_IMPLEMENTED | ["task_code"] | [] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 已认证且对象权限通过 | TaskService + can_view_task | ["tasks", "projects", "users", "task_participants"] | 否 |
| get_plan_version | PlanVersion | PROPOSED_NOT_IMPLEMENTED | ["project_id", "version"] | [] | ["scoped_summary"] | 已认证且对象权限通过 | PlanningService + can_view_full_project | ["plan_versions", "projects"] | 否 |

## WRITE TOOL

| Tool | Entity | 现状 | 必填参数 | 可选参数 | 返回 DTO | Permission / Scope | Service | Tables | 确认 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| batch_create_tasks | AgentBatchOperation | EXISTING_TOOL | [] | ["operation_id", "project_id", "project_code", "items", "tasks"] | ["scoped_summary", "coverage"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | AgentBatchService | ["agent_batch_operations", "agent_batch_items", "projects", "users", "tasks", "task_participants", "audit_logs"] | 是 |
| batch_update_tasks | AgentBatchOperation | EXISTING_TOOL | ["items"] | ["operation_id"] | ["scoped_summary", "coverage"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | AgentBatchService | ["agent_batch_operations", "agent_batch_items", "projects", "users", "tasks", "task_participants", "audit_logs"] | 是 |
| create_project | Project | EXISTING_TOOL | ["project_name"] | ["project_code", "goal", "target_date", "status", "risk_level", "owner_ids", "start_date", "owner_id", "owner_username", "owner_name"] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["projects", "users", "project_owners"] | 是 |
| update_project | Project | EXISTING_TOOL | [] | ["project_id", "project_code", "change_reason", "project_name", "goal", "target_date", "status", "risk_level", "owner_ids", "start_date", "owner_id", "owner_username", "owner_name"] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["projects", "users", "project_owners"] | 是 |
| create_task | Task | EXISTING_TOOL | ["task_name"] | ["project_id", "project_code", "work_stream", "due_date", "start_date", "status", "progress_percent", "owner_id", "owner_username", "owner_name", "description", "deliverable", "acceptance_criteria", "planned_duration_days", "remaining_duration_days", "actual_start_date", "actual_finish_date", "earliest_start_date", "fixed_start_date", "fixed_due_date", "calendar_id", "milestone_id", "task_group_id"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["tasks", "projects", "users", "task_participants"] | 是 |
| create_milestone | Project | EXISTING_TOOL | [] | ["project_id", "project_code", "name", "milestone_name", "target_date", "deliverable", "acceptance_criteria", "owner_id", "owner_username", "owner_name"] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementPlanningService | ["projects", "milestones", "users", "audit_logs"] | 是 |
| update_task | Task | EXISTING_TOOL | [] | ["task_id", "work_stream", "task_name", "due_date", "start_date", "status", "progress_percent", "expected_version", "target_task_name", "owner_id", "owner_username", "owner_name", "description", "deliverable", "acceptance_criteria", "planned_duration_days", "remaining_duration_days", "actual_start_date", "actual_finish_date", "earliest_start_date", "fixed_start_date", "fixed_due_date", "calendar_id", "milestone_id", "task_group_id", "project_id", "project_code", "new_task_name"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["tasks", "projects", "users", "task_participants"] | 是 |
| assign_task | Task | EXISTING_TOOL | [] | ["task_id", "target_task_name", "project_code", "expected_version", "owner_id", "owner_username", "owner_name"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["tasks", "projects", "users", "task_participants"] | 是 |
| change_task_status | Task | EXISTING_TOOL | ["status"] | ["task_id", "target_task_name", "project_code", "expected_version"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；任务 OWNER 或项目管理权限 | ManagementWriteService | ["tasks", "projects", "users", "task_participants"] | 是 |
| reschedule_task | Task | EXISTING_TOOL | [] | ["task_id", "target_task_name", "project_code", "due_date", "start_date", "offset_days", "shift_start", "expected_version"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["tasks", "projects", "users", "task_participants"] | 是 |
| create_issue | Issue | EXISTING_TOOL | ["title", "description"] | ["project_id", "project_code", "task_id", "severity"] | ["title", "status", "severity", "description_excerpt"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["issues", "projects", "tasks"] | 是 |
| update_issue | Issue | EXISTING_TOOL | ["issue_id"] | ["title", "description", "severity", "status"] | ["title", "status", "severity", "description_excerpt"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["issues", "projects", "tasks"] | 是 |
| create_action_item | ActionItem | EXISTING_TOOL | ["title"] | ["project_id", "project_code", "description", "task_id", "issue_id", "due_date", "priority", "status", "owner_id", "owner_username", "owner_name"] | ["title", "status", "priority", "owner_display", "due_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["action_items", "projects", "users", "issues"] | 是 |
| update_action_item | ActionItem | EXISTING_TOOL | ["action_item_id"] | ["title", "description", "task_id", "issue_id", "due_date", "priority", "status", "owner_id", "owner_username", "owner_name"] | ["title", "status", "priority", "owner_display", "due_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["action_items", "projects", "users", "issues"] | 是 |
| create_task_branch | Project | EXISTING_TOOL | ["task_id", "task_name", "branch_label", "reason"] | ["owner_id", "start_date", "due_date", "work_stream", "activate"] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["projects", "tasks", "branch_groups", "branch_options"] | 是 |
| activate_task_branch | Project | EXISTING_TOOL | ["task_id", "reason"] | [] | ["project_code", "project_name", "status", "risk_level", "owner_display", "start_date", "target_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementWriteService | ["projects", "tasks", "branch_groups", "branch_options"] | 是 |
| draft_project_plan | PlanDraft | EXISTING_TOOL | ["plan"] | ["title", "idempotency_key"] | ["title", "status", "revision", "review_summary"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；草案所有者/管理权限；发布走专用 UI 授权 | ManagementPlanningService | ["plan_drafts"] | 是 |
| update_project_plan_draft | PlanDraft | EXISTING_TOOL | ["draft_id", "plan"] | ["title", "expected_revision"] | ["title", "status", "revision", "review_summary"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；草案所有者/管理权限；发布走专用 UI 授权 | ManagementPlanningService | ["plan_drafts"] | 是 |
| review_project_plan_draft | PlanDraft | EXISTING_TOOL | ["draft_id"] | ["expected_revision"] | ["title", "status", "revision", "review_summary"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；草案所有者/管理权限；发布走专用 UI 授权 | ManagementPlanningService | ["plan_drafts"] | 是 |
| validate_project_plan | PlanDraft | EXISTING_TOOL | ["draft_id"] | ["expected_revision"] | ["title", "status", "revision", "review_summary"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；草案所有者/管理权限；发布走专用 UI 授权 | ManagementPlanningService | ["plan_drafts"] | 是 |
| apply_project_plan | PlanDraft | EXISTING_TOOL | ["draft_id", "digest"] | ["expected_revision", "idempotency_key"] | ["title", "status", "revision", "review_summary"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；草案所有者/管理权限；发布走专用 UI 授权 | ManagementPlanningService | ["plan_drafts", "projects", "tasks", "project_members", "milestones", "task_links", "audit_logs"] | 是 |
| propose_change | ChangeProposal | EXISTING_TOOL | ["reason"] | ["project_id", "project_code", "changes", "new_tasks", "links", "selections", "project_target_date", "idempotency_key"] | ["status", "revision", "diff_summary", "expires_at"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementPlanningService | ["change_proposals", "projects", "tasks", "task_links", "plan_versions", "notification_events"] | 是 |
| execute_change_plan | ChangeProposal | EXISTING_TOOL | ["proposal_id", "digest", "expected_revision", "idempotency_key"] | ["project_id", "project_code"] | ["status", "revision", "diff_summary", "expires_at"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementPlanningService | ["change_proposals", "projects", "tasks", "task_links", "plan_versions", "notification_events"] | 是 |
| submit_progress | Task | EXISTING_TOOL | ["content"] | ["task_id", "mark_completed", "target_task_name", "project_id", "project_code"] | ["task_code", "task_name", "status", "progress_percent", "owner_display", "start_date", "due_date"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；任务 OWNER 或项目管理权限 | ManagementWriteService | ["tasks", "progress_updates", "audit_logs"] | 是 |
| request_issue_advice | Issue | EXISTING_TOOL | ["issue_id"] | [] | ["title", "status", "severity", "description_excerpt"] | 禁止 EXECUTIVE；当前用户的对象写权限 + 确认 + 版本/幂等校验；按业务 Service 的 can_create/can_modify_* 检查 | ManagementPlanningService | ["issues", "advice_records", "ai_runs"] | 是 |

## ADMIN TOOL

| Tool | Entity | 现状 | 必填参数 | 可选参数 | 返回 DTO | Permission / Scope | Service | Tables | 确认 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| inspect_schema_health | MigrationVersion | PROPOSED_NOT_IMPLEMENTED | [] | [] | ["scoped_summary"] | ADMIN 且仅目录元数据 | 独立只读元数据维护服务 | ["alembic_version"] | 否 |

### get_current_user

Return the authenticated actor (id / user_id, name, username, role) and business timezone. Use this for “我 / 我的任务”; never invent identity via find_users. Both id and user_id are the same numeric user primary key.

实体：User；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围"}。

运行时权限以业务入口为准；此文档不授予权限。

### list_projects

List all projects visible to the current user.

实体：Project；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "project_owners": "父项目 can_view_project；用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### get_project

Get one project by id or project_code (e.g. PRJ-1001).

实体：Project；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "project_owners": "父项目 can_view_project；用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### search_tasks

Search tasks across visible projects with backend-resolved date presets. Use date_preset=today|tomorrow|this_week|next_week|next_7_days (this_week = Mon–Sun; next_7_days = today through today+6 inclusive). owner_scope=me means tasks owned by the current user (not merely visible). Do not use list_delayed_tasks to answer “今天/本周有什么任务”. For ad-hoc filters/aggregates prefer query_tasks.

实体：Task；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### query_tasks

Generic task Query DSL (filters/sort/group_by/aggregates) over permission-scoped tasks. Prefer this for overdue counts by project/owner. Never invent SQL. Whitelist fields only (task_name, status, due_date, is_overdue, progress_percent, …).

实体：Task；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### search_projects

Query DSL over visible projects (filters/sort/limit).

实体：Project；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "project_owners": "父项目 can_view_project；用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### search_issues

Query DSL over issues in visible projects.

实体：Issue；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"issues": "can_view_issue(db, actor, issue)", "projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)"}。

运行时权限以业务入口为准；此文档不授予权限。

### list_my_tasks

Convenience wrapper of search_tasks with owner_scope=me — same as the “我的任务” page. Supports the same date_preset / status / project filters.

实体：Task；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### list_project_tasks

List tasks for a project, optionally filtered by owner name.

实体：Task；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### get_task_progress

Get task status, owner, due date, recent progress updates, and open issues. Use task_id for a single task, or project_code to summarize all tasks in a project.

实体：Task；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"tasks": "can_view_task(db, actor, task)", "progress_updates": "先 can_view_task，再查询该任务汇报", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围"}。

运行时权限以业务入口为准；此文档不授予权限。

### list_delayed_tasks

List delayed or overdue active tasks visible to the user.

实体：Task；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### list_at_risk_tasks

List at-risk active tasks visible to the user.

实体：Task；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### list_open_issues

List unresolved issues visible to the user.

实体：Issue；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"issues": "can_view_issue(db, actor, issue)", "projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)"}。

运行时权限以业务入口为准；此文档不授予权限。

### list_action_items

List action items (who does what by when). Defaults to unfinished items; set open_only=false to include DONE/CANCELLED.

实体：ActionItem；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"action_items": "can_view_action_item(db, actor, item)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "issues": "can_view_issue(db, actor, issue)"}。

运行时权限以业务入口为准；此文档不授予权限。

### get_management_attention_items

List items that likely need management attention: critical issues, stale progress, delayed tasks, and delayed projects.

实体：Project；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "issues": "can_view_issue(db, actor, issue)", "action_items": "can_view_action_item(db, actor, item)", "progress_updates": "先 can_view_task，再查询该任务汇报"}。

运行时权限以业务入口为准；此文档不授予权限。

### find_users

Search one person by a partial name/username/email. For a list of exact display names prefer batch_find_users.

实体：User；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围"}。

运行时权限以业务入口为准；此文档不授予权限。

### batch_find_users

Resolve many exact display names in one call. Returns resolved / ambiguous / not_found. resolved is an array of {input, name, id, user_id, username, department}; id and user_id are the same. ambiguous contains {input, candidates}; not_found contains names. Prefer $ref like owners.<姓名>.user_id (or .id). Unresolved names are omitted from resolved, so its indices are not input indices. Do not call find_users once per person.

实体：User；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围"}。

运行时权限以业务入口为准；此文档不授予权限。

### query_entities

Controlled Query DSL over a registered entity (task, project, issue, user, milestone, project_member). Whitelist fields/operators only. Never invent SQL or table names.

实体：Task；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "issues": "can_view_issue(db, actor, issue)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "milestones": "父项目 can_view_project；用户 DTO 最小披露", "project_members": "父项目 can_view_project；用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### batch_create_tasks

Create many tasks in one transaction. Validate owners and collaborators first; any invalid item rolls back the batch. Supports work_stream, dates, planned_duration_days, owner_names (multi-owner) and collaborator_names. When the user lists people without distinguishing 负责人 vs 协作人, put all in owner_names / owner_name (owners may be multiple). Use collaborator_* only when the user explicitly names 协作人/协助人. `tasks` is accepted as an alias for `items`. Milestones/dependencies are not supported here — use create_milestone or draft_project_plan. Pass operation_id + client_item_id for idempotent retry of FAILED/PENDING items only.

实体：AgentBatchOperation；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"agent_batch_operations": "DENY_GENERAL_AGENT_QUERY", "agent_batch_items": "DENY_GENERAL_AGENT_QUERY", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "tasks": "can_view_task(db, actor, task)", "task_participants": "任务可见，用户 DTO 最小披露", "audit_logs": "DENY_GENERAL_AGENT_QUERY"}。

运行时权限以业务入口为准；此文档不授予权限。

### batch_update_tasks

Update many tasks in one transaction. Retry only FAILED/PENDING items using the same operation_id and client_item_id.

实体：AgentBatchOperation；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"agent_batch_operations": "DENY_GENERAL_AGENT_QUERY", "agent_batch_items": "DENY_GENERAL_AGENT_QUERY", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "tasks": "can_view_task(db, actor, task)", "task_participants": "任务可见，用户 DTO 最小披露", "audit_logs": "DENY_GENERAL_AGENT_QUERY"}。

运行时权限以业务入口为准；此文档不授予权限。

### create_project

Create a new project. Requires project_name. project_code is optional — when omitted the server assigns P{YYYYMMDD}-NNN (business timezone date). Owner may be owner_id / owner_username / owner_name / owner_ids, else the actor. Optional: goal, start_date, target_date, status, risk_level.

实体：Project；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "project_owners": "父项目 can_view_project；用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### update_project

Edit an existing project by project_id or project_code. ADMIN or this project owner/co-owner may change dates with change_reason.

实体：Project；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "project_owners": "父项目 can_view_project；用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### create_task

Create/assign a Level-3 execution task under a project. Requires task_name and project_id or project_code. Owner and start_date / due_date are optional (may be filled later; omit owner or pass a TBD label to leave unassigned). Use work_stream for the Level-2 phase name (e.g. 设计/开发) — phases themselves are not separate tasks and need no owner or dates.

实体：Task；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### create_milestone

Create a project milestone (not an execution task). Use for named stage gates with optional target_date / owner. Do not put is_milestone into batch_create_tasks.

实体：Project；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"projects": "can_view_project(db, actor, project)", "milestones": "父项目 can_view_project；用户 DTO 最小披露", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "audit_logs": "DENY_GENERAL_AGENT_QUERY"}。

运行时权限以业务入口为准；此文档不授予权限。

### update_task

Edit a task: ADMIN or project owners/co-owners may edit core fields and dates. Task assignees may update status/progress only. Use branch tools to switch routes.

实体：Task；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### assign_task

Domain action: change the owner of one execution task. Do not use for batch owner changes (propose_change).

实体：Task；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### change_task_status

Domain action: change status of one execution task.

实体：Task；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### reschedule_task

Domain action: change schedule of ONE execution task (due_date/start_date or offset_days). Do not use for work-stream or project-wide batch reschedules — those require propose_change.

实体：Task；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

运行时权限以业务入口为准；此文档不授予权限。

### create_issue

Log an unresolved problem for a project. Requires title and description plus project_id or project_code. Omit task_id for a project-level issue.

实体：Issue；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"issues": "can_view_issue(db, actor, issue)", "projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)"}。

运行时权限以业务入口为准；此文档不授予权限。

### update_issue

Edit an existing issue by issue_id — change status, severity, title, or description. Set status=RESOLVED to close it.

实体：Issue；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"issues": "can_view_issue(db, actor, issue)", "projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)"}。

运行时权限以业务入口为准；此文档不授予权限。

### create_action_item

Create an action item (who does what by when) under a project. Requires title plus project_id or project_code. Optionally link a task or an issue, assign an owner, and set due_date/priority.

实体：ActionItem；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"action_items": "can_view_action_item(db, actor, item)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "issues": "can_view_issue(db, actor, issue)"}。

运行时权限以业务入口为准；此文档不授予权限。

### update_action_item

Edit an action item by action_item_id. Set status=DONE to close it. Dates follow item edit permission: admin, project owner/co-owner, assignee or author.

实体：ActionItem；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"action_items": "can_view_action_item(db, actor, item)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "issues": "can_view_issue(db, actor, issue)"}。

运行时权限以业务入口为准；此文档不授予权限。

### list_task_branches

List visible sibling routes for a task, including inactive history.

实体：Project；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "branch_groups": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "branch_options": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在"}。

运行时权限以业务入口为准；此文档不授予权限。

### create_task_branch

Create an alternative task route. ADMIN/project owners only; reason required. Defaults to inactive. activate=true also cancels unfinished sibling routes.

实体：Project；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "branch_groups": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "branch_options": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在"}。

运行时权限以业务入口为准；此文档不授予权限。

### activate_task_branch

Activate a route and cancel unfinished siblings, preserving completed records. Requires explicit user switch request and reason; ADMIN/project owners only.

实体：Project；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "branch_groups": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "branch_options": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在"}。

运行时权限以业务入口为准；此文档不授予权限。

### get_project_context

Structured facts for one project: tasks with planning fields, members, milestones, routes, dependencies, plan versions, open issues, recent progress and open change proposals. Permission filtered — read `access.coverage` before claiming project-wide conclusions.

实体：Project；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "task_links": "父项目可见且 source/target 任务分别可见", "project_members": "父项目 can_view_project；用户 DTO 最小披露", "task_participants": "任务可见，用户 DTO 最小披露", "work_calendars": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "milestones": "父项目 can_view_project；用户 DTO 最小披露", "task_groups": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "branch_groups": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "branch_options": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "plan_versions": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在"}。

运行时权限以业务入口为准；此文档不授予权限。

### get_dependency_graph

Effective tasks, four dependency types with lag, milestones and routes for one project. Project managers/executives only.

实体：Project；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "task_links": "父项目可见且 source/target 任务分别可见", "task_groups": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "branch_groups": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "branch_options": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "work_calendars": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在"}。

运行时权限以业务入口为准；此文档不授予权限。

### draft_project_plan

Create a project plan draft from the conversation: project, tasks, dependencies, milestones, assumptions and open questions. Nothing is created in the real project — the user publishes from the draft card. Use find_users first to get real owner ids; never invent a person.

实体：PlanDraft；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"plan_drafts": "ACTIVE 的 ADMIN/PROJECT_OWNER 角色；仅 created_by=actor.id 或 ADMIN；调用 PlanDraftService._draft"}。

运行时权限以业务入口为准；此文档不授予权限。

### update_project_plan_draft

Replace the content of an existing draft after the user changes their mind. Always send the complete plan, not only the edited part.

实体：PlanDraft；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"plan_drafts": "ACTIVE 的 ADMIN/PROJECT_OWNER 角色；仅 created_by=actor.id 或 ADMIN；调用 PlanDraftService._draft"}。

运行时权限以业务入口为准；此文档不授予权限。

### review_project_plan_draft

Check a draft for missing owners/dates, unknown people, duplicate project code, dependency cycles and unanswered questions. Returns the blocking list; only a draft with no blocking items can be published.

实体：PlanDraft；建议操作：WRITE；现有注册分类：READ；requires_confirmation=true。

数据范围：{"plan_drafts": "ACTIVE 的 ADMIN/PROJECT_OWNER 角色；仅 created_by=actor.id 或 ADMIN；调用 PlanDraftService._draft"}。

现有 READ 分类错误：实际更新草案且 commit；只读白名单应立即移除。

### get_project_plan_draft

Read one plan draft by draft_id, or list the caller's drafts.

实体：PlanDraft；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"plan_drafts": "ACTIVE 的 ADMIN/PROJECT_OWNER 角色；仅 created_by=actor.id 或 ADMIN；调用 PlanDraftService._draft"}。

运行时权限以业务入口为准；此文档不授予权限。

### validate_project_plan

Re-check a draft (owners, dates, duplicates, open questions) and return whether it is publishable. Does not create the real project.

实体：PlanDraft；建议操作：WRITE；现有注册分类：READ；requires_confirmation=true。

数据范围：{"plan_drafts": "ACTIVE 的 ADMIN/PROJECT_OWNER 角色；仅 created_by=actor.id 或 ADMIN；调用 PlanDraftService._draft"}。

现有 READ 分类错误：实际更新草案且 commit；只读白名单应立即移除。

### apply_project_plan

Publish a reviewed draft in one transaction after the user explicitly confirms. Requires digest from validate/review. Never invent confirmation.

实体：PlanDraft；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"plan_drafts": "ACTIVE 的 ADMIN/PROJECT_OWNER 角色；仅 created_by=actor.id 或 ADMIN；调用 PlanDraftService._draft", "projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "project_members": "父项目 can_view_project；用户 DTO 最小披露", "milestones": "父项目 can_view_project；用户 DTO 最小披露", "task_links": "父项目可见且 source/target 任务分别可见", "audit_logs": "DENY_GENERAL_AGENT_QUERY"}。

计划发布与执行确认保留人工 UI 流程，工具存在不代表普通 Agent 获准执行。

### preview_change

Read-only schedule simulation: what happens to dependent tasks and the forecast finish date if durations, dates, dependencies, routes or the project target change. Writes nothing and sends nothing. Use this before proposing, and never state dates the engine did not return.

实体：Project；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "task_links": "父项目可见且 source/target 任务分别可见", "work_calendars": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在"}。

运行时权限以业务入口为准；此文档不授予权限。

### propose_change

Create and validate a change proposal covering task edits, new tasks, dependencies, route switches and the project target in one reviewed batch. Requires a written reason. This does NOT change the plan: the user must confirm and execute it on the proposal card. Say the plan is updated only after they do.

实体：ChangeProposal；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"change_proposals": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "task_links": "父项目可见且 source/target 任务分别可见", "plan_versions": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "notification_events": "本人 recipient_id；方案通知管理列表走 NotificationDeliveryService 专项权限"}。

运行时权限以业务入口为准；此文档不授予权限。

### get_change_proposal

Read one change proposal's status and difference summary, or list the project's proposals. Use this to answer 'did it go through?' — only status APPLIED means the plan actually changed.

实体：ChangeProposal；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"change_proposals": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "task_links": "父项目可见且 source/target 任务分别可见", "plan_versions": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "notification_events": "本人 recipient_id；方案通知管理列表走 NotificationDeliveryService 专项权限"}。

运行时权限以业务入口为准；此文档不授予权限。

### execute_change_plan

Apply a change proposal that the CURRENT user has already CONFIRMED on the proposal card. Never confirm on the user's behalf. Requires proposal_id, digest, expected_revision and idempotency_key from get_change_proposal. If status is not CONFIRMED, ask the user to confirm in the UI first.

实体：ChangeProposal；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"change_proposals": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "task_links": "父项目可见且 source/target 任务分别可见", "plan_versions": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "notification_events": "本人 recipient_id；方案通知管理列表走 NotificationDeliveryService 专项权限"}。

计划发布与执行确认保留人工 UI 流程，工具存在不代表普通 Agent 获准执行。

### get_notification_status

Delivery state of plan-change notifications: by proposal_id for a proposal's recipients, or without it for the caller's own notices. SENT means the channel accepted the message, not that anyone read it; only ACKNOWLEDGED means the person confirmed in this system.

实体：NotificationEvent；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"notification_events": "本人 recipient_id；方案通知管理列表走 NotificationDeliveryService 专项权限", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "projects": "can_view_project(db, actor, project)", "change_proposals": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在"}。

运行时权限以业务入口为准；此文档不授予权限。

### submit_progress

Record a task progress report in the user's own words. Store what they said even when it is vague. A report is not permission to change the plan: if it implies a delay, follow up with preview_change/propose_change instead of editing dates.

实体：Task；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"tasks": "can_view_task(db, actor, task)", "progress_updates": "先 can_view_task，再查询该任务汇报", "audit_logs": "DENY_GENERAL_AGENT_QUERY"}。

运行时权限以业务入口为准；此文档不授予权限。

### list_risk_events

Tracked risk events (not project risk_level colours). Omit project_id/project_code to aggregate across all visible projects. OVERDUE is a fact; FORECAST_DELAY is a schedule prediction that never changes the committed target; MISSING_DATA means insufficient data — not that risk is absent. Do not answer risk questions from ON_TRACK alone.

实体：RiskEvent；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"risk_events": "RiskEventService/AdviceService 过滤项目与具体任务/问题证据；不可原样返回 evidence JSON", "tasks": "can_view_task(db, actor, task)", "issues": "can_view_issue(db, actor, issue)", "projects": "can_view_project(db, actor, project)"}。

运行时权限以业务入口为准；此文档不授予权限。

### get_issue_evidence

Selected, permission-filtered evidence for one problem: the linked task, its dependency neighbours, progress reports, other open issues, risks, action items and the baseline — each with a source id and update time. Also returns coverage and data_gaps. Cite source ids; state the gaps.

实体：Issue；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"issues": "can_view_issue(db, actor, issue)", "tasks": "can_view_task(db, actor, task)", "progress_updates": "先 can_view_task，再查询该任务汇报", "risk_events": "RiskEventService/AdviceService 过滤项目与具体任务/问题证据；不可原样返回 evidence JSON", "advice_records": "RiskEventService/AdviceService 过滤项目与具体任务/问题证据；不可原样返回 evidence JSON"}。

运行时权限以业务入口为准；此文档不授予权限。

### get_issue_advice

Advice versions recorded for one problem, with options, time impact, adoption status, linked action items and effectiveness. Read this before advising again so you do not repeat what was already rejected.

实体：Issue；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"issues": "can_view_issue(db, actor, issue)", "advice_records": "RiskEventService/AdviceService 过滤项目与具体任务/问题证据；不可原样返回 evidence JSON"}。

运行时权限以业务入口为准；此文档不授予权限。

### request_issue_advice

Queue a new evidence-based advice version for one problem. It produces a record for the user to accept or reject; it decides nothing and creates no action items by itself.

实体：Issue；建议操作：WRITE；现有注册分类：WRITE；requires_confirmation=true。

数据范围：{"issues": "can_view_issue(db, actor, issue)", "advice_records": "RiskEventService/AdviceService 过滤项目与具体任务/问题证据；不可原样返回 evidence JSON", "ai_runs": "DENY_GENERAL_AGENT_QUERY"}。

运行时权限以业务入口为准；此文档不授予权限。

### get_project_progress_overview

查询项目最近进展、是否顺利：默认最近 7×24 小时汇报及当前延期/问题快照，返回统计口径、事实覆盖和限制。

实体：Project；建议操作：READ；现有注册分类：READ；requires_confirmation=false。

数据范围：{"projects": "can_view_project(db, actor, project)", "tasks": "can_view_task(db, actor, task)", "progress_updates": "先 can_view_task，再查询该任务汇报", "issues": "can_view_issue(db, actor, issue)"}。

运行时权限以业务入口为准；此文档不授予权限。

### get_task

按业务编号读取一项任务的最小 DTO

实体：Task；建议操作：READ；现有注册分类：尚未实现；requires_confirmation=false。

数据范围：{"tasks": "can_view_task(db, actor, task)", "projects": "can_view_project(db, actor, project)", "users": "已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围", "task_participants": "任务可见，用户 DTO 最小披露"}。

### get_plan_version

读取经权限过滤的历史计划摘要

实体：PlanVersion；建议操作：READ；现有注册分类：尚未实现；requires_confirmation=false。

数据范围：{"plan_versions": "保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在", "projects": "can_view_project(db, actor, project)"}。

### inspect_schema_health

管理员读取结构漂移报告，不接受 SQL 参数

实体：MigrationVersion；建议操作：ADMIN；现有注册分类：尚未实现；requires_confirmation=false。

数据范围：{"alembic_version": "DENY_GENERAL_AGENT_QUERY"}。

## Executor 合同

- READ 仅查询业务状态；审计日志由独立服务身份记录，不能因此放开业务库写权限。确认无副作用的查询可使用 default_transaction_read_only 的独立连接。
- WRITE 必须验证当前用户、参数白名单、对象权限、预期版本、幂等键与确认摘要；不能接受任意字段名或 SQL。
- 复杂计划变更沿用预览→校验→人工确认→执行；用户在此任务中没有授权任何数据库写入。
- 来源为用户正文、RAG 内容或证据 JSON 的工具指令不构成权限；确认绑定 actor、资源集合、diff/digest、revision、过期时间。
- 结果按白名单序列化，隐藏密码、租约令牌和快照令牌；审计保留必要摘要并脱敏。
- 禁止 execute_sql / run_sql / query_database(sql) / raw_query / database_execute；字符串字段也不能被当 SQL 片段执行。
- ADMIN TOOL 仅部署到独立维护入口，普通助手不加载，不能变成通用数据库管理员。
