# 项目助手运行时（AgentScope + 结构化操作）

**产品**：AI 项目管理 Agent  
**范围**：项目助手的 ReAct 编排，以及受控的结构化查询 / 批量写入。  
**依赖**：AgentScope 2.x（`agentscope>=2.0.0,<3`）

本文说明编排层如何跑，以及 Agent 如何通过 JSON 意图访问数据库——**不生成、不执行 SQL**。

---

## 1. 结论

助手主路径默认用 AgentScope 做「想一步、调工具、再回答」。工具执行仍走本系统的 Executor → Service → ORM。

- **换了**：后端编排引擎；查询/批量写入改为结构化 Intent。
- **没换**：助手页 UI、SSE 协议、会话落库、生成槽 / 停写、RBAC、命令规划旁路、Worker 分析 / 日报。
- **禁止**：`execute_sql` / Raw SQL / Schema SQL Generator。Agent 不能访问数据库连接。

页面看起来和以前一样是刻意的：前端仍消费自家 SSE（`message_start` / `delta` / `tool_*` / `card` / `done` / `error`）。

```text
用户自然语言
    → Agent 生成结构化 Intent / JSON
    → Tool Executor（当前用户）
    → RBAC / 参数校验 / 操作范围
    → Service
    → SQLAlchemy / Repository
    → PostgreSQL
```

---

## 2. 原先怎么跑

未接入 AgentScope 时，助手主路径是：

1. `ConversationService` 组上下文（摘要、记忆、绑定项目、时间）。
2. `ManagementAgent.chat` / `chat_stream` 自己跑固定轮次的 tool loop：
   - 调 `LLMGateway.chat_with_tools` / `chat_with_tools_stream`（httpx，OpenAI 兼容）。
   - 若模型返回 `tool_calls`，由 `ManagementToolExecutor` 同步执行。
   - 把工具 JSON 追加进消息，再进下一轮。
3. 流式事件直接打成 `AgentStreamEvent`，经 FastAPI SSE 给 `frontend/app/agent/page.tsx`。

早期上限是 **6** 轮；人员核对等场景容易一人一查把预算用尽。现已拆成推理轮与纠错轮（见第 6 节）。

另外两条旁路不变：

| 旁路 | 触发 | 实现 |
| --- | --- | --- |
| Stub | 未配置 `LLM_BASE_URL` / `LLM_API_KEY` | 关键词规划工具，明确降级 |
| 命令规划 | 写操作清单类意图 | `command_agent` 先规划再执行 |

进度分析、日报、方案建议走 `LLMGateway.structured_output`，**不是**项目助手 agent。

---

## 3. 现在怎么跑

配置了 LLM 且 `AGENT_RUNTIME=agentscope`（默认）时：

1. 会话、上下文、stub、命令规划与原先相同。
2. 主问答改为 AgentScope：
   - `OpenAIChatModel` + `OpenAICredential`，`base_url` 仍用现有 `LLM_*`。
   - `Toolkit` 挂上全部 `MANAGEMENT_TOOLS`。
   - 每个工具是 `ExecutorBoundTool`：AgentScope 只负责调用，真正执行仍是 `ManagementToolExecutor`（当前用户 RBAC、幂等、审计、卡片）。
   - `ReActConfig(max_iters)` 对齐 `AGENT_REASONING_ROUNDS`（默认 20）。
   - 同一写入 `operation_id` 的参数纠错另计 `AGENT_TOOL_CORRECTION_ROUNDS`（默认 10）；读工具不占纠错次数。
   - AgentScope 权限模式为 `BYPASS` / 工具 `check_permissions` 恒为 ALLOW，**避免**官方 `FunctionTool` 默认 ASK。业务鉴权不在这一层。
3. `reply_stream` 事件映射为原 SSE 后，前端无感。

未安装 `agentscope`、或 `AGENT_RUNTIME=legacy`、或构造 `ManagementAgent` 时**注入了自定义 gateway**（测试常见），则回退自研循环（同样使用 20 / 10 两套上限）。

```text
浏览器（原助手页）
    → Nginx → Frontend / Backend SSE（协议不变）
    → ConversationService（会话、槽位、停写、落库）
    → ManagementAgent
         ├─ stub / command_agent
         ├─ AgentScope Agent         （默认）
         └─ 自研 tool loop           （legacy）
    → ManagementToolExecutor
    → Service / Repository / ORM
    → PostgreSQL
```

---

## 4. 结构化查询与批量写入

Agent 决定查什么、筛什么、批量包含哪些记录、失败后改哪些参数。Backend 决定能否访问、如何建 SQL、如何回滚。

### 4.1 `query_entities`

不要为每种自然语言再加一个固定查询工具。统一入口：

```json
{
  "entity": "task",
  "filters": [{"field": "status", "operator": "eq", "value": "IN_PROGRESS"}],
  "fields": ["id", "task_name", "owner_name", "status"],
  "order_by": [{"field": "start_date", "direction": "asc"}],
  "limit": 100
}
```

允许的 entity：`task` / `project` / `issue` / `user` / `milestone` / `project_member`。  
字段、运算符、返回列必须在 Query Schema 白名单内。当前用户可见范围与最大条数由 Backend 强制。

原有 `query_tasks` / `search_projects` / `search_issues` 仍可用。

### 4.2 批量人员

名单已是具体姓名时，一次 `batch_find_users`（或 `find_users.names`），精确匹配 `name =`：

```json
{"names": ["示例甲", "示例乙"]}
```

返回 `resolved` / `ambiguous` / `not_found`。只处理异常人员，不要因一个人找不到而重查全部。

### 4.3 整份计划 Draft Once

一个项目 + 多个 work_stream + 几十个任务：一次 `draft_project_plan`（任务可带 `owner_name`，内部批量解析）。  
用户确认后：`validate_project_plan` → `apply_project_plan`（需要 review 的 `digest`，且当前消息须有明确写入意图）。  
已有项目上补一批评任务：`batch_create_tasks`，不要连续几十次 `create_task`。

### 4.4 事务、幂等、校验

| 原则 | 实现 |
| --- | --- |
| 单事务 | 能在一个事务完成的批量写入：先校验全部，再写入，再 `COMMIT`；任一项失败 `ROLLBACK` |
| 幂等 | `UNIQUE(operation_id, client_item_id)`；已 `SUCCESS` 的项返回原 `resource_id`，不重插 |
| 断点 | 下一轮只处理 `FAILED` / `PENDING`，不得重做 `SUCCESS` |
| 写后校验 | 返回 `verification`（`expected_count` / `actual_count` / `duplicate_count`）；对不上不得称已完成 |
| 纠错对象 | 结构化 `error_code`（如 `OWNER_NOT_FOUND`），不是 Postgres 原文，也不是 SQL |

---

## 5. 文件改动

| 路径 | 说明 |
| --- | --- |
| `backend/app/agents/agentscope_runtime.py` | AgentScope 编排；`max_iters` 对齐推理轮；写入纠错封顶 |
| `backend/app/agents/agentscope_tools.py` | `ToolBase` 包装 executor |
| `backend/app/agents/management_agent.py` | 默认 AgentScope；`CorrectionTracker` |
| `backend/app/agents/management_tools.py` | `query_entities` / `batch_*` / `validate_project_plan` / `apply_project_plan` |
| `backend/app/agents/query/` | 白名单 DSL；支持 `operator` / `order_by` / `fields` |
| `backend/app/services/agent_batch.py` | 批量人员与事务性任务写入 |
| `backend/app/models/agent_batch.py` | 批量 operation / item 回执 |
| `backend/alembic/versions/20260911_1400_a1b2c3d4e5f6_agent_batch_operations.py` | 批量回执表 |
| `backend/app/core/config.py` | `AGENT_RUNTIME`、`AGENT_REASONING_ROUNDS`、`AGENT_TOOL_CORRECTION_ROUNDS` |
| `.env.example` | 上述开关示例 |
| `backend/app/prompts/management_agent.md` | 禁止 SQL；优先批量工具 |
| `mcp/skills/project-agent-assistant/SKILL.md` | 运行时与工具约定 |

**未改的代表路径**：`frontend/app/agent/page.tsx`、`backend/app/services/conversation.py`、`backend/app/api/v1/agent.py`、Worker 分析任务。发布计划仍需用户确认，不能由模型静默发布。

---

## 6. 与原先的具体区别

| 点 | 原先 | 现在 |
| --- | --- | --- |
| ReAct 循环 | 手写 for 循环，最多 6 轮 | AgentScope（默认）或 legacy；推理 20 轮 |
| 写入纠错 | 与查询轮混用 | 同一 operation 最多 10 次参数纠错 |
| 模型客户端 | 自研 `LLMGateway` + httpx | 助手主路径 `OpenAIChatModel`；Worker 仍用网关 |
| 查询 | 大量固定 list/get 工具 | 增加受控 `query_entities` |
| 建任务 | 易变成一人一查、一任务一建 | `batch_find_users` + `draft_project_plan` / `batch_create_tasks` |
| 工具执行 | executor | 仍是 executor；AgentScope 外再包一层 `ToolBase.call` |
| 权限 | 项目 RBAC | 不变；AgentScope ASK 关掉 |
| 流式 | 网关 token / tool_calls → SSE | AgentScope 事件译成同一套 SSE |
| 助手 UI | Next.js + Ant Design | **相同** |

事件对照（后端翻译，前端仍只认右列）：

| AgentScope | 项目 SSE |
| --- | --- |
| `TEXT_BLOCK_DELTA` | `delta`（`content`） |
| `TOOL_CALL_START` | `tool_start` |
| `TOOL_RESULT_END` | `tool_end`，并追加本次新增 `card` |
| `EXCEED_MAX_ITERS` | `delta`（步骤上限说明） |
| 思考块等 | 不转发给前端 |

---

## 7. 开关与部署

```bash
# .env
AGENT_RUNTIME=agentscope
AGENT_REASONING_ROUNDS=20
AGENT_TOOL_CORRECTION_ROUNDS=10
LLM_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL_REASONING=...
```

源码未 bind-mount 时需重建 backend，并升级库（批量回执表）：

```bash
docker compose build backend
docker compose exec backend alembic upgrade head
docker compose up -d --force-recreate backend
```

未配置 LLM 时行为与原先一致：stub，不假装模型成功。

---

## 8. 明确未做

- 不用 AgentScope 官方 WebUI、`create_app` Agent Service、自带 session。
- 不把对话事实源改成 AgentScope memory；PostgreSQL 会话表仍是准。
- 不引入 AgentScope 内置 `Bash` / `Read` / `Write`，也不引入任何 SQL 执行工具。
- 不替换进度分析、日报、方案建议。
- 不改前端视觉与交互。
- `apply_project_plan` 不能绕过确认策略和草案 `digest`。

---

## 9. 验收建议

1. 未配 LLM：助手仍返回「工具查询结果」类 stub。
2. 已配 LLM：问「PRJ-1001 进展如何」，应出现工具活动 + 流式正文，事实来自库。
3. 多名负责人：一次 `batch_find_users`，不应出现十几次「查询负责人」。
4. 整份立项清单：一次 `draft_project_plan`；确认后才能 `apply_project_plan`。
5. 批量创建中有一个负责人不存在：整批回滚，库中 0 条新任务，回执含 `OWNER_NOT_FOUND`。
6. 同一 `operation_id` 重试：已成功项不重复插入。
7. 写成功回执必须带 `verification`，`actual_count != expected_count` 时不得说「已创建完成」。
8. 离开页面 / 点停止：生成结束，会话可再发。
9. `AGENT_RUNTIME=legacy`：编排回退自研循环，页面协议与工具语义不变。

---

## 10. 相关文档

- 产品手册：`docs/HANDBOOK.md` 第 4.3、第 7 节
- 助手技能：`mcp/skills/project-agent-assistant/SKILL.md`
