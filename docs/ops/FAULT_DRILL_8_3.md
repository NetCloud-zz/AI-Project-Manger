# 故障注入演练登记表（对照 FULL_FUNCTION_TESTING_GUIDE.md §8.3）
#
# 规则：仅在登记的测试环境执行；记录故障开始/恢复时间与证据路径。
# 本文件是模板——复制为 `FAULT_DRILL_<env>_<date>.md` 填写后归档到 docs/qa/。

## 环境登记

| 字段 | 值 |
| --- | --- |
| 环境名 / URL | |
| 执行人 | |
| 窗口开始 | |
| 窗口结束 | |
| 数据前缀 | QA-* |
| 备注 | |

## 清单

| 故障 | 注入时点 | 开始 | 恢复 | 核验结果 | 证据 |
| --- | --- | --- | --- | --- | --- |
| 浏览器断网 | 写入前 / 提交中 / 响应前 | | | | |
| API 4xx／5xx | | | | | |
| LLM 超时／无效 JSON | | | | | |
| Worker 停止 | | | | | |
| Redis 不可用 | | | | | |
| 后端重启 | 执行前 / 中途 / 写入后回执前 | | | | |
| 数据库拒绝／事务失败 | | | | | |

## 最小可执行烟测（本机 compose）

```bash
# Worker 停止
docker compose stop worker
# …提交进展 / 触发通知…
docker compose start worker

# Redis（会连带影响限速、SSO ticket、日扫去重）
docker compose stop redis
# …观察降级，勿宣称已投递…
docker compose start redis

# 后端重启
docker compose restart backend
```

未命中「写入后、回执前」窗口时，不得宣称该故障窗口已覆盖。
