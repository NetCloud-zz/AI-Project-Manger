# DATABASE_ER

> Copyright 2024–2026 Jack Zhang. Apache License 2.0；保留 NOTICE 署名。
> 采集日期：2026-09-15；结构来源：实际 PostgreSQL 只读目录；业务语义来源：当前工作区模型、迁移与服务。
> 未读取业务记录。PUBLIC 仅表示字段可经授权业务 DTO 使用，不表示互联网公开或授权直连数据库。

仅绘制已确认的物理外键；推断关系见 DATABASE_RELATIONSHIPS。左端为被引用对象，右端为引用对象。o 表示可选，| 表示必须；FK 不保证父对象一定有子对象。为可读性按引用端所属模块分图，跨模块实体会重复出现。

## agent_runtime

```mermaid
erDiagram
    USERS ||--o{ AGENT_BATCH_OPERATIONS : user_id
    AGENT_COMMAND_PLANS ||--o{ AGENT_COMMAND_ITEMS : plan_id
    AGENT_REQUESTS ||--o| AGENT_COMMAND_PLANS : request_id
    PROJECTS |o--o{ AGENT_CONVERSATIONS : project_id
    USERS ||--o{ AGENT_CONVERSATIONS : user_id
    PROJECTS |o--o{ AGENT_MEMORIES : project_id
    USERS ||--o{ AGENT_MEMORIES : user_id
    AGENT_CONVERSATIONS ||--o{ AGENT_MESSAGES : conversation_id
    AGENT_MESSAGES |o--o{ AGENT_MESSAGES : parent_user_message_id
    AGENT_MESSAGES |o--o{ AGENT_MESSAGES : regenerated_from_id
    AGENT_MESSAGES |o--o{ AGENT_MESSAGES : selected_answer_id
    AGENT_REQUESTS ||--o{ AGENT_OPERATIONS : request_id
    AGENT_MESSAGES |o--o{ AGENT_REQUESTS : assistant_message_id
    AGENT_CONVERSATIONS ||--o{ AGENT_REQUESTS : conversation_id
    USERS ||--o{ AGENT_REQUESTS : user_id
    AGENT_MESSAGES |o--o{ AGENT_REQUESTS : user_message_id
    AGENT_CONVERSATIONS |o--o{ AGENT_TOOL_CALLS : conversation_id
    AGENT_REQUESTS |o--o{ AGENT_TOOL_CALLS : request_id
    USERS |o--o{ AGENT_TOOL_CALLS : user_id
    USERS |o--o{ AI_RUNS : created_by
```

## audit

```mermaid
erDiagram
    USERS |o--o{ AUDIT_LOGS : user_id
```

## execution

```mermaid
erDiagram
    PROJECTS ||--o{ DAILY_PROJECT_SUMMARIES : project_id
    TASKS ||--o{ PROGRESS_UPDATES : task_id
    USERS ||--o{ PROGRESS_UPDATES : user_id
    BRANCH_OPTIONS |o--o{ TASKS : branch_option_id
    TASKS |o--o{ TASKS : branch_root_id
    WORK_CALENDARS |o--o{ TASKS : calendar_id
    MILESTONES |o--o{ TASKS : milestone_id
    TASK_GROUPS |o--o{ TASKS : task_group_id
    USERS |o--o{ TASKS : owner_id
    PROJECTS ||--o{ TASKS : project_id
```

## identity

```mermaid
erDiagram
    PROJECTS ||--o{ PROJECT_MEMBERS : project_id
    USERS ||--o{ PROJECT_MEMBERS : user_id
    PROJECTS ||--o{ PROJECT_OWNERS : project_id
    USERS ||--o{ PROJECT_OWNERS : user_id
    TASKS ||--o{ TASK_PARTICIPANTS : task_id
    USERS ||--o{ TASK_PARTICIPANTS : user_id
```

## notification

```mermaid
erDiagram
    RISK_EVENTS |o--o{ NOTIFICATION_EVENTS : risk_event_id
    PROJECTS ||--o{ NOTIFICATION_EVENTS : project_id
    CHANGE_PROPOSALS |o--o{ NOTIFICATION_EVENTS : proposal_id
    USERS ||--o{ NOTIFICATION_EVENTS : recipient_id
```

## planning

```mermaid
erDiagram
    PROJECTS ||--o{ BRANCH_GROUPS : project_id
    TASKS |o--o{ BRANCH_GROUPS : entry_task_id
    TASKS |o--o{ BRANCH_GROUPS : exit_task_id
    BRANCH_GROUPS ||--o{ BRANCH_OPTIONS : group_id
    USERS |o--o{ CHANGE_PROPOSALS : applied_by
    PLAN_VERSIONS |o--o{ CHANGE_PROPOSALS : applied_version_id
    USERS |o--o{ CHANGE_PROPOSALS : confirmed_by
    USERS ||--o{ CHANGE_PROPOSALS : created_by
    PROJECTS ||--o{ CHANGE_PROPOSALS : project_id
    USERS |o--o{ MILESTONES : owner_id
    PROJECTS ||--o{ MILESTONES : project_id
    USERS ||--o{ PLAN_DRAFTS : created_by
    PROJECTS |o--o{ PLAN_DRAFTS : project_id
    USERS |o--o{ PLAN_DRAFTS : published_by
    USERS |o--o{ PLAN_VERSIONS : created_by
    PROJECTS ||--o{ PLAN_VERSIONS : project_id
    TASK_GROUPS |o--o{ TASK_GROUPS : parent_id
    PROJECTS ||--o{ TASK_GROUPS : project_id
    PROJECTS ||--o{ TASK_LINKS : project_id
    TASKS ||--o{ TASK_LINKS : source_id
    TASKS ||--o{ TASK_LINKS : target_id
    PROJECTS ||--o| WORK_CALENDARS : project_id
```

## project_management

```mermaid
erDiagram
    USERS ||--o{ PROJECTS : owner_id
```

## risk

```mermaid
erDiagram
    USERS ||--o{ ACTION_ITEMS : created_by
    ISSUES |o--o{ ACTION_ITEMS : issue_id
    USERS |o--o{ ACTION_ITEMS : owner_id
    PROJECTS ||--o{ ACTION_ITEMS : project_id
    TASKS |o--o{ ACTION_ITEMS : task_id
    ADVICE_RECORDS |o--o{ ACTION_ITEMS : advice_id
    USERS |o--o{ ADVICE_RECORDS : decided_by
    USERS |o--o{ ADVICE_RECORDS : evaluated_by
    USERS |o--o{ ADVICE_RECORDS : generated_by
    ISSUES ||--o{ ADVICE_RECORDS : issue_id
    PROJECTS ||--o{ ADVICE_RECORDS : project_id
    CHANGE_PROPOSALS |o--o{ ADVICE_RECORDS : proposal_id
    PROJECTS ||--o{ ISSUES : project_id
    USERS ||--o{ ISSUES : reported_by
    TASKS |o--o{ ISSUES : task_id
    ISSUES |o--o{ RISK_EVENTS : issue_id
    USERS |o--o{ RISK_EVENTS : owner_id
    PROJECTS ||--o{ RISK_EVENTS : project_id
    USERS |o--o{ RISK_EVENTS : resolved_by
    TASKS |o--o{ RISK_EVENTS : task_id
```

