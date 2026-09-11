# 合并测试结论（2026-09-10）

**来源**

| 流 | 文档 | 环境 | 方法 |
| --- | --- | --- | --- |
| 系统审计验证 | `docs/TEST_REPORT.md` | 生产实例（主机已脱敏） | 只读（仅登录写 JWT）；curl / psql / Playwright |
| 全功能抽样 | `docs/qa/QA-20260910-{A,B,C,D}/REPORT.md` | `127.0.0.1:8080` 本地 Compose | Playwright + API 写入（仅 `QA-20260910-*` 前缀） |

两套结果互补：审计侧重安全/配置/移动端；QA 侧重业务主链、权限、计划变更、助手与并发。**不以任一流的通过率单独放行。**

关联：本文件；修复计划 `docs/SYSTEM_FIX_PLAN.md`；检测手册 `docs/FULL_FUNCTION_TESTING_GUIDE.md`。

---

## 1. 合并统计（粗算）

| 流 | 已执行 | PASS | FAIL | 其他 |
| --- | --- | --- | --- | --- |
| TEST_REPORT | 43 | 17 | 22 | 4 警告/N-A |
| QA-A | ~23 | 22 | 1（BRAND） | 大量未覆盖 |
| QA-B | ~21 | 21 | 1（BRAND） | — |
| QA-C | 32 | 24 | 3（后裁定部分为夹具/断言） | 5 BLOCKED |
| QA-D | 42 | 36 | 3 | 3 N/A |

去重后的**产品缺陷**见第 2 节；测试误报与顺序副作用单独标注。

---

## 2. 统一缺陷台账（去重）

### P0 — 发布阻断

| ID | 标题 | 证据来源 | 状态 |
| --- | --- | --- | --- |
| **P0-1** | 默认 JWT 密钥 `change-me-in-production` 可伪造任意身份；伪造 token 可读 `/auth/me` 与全量用户 PII | TEST A2/A3/A7/S6 | **未修** |
| **P0-2** | 生产 `ENVIRONMENT=local`（影响 CORS/docs 等策略）与弱密钥叠加 | TEST O3 | **未修** |

> 审计结论：「内网即 admin」现实路径成立。QA 流未覆盖密钥伪造（账号体系不同）。

### P1 — 高优先级

| ID | 标题 | 证据来源 | 状态 |
| --- | --- | --- | --- |
| **P1-1** | 业务日用 `date.today()` / UTC，违反 BusinessClock；compose 无 TZ | TEST C1/C3/O2 | **已修（阶段2）** |
| **P1-2** | 乐观锁 `expected_version` REST 不可达（schema forbid → 422） | TEST B6 | **已修（阶段2）** |
| **P1-3** | OA SSO ticket 300s 无 nonce 可重放；nginx access log 含完整 query | TEST C5/S4 | **已修（阶段1）** |
| **P1-4** | INACTIVE 用户 SSO 自动复活为 ACTIVE | TEST C6 | **已修（阶段1）** |
| **P1-5** | 移动端无替代导航（&lt;768）；通知/用户表横滚溢出 | TEST D7/D8/D9 | **已修（阶段4：Tab+汉堡；表本地滚动）** |
| **P1-6** | 生产 admin 口令仍为仓库公开 seed | TEST A5 | **未修** |
| **P1-7** | 助手一次指令创建多任务（CMD-01）不稳定，C/D 两轮均 0 落库 | QA-C/D CMD-01 | **已修（阶段3：mutation 意图 + independent 默认；CMD-01×3 / AG-10 PASS）** |
| **P1-8**（观察→待确认） | 删除任务与提交进展竞态：delete=204 且 progress=201 且 task 404，疑孤儿进展 | QA-D CON-03 | **已修（阶段2：行锁 + 孤儿核对为 0）** |

### P2 — 中优先级

| ID | 标题 | 证据来源 | 状态 |
| --- | --- | --- | --- |
| **P2-1** | `ai-runs/latest` 无对象级鉴权（静态） | TEST B1 | **已修（阶段1）** |
| **P2-3** | 生产 `/docs` `/openapi.json` 全开；登录无限速 | TEST B4/B5 | **未修** |
| **P2-5** | `/my-tasks` 全量拉取（规模上去后的性能风险） | TEST D5 | **已修（阶段5：服务端分页/过滤/排序）** |
| **P2-9** | 登录失败审计丢失（`login_failed` 0 行，异常路径未 commit） | TEST S5 | **已修（阶段1）** |
| **P2-10** | Agent 页请求 `projects/undefined/risk-events` → 422，约 40s 复现 | TEST D6 | **已修（阶段4：无 project_id 不发请求）** |
| **P2-11** | 已登录首页仍显示「登录」快捷卡；自检面板泄露 env/失败原因 | TEST D2 | **已修（阶段4：登录卡隐藏；prod 细节仅 ADMIN）** |

### P3 — 体验 / 文案

| ID | 标题 | 证据来源 | 状态 |
| --- | --- | --- | --- |
| **P3-BRAND** | 登录页 badge 仍为 `R&D Project Agent` | QA-A/B/D BRAND-01 | **已修（阶段4）** |
| **P3-UI** | 看板 0 值统计用红色；favicon 404 等 | TEST D3/D11 | **部分已修（阶段4：D3 零值中性色；favicon 未改）** |
| **P3-NOTIFY** | WeCom 无去重；每日 scan 可重复（渠道未配置时风险潜伏） | TEST C7 | **部分已修（阶段5：日扫 Redis NX；真投递见 ops 手册）** |

### 已澄清 / 非产品缺陷（合并裁定）

| 项 | 裁定 |
| --- | --- |
| QA-C RISK-01-OVERDUE | 断言读错字段（应用 `event_type`）；D 轮与数据核对后 OVERDUE 可生成 |
| QA-C PLAN-09 无 digest | 同项目其它任务缺计划数据 → `feasible=False`；D 轮夹具补齐后 **PASS** |
| QA-D RISK-01-OVERDUE | PLAN apply 改写了超期夹具 due，属**测试顺序副作用** |
| QA PLAN-08 路径 | 正确为 `/api/v1/projects/{id}/planning/schedule-preview` |
| 审计 A1 首次 401 | 测试侧命令脱敏干扰，修正后 PASS |
| 计划变更代码质量 / RBAC 对象级 | 审计 C4、A4 与 QA 权限抽样一致：**通过** |

### 已验证通过的关键能力（合并）

- 登录、项目/任务 CRUD 抽样、进展提交、确认删除、助手查询与停止/离页恢复
- 变更方案：预览→校验 digest→确认→执行→幂等（QA-D）
- 风险 MISSING_DATA / 关闭权限；建议生成与驳回、他人采纳拒绝
- 通知列表与他人确认拒绝；企微未配置不得声称外送
- 真实模型只读查询 3 次采样（QA-D）；桌面端主页面可读

---

## 3. 放行判断（合并）

| 门槛 | 结论 |
| --- | --- |
| 安全 P0 | **本机已修**（阶段 0–1）；对外实例需确认同 compose / 密钥轮换 |
| 功能主链 | **阶段 2–4 已回归**：时钟/乐观锁/CMD-01/移动导航/品牌等 PASS |
| 工程化 | **阶段 5**：最小 pytest、`/my-tasks` 分页、日扫去重、演练/WeCom 文档就绪 |
| 外部渠道 / 破坏性故障 | WeCom **真投递**与 §8.3 **破坏窗口**仍待登记环境补证据 |
| **总体** | 代码侧阶段 0–5 已落地；放行前补：对外安全烟测 + WeCom（若启用）+ 一次故障演练登记 |

---

## 4. 证据索引

- 审计：`docs/TEST_REPORT.md`；截图见报告内 `/data/test` 路径说明
- QA：`docs/qa/QA-20260910-A|B|C|D/`（`REPORT.md`、`screenshots/`、`results.json`）
- 修复执行顺序：`docs/SYSTEM_FIX_PLAN.md`
