# 项目手册（Project Agent Handbook）

**产品**：创新药研发项目管理 Agent  
**版权**：Copyright 2024–2026 Jack Zhang（`59841153z@gmail.com` / `598411539@qq.com`）  
**许可**：Apache License 2.0（见仓库根目录 `LICENSE` / `NOTICE`）

本文档合并原分散的使用说明、运维、安全与助手说明，作为开源发行版**唯一手册**。

---

## 1. 产品定位

轻量级 AI 项目跟踪系统：成员维护「任务 / 负责人 / 完成时间 / 一句话进展」，系统负责进度跟踪、提醒、延期判断、风险识别、Issue、AI 总结、方案建议、管理层看板与自然语言查询。

**硬原则**

- **业务事实**由 PostgreSQL + Backend 决定（截止日期、延期、状态、负责人、权限、完成判定）。
- **AI** 只做理解、总结、风险提示、建议与自然语言查询；不能绕过 RBAC，不能静默改计划。

---

## 2. 架构与技术栈

| 组件 | 技术 / 职责 |
| --- | --- |
| Frontend | Next.js · React · TypeScript · Ant Design（移动优先） |
| Backend | FastAPI · SQLAlchemy 2 · Pydantic 2 · Alembic |
| Worker / Beat | Celery（AI 分析、风险扫描、通知投递、定时任务） |
| 数据 | PostgreSQL（事实源）· Redis（队列 / 锁） |
| AI | OpenAI 兼容网关；未配置时使用 Stub，功能明确降级 |
| 入口 | Docker Compose · Nginx |

```text
浏览器 → Nginx → Frontend / Backend API
Backend → PostgreSQL / Redis
Worker / Beat → Redis → PostgreSQL（可选 LLM / 企业微信）
```

---

## 3. 快速开始

### 3.1 环境变量

```bash
cp .env.example .env
# 编辑 .env：至少设置 JWT_SECRET；生产务必更换全部密钥与数据库口令
```

**切勿**把含真实 `LLM_API_KEY`、数据库密码、OA 口令、内网 IP 的 `.env` 提交到 Git（已在 `.gitignore`）。

关键变量见 `.env.example`：

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` / `POSTGRES_*` | 数据库 |
| `REDIS_URL` | Redis |
| `JWT_SECRET` | 会话签名（生产必须更换） |
| `LLM_BASE_URL` / `LLM_API_KEY` | 可选；空则 Stub |
| `LLM_MODEL_FAST` / `LLM_MODEL_REASONING` | 快模型 / 对话推理模型 |
| `WECOM_*` | 可选企业微信 |
| `OA_MYSQL_*` / `OA_SSO_SECRET` | 可选 OA 只读库与免登 |
| `SEED_*_PASSWORD` | `make seed` 时的演示账号口令（勿用默认值上生产） |

### 3.2 Docker Compose（推荐）

```bash
docker compose up -d --build
docker compose ps
```

默认经 Nginx 访问 `http://localhost`（或 `.env` 中 `NGINX_PORT`）。健康检查：`/health`、`/health/ready`。

### 3.3 本地开发

```bash
docker compose up -d postgres redis
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
# 另开终端：celery worker / beat
cd frontend && npm install && NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

常用：`make help`、`make up`、`make migrate`、`make seed`。

---

## 4. 使用说明（业务）

### 4.1 三种信息不要混

| 系统说法 | 含义 |
| --- | --- |
| 已超期、已完成、Issue 已提出 | **事实** |
| 预测完成日期、预计延期 | **计算结果**（数据变则结果变） |
| AI 建议、风险原因分析 | **参考意见**（需有证据） |
| 无法计算 / 数据不足 | **缺依据**，不是“没风险” |

### 4.2 日常进度

- 提交进度立即落库，不依赖 AI；模型不可用时标为未分析，原文保留。
- 汇报里的“可能延期”不会自动改计划；改期需授权流程。

### 4.3 项目助手

助手可查询、模拟排期、起草计划/变更说明、解释风险。  
**不能**代替你：发布计划、确认执行变更、关闭风险、代替他人确认通知。

离开对话页时，进行中的生成会尽量停止并释放会话锁；重新进入可停止或继续发送。

### 4.4 改计划

影响日期或依赖时走：**预览 → 核对 → 确认 → 执行**。预览只读；冲突会展示而不会偷偷压工期；确认绑定账号；并发冲突会拒绝并要求重算。

### 4.5 风险

规则判定（如已超期、缺进度、关键路径压力等），不是模型臆测。AI 可补充解释，但采纳与否由人决定。

---

## 5. 运维

| 进程 | 作用 | 停掉的影响 |
| --- | --- | --- |
| Backend | API | 全部不可用 |
| Worker | AI / 通知投递 | 通知积压、分析不跑 |
| Beat | 定时扫描 | 定时任务停 |
| PostgreSQL | 数据 | 全部不可用 |
| Redis | 队列 / 锁 | 任务无法排队 |

升级前备份数据库；用 Alembic 升级；保持单一 migration head。  
`FRONTEND_BASE_URL` 必须是收件人能打开的地址。  
LLM / WeCom 未配置时按设计降级（可见、可理解），不要当成静默成功。

数据完整性：

```bash
cd backend && .venv/bin/python -m app.scripts.check_data_integrity
```

---

## 6. 安全边界

- 密码 bcrypt；JWT；角色 ADMIN / EXECUTIVE / PROJECT_OWNER / MEMBER。
- 对象访问在 Service / `permissions.py` 校验，不依赖前端隐藏。
- 审计与日志脱敏：password、token、api_key 等。
- OA MySQL **只读**；SSO 使用短时 HMAC。
- Agent 工具以当前用户身份执行，复用同一套权限；项目改期需原因。

**开源发行注意**：勿提交真实密钥、内网地址、客户数据、备份库、评测原始语料。

---

## 7. 项目助手（开发要点）

- 对话流式 SSE；请求层幂等（`client_request_id`）。
- 工具结果瘦身与脱敏；乐观锁 / 版本冲突。
- 生成中会话槽位：离开页面 stop / 超时回收，避免“无法再发消息”。
- 模型名来自环境变量 `LLM_MODEL_*`，改 `.env` 后需重启 backend/worker。

Agent Skills（Claude Code / Cursor / Codex）见仓库 `mcp/skills/`。

---

## 8. 目录（发行版）

```text
.
├── LICENSE / NOTICE / COPYRIGHT
├── README.md
├── docs/HANDBOOK.md          # 本手册
├── mcp/skills/               # Agent Skills
├── backend/app/              # FastAPI 应用
├── frontend/                 # Next.js
├── deploy/nginx/
├── docker-compose.yml
├── .env.example
└── Makefile
```

本发行版不包含历史阶段设计稿、内部验收报告、本地备份、测试套件与业务样例数据。

---

## 9. 贡献与版权

欢迎 Issue / PR。提交即表示同意以 Apache 2.0 贡献。  
**版权人 Jack Zhang 的署名与 NOTICE 不得删除或替换**；你可为自有修改追加自己的版权声明。
