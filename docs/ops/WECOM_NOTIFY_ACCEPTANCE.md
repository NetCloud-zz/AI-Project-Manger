# WeCom 通知验收（P3-NOTIFY / C7）

未配置 `WECOM_CORP_ID` / `WECOM_AGENT_ID` / `WECOM_SECRET` 时，系统使用 console 降级——**不能宣称外部渠道达标**。

## 配置后验收

1. 在 `.env` 填入企业微信应用凭证与测试收件人的 `wechat_user_id`。
2. `docker compose up -d backend worker scheduler`，确认 readiness 中 WeCom = up。
3. **计划变更 / 风险**：走 `notification_events` outbox（`dedupe_key` UNIQUE）；二次扫描不得重复投递同一 `dedupe_key+recipient+channel`。
4. **每日提醒 / 缺进度**：`TASK_REMINDER:{task_id}:{date}` / `MISSING_PROGRESS:{task_id}:{date}` 经 Redis NX 一次性认领；同日二次 Beat 或手工重跑应跳过。
5. 真实投递：选 1 名测试用户，确认企微收到且系统状态 `SENT`；点确认后为 `ACKNOWLEDGED`。
6. 证据：通知中心截图、outbox 行、企微侧截图（脱敏）归档到 `docs/qa/`。

## 本机未配置时的可回归点

```bash
# 单元：一次性认领幂等
cd backend && .venv/bin/pytest tests/test_notification_once.py -q
```
