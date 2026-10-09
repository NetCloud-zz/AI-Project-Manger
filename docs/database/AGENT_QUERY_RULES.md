# AGENT_QUERY_RULES

> Copyright 2024–2026 Jack Zhang. Apache License 2.0；保留 NOTICE 署名。
> 采集日期：2026-09-15；结构来源：实际 PostgreSQL 只读目录；业务语义来源：当前工作区模型、迁移与服务。
> 未读取业务记录。PUBLIC 仅表示字段可经授权业务 DTO 使用，不表示互联网公开或授权直连数据库。

## RULE 1

优先使用已经定义的业务实体，不要直接猜数据库表。

## RULE 2

优先使用 semantic_aliases 将自然语言映射到字段；重名需结合实体消歧。

## RULE 3

JOIN 必须优先使用 join_paths，并由受控服务编译。

## RULE 4

不存在已确认关系时，不得自行假设 JOIN；MEDIUM/LOW 推断不可用于自动 JOIN。

## RULE 5

默认应用 soft_delete_rules；不存在软删除机制时不得虚构条件。

## RULE 6

必须应用 tenant / organization / workspace 范围（存在时）及当前系统对象权限；不可移除范围约束。

## RULE 7

不得读取、过滤、排序、聚合或输出 HIDDEN 字段，亦不得将其放入 RAG。

## RULE 8

不得向用户暴露 INTERNAL ID，除非业务操作需要；内部审计字段不作为普通查询能力。

## RULE 9

状态查询必须使用对应实体状态字典；未知值返回 UNKNOWN，不发明状态。

## RULE 10

Agent 不直接执行数据库写 SQL。

## RULE 11

写操作必须调用 Business Tool，并复用 Business Service 权限和校验。

## RULE 12

重要写操作必须 requires_confirmation = true；本语义层建议所有 WRITE TOOL 默认确认。

## 执行补充

未知实体、字段、关系、枚举值或缺失身份均拒绝执行。INTERNAL ID 仅在工具定位确有需要时传递；HIDDEN 字段禁止查询，不因管理员身份例外。聚合先权限过滤，再按业务粒度去重；NULL 与 0 分开；结果必须报告 scope、时间窗口、分页覆盖和截断。SENSITIVE 字段只可通过专用脱敏 DTO 摘录。

当前没有 tenant/organization/workspace 键，不得伪造多租户保障；必须执行已存在的 RBAC 与对象级权限。将来加入租户字段时，scope 由可信服务注入，Agent 不得移除。
