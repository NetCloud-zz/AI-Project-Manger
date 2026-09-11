# TEST_REPORT.md — 系统测试报告

**被测系统**：AI 项目管理 Agent（生产实例 [REDACTED_HOST]:8080，v0.2.0）
**报告日期**：2026-09-10
**测试轮次**：第一轮系统审计随附验证测试
**测试原则**：生产只读——未执行任何写操作（POST/PUT/DELETE 仅限登录端点）、未修改数据、未修改代码
**关联文档**：`MERGED_TEST_SUMMARY.md`（与 QA-A/B/C/D 合并结论）、`SYSTEM_FIX_PLAN.md`（修复/改进计划）、截图 `ui-*.png`  
**说明**：本报告为生产实例只读审计验证；功能写入抽样见 `docs/qa/QA-20260910-*/REPORT.md`。放行以合并结论为准。

---

## 1. 测试环境

| 项 | 值 |
| --- | --- |
| 部署 | Docker Compose 7 容器（postgres/redis/backend/worker/scheduler/frontend/nginx） |
| 状态 | 全部 Up (healthy)（`docker ps` 实测） |
| 入口 | http://[REDACTED_HOST]:8080（nginx :8080→:80；backend :8000、frontend :3000、postgres :5432、redis :6379 均映射宿主） |
| 数据规模 | 3 个项目（id 1,3,4）、2 个任务、42 个用户（OA 同步）、ai_runs=0、通知/进展若干 |
| 依赖健康 | PostgreSQL 正常 · Redis 正常 · LLM Gateway 正常 · WeCom 未配置（console 降级）· OA MySQL/SSO 正常（首页自检面板实测） |
| 测试账号 | admin（ADMIN，密码=（审计时为公开 seed，已要求轮换；勿写入仓库））；伪造 token：ADMIN(id=1)/MEMBER 两种 |
| 工具 | curl（API 探针）· psql 只读 SELECT（审计/用户数据核对）· Playwright MCP（UI 实测）· 后端容器内 python（bcrypt/服务层验证） |

---

## 2. 测试范围与方法

1. **认证与会话**（TC-A）：真实登录、JWT 签发/校验、密钥伪造、越权 token
2. **API 行为探针**（TC-B）：RBAC 对象级拒绝、IDOR、错误契约
3. **业务逻辑静态验证 + 生产数据核对**（TC-C）：时区、乐观锁、AI 队列
4. **UI 实测**（TC-D）：1440/1024/767/375 四断点、10 个页面、console/网络错误捕获、溢出探针
5. **安全与配置**（TC-S）：密钥、Git 泄漏、nginx、审计日志、信息泄露
6. **运行工具**（TC-O）：容器健康、服务层诊断（容器内执行）

> 注：开源发行树 `backend/tests` 为空、`Makefile test` 故意 exit 1——**无既有测试可跑**，全部用例为本次审计新写的手工/脚本用例。

---

## 3. 用例结果

### TC-A 认证与会话

| ID | 用例 | 预期 | 实测 | 判定 | 关联 |
| --- | --- | --- | --- | --- | --- |
| A1 | admin/Admin@12345 表单登录（API） | 明确的成功/失败 | 首次 401（后查明为**测试侧命令脱敏干扰**，分段重发后 200 签发 JWT） | ⚠️ 修正后 PASS | — |
| A2 | 默认密钥 `change-me-in-production` HS256 伪造 admin token → `/auth/me` | 401 拒绝 | **200，返回完整 admin 身份** | ❌ FAIL | P0-1 |
| A3 | 伪造 admin token → `GET /api/v1/users` | 401/403 | **200，返回 42 用户 PII（姓名/邮箱/OA id/部门）** | ❌ FAIL | P0-1 |
| A4 | 伪造 MEMBER token 访问他人项目/任务 | 403/404 | 403/404 正确 | ✅ PASS | RBAC 扎实 |
| A5 | bcrypt 校验 admin 生产 hash vs 仓库公开 seed 密码 | 不匹配 | **匹配（True）** | ❌ FAIL | P1-6 |
| A6 | 其余候选口令（admin/Admin@123456/Project@12345/Osri@202405） | 不匹配 | 均 False | ✅ PASS | 密码策略正常 |
| A7 | 后端容器内 `AuthService.login()` 直调 | 200 等价 | LOGIN OK user=1 role=ADMIN（同时输出 `InsecureKeyLengthWarning: HMAC key 23 bytes`） | ✅ PASS（附 P0 佐证） | P0-1 |

### TC-B API 行为探针

| ID | 用例 | 预期 | 实测 | 判定 | 关联 |
| --- | --- | --- | --- | --- | --- |
| B1 | `GET /api/v1/ai-runs/latest?resource_type=project&resource_id=<任意>` 低权限 token | 403/404 | 路由存在（源码 `del current_user` 无校验）；生产表空，无法产出真实数据 | ⚠️ 静态确认 | P2-1 |
| B2 | `GET /projects/undefined/risk-events` | 客户端应阻止 | 前端 AgentCards 确实发出，**422**（见 D6） | ❌ FAIL | P2-10 |
| B3 | `/health`、`/health/ready` | 200 | 200 | ✅ PASS | — |
| B4 | `/docs`、`/openapi.json` 生产可达 | 生产关闭 | **200 全开** | ❌ FAIL | P2-3 |
| B5 | 登录接口速率限制 | 有限速 | 连续 6 次无任何限制 | ❌ FAIL | P2-3 |
| B6 | PATCH 任务携带 `expected_version` | 409 或 200 | schema `extra="forbid"` → 422；服务层冲突分支从 REST 不可达 | ❌ FAIL（静态+探针） | P1-2 |

### TC-C 业务逻辑（源码+数据核对）

| ID | 用例 | 结果 | 判定 | 关联 |
| --- | --- | --- | --- | --- |
| C1 | "今天"取值方式全量 grep | 6 文件用 `date.today()`/`datetime.now(UTC).date()`，违反自身 `BusinessClock` 规则；容器 TZ=UTC | ❌ FAIL | P1-1 |
| C2 | 风险引擎规则/LLM 合并方向 | `merge_ai_status` max-priority，LLM 不能下调规则风险 | ✅ PASS | 设计正确 |
| C3 | 进度分析当前日期 | `workers/tasks.py:129` 传 UTC `date.today()` 给 LLM | ❌ FAIL | P1-1 |
| C4 | 计划变更闭环（快照指纹/行锁/幂等） | 代码审查全通过（change_proposal.py、plan_lock.py） | ✅ PASS | 高质量 |
| C5 | OA SSO ticket 重放 | 300s 窗口无 nonce → 可重放 | ❌ 静态 FAIL | P1-3 |
| C6 | INACTIVE 用户 SSO 复活 | `user.py:217` 自动置 ACTIVE | ❌ FAIL | P1-4 |
| C7 | 通知去重 | WeCom provider 无 dedup；每日 scan 可重复 | ⚠️ 风险确认 | P3-1/2 |

### TC-D UI 实测（Playwright，admin 会话，只读）

| ID | 检查项 | 实测 | 判定 | 关联 |
| --- | --- | --- | --- | --- |
| D1 | 登录注入后会话引导（/me→渲染） | 侧栏显示 管理员/系统管理员，各页数据加载正常 | ✅ PASS | — |
| D2 | / 首页 桌面 | 布局整洁；但已登录仍显示"登录"快捷卡；自检面板泄露 env/version/失败原因 | ⚠️ FAIL（P3 + P2-11） | P2-11 |
| D3 | /dashboard 桌面 1440 | 卡片+筛选+搜索正常；**0 值统计卡用红色**（需关注 0/延期 0） | ⚠️ FAIL（P3） | — |
| D4 | /projects、/projects/3 | 详情/交付预测不可算有原因说明；空态完整（行动项/进展/问题/每日摘要 AI 文案正常显示） | ✅ PASS | — |
| D5 | /my-tasks | 渲染正常；全量拉取（2 条无感）；筛选行 ≤1024 换行正常 | ✅ PASS（附 P2-5） | P2-5 |
| D6 | /agent | 输入框 14px 正常（初测 9px 为隐藏节点误报，已排除）；**console 捕获 `projects/undefined/risk-events→422`，约 40s 复现一次** | ❌ FAIL | P2-10 |
| D7 | /notifications | 空态+Tabs 正常；375px 下 **scrollWidth=1503** 整页横滚 | ❌ FAIL | P1-5 |
| D8 | /users 表格 | **1440 桌面即溢出（scrollWidth=1600），邮箱列被裁切**；375px 下 906px；42 行分页正常 | ❌ FAIL | P1-5 |
| D9 | 响应式断点 767/768 | 1024：侧栏折叠 72px 图标栏+tooltip ✓；**<768 侧栏宽度归零且无任何替代导航（无汉堡/抽屉/底部 Tab）**——移动端跨页导航不可能 | ❌ FAIL | P1-5 |
| D10 | /tasks/2、/tasks/2/update 移动端 375 | 页面主体可读可操作，更新输入框 14px（<16px iOS 缩放风险排除），提交按钮大目标区 | ✅ PASS | — |
| D11 | 全局 console | 仅 favicon 404（P3）；无 JS 异常、无 hydration 错误 | ✅ PASS（附 P3） | — |

### TC-S 安全与配置

| ID | 检查项 | 结果 | 判定 |
| --- | --- | --- | --- |
| S1 | `.env` 是否入 Git | 否（`git ls-files` 核对） | ✅ PASS |
| S2 | 代码/前端硬编码密钥全量 grep | 无 | ✅ PASS |
| S3 | 业务代码 console.log/print 残留 | 无（仅 CLI 脚本合理输出） | ✅ PASS |
| S4 | nginx：access log 含完整 query string（SSO/JWT 进 URL 时落日志） | 确认（log_format `$request`） | ❌ FAIL | P1-3 共因 |
| S5 | 登录失败审计 | `auth.login_failed` **0 行**（异常路径 db.commit 未执行，失败事件全部丢失）；同时 `login_success` 正常入库 | ❌ FAIL（新发现，并入 P2-9 类） |
| S6 | JWT 密钥长度 | 23 字节 < 32 推荐值（库级警告实测捕获） | ❌ FAIL（同 P0-1） |
| S7 | LLM/Agent 安全：SQL/命令注入面 | 白名单 DSL + policy + 行级预过滤，无裸 SQL——未做对抗性 prompt 注入实测（第一轮未写数据） | ⚠️ 静态 PASS，待 E2E |
| S8 | XSS | 无 dangerouslySetInnerHTML；富文本渲染未深测 | ⚠️ 部分 |

### TC-O 运维/部署

| ID | 检查项 | 结果 | 判定 |
| --- | --- | --- | --- |
| O1 | 容器与端口映射核查 | 7 容器 healthy；host:8000 确认为同一 backend 容器（曾疑双实例，`ss`+容器内回环对比排除） | ✅ PASS |
| O2 | docker-compose TZ | x-backend-env 无 TZ → 全部 UTC | ❌ FAIL（P1-1 共因） |
| O3 | ENVIRONMENT 值 | 生产运行 `local`（自检面板实测可见） | ❌ FAIL |
| O4 | 既有测试套件 | 开源树无测试可执行（Makefile 明示 exit 1） | ⚠️ N/A → 覆盖缺口 P2 |

---

## 4. 汇总统计

| 维度 | 执行 | PASS | FAIL | 警告/N-A |
| --- | --- | --- | --- | --- |
| 认证会话 A | 7 | 3 | 4 | — |
| API 探针 B | 6 | 2 | 4 | — |
| 业务逻辑 C | 7 | 2 | 4 | 1 |
| UI 实测 D | 11 | 5 | 5 | 1（D11 附 P3） |
| 安全配置 S | 8 | 4 | 3 | 1 |
| 运维部署 O | 4 | 1 | 2 | 1 |
| **合计** | **43** | **17 (40%)** | **22 (51%)** | **4 (9%)** |

> FAIL 多数映射到已分级缺陷；无未解释失败。

## 5. 测试结论

1. **功能主干可用**：登录、项目/任务/通知/助手页面在桌面端渲染与数据流全部正常，RBAC 对象级校验在真实探针下工作正确，计划变更/风险引擎等核心链路代码质量高。
2. **安全验证不通过**：默认 JWT 密钥 + 公开 seed 管理员密码 + docs 无限速暴露构成"内网即 admin"的现实路径（A2/A3/A5/B4/B5）。
3. **移动优先承诺未兑现**：D9/D7/D8 实测判定 P1-5。
4. **新发现（测试期产生，超出首轮静态清单）**：
   - S5 **登录失败审计丢失**（异常路径未 commit，0 行 login_failed）——建议并入 P2，修复方案：`auth.py` login 失败分支 `db.commit()` 后再 raise（注意 session 生命周期）。
   - O3 生产 `ENVIRONMENT=local`（影响 CORS/docs 策略，与 P0-1 一并整改）。
5. **放行建议**：TC-A/S 的 P0+P1 项修复复测通过前，不应将该实例交付更多真实用户；修复后需回归 A2–A5、B4–B6、D6、D9。

## 6. 证据清单

- 截图：`ui-home-1440.png`、`ui-dashboard-1440.png`、`ui-projects-1440.png`、`ui-users-375.png`、`ui-agent-overflow-1440.png`、`ui-agent-empty-1440.png`、`ui-dashboard-1024.png`、`ui-dashboard-767.png`、`ui-task-mobile-375.png`（/data/test）
- 网络/console：`/data/test/.playwright-mcp/console-*.log`（422 risk-events ×2、favicon 404）
- API 原始响应：`/tmp/login.json`、`/tmp/x.json`；JWT 样例 `/tmp/admin_jwt.txt`（12h 过期，无需处置）
- DB 取证（只读 SELECT）：users/audit_logs 关键行、bcrypt 容器内校验输出
