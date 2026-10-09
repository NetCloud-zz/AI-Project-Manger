# DATABASE_DICTIONARY

> Copyright 2024–2026 Jack Zhang. Apache License 2.0；保留 NOTICE 署名。
> 采集日期：2026-09-15；结构来源：实际 PostgreSQL 只读目录；业务语义来源：当前工作区模型、迁移与服务。
> 未读取业务记录。PUBLIC 仅表示字段可经授权业务 DTO 使用，不表示互联网公开或授权直连数据库。

完整覆盖 35 张表（含迁移版本表）。数据库列类型、NULL、默认值、PK/FK/索引取自实际目录；应用默认值另列，不等于数据库默认值。无 COMMENT 记为 —，不是自行补写的数据库注释。示例仅合成项目编号；没有数据样本。

可见性：PUBLIC＝授权业务字段；INTERNAL＝内部标识/实现细节；SENSITIVE＝个人信息或未经投影的自由文本/JSON；HIDDEN＝任何 Agent 查询都禁止。

## public.action_items · 行动项 / ActionItem

模块：`risk`。用途：有负责人和期限的跟进事项，可关联问题、任务及建议。粒度：一条记录代表有负责人和期限的跟进事项，可关联问题、任务及建议。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/action_item.py:37`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('action_items_id_seq'::regclass) | — | 是 | 是 | [] | ["action_items_pkey"] | — | 行动项：记录主键，内部定位使用 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_action_items_project_id"] | — | 行动项：所属或关联项目的内部标识 | INTERNAL |
| task_id | integer | 是 | — | — | 否 | 否 | ["public.tasks.id"] | ["ix_action_items_task_id"] | — | 行动项：关联执行任务标识 | INTERNAL |
| issue_id | integer | 是 | — | — | 否 | 否 | ["public.issues.id"] | ["ix_action_items_issue_id"] | — | 行动项：关联问题标识 | INTERNAL |
| owner_id | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | ["ix_action_items_owner_id"] | — | 行动项：业务主负责人用户标识（不是创建人） | INTERNAL |
| created_by | integer | 否 | — | — | 否 | 否 | ["public.users.id"] | ["ix_action_items_created_by"] | — | 行动项：创建人用户标识 | INTERNAL |
| title | character varying(300) | 否 | — | — | 否 | 否 | [] | [] | — | 行动项：该业务对象的标题 | PUBLIC |
| description | text | 是 | — | — | 否 | 否 | [] | [] | — | 行动项：业务描述原文 | SENSITIVE |
| due_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 行动项：任务或行动项计划截止日期 | PUBLIC |
| status | character varying(16) | 否 | — | OPEN | 否 | 否 | [] | [] | — | 行动项：该对象状态；必须使用本表状态字典 | PUBLIC |
| priority | character varying(16) | 否 | — | MEDIUM | 否 | 否 | [] | [] | — | 行动项：行动项优先级 | PUBLIC |
| completed_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 行动项：对象完成事件时间，具体为任务完成或请求/消息/作业结束 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 行动项：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 行动项：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |
| advice_id | integer | 是 | — | — | 否 | 否 | ["public.advice_records.id"] | ["ix_action_items_advice_id"] | — | 行动项：产生该行动的建议版本标识 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| task_id | 否 | 否 | 否 | [] | 是 | [] | — |
| issue_id | 否 | 否 | 否 | [] | 是 | [] | — |
| owner_id | 否 | 否 | 否 | [] | 是 | [] | — |
| created_by | 否 | 否 | 否 | [] | 否 | [] | — |
| title | 是 | 是 | 是 | [] | 否 | [] | — |
| description | 否 | 否 | 否 | [] | 否 | [] | — |
| due_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"] | — |
| priority | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["LOW", "MEDIUM", "HIGH", "URGENT"] | — |
| completed_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| advice_id | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| action_items_created_by_fkey | f | FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT |
| action_items_issue_id_fkey | f | FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE SET NULL |
| action_items_owner_id_fkey | f | FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT |
| action_items_pkey | p | PRIMARY KEY (id) |
| action_items_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| action_items_task_id_fkey | f | FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL |
| fk_action_items_advice_id | f | FOREIGN KEY (advice_id) REFERENCES advice_records(id) ON DELETE SET NULL |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| action_items_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_action_items_advice_id | btree | 否 | 否 | ["advice_id"] | — | 是 |
| ix_action_items_created_by | btree | 否 | 否 | ["created_by"] | — | 是 |
| ix_action_items_issue_id | btree | 否 | 否 | ["issue_id"] | — | 是 |
| ix_action_items_owner_id | btree | 否 | 否 | ["owner_id"] | — | 是 |
| ix_action_items_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| ix_action_items_task_id | btree | 否 | 否 | ["task_id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：can_view_action_item(db, actor, item)。禁止直接修改。

## public.advice_records · 建议版本 / AdviceRecord

模块：`risk`。用途：一个问题的一版建议及证据、采纳决定和效果评价。粒度：一条记录代表一个问题的一版建议及证据、采纳决定和效果评价。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/advice_record.py:50`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('advice_records_id_seq'::regclass) | — | 是 | 是 | [] | ["advice_records_pkey"] | — | 建议版本：记录主键，内部定位使用 | INTERNAL |
| issue_id | integer | 否 | — | — | 否 | 否 | ["public.issues.id"] | ["ix_advice_records_issue_id", "ix_advice_records_issue_status", "uq_advice_version"] | — | 建议版本：关联问题标识 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_advice_records_project_id"] | — | 建议版本：所属或关联项目的内部标识 | INTERNAL |
| version | integer | 否 | 1 | 1 | 否 | 否 | [] | ["uq_advice_version"] | — | 建议版本：版本计数，具体为任务并发版本、项目计划版本或日历版本 | INTERNAL |
| status | character varying(16) | 否 | 'PROPOSED'::character varying | PROPOSED | 否 | 否 | [] | ["ix_advice_records_issue_status", "ix_advice_records_status"] | — | 建议版本：该对象状态；必须使用本表状态字典 | PUBLIC |
| content | json | 否 | — | — | 否 | 否 | [] | [] | — | 建议版本：建议结构化内容（原因、方案、影响和信息缺口） | SENSITIVE |
| evidence | json | 是 | — | APPLICATION_CALLABLE:list | 否 | 否 | [] | [] | — | 建议版本：证据引用列表，含 source_type/source_id，需逐资源授权 | SENSITIVE |
| coverage | json | 是 | — | — | 否 | 否 | [] | [] | — | 建议版本：建议证据覆盖面及缺失信息 | SENSITIVE |
| context_digest | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 建议版本：生成建议时上下文指纹，用于发现过期证据 | INTERNAL |
| model | character varying(120) | 是 | — | — | 否 | 否 | [] | [] | — | 建议版本：生成或分析所用模型标识 | INTERNAL |
| generated_by | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 建议版本：建议生成请求人用户标识 | INTERNAL |
| decided_by | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 建议版本：建议采纳或拒绝的决定人 | INTERNAL |
| decided_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 建议版本：建议决策时间 | PUBLIC |
| decision_note | text | 是 | — | — | 否 | 否 | [] | [] | — | 建议版本：采纳或拒绝原因 | PUBLIC |
| proposal_id | character varying(36) | 是 | — | — | 否 | 否 | ["public.change_proposals.id"] | [] | — | 建议版本：关联计划变更方案标识（字符串主键） | INTERNAL |
| outcome | character varying(16) | 是 | — | — | 否 | 否 | [] | [] | — | 建议版本：建议效果枚举 | PUBLIC |
| issue_resolved | boolean | 是 | — | — | 否 | 否 | [] | [] | — | 建议版本：评价时记录的问题是否已解决，独立于建议效果 | PUBLIC |
| outcome_note | text | 是 | — | — | 否 | 否 | [] | [] | — | 建议版本：建议效果说明 | PUBLIC |
| evaluated_by | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 建议版本：建议效果评价人 | INTERNAL |
| evaluated_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 建议版本：建议效果评价时间 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 建议版本：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 建议版本：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| issue_id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| version | 否 | 否 | 否 | [] | 否 | [] | — |
| status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["PROPOSED", "ADOPTED", "REJECTED", "SUPERSEDED"] | — |
| content | 否 | 否 | 否 | [] | 否 | [] | — |
| evidence | 否 | 否 | 否 | [] | 否 | [] | — |
| coverage | 否 | 否 | 否 | [] | 否 | [] | — |
| context_digest | 否 | 否 | 否 | [] | 否 | [] | — |
| model | 否 | 否 | 否 | [] | 否 | [] | — |
| generated_by | 否 | 否 | 否 | [] | 否 | [] | — |
| decided_by | 否 | 否 | 否 | [] | 否 | [] | — |
| decided_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| decision_note | 是 | 否 | 否 | [] | 否 | [] | — |
| proposal_id | 否 | 否 | 否 | [] | 否 | [] | — |
| outcome | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["EFFECTIVE", "PARTIAL", "INEFFECTIVE"] | — |
| issue_resolved | 是 | 否 | 否 | [] | 否 | [] | — |
| outcome_note | 是 | 否 | 否 | [] | 否 | [] | — |
| evaluated_by | 否 | 否 | 否 | [] | 否 | [] | — |
| evaluated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| advice_records_decided_by_fkey | f | FOREIGN KEY (decided_by) REFERENCES users(id) ON DELETE SET NULL |
| advice_records_evaluated_by_fkey | f | FOREIGN KEY (evaluated_by) REFERENCES users(id) ON DELETE SET NULL |
| advice_records_generated_by_fkey | f | FOREIGN KEY (generated_by) REFERENCES users(id) ON DELETE SET NULL |
| advice_records_issue_id_fkey | f | FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE CASCADE |
| advice_records_pkey | p | PRIMARY KEY (id) |
| advice_records_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| advice_records_proposal_id_fkey | f | FOREIGN KEY (proposal_id) REFERENCES change_proposals(id) ON DELETE SET NULL |
| ck_advice_version | c | CHECK ((version >= 1)) |
| uq_advice_version | u | UNIQUE (issue_id, version) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| advice_records_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_advice_records_issue_id | btree | 否 | 否 | ["issue_id"] | — | 是 |
| ix_advice_records_issue_status | btree | 否 | 否 | ["issue_id", "status"] | — | 是 |
| ix_advice_records_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| ix_advice_records_status | btree | 否 | 否 | ["status"] | — | 是 |
| uq_advice_version | btree | 否 | 是 | ["issue_id", "version"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：RiskEventService/AdviceService 过滤项目与具体任务/问题证据；不可原样返回 evidence JSON。禁止直接修改。

## public.agent_batch_items · 批量操作条目 / AgentBatchItem

模块：`agent_runtime`。用途：批量操作中一个 client_item_id 对应的执行回执。粒度：一条记录代表批量操作中一个 client_item_id 对应的执行回执。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：144（非精确）。证据：`backend/app/models/agent_batch.py:31`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('agent_batch_items_id_seq'::regclass) | — | 是 | 是 | [] | ["agent_batch_items_pkey"] | — | 批量操作条目：记录主键，内部定位使用 | INTERNAL |
| operation_id | character varying(100) | 否 | — | — | 否 | 否 | [] | ["ix_agent_batch_items_operation", "uq_agent_batch_item"] | — | 批量操作条目：幂等操作标识，按表上下文区分批次和请求操作 | INTERNAL |
| client_item_id | character varying(80) | 否 | — | — | 否 | 否 | [] | ["uq_agent_batch_item"] | — | 批量操作条目：批次内客户端条目幂等键 | INTERNAL |
| status | character varying(16) | 否 | 'PENDING'::character varying | PENDING | 否 | 否 | [] | [] | — | 批量操作条目：该对象状态；必须使用本表状态字典 | INTERNAL |
| resource_id | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 批量操作条目：多态业务资源标识，必须结合资源类型或已验证工具类型 | INTERNAL |
| error_code | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 批量操作条目：结构化错误码 | INTERNAL |
| error_message | text | 是 | — | — | 否 | 否 | [] | [] | — | 批量操作条目：条目错误说明，可能含内部信息 | SENSITIVE |
| payload | jsonb | 是 | — | — | 否 | 否 | [] | [] | — | 批量操作条目：内部结构化载荷，必须经 DTO 白名单脱敏 | SENSITIVE |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 批量操作条目：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 批量操作条目：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| operation_id | 否 | 否 | 否 | [] | 否 | [] | — |
| client_item_id | 否 | 否 | 否 | [] | 否 | [] | — |
| status | 否 | 否 | 否 | [] | 否 | ["FAILED", "PENDING", "VALIDATION_FAILED"] | — |
| resource_id | 否 | 否 | 否 | [] | 否 | [] | — |
| error_code | 否 | 否 | 否 | [] | 否 | [] | — |
| error_message | 否 | 否 | 否 | [] | 否 | [] | — |
| payload | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |
| updated_at | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| agent_batch_items_pkey | p | PRIMARY KEY (id) |
| uq_agent_batch_item | u | UNIQUE (operation_id, client_item_id) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| agent_batch_items_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_agent_batch_items_operation | btree | 否 | 否 | ["operation_id"] | — | 是 |
| uq_agent_batch_item | btree | 否 | 是 | ["operation_id", "client_item_id"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.agent_batch_operations · 批量操作 / AgentBatchOperation

模块：`agent_runtime`。用途：某用户一次带幂等标识的批量工具调用。粒度：一条记录代表某用户一次带幂等标识的批量工具调用。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/agent_batch.py:18`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('agent_batch_operations_id_seq'::regclass) | — | 是 | 是 | [] | ["agent_batch_operations_pkey"] | — | 批量操作：记录主键，内部定位使用 | INTERNAL |
| operation_id | character varying(100) | 否 | — | — | 否 | 是 | [] | ["uq_agent_batch_operations_op"] | — | 批量操作：幂等操作标识，按表上下文区分批次和请求操作 | INTERNAL |
| user_id | integer | 否 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 批量操作：关联用户标识，具体角色见表用途 | INTERNAL |
| tool_name | character varying(100) | 否 | — | — | 否 | 否 | [] | [] | — | 批量操作：已注册结构化工具名 | INTERNAL |
| status | character varying(32) | 否 | 'PENDING'::character varying | PENDING | 否 | 否 | [] | [] | — | 批量操作：该对象状态；必须使用本表状态字典 | INTERNAL |
| expected_count | integer | 否 | 0 | 0 | 否 | 否 | [] | [] | — | 批量操作：预期条目数 | INTERNAL |
| details | jsonb | 是 | — | — | 否 | 否 | [] | [] | — | 批量操作：批量操作诊断载荷 | SENSITIVE |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 批量操作：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 批量操作：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| operation_id | 否 | 否 | 否 | [] | 否 | [] | — |
| user_id | 否 | 否 | 否 | [] | 是 | [] | — |
| tool_name | 否 | 否 | 否 | [] | 否 | [] | — |
| status | 否 | 否 | 否 | [] | 否 | ["FAILED", "PENDING", "VALIDATION_FAILED"] | — |
| expected_count | 否 | 否 | 否 | [] | 否 | [] | — |
| details | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |
| updated_at | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| agent_batch_operations_pkey | p | PRIMARY KEY (id) |
| agent_batch_operations_user_id_fkey | f | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| uq_agent_batch_operations_op | u | UNIQUE (operation_id) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| agent_batch_operations_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| uq_agent_batch_operations_op | btree | 否 | 是 | ["operation_id"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.agent_command_items · 指令执行步骤 / AgentCommandItem

模块：`agent_runtime`。用途：命令计划中的一个有序步骤及依赖、结果。粒度：一条记录代表命令计划中的一个有序步骤及依赖、结果。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：13（非精确）。证据：`backend/app/models/agent_command.py:37`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('agent_command_items_id_seq'::regclass) | — | 是 | 是 | [] | ["agent_command_items_pkey"] | — | 指令执行步骤：记录主键，内部定位使用 | INTERNAL |
| plan_id | integer | 否 | — | — | 否 | 否 | ["public.agent_command_plans.id"] | ["ix_agent_command_items_plan_id", "uq_command_plan_item"] | — | 指令执行步骤：所属指令执行计划 | INTERNAL |
| item_id | character varying(64) | 否 | — | — | 否 | 否 | [] | ["uq_command_plan_item"] | — | 指令执行步骤：同一命令计划内的逻辑步骤标识 | INTERNAL |
| ordinal | integer | 否 | — | — | 否 | 否 | [] | [] | — | 指令执行步骤：步骤排序序号 | INTERNAL |
| tool | character varying(100) | 否 | — | — | 否 | 否 | [] | [] | — | 指令执行步骤：该步骤的结构化工具名 | INTERNAL |
| source_text | text | 否 | — | — | 否 | 否 | [] | [] | — | 指令执行步骤：用户原文中授权该动作的证据文本 | SENSITIVE |
| source_start | integer | 否 | — | — | 否 | 否 | [] | [] | — | 指令执行步骤：授权原文片段起始偏移 | INTERNAL |
| source_end | integer | 否 | — | — | 否 | 否 | [] | [] | — | 指令执行步骤：授权原文片段结束偏移 | INTERNAL |
| arguments | json | 否 | — | — | 否 | 否 | [] | [] | — | 指令执行步骤：步骤工具参数 | SENSITIVE |
| depends_on | json | 否 | — | — | 否 | 否 | [] | [] | — | 指令执行步骤：同计划内依赖步骤 item_id 列表，不是数据库 ID 数组 | INTERNAL |
| state | character varying(24) | 否 | 'PENDING'::character varying | PENDING | 否 | 否 | [] | [] | — | 指令执行步骤：指令条目执行状态；不是任务状态 | INTERNAL |
| attempts | integer | 否 | 0 | 0 | 否 | 否 | [] | [] | — | 指令执行步骤：执行或投递尝试次数 | INTERNAL |
| result | json | 是 | — | — | 否 | 否 | [] | [] | — | 指令执行步骤：执行结果载荷，须受控投影 | SENSITIVE |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 指令执行步骤：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 指令执行步骤：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| plan_id | 否 | 否 | 否 | [] | 否 | [] | — |
| item_id | 否 | 否 | 否 | [] | 否 | [] | — |
| ordinal | 否 | 否 | 否 | [] | 否 | [] | — |
| tool | 否 | 否 | 否 | [] | 否 | [] | — |
| source_text | 否 | 否 | 否 | [] | 否 | [] | — |
| source_start | 否 | 否 | 否 | [] | 否 | [] | — |
| source_end | 否 | 否 | 否 | [] | 否 | [] | — |
| arguments | 否 | 否 | 否 | [] | 否 | [] | — |
| depends_on | 否 | 否 | 否 | [] | 否 | [] | — |
| state | 否 | 否 | 否 | [] | 否 | ["BLOCKED", "FAILED", "PENDING", "ROLLED_BACK", "RUNNING", "SUCCEEDED", "UNKNOWN"] | — |
| attempts | 否 | 否 | 否 | [] | 否 | [] | — |
| result | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |
| updated_at | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| agent_command_items_pkey | p | PRIMARY KEY (id) |
| agent_command_items_plan_id_fkey | f | FOREIGN KEY (plan_id) REFERENCES agent_command_plans(id) ON DELETE CASCADE |
| uq_command_plan_item | u | UNIQUE (plan_id, item_id) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| agent_command_items_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_agent_command_items_plan_id | btree | 否 | 否 | ["plan_id"] | — | 是 |
| uq_command_plan_item | btree | 否 | 是 | ["plan_id", "item_id"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.agent_command_plans · 指令执行计划 / AgentCommandPlan

模块：`agent_runtime`。用途：一个助手请求对应的一份结构化命令计划。粒度：一条记录代表一个助手请求对应的一份结构化命令计划。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：18（非精确）。证据：`backend/app/models/agent_command.py:19`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('agent_command_plans_id_seq'::regclass) | — | 是 | 是 | [] | ["agent_command_plans_pkey"] | — | 指令执行计划：记录主键，内部定位使用 | INTERNAL |
| request_id | integer | 否 | — | — | 否 | 是 | ["public.agent_requests.id"] | ["agent_command_plans_request_id_key"] | — | 指令执行计划：助手请求标识 | INTERNAL |
| source | text | 否 | — | — | 否 | 否 | [] | [] | — | 指令执行计划：授权指令完整原文，私有 | SENSITIVE |
| policy | character varying(20) | 否 | 'independent'::character varying | independent | 否 | 否 | [] | [] | — | 指令执行计划：命令计划事务策略，例如 independent | INTERNAL |
| status | character varying(24) | 否 | 'PLANNING'::character varying | PLANNING | 否 | 否 | [] | [] | — | 指令执行计划：该对象状态；必须使用本表状态字典 | INTERNAL |
| expected_count | integer | 否 | 0 | 0 | 否 | 否 | [] | [] | — | 指令执行计划：预期条目数 | INTERNAL |
| error | text | 是 | — | — | 否 | 否 | [] | [] | — | 指令执行计划：命令计划错误信息 | SENSITIVE |
| revision | integer | 否 | 1 | 1 | 否 | 否 | [] | [] | — | 指令执行计划：草案或方案内容修订号，用于乐观并发控制 | INTERNAL |
| lease_token | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 指令执行计划：执行租约令牌，禁止 Agent 查询或输出 | HIDDEN |
| lease_until | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 指令执行计划：命令计划执行租约到期时间 | INTERNAL |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 指令执行计划：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 指令执行计划：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | INTERNAL |
| planning_details | jsonb | 是 | — | — | 否 | 否 | [] | [] | — | 指令执行计划：命令规划诊断载荷 | SENSITIVE |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| request_id | 否 | 否 | 否 | [] | 否 | [] | — |
| source | 否 | 否 | 否 | [] | 否 | [] | — |
| policy | 否 | 否 | 否 | [] | 否 | ["independent", "atomic"] | — |
| status | 否 | 否 | 否 | [] | 否 | ["COMPLETED", "FAILED", "PARTIAL", "PAUSED", "PENDING", "PLANNING", "PLANNING_FAILED", "SUCCEEDED"] | — |
| expected_count | 否 | 否 | 否 | [] | 否 | [] | — |
| error | 否 | 否 | 否 | [] | 否 | [] | — |
| revision | 否 | 否 | 否 | [] | 否 | [] | — |
| lease_token | 否 | 否 | 否 | [] | 否 | [] | — |
| lease_until | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |
| updated_at | 否 | 否 | 否 | [] | 否 | [] | — |
| planning_details | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| agent_command_plans_pkey | p | PRIMARY KEY (id) |
| agent_command_plans_request_id_fkey | f | FOREIGN KEY (request_id) REFERENCES agent_requests(id) ON DELETE CASCADE |
| agent_command_plans_request_id_key | u | UNIQUE (request_id) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| agent_command_plans_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| agent_command_plans_request_id_key | btree | 否 | 是 | ["request_id"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.agent_conversations · 助手会话 / AgentConversation

模块：`agent_runtime`。用途：某用户的一段对话及可选绑定项目。粒度：一条记录代表某用户的一段对话及可选绑定项目。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：10（非精确）。证据：`backend/app/models/agent_conversation.py:41`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('agent_conversations_id_seq'::regclass) | — | 是 | 是 | [] | ["agent_conversations_pkey"] | — | 助手会话：记录主键，内部定位使用 | INTERNAL |
| user_id | integer | 否 | — | — | 否 | 否 | ["public.users.id"] | ["ix_agent_conversations_user_id", "ix_agent_conversations_user_last_message"] | — | 助手会话：会话所有者，权限隔离键 | INTERNAL |
| title | character varying(200) | 否 | — | 新对话 | 否 | 否 | [] | [] | — | 助手会话：该业务对象的标题 | INTERNAL |
| status | character varying(16) | 否 | — | ACTIVE | 否 | 否 | [] | [] | — | 助手会话：该对象状态；必须使用本表状态字典 | INTERNAL |
| project_id | integer | 是 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_agent_conversations_project_id"] | — | 助手会话：所属或关联项目的内部标识 | INTERNAL |
| last_message_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | ["ix_agent_conversations_last_message_at", "ix_agent_conversations_user_last_message"] | — | 助手会话：会话最近消息时间 | INTERNAL |
| summary | text | 是 | — | — | 否 | 否 | [] | [] | — | 助手会话：业务或会话摘要；AI 摘要不等于原始事实 | INTERNAL |
| summary_updated_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 助手会话：会话滚动摘要更新时间 | INTERNAL |
| summary_message_id | integer | 是 | — | — | 否 | 否 | [] | [] | — | 助手会话：旧滚动摘要覆盖到的消息标识 | INTERNAL |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 助手会话：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 助手会话：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | INTERNAL |
| summary_through_message_id | integer | 是 | — | — | 否 | 否 | [] | [] | — | 助手会话：滚动摘要覆盖到的最后消息标识 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| user_id | 否 | 否 | 否 | [] | 是 | [] | — |
| title | 否 | 否 | 否 | [] | 否 | [] | — |
| status | 否 | 否 | 否 | [] | 否 | ["ACTIVE", "ARCHIVED"] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| last_message_at | 否 | 否 | 否 | [] | 否 | [] | — |
| summary | 否 | 否 | 否 | [] | 否 | [] | — |
| summary_updated_at | 否 | 否 | 否 | [] | 否 | [] | — |
| summary_message_id | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |
| updated_at | 否 | 否 | 否 | [] | 否 | [] | — |
| summary_through_message_id | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| agent_conversations_pkey | p | PRIMARY KEY (id) |
| agent_conversations_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL |
| agent_conversations_user_id_fkey | f | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| agent_conversations_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_agent_conversations_last_message_at | btree | 否 | 否 | ["last_message_at"] | — | 是 |
| ix_agent_conversations_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| ix_agent_conversations_user_id | btree | 否 | 否 | ["user_id"] | — | 是 |
| ix_agent_conversations_user_last_message | btree | 否 | 否 | ["user_id", "last_message_at"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.agent_memories · 用户记忆 / AgentMemory

模块：`agent_runtime`。用途：某用户的一条偏好、指令或固定上下文；不是动态业务事实。粒度：一条记录代表某用户的一条偏好、指令或固定上下文；不是动态业务事实。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/agent_memory.py:25`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('agent_memories_id_seq'::regclass) | — | 是 | 是 | [] | ["agent_memories_pkey"] | — | 用户记忆：记录主键，内部定位使用 | INTERNAL |
| user_id | integer | 否 | — | — | 否 | 否 | ["public.users.id"] | ["ix_agent_memories_user_active", "ix_agent_memories_user_id"] | — | 用户记忆：记忆所有者，权限隔离键 | INTERNAL |
| scope | character varying(16) | 否 | — | USER | 否 | 否 | [] | [] | — | 用户记忆：用户记忆作用域 USER/PROJECT | INTERNAL |
| memory_type | character varying(32) | 否 | — | PREFERENCE | 否 | 否 | [] | [] | — | 用户记忆：用户记忆内容类别 | INTERNAL |
| content | text | 否 | — | — | 否 | 否 | [] | [] | — | 用户记忆：当前用户显式偏好或关注点，不允许保存动态业务事实 | SENSITIVE |
| project_id | integer | 是 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_agent_memories_project_id"] | — | 用户记忆：所属或关联项目的内部标识 | INTERNAL |
| is_active | boolean | 否 | true | 是 | 否 | 否 | [] | ["ix_agent_memories_user_active"] | — | 用户记忆：上下文有效性标志；成员有效性或记忆启用，不统一等于软删除 | INTERNAL |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 用户记忆：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 用户记忆：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| user_id | 否 | 否 | 否 | [] | 是 | [] | — |
| scope | 否 | 否 | 否 | [] | 否 | ["USER", "PROJECT"] | — |
| memory_type | 否 | 否 | 否 | [] | 否 | ["PREFERENCE", "INSTRUCTION", "PINNED_CONTEXT"] | — |
| content | 否 | 否 | 否 | [] | 否 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| is_active | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |
| updated_at | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| agent_memories_pkey | p | PRIMARY KEY (id) |
| agent_memories_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL |
| agent_memories_user_id_fkey | f | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| agent_memories_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_agent_memories_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| ix_agent_memories_user_active | btree | 否 | 否 | ["user_id", "is_active"] | — | 是 |
| ix_agent_memories_user_id | btree | 否 | 否 | ["user_id"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.agent_messages · 助手消息 / AgentMessage

模块：`agent_runtime`。用途：一个会话中的一条消息或一个回答版本。粒度：一条记录代表一个会话中的一条消息或一个回答版本。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：49（非精确）。证据：`backend/app/models/agent_conversation.py:88`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('agent_messages_id_seq'::regclass) | — | 是 | 是 | [] | ["agent_messages_pkey"] | — | 助手消息：记录主键，内部定位使用 | INTERNAL |
| conversation_id | integer | 否 | — | — | 否 | 否 | ["public.agent_conversations.id"] | ["ix_agent_messages_conversation_created", "ix_agent_messages_conversation_id"] | — | 助手消息：所属助手会话 | INTERNAL |
| role | character varying(16) | 否 | — | — | 否 | 否 | [] | [] | — | 助手消息：当前表上下文中的角色，用户权限角色与参与角色不可混用 | INTERNAL |
| content | text | 否 | — |  | 否 | 否 | [] | [] | — | 助手消息：按表上下文解释的正文或结构化内容，不能跨对象复用 JSON 字段语义 | SENSITIVE |
| status | character varying(16) | 否 | — | COMPLETED | 否 | 否 | [] | [] | — | 助手消息：该对象状态；必须使用本表状态字典 | INTERNAL |
| tool_calls | jsonb | 是 | — | — | 否 | 否 | [] | [] | — | 助手消息：消息内工具调用摘要列表 | SENSITIVE |
| tool_results | jsonb | 是 | — | — | 否 | 否 | [] | [] | — | 助手消息：消息内工具结果载荷 | SENSITIVE |
| model | character varying(100) | 是 | — | — | 否 | 否 | [] | [] | — | 助手消息：生成或分析所用模型标识 | INTERNAL |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | ["ix_agent_messages_conversation_created"] | — | 助手消息：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |
| completed_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 助手消息：对象完成事件时间，具体为任务完成或请求/消息/作业结束 | INTERNAL |
| cards | json | 是 | — | — | 否 | 否 | [] | [] | — | 助手消息：UI 结构化卡片引用，仍需后端授权 | SENSITIVE |
| parent_user_message_id | integer | 是 | — | — | 否 | 否 | ["public.agent_messages.id"] | ["ix_agent_messages_parent_user"] | — | 助手消息：回答所属的用户消息，不是组织树 | INTERNAL |
| regenerated_from_id | integer | 是 | — | — | 否 | 否 | ["public.agent_messages.id"] | [] | — | 助手消息：该回答从哪个旧回答重新生成 | INTERNAL |
| answer_version | integer | 是 | — | — | 否 | 否 | [] | [] | — | 助手消息：同一用户问题下的回答版本号，从 1 起 | INTERNAL |
| selected_answer_id | integer | 是 | — | — | 否 | 否 | ["public.agent_messages.id"] | [] | — | 助手消息：用户消息当前选择的回答版本 | INTERNAL |
| association_status | character varying(16) | 否 | 'NORMAL'::character varying | NORMAL | 否 | 否 | [] | [] | — | 助手消息：回答与用户消息绑定状态，NORMAL/LEGACY | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| conversation_id | 否 | 否 | 否 | [] | 否 | [] | — |
| role | 否 | 否 | 否 | [] | 否 | ["USER", "ASSISTANT", "SYSTEM"] | — |
| content | 否 | 否 | 否 | [] | 否 | [] | — |
| status | 否 | 否 | 否 | [] | 否 | ["PENDING", "STREAMING", "COMPLETED", "FAILED", "STOPPED", "INTERRUPTED"] | — |
| tool_calls | 否 | 否 | 否 | [] | 否 | [] | — |
| tool_results | 否 | 否 | 否 | [] | 否 | [] | — |
| model | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |
| completed_at | 否 | 否 | 否 | [] | 否 | [] | — |
| cards | 否 | 否 | 否 | [] | 否 | [] | — |
| parent_user_message_id | 否 | 否 | 否 | [] | 否 | [] | — |
| regenerated_from_id | 否 | 否 | 否 | [] | 否 | [] | — |
| answer_version | 否 | 否 | 否 | [] | 否 | [] | — |
| selected_answer_id | 否 | 否 | 否 | [] | 否 | [] | — |
| association_status | 否 | 否 | 否 | [] | 否 | ["NORMAL", "LEGACY"] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| agent_messages_conversation_id_fkey | f | FOREIGN KEY (conversation_id) REFERENCES agent_conversations(id) ON DELETE CASCADE |
| agent_messages_pkey | p | PRIMARY KEY (id) |
| fk_agent_messages_parent_user | f | FOREIGN KEY (parent_user_message_id) REFERENCES agent_messages(id) ON DELETE SET NULL |
| fk_agent_messages_regenerated_from | f | FOREIGN KEY (regenerated_from_id) REFERENCES agent_messages(id) ON DELETE SET NULL |
| fk_agent_messages_selected_answer | f | FOREIGN KEY (selected_answer_id) REFERENCES agent_messages(id) ON DELETE SET NULL |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| agent_messages_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_agent_messages_conversation_created | btree | 否 | 否 | ["conversation_id", "created_at"] | — | 是 |
| ix_agent_messages_conversation_id | btree | 否 | 否 | ["conversation_id"] | — | 是 |
| ix_agent_messages_parent_user | btree | 否 | 否 | ["parent_user_message_id"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.agent_operations · 工具写入回执 / AgentOperation

模块：`agent_runtime`。用途：一个助手请求内一次有副作用工具动作的回执。粒度：一条记录代表一个助手请求内一次有副作用工具动作的回执。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/agent_request.py:93`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('agent_operations_id_seq'::regclass) | — | 是 | 是 | [] | ["agent_operations_pkey"] | — | 工具写入回执：记录主键，内部定位使用 | INTERNAL |
| operation_id | character varying(64) | 否 | — | — | 否 | 是 | [] | ["uq_agent_operations_operation_id"] | — | 工具写入回执：幂等操作标识，按表上下文区分批次和请求操作 | INTERNAL |
| request_id | integer | 否 | — | — | 否 | 否 | ["public.agent_requests.id"] | ["ix_agent_operations_request"] | — | 工具写入回执：助手请求标识 | INTERNAL |
| tool_name | character varying(100) | 否 | — | — | 否 | 否 | [] | [] | — | 工具写入回执：已注册结构化工具名 | INTERNAL |
| args_digest | character varying(64) | 否 | — | — | 否 | 否 | [] | [] | — | 工具写入回执：工具参数指纹 | INTERNAL |
| status | character varying(16) | 否 | — | — | 否 | 否 | [] | [] | — | 工具写入回执：该对象状态；必须使用本表状态字典 | INTERNAL |
| result_json | json | 是 | — | — | 否 | 否 | [] | [] | — | 工具写入回执：工具执行回执 JSON | SENSITIVE |
| tool_call_id | character varying(100) | 是 | — | — | 否 | 否 | [] | [] | — | 工具写入回执：模型工具调用标识，不是本地 agent_tool_calls.id | INTERNAL |
| created_at | timestamp with time zone | 否 | CURRENT_TIMESTAMP | — | 否 | 否 | [] | [] | — | 工具写入回执：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| operation_id | 否 | 否 | 否 | [] | 否 | [] | — |
| request_id | 否 | 否 | 否 | [] | 否 | [] | — |
| tool_name | 否 | 否 | 否 | [] | 否 | [] | — |
| args_digest | 否 | 否 | 否 | [] | 否 | [] | — |
| status | 否 | 否 | 否 | [] | 否 | ["SUCCEEDED", "FAILED"] | — |
| result_json | 否 | 否 | 否 | [] | 否 | [] | — |
| tool_call_id | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| agent_operations_pkey | p | PRIMARY KEY (id) |
| agent_operations_request_id_fkey | f | FOREIGN KEY (request_id) REFERENCES agent_requests(id) ON DELETE CASCADE |
| uq_agent_operations_operation_id | u | UNIQUE (operation_id) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| agent_operations_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_agent_operations_request | btree | 否 | 否 | ["request_id"] | — | 是 |
| uq_agent_operations_operation_id | btree | 否 | 是 | ["operation_id"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.agent_requests · 助手请求 / AgentRequest

模块：`agent_runtime`。用途：用户在会话中的一次带幂等标识的发送请求。粒度：一条记录代表用户在会话中的一次带幂等标识的发送请求。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：23（非精确）。证据：`backend/app/models/agent_request.py:44`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('agent_requests_id_seq'::regclass) | — | 是 | 是 | [] | ["agent_requests_pkey"] | — | 助手请求：记录主键，内部定位使用 | INTERNAL |
| user_id | integer | 否 | — | — | 否 | 否 | ["public.users.id"] | ["ix_agent_requests_user_id", "uq_agent_requests_user_conversation_client"] | — | 助手请求：关联用户标识，具体角色见表用途 | INTERNAL |
| conversation_id | integer | 否 | — | — | 否 | 否 | ["public.agent_conversations.id"] | ["ix_agent_requests_conversation_created", "ix_agent_requests_conversation_id", "uq_agent_requests_user_conversation_client"] | — | 助手请求：所属助手会话 | INTERNAL |
| client_request_id | character varying(100) | 否 | — | — | 否 | 否 | [] | ["uq_agent_requests_user_conversation_client"] | — | 助手请求：会话内客户端发送幂等键 | INTERNAL |
| content_digest | character varying(64) | 否 | — | — | 否 | 否 | [] | [] | — | 助手请求：请求原文指纹 | INTERNAL |
| content_preview | character varying(500) | 否 | — |  | 否 | 否 | [] | [] | — | 助手请求：请求原文预览，可能包含敏感业务内容 | SENSITIVE |
| status | character varying(16) | 否 | — | ACCEPTED | 否 | 否 | [] | [] | — | 助手请求：该对象状态；必须使用本表状态字典 | INTERNAL |
| user_message_id | integer | 是 | — | — | 否 | 否 | ["public.agent_messages.id"] | [] | — | 助手请求：请求输入消息标识 | INTERNAL |
| assistant_message_id | integer | 是 | — | — | 否 | 否 | ["public.agent_messages.id"] | [] | — | 助手请求：请求响应消息标识 | INTERNAL |
| error_code | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 助手请求：结构化错误码 | INTERNAL |
| completed_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 助手请求：对象完成事件时间，具体为任务完成或请求/消息/作业结束 | INTERNAL |
| created_at | timestamp with time zone | 否 | CURRENT_TIMESTAMP | — | 否 | 否 | [] | ["ix_agent_requests_conversation_created"] | — | 助手请求：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |
| updated_at | timestamp with time zone | 否 | CURRENT_TIMESTAMP | — | 否 | 否 | [] | [] | — | 助手请求：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | INTERNAL |
| cancel_requested | boolean | 否 | false | 否 | 否 | 否 | [] | [] | — | 助手请求：用户已请求取消生成 | INTERNAL |
| heartbeat_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 助手请求：生成请求最近存活心跳 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| user_id | 否 | 否 | 否 | [] | 是 | [] | — |
| conversation_id | 否 | 否 | 否 | [] | 否 | [] | — |
| client_request_id | 否 | 否 | 否 | [] | 否 | [] | — |
| content_digest | 否 | 否 | 否 | [] | 否 | [] | — |
| content_preview | 否 | 否 | 否 | [] | 否 | [] | — |
| status | 否 | 否 | 否 | [] | 否 | ["ACCEPTED", "RUNNING", "COMPLETED", "FAILED", "STOPPED", "INTERRUPTED"] | — |
| user_message_id | 否 | 否 | 否 | [] | 否 | [] | — |
| assistant_message_id | 否 | 否 | 否 | [] | 否 | [] | — |
| error_code | 否 | 否 | 否 | [] | 否 | [] | — |
| completed_at | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |
| updated_at | 否 | 否 | 否 | [] | 否 | [] | — |
| cancel_requested | 否 | 否 | 否 | [] | 否 | [] | — |
| heartbeat_at | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| agent_requests_assistant_message_id_fkey | f | FOREIGN KEY (assistant_message_id) REFERENCES agent_messages(id) ON DELETE SET NULL |
| agent_requests_conversation_id_fkey | f | FOREIGN KEY (conversation_id) REFERENCES agent_conversations(id) ON DELETE CASCADE |
| agent_requests_pkey | p | PRIMARY KEY (id) |
| agent_requests_user_id_fkey | f | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |
| agent_requests_user_message_id_fkey | f | FOREIGN KEY (user_message_id) REFERENCES agent_messages(id) ON DELETE SET NULL |
| uq_agent_requests_user_conversation_client | u | UNIQUE (user_id, conversation_id, client_request_id) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| agent_requests_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_agent_requests_conversation_created | btree | 否 | 否 | ["conversation_id", "created_at"] | — | 是 |
| ix_agent_requests_conversation_id | btree | 否 | 否 | ["conversation_id"] | — | 是 |
| ix_agent_requests_user_id | btree | 否 | 否 | ["user_id"] | — | 是 |
| uq_agent_requests_user_conversation_client | btree | 否 | 是 | ["user_id", "conversation_id", "client_request_id"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.agent_tool_calls · 工具调用审计 / AgentToolCall

模块：`agent_runtime`。用途：一次读或写工具调用及耗时、结果摘要。粒度：一条记录代表一次读或写工具调用及耗时、结果摘要。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：54（非精确）。证据：`backend/app/models/agent_tool_call.py:18`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('agent_tool_calls_id_seq'::regclass) | — | 是 | 是 | [] | ["agent_tool_calls_pkey"] | — | 工具调用审计：记录主键，内部定位使用 | INTERNAL |
| request_id | integer | 是 | — | — | 否 | 否 | ["public.agent_requests.id"] | ["ix_agent_tool_calls_request"] | — | 工具调用审计：助手请求标识 | INTERNAL |
| conversation_id | integer | 是 | — | — | 否 | 否 | ["public.agent_conversations.id"] | ["ix_agent_tool_calls_conversation_id"] | — | 工具调用审计：所属助手会话 | INTERNAL |
| user_id | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 工具调用审计：关联用户标识，具体角色见表用途 | INTERNAL |
| tool_name | character varying(100) | 否 | — | — | 否 | 否 | [] | [] | — | 工具调用审计：已注册结构化工具名 | INTERNAL |
| risk_level | character varying(32) | 否 | — | READ | 否 | 否 | [] | [] | — | 工具调用审计：项目风险等级或工具风险分类，见对应字典 | INTERNAL |
| tool_call_id | character varying(100) | 是 | — | — | 否 | 否 | [] | [] | — | 工具调用审计：模型工具调用标识，不是本地 agent_tool_calls.id | INTERNAL |
| arguments_json | jsonb | 是 | — | — | 否 | 否 | [] | [] | — | 工具调用审计：工具调用参数载荷，禁止直接披露 | SENSITIVE |
| result_summary | jsonb | 是 | — | — | 否 | 否 | [] | [] | — | 工具调用审计：工具结果摘要，须投影脱敏 | SENSITIVE |
| success | boolean | 否 | — | 否 | 否 | 否 | [] | [] | — | 工具调用审计：工具调用是否成功 | INTERNAL |
| error_code | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 工具调用审计：结构化错误码 | INTERNAL |
| duration_ms | integer | 是 | — | — | 否 | 否 | [] | [] | — | 工具调用审计：工具调用耗时毫秒 | INTERNAL |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | ["ix_agent_tool_calls_created"] | — | 工具调用审计：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| request_id | 否 | 否 | 否 | [] | 否 | [] | — |
| conversation_id | 否 | 否 | 否 | [] | 否 | [] | — |
| user_id | 否 | 否 | 否 | [] | 是 | [] | — |
| tool_name | 否 | 否 | 否 | [] | 否 | [] | — |
| risk_level | 否 | 否 | 否 | [] | 否 | [] | — |
| tool_call_id | 否 | 否 | 否 | [] | 否 | [] | — |
| arguments_json | 否 | 否 | 否 | [] | 否 | [] | — |
| result_summary | 否 | 否 | 否 | [] | 否 | [] | — |
| success | 否 | 否 | 否 | [] | 否 | [] | — |
| error_code | 否 | 否 | 否 | [] | 否 | [] | — |
| duration_ms | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| agent_tool_calls_conversation_id_fkey | f | FOREIGN KEY (conversation_id) REFERENCES agent_conversations(id) ON DELETE SET NULL |
| agent_tool_calls_pkey | p | PRIMARY KEY (id) |
| agent_tool_calls_request_id_fkey | f | FOREIGN KEY (request_id) REFERENCES agent_requests(id) ON DELETE CASCADE |
| agent_tool_calls_user_id_fkey | f | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| agent_tool_calls_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_agent_tool_calls_conversation_id | btree | 否 | 否 | ["conversation_id"] | — | 是 |
| ix_agent_tool_calls_created | btree | 否 | 否 | ["created_at"] | — | 是 |
| ix_agent_tool_calls_request | btree | 否 | 否 | ["request_id"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.ai_runs · 后台 AI 运行 / AIRun

模块：`agent_runtime`。用途：某业务资源的一次后台 AI 作业。粒度：一条记录代表某业务资源的一次后台 AI 作业。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/ai_run.py:29`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('ai_runs_id_seq'::regclass) | — | 是 | 是 | [] | ["ai_runs_pkey"] | — | 后台 AI 运行：记录主键，内部定位使用 | INTERNAL |
| run_type | character varying(32) | 否 | — | — | 否 | 否 | [] | ["ix_ai_runs_run_type"] | — | 后台 AI 运行：后台 AI 作业类型 | INTERNAL |
| resource_type | character varying(64) | 否 | — | — | 否 | 否 | [] | ["ix_ai_runs_resource"] | — | 后台 AI 运行：多态资源类型判别器，禁止无类型 JOIN | INTERNAL |
| resource_id | character varying(64) | 否 | — | — | 否 | 否 | [] | ["ix_ai_runs_resource"] | — | 后台 AI 运行：多态业务资源标识，必须结合资源类型或已验证工具类型 | INTERNAL |
| status | character varying(16) | 否 | — | QUEUED | 否 | 否 | [] | ["ix_ai_runs_status", "ix_ai_runs_status_created"] | — | 后台 AI 运行：该对象状态；必须使用本表状态字典 | INTERNAL |
| model | character varying(100) | 是 | — | — | 否 | 否 | [] | [] | — | 后台 AI 运行：生成或分析所用模型标识 | INTERNAL |
| error_code | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 后台 AI 运行：结构化错误码 | INTERNAL |
| user_message | character varying(255) | 是 | — | — | 否 | 否 | [] | [] | — | 后台 AI 运行：可呈现的作业状态说明，需业务接口筛选 | INTERNAL |
| created_by | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 后台 AI 运行：创建人用户标识 | INTERNAL |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | ["ix_ai_runs_resource", "ix_ai_runs_status_created"] | — | 后台 AI 运行：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |
| started_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 后台 AI 运行：后台 AI 作业实际开始时间 | INTERNAL |
| completed_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 后台 AI 运行：对象完成事件时间，具体为任务完成或请求/消息/作业结束 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| run_type | 否 | 否 | 否 | [] | 否 | ["PROGRESS_ANALYSIS", "ISSUE_ADVICE", "DAILY_SUMMARY", "CONVERSATION_SUMMARY"] | — |
| resource_type | 否 | 否 | 否 | [] | 否 | [] | — |
| resource_id | 否 | 否 | 否 | [] | 否 | [] | — |
| status | 否 | 否 | 否 | [] | 否 | ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "DISABLED"] | — |
| model | 否 | 否 | 否 | [] | 否 | [] | — |
| error_code | 否 | 否 | 否 | [] | 否 | [] | — |
| user_message | 否 | 否 | 否 | [] | 否 | [] | — |
| created_by | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |
| started_at | 否 | 否 | 否 | [] | 否 | [] | — |
| completed_at | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| ai_runs_created_by_fkey | f | FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL |
| ai_runs_pkey | p | PRIMARY KEY (id) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ai_runs_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_ai_runs_resource | btree | 否 | 否 | ["resource_type", "resource_id", "created_at"] | — | 是 |
| ix_ai_runs_run_type | btree | 否 | 否 | ["run_type"] | — | 是 |
| ix_ai_runs_status | btree | 否 | 否 | ["status"] | — | 是 |
| ix_ai_runs_status_created | btree | 否 | 否 | ["status", "created_at"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.alembic_version · 迁移版本 / MigrationVersion

模块：`maintenance`。用途：Alembic 记录的已应用迁移版本标识；不属于业务实体。粒度：一条记录代表Alembic 记录的已应用迁移版本标识；不属于业务实体。

表 COMMENT：UNKNOWN。主键：`version_num`；策略：`APPLICATION_STRING_ID`。估计行数：UNKNOWN（非精确）。证据：`backend/alembic/env.py`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| version_num | character varying(32) | 否 | — | — | 是 | 是 | [] | ["alembic_version_pkc"] | — | 迁移版本：Alembic 已应用迁移版本字符串 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| version_num | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| alembic_version_pkc | p | PRIMARY KEY (version_num) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| alembic_version_pkc | btree | 是 | 是 | ["version_num"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.audit_logs · 业务审计日志 / AuditLog

模块：`audit`。用途：一次业务变更的操作人与前后快照。粒度：一条记录代表一次业务变更的操作人与前后快照。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：182（非精确）。证据：`backend/app/models/audit_log.py:13`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('audit_logs_id_seq'::regclass) | — | 是 | 是 | [] | ["audit_logs_pkey"] | — | 业务审计日志：记录主键，内部定位使用 | INTERNAL |
| user_id | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | ["ix_audit_logs_user_id"] | — | 业务审计日志：业务操作人，可因删除用户而为空 | INTERNAL |
| action | character varying(64) | 否 | — | — | 否 | 否 | [] | ["ix_audit_logs_action"] | — | 业务审计日志：业务审计动作名 | INTERNAL |
| resource_type | character varying(64) | 否 | — | — | 否 | 否 | [] | ["ix_audit_logs_resource_type"] | — | 业务审计日志：多态资源类型判别器，禁止无类型 JOIN | INTERNAL |
| resource_id | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 业务审计日志：多态业务资源标识，必须结合资源类型或已验证工具类型 | INTERNAL |
| old_value | json | 是 | — | — | 否 | 否 | [] | [] | — | 业务审计日志：变更前审计快照，禁止普通 Agent 原样读取 | SENSITIVE |
| new_value | json | 是 | — | — | 否 | 否 | [] | [] | — | 业务审计日志：变更后审计快照，禁止普通 Agent 原样读取 | SENSITIVE |
| ip_address | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 业务审计日志：请求来源网络地址，敏感内部信息 | SENSITIVE |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | ["ix_audit_logs_created_at"] | — | 业务审计日志：记录创建时间，不是计划开始或汇报涵盖日期 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| user_id | 否 | 否 | 否 | [] | 是 | [] | — |
| action | 否 | 否 | 否 | [] | 否 | [] | — |
| resource_type | 否 | 否 | 否 | [] | 否 | [] | — |
| resource_id | 否 | 否 | 否 | [] | 否 | [] | — |
| old_value | 否 | 否 | 否 | [] | 否 | [] | — |
| new_value | 否 | 否 | 否 | [] | 否 | [] | — |
| ip_address | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| audit_logs_pkey | p | PRIMARY KEY (id) |
| audit_logs_user_id_fkey | f | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| audit_logs_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_audit_logs_action | btree | 否 | 否 | ["action"] | — | 是 |
| ix_audit_logs_created_at | btree | 否 | 否 | ["created_at"] | — | 是 |
| ix_audit_logs_resource_type | btree | 否 | 否 | ["resource_type"] | — | 是 |
| ix_audit_logs_user_id | btree | 否 | 否 | ["user_id"] | — | 是 |

读取策略：DENY_GENERAL_QUERY。范围：DENY_GENERAL_AGENT_QUERY。禁止直接修改。

## public.branch_groups · 路线决策组 / BranchGroup

模块：`planning`。用途：一个项目中一组互斥执行路线的决策点。粒度：一条记录代表一个项目中一组互斥执行路线的决策点。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/planning.py:101`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('branch_groups_id_seq'::regclass) | — | 是 | 是 | [] | ["branch_groups_pkey"] | — | 路线决策组：记录主键，内部定位使用 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_branch_groups_project_id"] | — | 路线决策组：所属或关联项目的内部标识 | INTERNAL |
| name | character varying(200) | 否 | — | — | 否 | 否 | [] | [] | — | 路线决策组：该业务对象的显示名称 | PUBLIC |
| legacy_root_id | integer | 是 | — | — | 否 | 是 | [] | ["branch_groups_legacy_root_id_key"] | — | 路线决策组：迁移时保留的旧版分支根任务标识 | INTERNAL |
| entry_task_id | integer | 是 | — | — | 否 | 否 | ["public.tasks.id"] | [] | — | 路线决策组：路线组入口任务 | INTERNAL |
| exit_task_id | integer | 是 | — | — | 否 | 否 | ["public.tasks.id"] | [] | — | 路线决策组：路线组出口任务 | INTERNAL |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 路线决策组：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 路线决策组：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| name | 是 | 是 | 是 | [] | 否 | [] | — |
| legacy_root_id | 否 | 否 | 否 | [] | 否 | [] | — |
| entry_task_id | 否 | 否 | 否 | [] | 否 | [] | — |
| exit_task_id | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| branch_groups_legacy_root_id_key | u | UNIQUE (legacy_root_id) |
| branch_groups_pkey | p | PRIMARY KEY (id) |
| branch_groups_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| fk_branch_entry | f | FOREIGN KEY (entry_task_id) REFERENCES tasks(id) ON DELETE RESTRICT |
| fk_branch_exit | f | FOREIGN KEY (exit_task_id) REFERENCES tasks(id) ON DELETE RESTRICT |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| branch_groups_legacy_root_id_key | btree | 否 | 是 | ["legacy_root_id"] | — | 是 |
| branch_groups_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_branch_groups_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在。禁止直接修改。

## public.branch_options · 路线选项 / BranchOption

模块：`planning`。用途：某路线决策组中的一个候选选项。粒度：一条记录代表某路线决策组中的一个候选选项。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/planning.py:117`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('branch_options_id_seq'::regclass) | — | 是 | 是 | [] | ["branch_options_pkey"] | — | 路线选项：记录主键，内部定位使用 | INTERNAL |
| group_id | integer | 否 | — | — | 否 | 否 | ["public.branch_groups.id"] | ["ix_branch_options_group_id", "uq_branch_option_name"] | — | 路线选项：路线选项所属决策组 | INTERNAL |
| name | character varying(120) | 否 | — | — | 否 | 否 | [] | ["uq_branch_option_name"] | — | 路线选项：该业务对象的显示名称 | PUBLIC |
| is_selected | boolean | 否 | false | 否 | 否 | 否 | [] | [] | — | 路线选项：路线选项是否被选中 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 路线选项：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 路线选项：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| group_id | 否 | 否 | 否 | [] | 否 | [] | — |
| name | 是 | 是 | 是 | [] | 否 | [] | — |
| is_selected | 是 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| branch_options_group_id_fkey | f | FOREIGN KEY (group_id) REFERENCES branch_groups(id) ON DELETE CASCADE |
| branch_options_pkey | p | PRIMARY KEY (id) |
| uq_branch_option_name | u | UNIQUE (group_id, name) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| branch_options_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_branch_options_group_id | btree | 否 | 否 | ["group_id"] | — | 是 |
| uq_branch_option_name | btree | 否 | 是 | ["group_id", "name"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在。禁止直接修改。

## public.change_proposals · 计划变更方案 / ChangeProposal

模块：`planning`。用途：一个经预览、校验、确认及执行的计划变更方案。粒度：一条记录代表一个经预览、校验、确认及执行的计划变更方案。

表 COMMENT：UNKNOWN。主键：`id`；策略：`APPLICATION_STRING_ID`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/change_proposal.py:25`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | character varying(36) | 否 | — | — | 是 | 是 | [] | ["change_proposals_pkey"] | — | 计划变更方案：记录主键，内部定位使用 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_change_proposals_project_id", "uq_proposal_create_key"] | — | 计划变更方案：所属或关联项目的内部标识 | INTERNAL |
| created_by | integer | 否 | — | — | 否 | 否 | ["public.users.id"] | ["uq_proposal_create_key"] | — | 计划变更方案：创建人用户标识 | INTERNAL |
| status | character varying(16) | 否 | 'DRAFT'::character varying | DRAFT | 否 | 否 | [] | [] | — | 计划变更方案：该对象状态；必须使用本表状态字典 | PUBLIC |
| revision | integer | 否 | 1 | 1 | 否 | 否 | [] | [] | — | 计划变更方案：草案或方案内容修订号，用于乐观并发控制 | INTERNAL |
| reason | text | 否 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：业务变更或计划快照原因 | PUBLIC |
| request | json | 否 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：方案结构化变更输入 | SENSITIVE |
| source | json | 是 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：变更来源或命令原文，按表上下文解释 | SENSITIVE |
| create_key | character varying(100) | 否 | — | — | 否 | 否 | [] | ["uq_proposal_create_key"] | — | 计划变更方案：创建幂等键 | INTERNAL |
| create_hash | character varying(64) | 否 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：创建参数指纹 | INTERNAL |
| preview | json | 是 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：变更排期预览结果 | SENSITIVE |
| diff | json | 是 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：变更前后差异 | SENSITIVE |
| snapshot_token | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：内部计划快照校验凭据，Agent 不可直接读取 | HIDDEN |
| digest | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：审核内容摘要，交互确认仅由受控业务 DTO 提供 | INTERNAL |
| base_plan_version | integer | 是 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：项目范围内基准 plan_versions.version；0 表示尚无版本 | PUBLIC |
| confirmed_by | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 计划变更方案：变更确认人，需与确认上下文绑定 | INTERNAL |
| confirmed_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：方案确认时间 | PUBLIC |
| expires_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：方案校验/确认有效期截止时间 | PUBLIC |
| applied_by | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 计划变更方案：变更执行人 | INTERNAL |
| applied_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：方案执行时间 | PUBLIC |
| applied_version_id | integer | 是 | — | — | 否 | 否 | ["public.plan_versions.id"] | [] | — | 计划变更方案：执行变更生成的计划快照主键 | INTERNAL |
| apply_key | character varying(100) | 是 | — | — | 否 | 是 | [] | ["change_proposals_apply_key_key"] | — | 计划变更方案：执行幂等键 | INTERNAL |
| result | json | 是 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：执行结果载荷，须受控投影 | SENSITIVE |
| failure_reason | text | 是 | — | — | 否 | 否 | [] | [] | — | 计划变更方案：执行失败原因，须脱敏 | SENSITIVE |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 计划变更方案：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 计划变更方案：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| created_by | 否 | 否 | 否 | [] | 否 | [] | — |
| status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["DRAFT", "VALIDATED", "CONFIRMED", "APPLIED", "REJECTED", "EXPIRED", "FAILED"] | — |
| revision | 否 | 否 | 否 | [] | 否 | [] | — |
| reason | 是 | 否 | 否 | [] | 否 | [] | — |
| request | 否 | 否 | 否 | [] | 否 | [] | — |
| source | 否 | 否 | 否 | [] | 否 | [] | — |
| create_key | 否 | 否 | 否 | [] | 否 | [] | — |
| create_hash | 否 | 否 | 否 | [] | 否 | [] | — |
| preview | 否 | 否 | 否 | [] | 否 | [] | — |
| diff | 否 | 否 | 否 | [] | 否 | [] | — |
| snapshot_token | 否 | 否 | 否 | [] | 否 | [] | — |
| digest | 否 | 否 | 否 | [] | 否 | [] | — |
| base_plan_version | 是 | 是 | 否 | [] | 否 | [] | — |
| confirmed_by | 否 | 否 | 否 | [] | 否 | [] | — |
| confirmed_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| expires_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| applied_by | 否 | 否 | 否 | [] | 否 | [] | — |
| applied_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| applied_version_id | 否 | 否 | 否 | [] | 否 | [] | — |
| apply_key | 否 | 否 | 否 | [] | 否 | [] | — |
| result | 否 | 否 | 否 | [] | 否 | [] | — |
| failure_reason | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| change_proposals_applied_by_fkey | f | FOREIGN KEY (applied_by) REFERENCES users(id) ON DELETE RESTRICT |
| change_proposals_applied_version_id_fkey | f | FOREIGN KEY (applied_version_id) REFERENCES plan_versions(id) ON DELETE RESTRICT |
| change_proposals_apply_key_key | u | UNIQUE (apply_key) |
| change_proposals_confirmed_by_fkey | f | FOREIGN KEY (confirmed_by) REFERENCES users(id) ON DELETE RESTRICT |
| change_proposals_created_by_fkey | f | FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT |
| change_proposals_pkey | p | PRIMARY KEY (id) |
| change_proposals_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| ck_proposal_revision | c | CHECK ((revision >= 1)) |
| ck_proposal_status | c | CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'VALIDATED'::character varying, 'CONFIRMED'::character varying, 'APPLIED'::character varying, 'REJECTED'::character varying, 'EXPIRED'::character varying, 'FAILED'::character varying])::text[]))) |
| uq_proposal_create_key | u | UNIQUE (project_id, created_by, create_key) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| change_proposals_apply_key_key | btree | 否 | 是 | ["apply_key"] | — | 是 |
| change_proposals_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_change_proposals_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| uq_proposal_create_key | btree | 否 | 是 | ["project_id", "created_by", "create_key"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在。禁止直接修改。

## public.daily_project_summaries · 项目日报 / DailyProjectSummary

模块：`execution`。用途：一个项目在一个业务日期的 AI 汇总。粒度：一条记录代表一个项目在一个业务日期的 AI 汇总。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/daily_project_summary.py:14`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('daily_project_summaries_id_seq'::regclass) | — | 是 | 是 | [] | ["daily_project_summaries_pkey"] | — | 项目日报：记录主键，内部定位使用 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_daily_project_summaries_project_id", "uq_daily_summary_project_date"] | — | 项目日报：所属或关联项目的内部标识 | INTERNAL |
| summary_date | date | 否 | — | — | 否 | 否 | [] | ["ix_daily_project_summaries_summary_date", "uq_daily_summary_project_date"] | — | 项目日报：日报对应的业务日期，不是生成日期 | PUBLIC |
| summary | text | 否 | — | — | 否 | 否 | [] | [] | — | 项目日报：业务或会话摘要；AI 摘要不等于原始事实 | PUBLIC |
| risk_summary | text | 否 | — | — | 否 | 否 | [] | [] | — | 项目日报：项目日报风险摘要（AI 参考） | PUBLIC |
| next_action | text | 否 | — | — | 否 | 否 | [] | [] | — | 项目日报：日报下一步行动建议 | PUBLIC |
| management_attention | text | 否 | — | — | 否 | 否 | [] | [] | — | 项目日报：日报管理关注事项 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 项目日报：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 项目日报：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| summary_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| summary | 是 | 否 | 是 | [] | 否 | [] | — |
| risk_summary | 是 | 否 | 否 | [] | 否 | [] | — |
| next_action | 是 | 否 | 否 | [] | 否 | [] | — |
| management_attention | 是 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| daily_project_summaries_pkey | p | PRIMARY KEY (id) |
| daily_project_summaries_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| uq_daily_summary_project_date | u | UNIQUE (project_id, summary_date) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| daily_project_summaries_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_daily_project_summaries_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| ix_daily_project_summaries_summary_date | btree | 否 | 否 | ["summary_date"] | — | 是 |
| uq_daily_summary_project_date | btree | 否 | 是 | ["project_id", "summary_date"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在。禁止直接修改。

## public.issues · 问题 / Issue

模块：`risk`。用途：一个项目级或任务级问题。粒度：一条记录代表一个项目级或任务级问题。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/issue.py:31`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('issues_id_seq'::regclass) | — | 是 | 是 | [] | ["issues_pkey"] | — | 问题：记录主键，内部定位使用 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_issues_project_id"] | — | 问题：所属或关联项目的内部标识 | INTERNAL |
| task_id | integer | 是 | — | — | 否 | 否 | ["public.tasks.id"] | ["ix_issues_task_id"] | — | 问题：关联执行任务标识 | INTERNAL |
| reported_by | integer | 否 | — | — | 否 | 否 | ["public.users.id"] | ["ix_issues_reported_by"] | — | 问题：问题报告人用户标识 | INTERNAL |
| title | character varying(300) | 否 | — | — | 否 | 否 | [] | [] | — | 问题：该业务对象的标题 | PUBLIC |
| description | text | 否 | — | — | 否 | 否 | [] | [] | — | 问题：业务描述原文 | SENSITIVE |
| severity | character varying(16) | 否 | — | MEDIUM | 否 | 否 | [] | [] | — | 问题：问题严重程度 | PUBLIC |
| status | character varying(16) | 否 | — | OPEN | 否 | 否 | [] | [] | — | 问题：该对象状态；必须使用本表状态字典 | PUBLIC |
| suggested_solution | text | 是 | — | — | 否 | 否 | [] | [] | — | 问题：问题最新建议文本，历史版本见 advice_records | PUBLIC |
| resolved_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 问题：问题或风险解决时间 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 问题：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 问题：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| task_id | 否 | 否 | 否 | [] | 是 | [] | — |
| reported_by | 否 | 否 | 否 | [] | 否 | [] | — |
| title | 是 | 是 | 是 | [] | 否 | [] | — |
| description | 否 | 否 | 否 | [] | 否 | [] | — |
| severity | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["LOW", "MEDIUM", "HIGH", "CRITICAL"] | — |
| status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["OPEN", "IN_PROGRESS", "RESOLVED"] | — |
| suggested_solution | 是 | 否 | 否 | [] | 否 | [] | — |
| resolved_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| issues_pkey | p | PRIMARY KEY (id) |
| issues_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| issues_reported_by_fkey | f | FOREIGN KEY (reported_by) REFERENCES users(id) ON DELETE RESTRICT |
| issues_task_id_fkey | f | FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| issues_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| ix_issues_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| ix_issues_reported_by | btree | 否 | 否 | ["reported_by"] | — | 是 |
| ix_issues_task_id | btree | 否 | 否 | ["task_id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：can_view_issue(db, actor, issue)。禁止直接修改。

## public.milestones · 里程碑 / Milestone

模块：`planning`。用途：一个项目中的验收或交付节点。粒度：一条记录代表一个项目中的验收或交付节点。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/planning.py:71`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('milestones_id_seq'::regclass) | — | 是 | 是 | [] | ["milestones_pkey"] | — | 里程碑：记录主键，内部定位使用 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_milestones_project_id"] | — | 里程碑：所属或关联项目的内部标识 | INTERNAL |
| name | character varying(200) | 否 | — | — | 否 | 否 | [] | [] | — | 里程碑：该业务对象的显示名称 | PUBLIC |
| deliverable | text | 是 | — | — | 否 | 否 | [] | [] | — | 里程碑：预期交付物 | PUBLIC |
| acceptance_criteria | text | 是 | — | — | 否 | 否 | [] | [] | — | 里程碑：交付验收标准 | PUBLIC |
| target_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 里程碑：项目或里程碑目标日期 | PUBLIC |
| owner_id | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 里程碑：业务主负责人用户标识（不是创建人） | INTERNAL |
| status | character varying(20) | 否 | 'PLANNED'::character varying | PLANNED | 否 | 否 | [] | [] | — | 里程碑：该对象状态；必须使用本表状态字典 | PUBLIC |
| achieved_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 里程碑：里程碑实际达成日期 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 里程碑：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 里程碑：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| name | 是 | 是 | 是 | [] | 否 | [] | — |
| deliverable | 是 | 否 | 否 | [] | 否 | [] | — |
| acceptance_criteria | 是 | 否 | 否 | [] | 否 | [] | — |
| target_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| owner_id | 否 | 否 | 否 | [] | 是 | [] | — |
| status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["PLANNED", "ACHIEVED", "CANCELLED"] | — |
| achieved_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| ck_milestone_status | c | CHECK (((status)::text = ANY ((ARRAY['PLANNED'::character varying, 'ACHIEVED'::character varying, 'CANCELLED'::character varying])::text[]))) |
| milestones_owner_id_fkey | f | FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT |
| milestones_pkey | p | PRIMARY KEY (id) |
| milestones_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ix_milestones_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| milestones_pkey | btree | 是 | 是 | ["id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：父项目 can_view_project；用户 DTO 最小披露。禁止直接修改。

## public.notification_events · 通知事件 / NotificationEvent

模块：`notification`。用途：某业务事件向某收件人在某渠道的一次通知意图。粒度：一条记录代表某业务事件向某收件人在某渠道的一次通知意图。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：37（非精确）。证据：`backend/app/models/notification.py:41`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('plan_notification_events_id_seq'::regclass) | — | 是 | 是 | [] | ["plan_notification_events_pkey"] | — | 通知事件：记录主键，内部定位使用 | INTERNAL |
| proposal_id | character varying(36) | 是 | — | — | 否 | 否 | ["public.change_proposals.id"] | ["ix_notification_events_proposal_id"] | — | 通知事件：关联计划变更方案标识（字符串主键） | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_notification_events_project_id"] | — | 通知事件：所属或关联项目的内部标识 | INTERNAL |
| recipient_id | integer | 否 | — | — | 否 | 否 | ["public.users.id"] | ["ix_notification_events_recipient_id", "uq_notification_recipient"] | — | 通知事件：通知收件人用户标识 | INTERNAL |
| payload | json | 否 | — | — | 否 | 否 | [] | [] | — | 通知事件：内部结构化载荷，必须经 DTO 白名单脱敏 | SENSITIVE |
| status | character varying(16) | 否 | 'QUEUED'::character varying | QUEUED | 否 | 否 | [] | ["ix_notification_events_status"] | — | 通知事件：该对象状态；必须使用本表状态字典 | PUBLIC |
| attempts | integer | 否 | 0 | 0 | 否 | 否 | [] | [] | — | 通知事件：执行或投递尝试次数 | PUBLIC |
| last_error | text | 是 | — | — | 否 | 否 | [] | [] | — | 通知事件：最近通知错误，可能含内部信息 | SENSITIVE |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 通知事件：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 通知事件：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |
| event_type | character varying(32) | 否 | 'PLAN_CHANGE'::character varying | PLAN_CHANGE | 否 | 否 | [] | [] | — | 通知事件：风险或通知事件种类，按表区分 | PUBLIC |
| channel | character varying(32) | 否 | 'console'::character varying | console | 否 | 否 | [] | ["uq_notification_recipient"] | — | 通知事件：通知投递渠道 | PUBLIC |
| next_attempt_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 通知事件：下一次通知重试时间 | PUBLIC |
| sent_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 通知事件：渠道接受通知时间，不代表阅读 | PUBLIC |
| delivery_uncertain | boolean | 否 | false | 否 | 否 | 否 | [] | [] | — | 通知事件：渠道超时导致投递结果不确定 | PUBLIC |
| acknowledged_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 通知事件：收件人在系统确认知悉时间 | PUBLIC |
| dedupe_key | character varying(160) | 否 | — | — | 否 | 否 | [] | ["ix_notification_events_dedupe_key", "uq_notification_recipient"] | — | 通知事件：业务事件去重标识，内部使用 | INTERNAL |
| risk_event_id | integer | 是 | — | — | 否 | 否 | ["public.risk_events.id"] | ["ix_notification_events_risk_event_id"] | — | 通知事件：关联风险事件标识，通知来源之一 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| proposal_id | 否 | 否 | 否 | [] | 否 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| recipient_id | 否 | 否 | 否 | [] | 否 | [] | — |
| payload | 否 | 否 | 否 | [] | 否 | [] | — |
| status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["QUEUED", "SENT", "FAILED", "ACKNOWLEDGED"] | — |
| attempts | 是 | 是 | 否 | [] | 否 | [] | — |
| last_error | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| event_type | 是 | 否 | 否 | [] | 否 | ["PLAN_CHANGE", "RISK_OPENED", "RISK_ESCALATED", "RISK_RESOLVED"] | — |
| channel | 是 | 否 | 否 | [] | 否 | [] | — |
| next_attempt_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| sent_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| delivery_uncertain | 是 | 否 | 否 | [] | 否 | [] | — |
| acknowledged_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| dedupe_key | 否 | 否 | 否 | [] | 否 | [] | — |
| risk_event_id | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| ck_notification_one_source | c | CHECK (((proposal_id IS NULL) <> (risk_event_id IS NULL))) |
| ck_notification_status | c | CHECK (((status)::text = ANY ((ARRAY['QUEUED'::character varying, 'SENT'::character varying, 'FAILED'::character varying, 'ACKNOWLEDGED'::character varying])::text[]))) |
| fk_notification_risk | f | FOREIGN KEY (risk_event_id) REFERENCES risk_events(id) ON DELETE CASCADE |
| plan_notification_events_pkey | p | PRIMARY KEY (id) |
| plan_notification_events_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| plan_notification_events_proposal_id_fkey | f | FOREIGN KEY (proposal_id) REFERENCES change_proposals(id) ON DELETE CASCADE |
| plan_notification_events_recipient_id_fkey | f | FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE RESTRICT |
| uq_notification_recipient | u | UNIQUE (dedupe_key, recipient_id, channel) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ix_notification_events_dedupe_key | btree | 否 | 否 | ["dedupe_key"] | — | 是 |
| ix_notification_events_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| ix_notification_events_proposal_id | btree | 否 | 否 | ["proposal_id"] | — | 是 |
| ix_notification_events_recipient_id | btree | 否 | 否 | ["recipient_id"] | — | 是 |
| ix_notification_events_risk_event_id | btree | 否 | 否 | ["risk_event_id"] | — | 是 |
| ix_notification_events_status | btree | 否 | 否 | ["status"] | — | 是 |
| plan_notification_events_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| uq_notification_recipient | btree | 否 | 是 | ["dedupe_key", "recipient_id", "channel"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：本人 recipient_id；方案通知管理列表走 NotificationDeliveryService 专项权限。禁止直接修改。

## public.plan_drafts · 项目计划草案 / PlanDraft

模块：`planning`。用途：尚未发布的结构化项目计划，发布后关联项目。粒度：一条记录代表尚未发布的结构化项目计划，发布后关联项目。

表 COMMENT：UNKNOWN。主键：`id`；策略：`APPLICATION_STRING_ID`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/plan_draft.py:27`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | character varying(36) | 否 | — | — | 是 | 是 | [] | ["plan_drafts_pkey"] | — | 项目计划草案：记录主键，内部定位使用 | INTERNAL |
| created_by | integer | 否 | — | — | 否 | 否 | ["public.users.id"] | ["ix_plan_drafts_created_by", "uq_plan_draft_create_key"] | — | 项目计划草案：创建人用户标识 | INTERNAL |
| title | character varying(200) | 否 | — | — | 否 | 否 | [] | [] | — | 项目计划草案：该业务对象的标题 | PUBLIC |
| status | character varying(16) | 否 | 'DRAFT'::character varying | DRAFT | 否 | 否 | [] | ["ix_plan_drafts_status"] | — | 项目计划草案：该对象状态；必须使用本表状态字典 | PUBLIC |
| revision | integer | 否 | 1 | 1 | 否 | 否 | [] | [] | — | 项目计划草案：草案或方案内容修订号，用于乐观并发控制 | INTERNAL |
| content | json | 否 | — | — | 否 | 否 | [] | [] | — | 项目计划草案：待发布计划 JSON，不是当前已生效计划 | SENSITIVE |
| review | json | 是 | — | — | 否 | 否 | [] | [] | — | 项目计划草案：草案结构化校验结果 | SENSITIVE |
| digest | character varying(64) | 是 | — | — | 否 | 否 | [] | [] | — | 项目计划草案：审核内容摘要，交互确认仅由受控业务 DTO 提供 | INTERNAL |
| create_key | character varying(100) | 否 | — | — | 否 | 否 | [] | ["uq_plan_draft_create_key"] | — | 项目计划草案：创建幂等键 | INTERNAL |
| publish_key | character varying(100) | 是 | — | — | 否 | 是 | [] | ["plan_drafts_publish_key_key"] | — | 项目计划草案：发布幂等键 | INTERNAL |
| project_id | integer | 是 | — | — | 否 | 否 | ["public.projects.id"] | [] | — | 项目计划草案：所属或关联项目的内部标识 | INTERNAL |
| published_by | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 项目计划草案：计划发布人 | INTERNAL |
| published_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 项目计划草案：计划发布完成时间 | PUBLIC |
| result | json | 是 | — | — | 否 | 否 | [] | [] | — | 项目计划草案：执行结果载荷，须受控投影 | SENSITIVE |
| failure_reason | text | 是 | — | — | 否 | 否 | [] | [] | — | 项目计划草案：执行失败原因，须脱敏 | SENSITIVE |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 项目计划草案：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 项目计划草案：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| created_by | 否 | 否 | 否 | [] | 否 | [] | — |
| title | 是 | 是 | 是 | [] | 否 | [] | — |
| status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["DRAFT", "REVIEWED", "PUBLISHED", "DISCARDED", "FAILED"] | — |
| revision | 否 | 否 | 否 | [] | 否 | [] | — |
| content | 否 | 否 | 否 | [] | 否 | [] | — |
| review | 否 | 否 | 否 | [] | 否 | [] | — |
| digest | 否 | 否 | 否 | [] | 否 | [] | — |
| create_key | 否 | 否 | 否 | [] | 否 | [] | — |
| publish_key | 否 | 否 | 否 | [] | 否 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| published_by | 否 | 否 | 否 | [] | 否 | [] | — |
| published_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| result | 否 | 否 | 否 | [] | 否 | [] | — |
| failure_reason | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| ck_plan_draft_revision | c | CHECK ((revision >= 1)) |
| ck_plan_draft_status | c | CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'REVIEWED'::character varying, 'PUBLISHED'::character varying, 'DISCARDED'::character varying, 'FAILED'::character varying])::text[]))) |
| plan_drafts_created_by_fkey | f | FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT |
| plan_drafts_pkey | p | PRIMARY KEY (id) |
| plan_drafts_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL |
| plan_drafts_publish_key_key | u | UNIQUE (publish_key) |
| plan_drafts_published_by_fkey | f | FOREIGN KEY (published_by) REFERENCES users(id) ON DELETE RESTRICT |
| uq_plan_draft_create_key | u | UNIQUE (created_by, create_key) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ix_plan_drafts_created_by | btree | 否 | 否 | ["created_by"] | — | 是 |
| ix_plan_drafts_status | btree | 否 | 否 | ["status"] | — | 是 |
| plan_drafts_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| plan_drafts_publish_key_key | btree | 否 | 是 | ["publish_key"] | — | 是 |
| uq_plan_draft_create_key | btree | 否 | 是 | ["created_by", "create_key"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：ACTIVE 的 ADMIN/PROJECT_OWNER 角色；仅 created_by=actor.id 或 ADMIN；调用 PlanDraftService._draft。禁止直接修改。

## public.plan_versions · 计划快照 / PlanVersion

模块：`planning`。用途：一个项目的一个不可直接修改的历史计划版本。粒度：一条记录代表一个项目的一个不可直接修改的历史计划版本。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/planning.py:128`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('plan_versions_id_seq'::regclass) | — | 是 | 是 | [] | ["plan_versions_pkey"] | — | 计划快照：记录主键，内部定位使用 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_plan_versions_project_id", "uq_plan_version"] | — | 计划快照：所属或关联项目的内部标识 | INTERNAL |
| version | integer | 否 | — | — | 否 | 否 | [] | ["uq_plan_version"] | — | 计划快照：项目内唯一的计划版本序号，不是全局主键 | INTERNAL |
| kind | character varying(24) | 否 | — | SNAPSHOT | 否 | 否 | [] | [] | — | 计划快照：计划快照种类 | PUBLIC |
| reason | character varying(2000) | 否 | — | — | 否 | 否 | [] | [] | — | 计划快照：业务变更或计划快照原因 | PUBLIC |
| created_by | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 计划快照：创建人用户标识 | INTERNAL |
| snapshot | json | 否 | — | — | 否 | 否 | [] | [] | — | 计划快照：不可直接修改的结构化计划历史快照 | SENSITIVE |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 计划快照：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 计划快照：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| version | 否 | 否 | 否 | [] | 否 | [] | — |
| kind | 是 | 否 | 否 | [] | 否 | ["SNAPSHOT"] | — |
| reason | 是 | 否 | 否 | [] | 否 | [] | — |
| created_by | 否 | 否 | 否 | [] | 否 | [] | — |
| snapshot | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| plan_versions_created_by_fkey | f | FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL |
| plan_versions_pkey | p | PRIMARY KEY (id) |
| plan_versions_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| uq_plan_version | u | UNIQUE (project_id, version) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ix_plan_versions_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| plan_versions_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| uq_plan_version | btree | 否 | 是 | ["project_id", "version"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在。禁止直接修改。

## public.progress_updates · 进度汇报 / ProgressUpdate

模块：`execution`。用途：某用户向某任务提交的一次原始汇报及异步分析结果。粒度：一条记录代表某用户向某任务提交的一次原始汇报及异步分析结果。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/progress_update.py:13`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('progress_updates_id_seq'::regclass) | — | 是 | 是 | [] | ["progress_updates_pkey"] | — | 进度汇报：记录主键，内部定位使用 | INTERNAL |
| task_id | integer | 否 | — | — | 否 | 否 | ["public.tasks.id"] | ["ix_progress_updates_task_id"] | — | 进度汇报：关联执行任务标识 | INTERNAL |
| user_id | integer | 否 | — | — | 否 | 否 | ["public.users.id"] | ["ix_progress_updates_user_id"] | — | 进度汇报：进度汇报提交人，可能为代报人，不等于任务负责人 | INTERNAL |
| raw_content | text | 否 | — | — | 否 | 否 | [] | [] | — | 进度汇报：用户提交的不可改写汇报原文 | SENSITIVE |
| summary | text | 是 | — | — | 否 | 否 | [] | [] | — | 进度汇报：业务或会话摘要；AI 摘要不等于原始事实 | PUBLIC |
| progress_percent | integer | 是 | — | — | 否 | 否 | [] | [] | — | 进度汇报：完成百分比，NULL 表示未知；任务快照和汇报分析值须区分 | PUBLIC |
| ai_status | character varying(16) | 是 | — | — | 否 | 否 | [] | [] | — | 进度汇报：AI 分析给出的状态参考，不是完成状态 | PUBLIC |
| risk_detected | boolean | 是 | — | — | 否 | 否 | [] | [] | — | 进度汇报：本次 AI 分析是否识别风险；NULL 为未知 | PUBLIC |
| ai_analysis_failed | boolean | 否 | false | 否 | 否 | 否 | [] | [] | — | 进度汇报：本次异步 AI 分析失败标志 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 进度汇报：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 进度汇报：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| task_id | 否 | 否 | 否 | [] | 是 | [] | — |
| user_id | 否 | 否 | 否 | [] | 是 | [] | — |
| raw_content | 否 | 否 | 否 | [] | 否 | [] | — |
| summary | 是 | 否 | 是 | [] | 否 | [] | — |
| progress_percent | 是 | 是 | 否 | ["count_non_null", "min", "max", "avg"] | 否 | [] | — |
| ai_status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["ON_TRACK", "AT_RISK", "DELAYED"] | — |
| risk_detected | 是 | 否 | 否 | [] | 否 | [] | — |
| ai_analysis_failed | 是 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| progress_updates_pkey | p | PRIMARY KEY (id) |
| progress_updates_task_id_fkey | f | FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE |
| progress_updates_user_id_fkey | f | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ix_progress_updates_task_id | btree | 否 | 否 | ["task_id"] | — | 是 |
| ix_progress_updates_user_id | btree | 否 | 否 | ["user_id"] | — | 是 |
| progress_updates_pkey | btree | 是 | 是 | ["id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：先 can_view_task，再查询该任务汇报。禁止直接修改。

## public.project_members · 项目成员 / ProjectMember

模块：`identity`。用途：一个项目与一个用户的成员关系及有效性。粒度：一条记录代表一个项目与一个用户的成员关系及有效性。

表 COMMENT：UNKNOWN。主键：`project_id, user_id`；策略：`COMPOSITE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/planning.py:25`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| project_id | integer | 否 | — | — | 是 | 否 | ["public.projects.id"] | ["project_members_pkey"] | — | 项目成员：所属或关联项目的内部标识 | INTERNAL |
| user_id | integer | 否 | — | — | 是 | 否 | ["public.users.id"] | ["project_members_pkey"] | — | 项目成员：关联用户标识，具体角色见表用途 | INTERNAL |
| role | character varying(20) | 否 | 'CONTRIBUTOR'::character varying | CONTRIBUTOR | 否 | 否 | [] | [] | — | 项目成员：当前表上下文中的角色，用户权限角色与参与角色不可混用 | PUBLIC |
| receive_notifications | boolean | 否 | true | 是 | 否 | 否 | [] | [] | — | 项目成员：成员是否订阅通知 | PUBLIC |
| is_active | boolean | 否 | true | 是 | 否 | 否 | [] | [] | — | 项目成员：上下文有效性标志；成员有效性或记忆启用，不统一等于软删除 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 项目成员：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 项目成员：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| user_id | 否 | 否 | 否 | [] | 是 | [] | — |
| role | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["CONTRIBUTOR", "OBSERVER"] | — |
| receive_notifications | 是 | 否 | 否 | [] | 否 | [] | — |
| is_active | 是 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| ck_member_role | c | CHECK (((role)::text = ANY ((ARRAY['CONTRIBUTOR'::character varying, 'OBSERVER'::character varying])::text[]))) |
| project_members_pkey | p | PRIMARY KEY (project_id, user_id) |
| project_members_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| project_members_user_id_fkey | f | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| project_members_pkey | btree | 是 | 是 | ["project_id", "user_id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：父项目 can_view_project；用户 DTO 最小披露。禁止直接修改。

## public.project_owners · 项目负责人关系 / ProjectOwner

模块：`identity`。用途：一个项目与一个共同负责人的关联。粒度：一条记录代表一个项目与一个共同负责人的关联。

表 COMMENT：UNKNOWN。主键：`project_id, user_id`；策略：`COMPOSITE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/project.py:33`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| project_id | integer | 否 | — | — | 是 | 否 | ["public.projects.id"] | ["pk_project_owners"] | — | 项目负责人关系：所属或关联项目的内部标识 | INTERNAL |
| user_id | integer | 否 | — | — | 是 | 否 | ["public.users.id"] | ["ix_project_owners_user_id", "pk_project_owners"] | — | 项目负责人关系：关联用户标识，具体角色见表用途 | INTERNAL |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| user_id | 否 | 否 | 否 | [] | 是 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| pk_project_owners | p | PRIMARY KEY (project_id, user_id) |
| project_owners_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| project_owners_user_id_fkey | f | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ix_project_owners_user_id | btree | 否 | 否 | ["user_id"] | — | 是 |
| pk_project_owners | btree | 是 | 是 | ["project_id", "user_id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：父项目 can_view_project；用户 DTO 最小披露。禁止直接修改。

## public.projects · 项目 / Project

模块：`project_management`。用途：一个项目的当前目标、计划日期及主负责人。粒度：一条记录代表一个项目的当前目标、计划日期及主负责人。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/project.py:36`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('projects_id_seq'::regclass) | — | 是 | 是 | [] | ["projects_pkey"] | — | 项目：记录主键，内部定位使用 | INTERNAL |
| project_code | character varying(64) | 否 | — | — | 否 | 是 | [] | ["uq_projects_project_code"] | — | 项目：项目业务编号（示例为合成 PRJ-1001） | PUBLIC |
| project_name | character varying(200) | 否 | — | — | 否 | 否 | [] | [] | — | 项目：项目业务名称 | PUBLIC |
| goal | text | 是 | — | — | 否 | 否 | [] | [] | — | 项目：项目目标 | PUBLIC |
| owner_id | integer | 否 | — | — | 否 | 否 | ["public.users.id"] | ["ix_projects_owner_id"] | — | 项目：业务主负责人用户标识（不是创建人） | INTERNAL |
| target_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 项目：项目或里程碑目标日期 | PUBLIC |
| status | character varying(16) | 否 | — | ACTIVE | 否 | 否 | [] | [] | — | 项目：该对象状态；必须使用本表状态字典 | PUBLIC |
| risk_level | character varying(16) | 否 | — | NORMAL | 否 | 否 | [] | [] | — | 项目：项目风险等级或工具风险分类，见对应字典 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 项目：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 项目：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |
| start_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 项目：计划开始日期 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_code | 是 | 是 | 是 | [] | 否 | [] | PRJ-1001 |
| project_name | 是 | 是 | 是 | [] | 否 | [] | — |
| goal | 是 | 否 | 是 | [] | 否 | [] | — |
| owner_id | 否 | 否 | 否 | [] | 是 | [] | — |
| target_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["PLANNING", "ACTIVE", "COMPLETED", "CANCELLED"] | — |
| risk_level | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["NORMAL", "AT_RISK", "DELAYED"] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| start_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| projects_owner_id_fkey | f | FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT |
| projects_pkey | p | PRIMARY KEY (id) |
| uq_projects_project_code | u | UNIQUE (project_code) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ix_projects_owner_id | btree | 否 | 否 | ["owner_id"] | — | 是 |
| projects_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| uq_projects_project_code | btree | 否 | 是 | ["project_code"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：can_view_project(db, actor, project)。禁止直接修改。

## public.risk_events · 风险事件 / RiskEvent

模块：`risk`。用途：一个项目中由 dedupe_key 标识的可重复开启风险事实。粒度：一条记录代表一个项目中由 dedupe_key 标识的可重复开启风险事实。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/risk_event.py:57`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('risk_events_id_seq'::regclass) | — | 是 | 是 | [] | ["risk_events_pkey"] | — | 风险事件：记录主键，内部定位使用 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_risk_events_project_id", "ix_risk_events_project_status", "uq_risk_event_key"] | — | 风险事件：所属或关联项目的内部标识 | INTERNAL |
| task_id | integer | 是 | — | — | 否 | 否 | ["public.tasks.id"] | ["ix_risk_events_task_id"] | — | 风险事件：关联执行任务标识 | INTERNAL |
| issue_id | integer | 是 | — | — | 否 | 否 | ["public.issues.id"] | [] | — | 风险事件：关联问题标识 | INTERNAL |
| event_type | character varying(24) | 否 | — | — | 否 | 否 | [] | [] | — | 风险事件：风险或通知事件种类，按表区分 | PUBLIC |
| dedupe_key | character varying(120) | 否 | — | — | 否 | 否 | [] | ["uq_risk_event_key"] | — | 风险事件：业务事件去重标识，内部使用 | INTERNAL |
| level | character varying(16) | 否 | — | — | 否 | 否 | [] | [] | — | 风险事件：风险事件等级 | PUBLIC |
| status | character varying(16) | 否 | 'OPEN'::character varying | OPEN | 否 | 否 | [] | ["ix_risk_events_project_status", "ix_risk_events_status"] | — | 风险事件：该对象状态；必须使用本表状态字典 | PUBLIC |
| title | character varying(300) | 否 | — | — | 否 | 否 | [] | [] | — | 风险事件：该业务对象的标题 | PUBLIC |
| cause | text | 否 | — | — | 否 | 否 | [] | [] | — | 风险事件：风险检测触发原因 | PUBLIC |
| evidence | json | 是 | — | APPLICATION_CALLABLE:list | 否 | 否 | [] | [] | — | 风险事件：证据引用列表，含 source_type/source_id，需逐资源授权 | SENSITIVE |
| impact_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 风险事件：风险影响日期，依风险类型为截止或预测日期 | PUBLIC |
| impact_days | integer | 是 | — | — | 否 | 否 | [] | [] | — | 风险事件：预计/事实影响天数，不可与工期混用 | PUBLIC |
| owner_id | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 风险事件：业务主负责人用户标识（不是创建人） | INTERNAL |
| first_seen_at | timestamp with time zone | 否 | — | — | 否 | 否 | [] | [] | — | 风险事件：风险首次被识别时间 | PUBLIC |
| last_seen_at | timestamp with time zone | 否 | — | — | 否 | 否 | [] | [] | — | 风险事件：风险最近仍被识别时间 | PUBLIC |
| resolved_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 风险事件：问题或风险解决时间 | PUBLIC |
| resolution | text | 是 | — | — | 否 | 否 | [] | [] | — | 风险事件：风险关闭原因 | PUBLIC |
| resolved_by | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | [] | — | 风险事件：风险关闭操作人 | INTERNAL |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 风险事件：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 风险事件：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| task_id | 否 | 否 | 否 | [] | 是 | [] | — |
| issue_id | 否 | 否 | 否 | [] | 是 | [] | — |
| event_type | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["OVERDUE", "FORECAST_DELAY", "ISSUE", "MISSING_DATA"] | — |
| dedupe_key | 否 | 否 | 否 | [] | 否 | [] | — |
| level | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["AT_RISK", "DELAYED"] | — |
| status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["OPEN", "RESOLVED"] | — |
| title | 是 | 是 | 是 | [] | 否 | [] | — |
| cause | 是 | 否 | 否 | [] | 否 | [] | — |
| evidence | 否 | 否 | 否 | [] | 否 | [] | — |
| impact_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| impact_days | 是 | 是 | 否 | ["count_non_null", "min", "max", "avg"] | 否 | [] | — |
| owner_id | 否 | 否 | 否 | [] | 是 | [] | — |
| first_seen_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| last_seen_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| resolved_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| resolution | 是 | 否 | 否 | [] | 否 | [] | — |
| resolved_by | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| ck_risk_event_impact | c | CHECK (((impact_days IS NULL) OR (impact_days >= 0))) |
| risk_events_issue_id_fkey | f | FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE CASCADE |
| risk_events_owner_id_fkey | f | FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL |
| risk_events_pkey | p | PRIMARY KEY (id) |
| risk_events_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| risk_events_resolved_by_fkey | f | FOREIGN KEY (resolved_by) REFERENCES users(id) ON DELETE SET NULL |
| risk_events_task_id_fkey | f | FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE |
| uq_risk_event_key | u | UNIQUE (project_id, dedupe_key) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ix_risk_events_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| ix_risk_events_project_status | btree | 否 | 否 | ["project_id", "status"] | — | 是 |
| ix_risk_events_status | btree | 否 | 否 | ["status"] | — | 是 |
| ix_risk_events_task_id | btree | 否 | 否 | ["task_id"] | — | 是 |
| risk_events_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| uq_risk_event_key | btree | 否 | 是 | ["project_id", "dedupe_key"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：RiskEventService/AdviceService 过滤项目与具体任务/问题证据；不可原样返回 evidence JSON。禁止直接修改。

## public.task_groups · 任务组 / TaskGroup

模块：`planning`。用途：一个项目中的一个可嵌套任务分组节点。粒度：一条记录代表一个项目中的一个可嵌套任务分组节点。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/planning.py:91`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('task_groups_id_seq'::regclass) | — | 是 | 是 | [] | ["task_groups_pkey"] | — | 任务组：记录主键，内部定位使用 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_task_groups_project_id"] | — | 任务组：所属或关联项目的内部标识 | INTERNAL |
| name | character varying(200) | 否 | — | — | 否 | 否 | [] | [] | — | 任务组：该业务对象的显示名称 | PUBLIC |
| parent_id | integer | 是 | — | — | 否 | 否 | ["public.task_groups.id"] | [] | — | 任务组：父任务组标识；可构成树 | INTERNAL |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 任务组：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 任务组：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| name | 是 | 是 | 是 | [] | 否 | [] | — |
| parent_id | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| task_groups_parent_id_fkey | f | FOREIGN KEY (parent_id) REFERENCES task_groups(id) ON DELETE RESTRICT |
| task_groups_pkey | p | PRIMARY KEY (id) |
| task_groups_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ix_task_groups_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| task_groups_pkey | btree | 是 | 是 | ["id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在。禁止直接修改。

## public.task_links · 任务依赖 / TaskDependency

模块：`planning`。用途：同一项目中两个任务之间的一条有方向依赖。粒度：一条记录代表同一项目中两个任务之间的一条有方向依赖。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/task.py:178`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('task_links_id_seq'::regclass) | — | 是 | 是 | [] | ["task_links_pkey"] | — | 任务依赖：记录主键，内部定位使用 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_task_links_project_id"] | — | 任务依赖：所属或关联项目的内部标识 | INTERNAL |
| source_id | integer | 否 | — | — | 否 | 否 | ["public.tasks.id"] | ["ix_task_links_source_id", "uq_task_links_source_target"] | — | 任务依赖：依赖前驱任务标识 | INTERNAL |
| target_id | integer | 否 | — | — | 否 | 否 | ["public.tasks.id"] | ["ix_task_links_target_id", "uq_task_links_source_target"] | — | 任务依赖：依赖后继任务标识 | INTERNAL |
| link_type | character varying(20) | 否 | — | FINISH_TO_START | 否 | 否 | [] | [] | — | 任务依赖：任务依赖端点类型 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 任务依赖：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 任务依赖：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |
| lag_days | integer | 否 | 0 | 0 | 否 | 否 | [] | [] | — | 任务依赖：依赖等待天数，当前约束不允许负值 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| source_id | 否 | 否 | 否 | [] | 否 | [] | — |
| target_id | 否 | 否 | 否 | [] | 否 | [] | — |
| link_type | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["FINISH_TO_START", "START_TO_START", "FINISH_TO_FINISH", "START_TO_FINISH"] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| lag_days | 是 | 是 | 否 | ["count_non_null", "min", "max", "avg"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| ck_link_lag | c | CHECK ((lag_days >= 0)) |
| ck_task_links_no_self_reference | c | CHECK ((source_id <> target_id)) |
| task_links_pkey | p | PRIMARY KEY (id) |
| task_links_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| task_links_source_id_fkey | f | FOREIGN KEY (source_id) REFERENCES tasks(id) ON DELETE CASCADE |
| task_links_target_id_fkey | f | FOREIGN KEY (target_id) REFERENCES tasks(id) ON DELETE CASCADE |
| uq_task_links_source_target | u | UNIQUE (source_id, target_id) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ix_task_links_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| ix_task_links_source_id | btree | 否 | 否 | ["source_id"] | — | 是 |
| ix_task_links_target_id | btree | 否 | 否 | ["target_id"] | — | 是 |
| task_links_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| uq_task_links_source_target | btree | 否 | 是 | ["source_id", "target_id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：父项目可见且 source/target 任务分别可见。禁止直接修改。

## public.task_participants · 任务参与关系 / TaskParticipant

模块：`identity`。用途：一个任务与一个用户的单一参与角色；OWNER 为共同负责人。粒度：一条记录代表一个任务与一个用户的单一参与角色；OWNER 为共同负责人。

表 COMMENT：UNKNOWN。主键：`task_id, user_id`；策略：`COMPOSITE`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/planning.py:41`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| task_id | integer | 否 | — | — | 是 | 否 | ["public.tasks.id"] | ["task_participants_pkey"] | — | 任务参与关系：关联执行任务标识 | INTERNAL |
| user_id | integer | 否 | — | — | 是 | 否 | ["public.users.id"] | ["task_participants_pkey"] | — | 任务参与关系：关联用户标识，具体角色见表用途 | INTERNAL |
| role | character varying(20) | 否 | 'COLLABORATOR'::character varying | COLLABORATOR | 否 | 否 | [] | [] | — | 任务参与关系：当前表上下文中的角色，用户权限角色与参与角色不可混用 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 任务参与关系：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 任务参与关系：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| task_id | 否 | 否 | 否 | [] | 是 | [] | — |
| user_id | 否 | 否 | 否 | [] | 是 | [] | — |
| role | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["COLLABORATOR", "WATCHER", "OWNER"] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| ck_participant_role | c | CHECK (((role)::text = ANY ((ARRAY['COLLABORATOR'::character varying, 'WATCHER'::character varying, 'OWNER'::character varying])::text[]))) |
| task_participants_pkey | p | PRIMARY KEY (task_id, user_id) |
| task_participants_task_id_fkey | f | FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE |
| task_participants_user_id_fkey | f | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| task_participants_pkey | btree | 是 | 是 | ["task_id", "user_id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：任务可见，用户 DTO 最小披露。禁止直接修改。

## public.tasks · 执行任务 / Task

模块：`execution`。用途：一个执行任务的当前计划、实际执行信息及状态。粒度：一条记录代表一个执行任务的当前计划、实际执行信息及状态。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：24（非精确）。证据：`backend/app/models/task.py:48`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('tasks_id_seq'::regclass) | — | 是 | 是 | [] | ["tasks_pkey"] | — | 执行任务：记录主键，内部定位使用 | INTERNAL |
| project_id | integer | 否 | — | — | 否 | 否 | ["public.projects.id"] | ["ix_tasks_project_id", "ix_tasks_work_stream"] | — | 执行任务：所属或关联项目的内部标识 | INTERNAL |
| task_name | character varying(300) | 否 | — | — | 否 | 否 | [] | [] | — | 执行任务：任务名称 | PUBLIC |
| owner_id | integer | 是 | — | — | 否 | 否 | ["public.users.id"] | ["ix_tasks_owner_id"] | — | 执行任务：业务主负责人用户标识（不是创建人） | INTERNAL |
| due_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：任务或行动项计划截止日期 | PUBLIC |
| status | character varying(16) | 否 | — | TODO | 否 | 否 | [] | [] | — | 执行任务：该对象状态；必须使用本表状态字典 | PUBLIC |
| ai_status | character varying(16) | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：AI 分析给出的状态参考，不是完成状态 | PUBLIC |
| ai_risk_level | character varying(16) | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：任务 AI 风险参考等级 | PUBLIC |
| completed_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：对象完成事件时间，具体为任务完成或请求/消息/作业结束 | PUBLIC |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 执行任务：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 执行任务：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |
| start_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：计划开始日期 | PUBLIC |
| progress_percent | integer | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：完成百分比，NULL 表示未知；任务快照和汇报分析值须区分 | PUBLIC |
| work_stream | character varying(120) | 是 | — | — | 否 | 否 | [] | ["ix_tasks_work_stream"] | — | 执行任务：自由文本工作流分组，不是 FK，不等于 task_group_id | PUBLIC |
| branch_root_id | integer | 是 | — | — | 否 | 否 | ["public.tasks.id"] | ["ix_tasks_branch_root_id"] | — | 执行任务：旧版路线共同根任务标识，不是通用父子任务 | INTERNAL |
| branch_label | character varying(80) | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：旧版路线标签 | PUBLIC |
| is_active_branch | boolean | 否 | true | 是 | 否 | 否 | [] | [] | — | 执行任务：是否当前激活路线，false 不是删除 | PUBLIC |
| risk_context_changed_at | timestamp with time zone | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：计划或问题变化导致风险证据失效的时间边界 | INTERNAL |
| description | text | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：业务描述原文 | SENSITIVE |
| deliverable | text | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：预期交付物 | PUBLIC |
| acceptance_criteria | text | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：交付验收标准 | PUBLIC |
| planned_duration_days | integer | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：计划工期天数，至少 1，依工作日历解释 | PUBLIC |
| remaining_duration_days | integer | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：剩余工期天数，可为 0 | PUBLIC |
| actual_start_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：任务实际开始日期 | PUBLIC |
| actual_finish_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：任务实际结束日期 | PUBLIC |
| earliest_start_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：排期约束：最早允许开始日期 | PUBLIC |
| fixed_start_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：排期约束：固定开始日期 | PUBLIC |
| fixed_due_date | date | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：排期约束：固定截止日期 | PUBLIC |
| branch_suspended_status | character varying(16) | 是 | — | — | 否 | 否 | [] | [] | — | 执行任务：路线停用前保留的任务状态 | INTERNAL |
| calendar_id | integer | 是 | — | — | 否 | 否 | ["public.work_calendars.project_id"] | [] | — | 执行任务：任务工作日历键，指向 work_calendars.project_id（无 calendar.id） | INTERNAL |
| milestone_id | integer | 是 | — | — | 否 | 否 | ["public.milestones.id"] | [] | — | 执行任务：任务关联里程碑 | INTERNAL |
| task_group_id | integer | 是 | — | — | 否 | 否 | ["public.task_groups.id"] | [] | — | 执行任务：任务所属结构化分组 | INTERNAL |
| branch_option_id | integer | 是 | — | — | 否 | 否 | ["public.branch_options.id"] | [] | — | 执行任务：任务所属路线选项 | INTERNAL |
| version | integer | 否 | 1 | 1 | 否 | 否 | [] | [] | — | 执行任务：任务乐观锁版本，变更需携带 expected_version | INTERNAL |
| task_code | character varying(64) | 是 | — | — | 否 | 是 | [] | ["uq_tasks_task_code"] | — | 执行任务：任务业务编号，历史记录可为空；不是 tasks.id | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| task_name | 是 | 是 | 是 | [] | 否 | [] | — |
| owner_id | 否 | 否 | 否 | [] | 是 | [] | — |
| due_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["TODO", "IN_PROGRESS", "COMPLETED", "CANCELLED"] | — |
| ai_status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["ON_TRACK", "AT_RISK", "DELAYED"] | — |
| ai_risk_level | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["ON_TRACK", "AT_RISK", "DELAYED"] | — |
| completed_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| start_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| progress_percent | 是 | 是 | 否 | ["count_non_null", "min", "max", "avg"] | 否 | [] | — |
| work_stream | 是 | 否 | 是 | ["count", "group_by"] | 否 | [] | — |
| branch_root_id | 否 | 否 | 否 | [] | 否 | [] | — |
| branch_label | 是 | 否 | 否 | [] | 否 | [] | — |
| is_active_branch | 是 | 否 | 否 | [] | 否 | [] | — |
| risk_context_changed_at | 否 | 否 | 否 | [] | 否 | [] | — |
| description | 否 | 否 | 否 | [] | 否 | [] | — |
| deliverable | 是 | 否 | 否 | [] | 否 | [] | — |
| acceptance_criteria | 是 | 否 | 否 | [] | 否 | [] | — |
| planned_duration_days | 是 | 是 | 否 | ["count_non_null", "min", "max", "avg"] | 否 | [] | — |
| remaining_duration_days | 是 | 是 | 否 | ["count_non_null", "min", "max", "avg"] | 否 | [] | — |
| actual_start_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| actual_finish_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| earliest_start_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| fixed_start_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| fixed_due_date | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| branch_suspended_status | 否 | 否 | 否 | [] | 否 | [] | — |
| calendar_id | 否 | 否 | 否 | [] | 否 | [] | — |
| milestone_id | 否 | 否 | 否 | [] | 是 | [] | — |
| task_group_id | 否 | 否 | 否 | [] | 是 | [] | — |
| branch_option_id | 否 | 否 | 否 | [] | 否 | [] | — |
| version | 否 | 否 | 否 | [] | 否 | [] | — |
| task_code | 是 | 是 | 是 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| ck_task_planned_duration | c | CHECK (((planned_duration_days IS NULL) OR (planned_duration_days >= 1))) |
| ck_task_remaining_duration | c | CHECK (((remaining_duration_days IS NULL) OR (remaining_duration_days >= 0))) |
| ck_tasks_progress_percent_range | c | CHECK (((progress_percent IS NULL) OR ((progress_percent >= 0) AND (progress_percent <= 100)))) |
| fk_tasks_branch_option_id | f | FOREIGN KEY (branch_option_id) REFERENCES branch_options(id) ON DELETE RESTRICT |
| fk_tasks_branch_root_id | f | FOREIGN KEY (branch_root_id) REFERENCES tasks(id) ON DELETE SET NULL |
| fk_tasks_calendar_id | f | FOREIGN KEY (calendar_id) REFERENCES work_calendars(project_id) ON DELETE RESTRICT |
| fk_tasks_milestone_id | f | FOREIGN KEY (milestone_id) REFERENCES milestones(id) ON DELETE RESTRICT |
| fk_tasks_task_group_id | f | FOREIGN KEY (task_group_id) REFERENCES task_groups(id) ON DELETE RESTRICT |
| tasks_owner_id_fkey | f | FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT |
| tasks_pkey | p | PRIMARY KEY (id) |
| tasks_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |
| uq_tasks_task_code | u | UNIQUE (task_code) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| ix_tasks_branch_root_id | btree | 否 | 否 | ["branch_root_id"] | — | 是 |
| ix_tasks_owner_id | btree | 否 | 否 | ["owner_id"] | — | 是 |
| ix_tasks_project_id | btree | 否 | 否 | ["project_id"] | — | 是 |
| ix_tasks_work_stream | btree | 否 | 否 | ["project_id", "work_stream"] | — | 是 |
| tasks_pkey | btree | 是 | 是 | ["id"] | — | 是 |
| uq_tasks_task_code | btree | 否 | 是 | ["task_code"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：can_view_task(db, actor, task)。禁止直接修改。

## public.users · 用户 / User

模块：`identity`。用途：一个本地用户账号及角色；外部身份仅映射。粒度：一条记录代表一个本地用户账号及角色；外部身份仅映射。

表 COMMENT：UNKNOWN。主键：`id`；策略：`SERIAL_SEQUENCE`。估计行数：36（非精确）。证据：`backend/app/models/user.py:26`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| id | integer | 否 | nextval('users_id_seq'::regclass) | — | 是 | 是 | [] | ["users_pkey"] | — | 用户：记录主键，内部定位使用 | INTERNAL |
| name | character varying(100) | 否 | — | — | 否 | 否 | [] | [] | — | 用户：用户显示姓名，可能重名，写操作必须消歧 | PUBLIC |
| username | character varying(64) | 否 | — | — | 否 | 是 | [] | ["uq_users_username"] | — | 用户：用户登录名，可用于人员消歧 | PUBLIC |
| email | character varying(255) | 是 | — | — | 否 | 是 | [] | ["uq_users_email"] | — | 用户：用户邮箱，个人敏感信息 | SENSITIVE |
| mobile | character varying(32) | 是 | — | — | 否 | 否 | [] | [] | — | 用户：用户手机号，个人敏感信息 | SENSITIVE |
| department | character varying(128) | 是 | — | — | 否 | 否 | [] | [] | — | 用户：用户部门文本，不是组织隔离键或部门 FK | PUBLIC |
| wechat_user_id | character varying(128) | 是 | — | — | 否 | 否 | [] | [] | — | 用户：外部通知系统用户标识 | SENSITIVE |
| role | character varying(32) | 否 | — | MEMBER | 否 | 否 | [] | [] | — | 用户：当前表上下文中的角色，用户权限角色与参与角色不可混用 | PUBLIC |
| status | character varying(16) | 否 | — | ACTIVE | 否 | 否 | [] | [] | — | 用户：该对象状态；必须使用本表状态字典 | PUBLIC |
| password_hash | text | 否 | — | — | 否 | 否 | [] | [] | — | 用户：密码验证散列，禁止 Agent 查询、输出或索引入 RAG | HIDDEN |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 用户：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 用户：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |
| oa_admin_id | integer | 是 | — | — | 否 | 是 | [] | ["uq_users_oa_admin_id"] | — | 用户：外部 OA 账号标识，非本库用户 FK | SENSITIVE |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 否 | 否 | 否 | [] | 是 | [] | — |
| name | 是 | 是 | 是 | [] | 否 | [] | — |
| username | 是 | 否 | 否 | [] | 否 | [] | — |
| email | 否 | 否 | 否 | [] | 否 | [] | — |
| mobile | 否 | 否 | 否 | [] | 否 | [] | — |
| department | 是 | 否 | 否 | ["count", "group_by"] | 否 | [] | — |
| wechat_user_id | 否 | 否 | 否 | [] | 否 | [] | — |
| role | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["ADMIN", "EXECUTIVE", "PROJECT_OWNER", "MEMBER"] | — |
| status | 是 | 否 | 否 | ["count", "group_by"] | 否 | ["ACTIVE", "INACTIVE"] | — |
| password_hash | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| oa_admin_id | 否 | 否 | 否 | [] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| uq_users_email | u | UNIQUE (email) |
| uq_users_oa_admin_id | u | UNIQUE (oa_admin_id) |
| uq_users_username | u | UNIQUE (username) |
| users_pkey | p | PRIMARY KEY (id) |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| uq_users_email | btree | 否 | 是 | ["email"] | — | 是 |
| uq_users_oa_admin_id | btree | 否 | 是 | ["oa_admin_id"] | — | 是 |
| uq_users_username | btree | 否 | 是 | ["username"] | — | 是 |
| users_pkey | btree | 是 | 是 | ["id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：已认证；现有 QueryService 返回 ACTIVE 用户目录的白名单 DTO；非租户范围。禁止直接修改。

## public.work_calendars · 项目工作日历 / WorkCalendar

模块：`planning`。用途：一个项目的一份版本化工作日历，以 project_id 为主键。粒度：一条记录代表一个项目的一份版本化工作日历，以 project_id 为主键。

表 COMMENT：UNKNOWN。主键：`project_id`；策略：`BUSINESS_KEY`。估计行数：UNKNOWN（非精确）。证据：`backend/app/models/planning.py:57`。

| Column | Type | Nullable | DB Default | App Default | PK | Unique | FK | Index | Comment | Business Meaning | Agent Visibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| project_id | integer | 否 | — | — | 是 | 是 | ["public.projects.id"] | ["work_calendars_pkey"] | — | 项目工作日历：所属或关联项目的内部标识 | INTERNAL |
| name | character varying(120) | 否 | — | 项目工作日历 | 否 | 否 | [] | [] | — | 项目工作日历：该业务对象的显示名称 | PUBLIC |
| timezone | character varying(64) | 否 | — | Asia/Shanghai | 否 | 否 | [] | [] | — | 项目工作日历：日历或业务时区名称 | PUBLIC |
| weekdays | json | 否 | — | APPLICATION_CALLABLE:<lambda> | 否 | 否 | [] | [] | — | 项目工作日历：工作日编号列表，模型默认 0–4 表示周一至周五 | PUBLIC |
| exceptions | json | 否 | — | APPLICATION_CALLABLE:dict | 否 | 否 | [] | [] | — | 项目工作日历：特殊日期到是否工作日的映射 | PUBLIC |
| version | integer | 否 | — | 1 | 否 | 否 | [] | [] | — | 项目工作日历：版本计数，具体为任务并发版本、项目计划版本或日历版本 | INTERNAL |
| created_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 项目工作日历：记录创建时间，不是计划开始或汇报涵盖日期 | PUBLIC |
| updated_at | timestamp with time zone | 否 | now() | — | 否 | 否 | [] | [] | — | 项目工作日历：记录最后更新时间，包含分析及后台更新，不是进度日期；ORM onupdate 不等于数据库触发器 | PUBLIC |

### 字段查询建议

推荐能力须由 Query Service 实现白名单；不代表现有 DSL 已支持。INTERNAL lookup 仅业务服务定位使用。SENSITIVE 需独立 DTO 处理，不允许通用字段查询。

| 字段 | 筛选 | 排序 | 文本检索 | 聚合 | 服务内部 lookup | 状态值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| project_id | 否 | 否 | 否 | [] | 是 | [] | — |
| name | 是 | 是 | 是 | [] | 否 | [] | — |
| timezone | 是 | 否 | 否 | [] | 否 | [] | — |
| weekdays | 是 | 否 | 否 | [] | 否 | [] | — |
| exceptions | 是 | 否 | 否 | [] | 否 | [] | — |
| version | 否 | 否 | 否 | [] | 否 | [] | — |
| created_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |
| updated_at | 是 | 是 | 否 | ["count_non_null", "min", "max"] | 否 | [] | — |

### 约束与索引

| 约束名 | 类型 | 定义 |
| --- | --- | --- |
| ck_calendar_version | c | CHECK ((version >= 1)) |
| work_calendars_pkey | p | PRIMARY KEY (project_id) |
| work_calendars_project_id_fkey | f | FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE |

| 索引 | 方法 | 主键 | 唯一 | 列顺序 | 条件 | 有效 |
| --- | --- | --- | --- | --- | --- | --- |
| work_calendars_pkey | btree | 是 | 是 | ["project_id"] | — | 是 |

读取策略：SCOPED_DTO_ONLY。范围：保守使用 can_view_full_project；复用对应业务接口权限，不能只判断 project_id 存在。禁止直接修改。

