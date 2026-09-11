# Release 0.2.1 — 2026-09-10

本机全量烟测通过后的修复发布（阶段 0–5）。

## 变更摘要

- **安全**：弱 JWT 拒绝、`ENVIRONMENT=prod`、OpenAPI 关闭、登录限速、SSO ticket 一次性、登录失败审计、`ai-runs` 对象鉴权
- **业务**：BusinessClock / TZ、任务乐观锁 409、删任务×进展竞态 404、变更方案文档约定
- **助手**：多创建 CMD-01（mutation 意图 + independent 默认）、讨论不写 AG-10
- **前端**：移动 Tab+汉堡、表本地滚动、风险卡无 `undefined` 请求、品牌 badge、看板 0 值中性色、首页自检脱敏
- **工程化**：`make test` 最小集、`/tasks/my` 服务端分页、日扫 Redis NX 去重、演练/WeCom/eval 文档

## 全量烟测

见 `docs/qa/QA-20260910-FULL/REPORT.md`：**31 PASS / 0 FAIL**（本机 `127.0.0.1:8080`）。

## 安装

```bash
tar -xzf project-agent-0.2.1.tar.gz
cd project-agent-0.2.1   # 或解压后的目录名
cp .env.example .env     # 填写 JWT_SECRET（≥32）等；勿用公开 seed 口令
docker compose up -d --build
curl -sS http://localhost/health
```

默认入口为 Nginx（compose 映射端口以本机 `.env` / `docker-compose.yml` 为准）。

## 明确未宣称

- WeCom 真实投递（需配置后按 `docs/ops/WECOM_NOTIFY_ACCEPTANCE.md`）
- §8.3 破坏性故障演练（需登记窗口，模板见 `docs/ops/FAULT_DRILL_8_3.md`）
