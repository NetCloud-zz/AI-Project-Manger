# 助手修复验收与发布操作清单

Copyright 2024–2026 Jack Zhang. Licensed under the Apache License, Version 2.0.

配套方案：[ASSISTANT_REPAIR_PLAN.md](ASSISTANT_REPAIR_PLAN.md)。  
本页是可执行验收步骤，不代表已对外发版。脱敏夹具：`backend/evals/assistant_repair_24x1.yaml`。

## 1. 自动化（本地／CI）

```bash
cd backend
.venv/bin/pytest tests/test_assistant_repair_*.py tests/test_command_planning_repair.py \
  tests/test_batch_owner_refs.py tests/test_mutation_intent.py -q
```

## 2. 隔离 PostgreSQL

要求：可写的 PostgreSQL（Compose 中的 `postgres` 即可），并设置：

```bash
export COMMAND_PG_TESTS=1
cd backend && .venv/bin/pytest tests/test_command_planning_postgres.py -q
```

覆盖：迁移往返、并发独立创建、HTTP 取消等待写入落盘、原子批次外部停止回滚。  
真实模型用例默认跳过，需另设 `COMMAND_REAL_MODEL=1`。

## 3. Redis

```bash
export REDIS_TESTS=1
cd backend && .venv/bin/pytest tests/test_redis_ready.py -q
```

## 4. 脱敏标准场景（24 任务 + 1 里程碑）

1. 使用夹具 `assistant_repair_24x1.yaml`（仅合成姓名）。
2. 在隔离库准备 `PRJ-1001` 与账号「测试甲／测试乙」。
3. 按五种排版（Markdown／压平／自然段／表格／JSON 文本）各跑 ≥3 次真实模型。
4. 验收：任务 24、里程碑 1；协作人／工期／待定负责人／部分日期与夹具一致；里程碑走 `create_milestone`。
5. 记录模型标识、修复轮次、耗时；日志脱敏。评估证明采样表现，不证明任意输入永远正确。

## 5. 灰度与回滚准备（发版前）

1. 备份 Postgres（`pg_dump`）并在隔离环境验证可恢复。
2. 确认单一 Alembic head；无破坏性降级依赖。
3. 通过 `COMMAND_PLAN_ENABLED` 灰度新规划路径（仅影响新请求）。
4. 先后端／Worker／Scheduler 同版本，再前端；观察错误率与回读差异。
5. 通过第 7 节门槛后再 bump 版本并写 `docs/releases/X.Y.Z.md`。

## 6. 仍需人工确认才可勾「完成定义」

- 真实模型 24+1 全矩阵评估报告
- 生产／准生产备份恢复演练记录
- 正式版本号与发布说明已发布
