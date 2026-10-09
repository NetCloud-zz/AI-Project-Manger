# 项目助手 Agent 工程改造计划书

Copyright 2024–2026 Jack Zhang. Licensed under the Apache License, Version 2.0.
保留仓库 `LICENSE`、`NOTICE` 与版权归属。

日期：2026-10-08
状态：本期 W1–W4 已实现并通过自动化测试与真实模型评测（结果见第 10 节）。`hybrid` 意图判定已满足第 7 节门槛，默认仍为 `regex`，由部署方灰度开启。
关联文档：[HANDBOOK.md](HANDBOOK.md) 第 7 节、[AGENTSCOPE_ASSISTANT_RUNTIME.md](AGENTSCOPE_ASSISTANT_RUNTIME.md)、[ASSISTANT_REPAIR_PLAN.md](ASSISTANT_REPAIR_PLAN.md)。

## 1. 背景与问题

助手的安全底座是对的：模型不碰 SQL，读写以当前用户身份走 Executor → Service → ORM，批量写入有回执、幂等和写后核对。本计划不改这些。

改造前的主要问题（2026-10-08 基线）：

| 编号 | 问题 | 证据 | 影响 |
| --- | --- | --- | --- |
| P1 | 写入授权靠中文正则 | `services/agent_entities.py` 中 `_MUTATION`、`_CONFIRMATION`、`_READ_ONLY_INTENT` 等同时决定路由与授权；注释 NL-01/NL-05 为逐句补丁 | 换个说法就误判：应写被拦或不应写被放行 |
| P2 | 四套执行方式、三份工具循环 | `management_agent.py` 中 `chat` 与 `chat_stream` 各一份自研循环，另有 AgentScope 一份 | 预算、错误、停止逻辑需多处同步 |
| P3 | 每轮发送全部 57 个工具 | 工具定义约 4.9 万字符，系统提示词约 1.9 万字符 | 选错工具、延迟和费用上升 |
| P4 | 缺少可度量的评测 | `evals/cases.yaml` 仅 3 例，`make eval-list` 只打印 YAML | 改动好坏无法量化 |
| P5 | 看不到单次请求全过程 | 无逐请求的路由、工具链、耗时记录 | 线上问题只能复现排查 |

## 2. 目标与非目标

目标：

1. 改动可度量：同一评测集可以对比两种意图判定、两种工具加载方式。
2. 写入授权从"补正则"转为"模型判定 + 正则硬性否决"，且安全方向不放松。
3. 每轮默认只发核心工具，专项能力按需激活。
4. 流式与非流式共用一份实现；每次请求输出一条结构化追踪。

非目标（本期不做）：

- 不在 ReAct 路径内改成"写入先暂存、轮末统一执行"。连续写入需要引用前一步结果（如新项目 ID），命令规划器已经用 `$ref` 解决了这类问题；在 ReAct 里重做一遍成本高、收益低。本期改为统一授权判定，写入仍优先走命令规划器。
- 不新增数据库表或迁移；追踪先写结构化日志。
- 不改 SSE 协议、前端交互、RBAC、幂等和确认卡片流程。
- 不删除任何工具；不常用工具只是移出默认集合。

## 3. 总体设计

```text
用户消息
  → decide_turn（W2）：正则否决 → [hybrid] 快速模型结构化判定 → TurnDecision
       ├─ 授权写入 / 复合指令 → 命令规划器（只读查询 + plan_commands → 校验 → 执行）
       └─ 其他 → ReAct（AgentScope 或自研循环，W4 统一）
                 工具：核心集合 + 按需激活的工具组（W3）
  → Executor（guard_mutation 使用同一份 TurnDecision）
  → AgentTrace（W1）：路由、意图、工具链、耗时、提示词体积 → 日志 / 评测
```

## 4. 工作项

### W1 评测框架与请求追踪

| 交付物 | 路径 |
| --- | --- |
| 请求追踪 | `backend/app/agents/trace.py`：`AgentTrace` 记录路由、意图判定、工具调用（名称、成败、错误码、耗时）、激活的工具组、首轮提示词与工具定义字符数、总耗时；请求结束输出 `agent.trace` 日志，并通知已注册的监听器 |
| 评测框架 | `backend/app/evals/`：用例加载、隔离数据世界、两种运行模式、打分与报告 |
| 用例集 | `backend/evals/assistant_core.yaml`：覆盖查询、写入、讨论、状态追问、强/弱确认、模糊修改、越权、多负责人、待定负责人等场景 |
| 入口 | `python -m app.evals`；`make eval-intent`、`make eval-agent` |

运行模式：

- `intent`：只评测意图与授权判定，可对比 `regex` 与 `hybrid`。不写库，成本低，适合每次改动后跑。
- `agent`：在一次性 PostgreSQL schema（或 SQLite）中灌入脱敏种子数据，经 `ConversationService` 跑完整对话，按数据库前后差异和追踪打分。结束即删除 schema。

指标：通过率、未授权写入数、漏写数、平均工具调用数、平均耗时、首轮提示词体积。结果写入 `backend/evals/results/`（不入库）。

### W2 意图与授权判定

| 交付物 | 路径 |
| --- | --- |
| 判定模块 | `backend/app/agents/intent.py`：`TurnDecision`、`decide_turn()` |
| 判定提示词 | `backend/app/prompts/intent_classifier.md` |
| 守卫 | `guard_mutation(..., authorized=)`；`ManagementToolExecutor(write_authorized=)` |
| 计划执行 | 命令计划 `planning_details.authorization` 记录判定来源；执行时沿用 |

判定规则（`AGENT_INTENT_MODE=hybrid`）：

1. 正则硬性否决优先：状态追问（"建好了吗"）和明确的只读/讨论表述，一律不授权，不调用模型。
2. 其余情况调用快速模型，输出意图、是否请求写入、是否确认上一轮、置信度和原文证据。
3. 模型判定"授权写入"必须同时满足：置信度不低于 `AGENT_INTENT_MIN_CONFIDENCE`，且证据是当前消息的原文片段。否则不采纳。
4. 模型可以否定正则的误报（如"怎么创建任务？"），这是更安全的方向。
5. 模型调用失败、超时或网关不支持时，退回 `regex` 结果，并在追踪里标记。

`AGENT_INTENT_MODE=regex`（默认）与改造前行为完全一致，`decide_turn` 只是把原有函数集中到一处。

### W3 工具分组与提示词拆分

| 交付物 | 路径 |
| --- | --- |
| 工具组定义 | `backend/app/agents/toolsets.py` |
| 核心提示词 | `backend/app/prompts/management_agent.md`（重排编号、去重） |
| 工具组说明 | `backend/app/prompts/toolsets/*.md`，激活工具组时随结果返回 |

分组：

| 工具组 | 内容 |
| --- | --- |
| 核心（常驻） | 当前用户、项目/任务/问题/行动项查询、`query_entities`、人员查找、进展总览、风险记录、单对象与批量写入、里程碑、进展汇报、数据库工具契约 |
| `plan_draft` | 计划草案起草、修改、审查、校验、发布前检查 |
| `change_plan` | 排期预览、变更方案、方案查询与执行、依赖图、项目上下文、通知状态 |
| `branches` | 任务分支的查询、创建与切换 |
| `issue_advice` | 问题证据、建议生成与查询 |
| `extra_queries` | 兼容查询（`query_tasks`、`list_projects`、`list_project_tasks`） |

激活方式：AgentScope 使用原生 `ToolGroup` 与元工具；自研循环提供同语义的 `activate_toolsets`。调用未激活工具组中的工具时返回 `TOOLSET_INACTIVE` 并提示要激活的组。命令规划器不受影响，并额外带上 `plan_draft` 的说明。`AGENT_TOOLSETS_ENABLED=false` 时回到全量工具。

### W4 运行时收敛

- `ManagementAgent.chat` 改为消费 `chat_stream` 的事件，删除重复的非流式循环。
- 路由只在 `_route_stream` 一处完成；AgentScope、自研循环和降级模式共用同一份 `TurnDecision`、执行器构造和追踪。
- 自研循环保留，用于未安装 AgentScope 的环境和注入假网关的测试。

## 5. 配置开关

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `AGENT_INTENT_MODE` | `regex` | `regex` 与改造前一致；`hybrid` 启用模型判定 |
| `AGENT_INTENT_MIN_CONFIDENCE` | `0.7` | 模型授权写入的最低置信度 |
| `AGENT_INTENT_TIMEOUT_SECONDS` | `15` | 判定调用超时，超时退回正则 |
| `AGENT_TOOLSETS_ENABLED` | `true` | 核心工具 + 按需工具组；`false` 回到全量工具 |
| `AGENT_TRACE_LOG` | `true` | 每次请求输出 `agent.trace` 日志 |

## 6. 测试计划

1. 单元测试：`decide_turn` 两种模式（含否决、低置信度、证据不在原文、模型异常回退、确认继承）；工具组激活与未激活报错；提示词拆分后每个工具都归属唯一分组；追踪字段；`chat` 与 `chat_stream` 结果一致。
2. 回归：完整后端测试集保持通过；AgentScope 路径在本地安装依赖后同样运行。
3. 评测：`intent` 模式在 `regex` 与 `hybrid` 下各跑 3 次；`agent` 模式在一次性 PostgreSQL schema 中跑核心用例。
4. 前端：TypeScript 编译与 ESLint。

## 7. 验收与灰度

- `regex` 模式下全部既有测试通过，行为不变。
- `hybrid` 开启门槛：`intent` 评测中未授权写入为 0，且通过率不低于 `regex`。达不到时保持关闭，并把失败用例转为单元测试。
- 工具分组开启门槛：`agent` 评测通过率不低于全量工具模式，首轮提示词体积明显下降。
- 每次修复先补评测用例或单元测试，再改正则或提示词。

## 8. 风险与回滚

| 风险 | 应对 |
| --- | --- |
| 模型误授权写入 | 正则硬性否决、置信度门槛、原文证据校验；执行层权限与确认卡片不变 |
| 判定增加延迟 | 只用快速模型、设置超时；否决场景不调用模型 |
| 模型不激活所需工具组 | 未激活调用返回明确提示；核心集合覆盖高频操作；可一键关闭分组 |
| 提示词拆分导致行为漂移 | 只搬移、不改写规则；用评测对比 |

回滚：把 `AGENT_INTENT_MODE` 设为 `regex`、`AGENT_TOOLSETS_ENABLED` 设为 `false`，重启 backend 即可，无数据库变更。

## 9. 后续方向

- 追踪落库并在管理页查看单次请求链路；接入自建 OpenTelemetry / Langfuse。
- 评测进入发版流程：固定模型与网关标识，保存历次结果做趋势对比。
- 视评测结果决定是否移除自研循环、是否将正则降为纯兜底。
- 降低判定延迟：对明显的只读问句（无任何写动词、无确认词）跳过模型判定。
- 命令计划的参数校验进一步统一为基于工具 JSON Schema 的严格校验（当前仅覆盖批量创建与更新类工具）。

## 10. 评测结果（2026-10-08）

环境：快速模型 / 推理模型均为当前 `.env` 配置的 OpenAI 兼容网关；端到端评测每例使用一次性 PostgreSQL schema，不接触业务库。

意图评测（39 例 × 3 次）：

| 模式 | 通过率 | 误授权写入 | 漏授权 | 平均判定耗时 |
| --- | --- | --- | --- | --- |
| `regex` | 62% | 18 | 27 | ≈0 ms |
| `hybrid` | 100% | 0 | 0 | ≈4.5 s |

端到端评测（核心 36 例；`hybrid`+分组另含 24 任务 + 1 里程碑夹具 5 种排版）：

| 变体 | 通过率 | 误写入 | 平均工具调用 | 平均耗时 |
| --- | --- | --- | --- | --- |
| `regex` + 工具分组 | 69% | 0 | 2.8 | 29 s |
| `hybrid` + 全量工具 | 92% | 0 | 2.6 | 35 s |
| `hybrid` + 工具分组 | 98%（41 例） | 0 | 2.6 | 36 s |

结论：

- `regex` 的主要问题是把讨论/查询句送进命令规划（最终以失败告终，体验差）和漏掉口语化写入；`hybrid` 消除了这两类问题，且没有新增误写入。
- 工具分组首轮工具 schema 由约 49K 字符降到约 30K 字符，通过率不低于全量工具。
- 判定延迟约 4.5 s/轮，是开启 `hybrid` 的主要代价。

评测期间发现并修复的缺陷（均已补单元测试）：

1. AgentScope `observe` 拒收带工具调用的历史，状态追问时预取的进展总览连同全部历史被丢弃；现压平为事实文本。
2. 命令规划查询阶段，结果含日期时 `json.dumps` 抛错导致整轮失败。
3. 规划给 `batch_create_tasks` 传未知字段（如 `name`、`note`）只在执行时失败、无法修复；现在规划校验阶段报错并进入修复轮，`name` 视作 `task_name` 别名。
4. 更新类工具静默忽略拼错字段，变成「无可更新字段」；现在规划阶段即拒绝未知参数。
5. 任务负责人（非项目负责人）更新进度时附带了与当前值相同的 `owner_id`，被当作改核心字段拒绝；现在相同值不视为变更。
6. 追踪把 AgentScope 的每次工具调用计成两次（结束事件无 `tool_call_id`）。

残余：个别用例存在模型随机性（同一用例 3 次中偶发 1 次失败），以执行层安全失败告终，无误写入。
