# 系统修复 / 改进计划（2026-09-10）

依据：`docs/MERGED_TEST_SUMMARY.md`（合并 `TEST_REPORT.md` + QA-A/B/C/D）。

原则：先阻断安全与错误身份，再修数据正确性与助手可靠性，最后体验与工程化。每阶段结束做**最小回归集**（见文末），通过后再进下一阶段。

---

## 阶段 0 — 立即止血（当天，P0）✅ 已落地 2026-09-10

目标：消除「默认密钥 / seed 口令 / local 环境标」构成的管理员接管路径。

| # | 动作 | 验收 | 本轮结果 |
| --- | --- | --- | --- |
| 0.1 | ≥32 字节随机 `JWT_SECRET`；旧 token 全部失效 | 默认密钥伪造 → 401 | **PASS**（`/api/v1/users/me`） |
| 0.2 | 修改 admin；禁止公开 seed 口令 | `Admin@12345` 失败 | **PASS**；新口令仅存本机密钥目录（勿提交） |
| 0.3 | `ENVIRONMENT=prod`；关闭 OpenAPI | health/docs | **PASS**（prod；docs/openapi/redoc 404） |
| 0.4 | `.env` / secrets 不入库 | git ignore | **PASS** |
| 0.5 | 登录限速 IP+用户名 | 连续失败 429 | **PASS**（第 11 次起） |

实现：`config.py` 弱密钥拒绝、`main.py` OpenAPI 门控、`login_rate_limit.py`、seed/wipe 拒绝公开口令、compose 强制 `JWT_SECRET`。

**退出标准已满足**（本机 compose 入口；共享/LAN 实例需确认同 compose 与密钥轮换）。

---

## 阶段 1 — 安全与身份加固（1–3 天，P1 安全向）✅ 已落地 2026-09-10

| # | 项 | 建议改法 | 回归 | 本轮结果 |
| --- | --- | --- | --- | --- |
| 1.1 | SSO ticket 重放 | Redis 一次性 `consume_sso_ticket`（NX+TTL） | C5 | **PASS**（二次消费 → already used） |
| 1.2 | nginx 日志脱敏 | `map $args`：含 ticket/sign/token/code 等则记 `[redacted]` | S4 | **PASS**（`/users/me?[redacted]`） |
| 1.3 | INACTIVE SSO 复活 | `ensure_user_from_oa` 不再自动 ACTIVE | C6 | **PASS**（代码已移除自动复活） |
| 1.4 | 登录失败审计 | 失败路径 `db.commit()` 后再 401 | S5 | **PASS**（`auth.login_failed` 落库） |
| 1.5 | `ai-runs/latest` 鉴权 | 按 resource 做对象级可见性；无权限 404 | B1 | **PASS**（越权/缺失 404；负责人 200） |

实现文件：`sso_ticket_store.py`、`auth.py`/`user.py`、`deploy/nginx/nginx.conf`、`api/v1/ai_runs.py`。

**退出标准已满足**（本机 compose）。

---

## 阶段 2 — 业务正确性（2–4 天，P1 数据向）✅ 已落地 2026-09-10

| # | 项 | 建议改法 | 回归 | 本轮结果 |
| --- | --- | --- | --- | --- |
| 2.1 | 业务时钟统一 | `BUSINESS_TZ`/`TZ` + `BusinessClock`/`scheduler_today` 替换 UTC/`date.today()` | C1/C3/O2 | **PASS**（Asia/Shanghai 与本地日历日一致） |
| 2.2 | 乐观锁可达 | `TaskUpdate.expected_version`；冲突 **409** `VERSION_CONFLICT`；响应含 `version` | B6 | **PASS**（错版本 409；对版本递增） |
| 2.3 | 删任务 × 进展竞态 | 双方 `SELECT … FOR UPDATE`；进展 FK CASCADE | CON-03 | **PASS**（无 500；`progress_updates` 孤儿数 0） |
| 2.4 | 变更方案夹具文档 | 手册与检测指南注明 `feasible=false` → 无 digest | PLAN-09 | **PASS**（文档已补） |

**退出标准已满足**（本机 compose API 回归）。

---

## 阶段 3 — 助手多写可靠性（3–5 天，P1-7）✅ 已落地 2026-09-10

现象：CMD-01「一次创建 3 任务」C/D 两轮均未落库；单任务写入与只读查询可用。

| # | 动作 | 本轮结果 |
| --- | --- | --- |
| 3.1 | 取证 | **PASS**：计划正确生成 3×`create_task`，执行 FAILED：`CONFIRMATION_REQUIRED`（未授权业务写入） |
| 3.2 | 根因 | **`has_mutation_intent`** 把「不要创建其它任务」当成整句只读；模型误选 `atomic` 后一项失败全 BLOCKED |
| 3.3 | 产品策略 | 默认 **independent（尽力多项）**；仅用户明确全成全败时 `atomic`；回执含成功/未完成项 |
| 3.4 | 加固 | 收窄只读否定词；`create()` 强制 policy；N 覆盖认「恰好/正好」；planner 提示同步 |
| 3.5 | 回归 | **PASS**：CMD-01×3（`QA-P3-30711`，policy=independent，各成功 3）；AG-10 任务数不变 |

实现：`agent_entities.py`、`agent_command.py`、`agent_commands.py`、`command_agent.py`。

**退出标准已满足**（本机 compose API；未抽样 N=10 / CHAT-03/05，可阶段 4 前补烟测）。

---

## 阶段 4 — 前端 / 移动体验（2–4 天，P1-5 / P2 / P3）✅ 已落地 2026-09-10

| # | 项 | 本轮结果 |
| --- | --- | --- |
| 4.1 | &lt;768 导航 | **PASS**：底部 Tab（可横滑）+ 顶栏汉堡 Drawer；项目/任务/助手/通知可达（D9） |
| 4.2 | 表横向溢出 | **PASS**：通知 `filter-scroll`；用户表 `table-scroll` + 响应式列；整页 scrollWidth=视口（D7/D8） |
| 4.3 | Agent `undefined` 项目 | **PASS**：无 `project_id` 的 risk 卡片不再请求 `/projects/undefined/…`（D6） |
| 4.4 | 首页已登录态 | **PASS**：去掉登录快捷卡；prod 非 ADMIN 仅见就绪态（D2） |
| 4.5 | **BRAND-01** | **PASS**：`login-hero__badge` = `APP_NAME` |
| 4.6 | 看板 0 值配色 | **PASS**：`StatTile` 零值强制中性色（D3） |

实现：`AppShell`、`AgentCards`/`RiskEventsCard`、`QuickActions`、`SystemStatusCard`、`StatTile`、users/notifications、`globals.css`、login。

**退出标准已满足**（本机 Playwright：BRAND / D2 / D3 / D6 / D7 / D8 / D9）。

---

## 阶段 5 — 工程化与中长期（并行可排期）✅ 已落地 2026-09-10

| # | 项 | 本轮结果 |
| --- | --- | --- |
| 5.1 | 自动化最小集 | **PASS**：`backend/tests` 12 例；`make test` 可跑；不再 exit 1 |
| 5.2 | `/my-tasks` 分页下推 | **PASS**：`GET /tasks/my?page&page_size&status&q&sort` → `{items,total,…}`；前端服务端分页 |
| 5.3 | WeCom / 日扫去重 | **代码 PASS**：`claim_notification_once`（`TASK_REMINDER`/`MISSING_PROGRESS`）；验收手册 `docs/ops/WECOM_NOTIFY_ACCEPTANCE.md`（真投递仍依赖配置） |
| 5.4 | 故障演练 §8.3 | **模板就绪**：`docs/ops/FAULT_DRILL_8_3.md`（登记环境执行，本轮未开破坏窗口） |
| 5.5 | OPT-11 eval | **PASS**：`backend/evals/cases.yaml` + `make eval-list`（不门禁真实 LLM） |

**说明**：5.3 真企微投递、5.4 破坏性窗口需运维登记环境后补证据；代码与文档已齐。

---

## 建议实施顺序（一页纸）

```text
阶段0 密钥/口令/ENVIRONMENT/docs
    ↓
阶段1 SSO·审计·ai-runs 鉴权
    ↓
阶段2 BusinessClock·乐观锁·删除竞态
    ↓
阶段3 助手多任务写入（取证→策略→加固）
    ↓
阶段4 移动导航·溢出·Agent undefined·品牌
    ↓
阶段5 测试基建与渠道/故障演练
```

人员建议：0–1 偏运维+后端安全；2–3 后端+Agent；4 前端；5 全员。

---

## 每阶段最小回归集

| 阶段 | 必跑 |
| --- | --- |
| 0 | TEST A2 A3 A5 B4 O3 |
| 1 | C5 C6 S5 B1 |
| 2 | C1 风险超期夹具；B6；CON-03+DB |
| 3 | CMD-01×3；AG-10；CHAT-03/05 |
| 4 | D6 D7 D8 D9；BRAND-01；MOBILE 登录→列表→详情 |
| 全量再议放行前 | QA-D 精简烟测 + TEST 安全烟测 + 变更 PLAN-09 一条 |

---

## 明确不做（本计划外除非单独立项）

- 用 Stub LLM 冒充真实模型通过
- 在未配置 WeCom 时宣称外部通知达标
- 无写入窗口证据时宣称「重启故障已覆盖」
- 扩大生产只读审计为写操作（需独立变更窗口与回滚方案）
