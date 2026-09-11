"""Validate Agent Query DSL against field whitelist and safe operators."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.agents.query.fields import ENTITY_FIELDS
from app.agents.query.schema import AgentQueryRequest, QueryAggregate, QueryFilter, QuerySort
from app.services.exceptions import DomainValidationError

_DATE_OPS = {"before", "after", "between", "gt", "gte", "lt", "lte", "eq", "ne"}
_LIST_OPS = {"in", "not_in"}
_NULL_OPS = {"is_null"}
_BLOCKED_FIELDS = frozenset(
    {
        "password",
        "password_hash",
        "secret",
        "token",
        "api_key",
        "permission_mask",
        "tenant_secret",
        "__dict__",
        "__class__",
    }
)


class QueryPolicyValidator:
    def __init__(self, entity: str) -> None:
        if entity not in ENTITY_FIELDS:
            raise DomainValidationError(f"不支持的查询实体: {entity}")
        self.entity = entity
        self.allowed = ENTITY_FIELDS[entity]

    def validate(self, request: AgentQueryRequest) -> AgentQueryRequest:
        for filt in request.filters:
            self._check_filter(filt)
        for sort in request.sort:
            self._check_sort(sort)
        for field in request.group_by:
            self._check_field(field)
        for agg in request.aggregates:
            self._check_aggregate(agg)
        return request

    def _check_field(self, field: str) -> None:
        if field in _BLOCKED_FIELDS or field.startswith("_"):
            raise DomainValidationError(f"非法查询字段: {field}")
        if field not in self.allowed and not field.endswith("_count"):
            # aggregate aliases like overdue_count allowed in sort only after aggregates
            raise DomainValidationError(f"字段不在白名单: {field}")

    def _check_filter(self, filt: QueryFilter) -> None:
        if filt.field in _BLOCKED_FIELDS or ";" in filt.field or "--" in filt.field:
            raise DomainValidationError("INVALID_ARGUMENT: 非法字段")
        if filt.field not in self.allowed:
            raise DomainValidationError(f"字段不在白名单: {filt.field}")
        if filt.op in _NULL_OPS:
            return
        if filt.op in _LIST_OPS:
            if not isinstance(filt.value, list) or not filt.value:
                raise DomainValidationError(f"{filt.op} 需要非空列表")
            return
        if filt.op == "between":
            if not isinstance(filt.value, (list, tuple)) or len(filt.value) != 2:
                raise DomainValidationError("between 需要长度为 2 的区间")
            return
        if filt.op in _DATE_OPS and filt.field.endswith("date"):
            self._coerce_dateish(filt.value)
        if filt.op == "contains" and not isinstance(filt.value, str):
            raise DomainValidationError("contains 需要字符串")

    def _check_sort(self, sort: QuerySort) -> None:
        if sort.field in self.allowed or sort.field.endswith("_count"):
            return
        raise DomainValidationError(f"排序字段不在白名单: {sort.field}")

    def _check_aggregate(self, agg: QueryAggregate) -> None:
        if agg.field not in self.allowed and agg.field != "*":
            raise DomainValidationError(f"聚合字段不在白名单: {agg.field}")

    @staticmethod
    def _coerce_dateish(value: Any) -> None:
        if value is None or isinstance(value, (date, datetime)):
            return
        if isinstance(value, str):
            try:
                date.fromisoformat(value[:10])
                return
            except ValueError as exc:
                raise DomainValidationError("日期格式无效") from exc
        raise DomainValidationError("日期类型无效")
