"""Read-only MySQL client for RockOA ``osri_admin`` (and configurable table).

Hard rule: this client never issues INSERT/UPDATE/DELETE/DDL against OA.
Connections also request ``TRANSACTION READ ONLY`` when supported.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.core.config import Settings, get_settings
from app.integrations.oa.exceptions import OaNotConfiguredError, OaReadOnlyError, OaUserNotFoundError

_MUTATING_PREFIXES = (
    "insert",
    "update",
    "delete",
    "replace",
    "alter",
    "drop",
    "create",
    "truncate",
    "rename",
    "grant",
    "revoke",
    "call",
    "load",
    "handler",
    "lock",
)


@dataclass(frozen=True, slots=True)
class OaAdminRecord:
    """Safe projection of an OA admin row (never includes password fields)."""

    id: int
    user: str
    name: str
    status: int
    email: str | None
    mobile: str | None
    deptname: str | None
    ranking: str | None
    num: str | None
    type: int | None
    weixinid: str | None
    quitdt: date | None


_SAFE_COLUMNS = (
    "id",
    "user",
    "name",
    "status",
    "email",
    "mobile",
    "deptname",
    "ranking",
    "num",
    "type",
    "weixinid",
    "quitdt",
)


class OaMySQLClient:
    """Read-only accessor for the OA MySQL user directory."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def ensure_configured(self) -> None:
        if not self.settings.oa_mysql_configured:
            raise OaNotConfiguredError(
                "OA MySQL is not configured "
                "(set OA_MYSQL_HOST/OA_MYSQL_USER/OA_MYSQL_PASSWORD/OA_MYSQL_DATABASE)"
            )

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        self.ensure_configured()
        try:
            import pymysql
        except ImportError as exc:  # pragma: no cover - dependency declared in pyproject
            raise OaNotConfiguredError("pymysql is not installed") from exc

        conn = pymysql.connect(
            host=self.settings.OA_MYSQL_HOST,
            port=self.settings.OA_MYSQL_PORT,
            user=self.settings.OA_MYSQL_USER,
            password=self.settings.OA_MYSQL_PASSWORD or "",
            database=self.settings.OA_MYSQL_DATABASE,
            charset="utf8mb4",
            connect_timeout=10,
            read_timeout=30,
            write_timeout=5,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
        try:
            with conn.cursor() as cur:
                # Best-effort; ignore if the server rejects it.
                try:
                    cur.execute("SET SESSION TRANSACTION READ ONLY")
                except Exception:  # noqa: BLE001
                    pass
            yield conn
        finally:
            conn.close()

    def _assert_select_only(self, sql: str) -> None:
        normalized = " ".join(sql.strip().lower().split())
        if not normalized.startswith("select"):
            raise OaReadOnlyError("Only SELECT is allowed against OA MySQL")
        for prefix in _MUTATING_PREFIXES:
            # Reject embedded statements after semicolon.
            if f";{prefix}" in normalized.replace(" ", ""):
                raise OaReadOnlyError("Mutating SQL is forbidden against OA MySQL")

    def _execute_select(self, sql: str, params: tuple[Any, ...] | list[Any]) -> list[dict[str, Any]]:
        self._assert_select_only(sql)
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                return list(rows)

    def _table(self) -> str:
        # Table name comes from settings only (not user input).
        name = self.settings.OA_MYSQL_ADMIN_TABLE.strip()
        if not name.replace("_", "").isalnum():
            raise OaNotConfiguredError("Invalid OA_MYSQL_ADMIN_TABLE")
        return f"`{name}`"

    def _active_clause(self) -> str:
        # Per ops:在职 = status IN (0, 1). Also exclude already-quit rows when quitdt set.
        return "`status` IN (0, 1) AND (`quitdt` IS NULL OR `quitdt` > CURDATE())"

    def _row_to_record(self, row: dict[str, Any]) -> OaAdminRecord:
        quitdt = row.get("quitdt")
        if isinstance(quitdt, datetime):
            quitdt = quitdt.date()
        return OaAdminRecord(
            id=int(row["id"]),
            user=str(row["user"] or "").strip(),
            name=str(row.get("name") or row.get("user") or "").strip() or str(row["user"]),
            status=int(row.get("status") or 0),
            email=(str(row["email"]).strip() if row.get("email") else None) or None,
            mobile=(str(row["mobile"]).strip() if row.get("mobile") else None) or None,
            deptname=(str(row["deptname"]).strip() if row.get("deptname") else None) or None,
            ranking=(str(row["ranking"]).strip() if row.get("ranking") else None) or None,
            num=(str(row["num"]).strip() if row.get("num") else None) or None,
            type=int(row["type"]) if row.get("type") is not None else None,
            weixinid=(str(row["weixinid"]).strip() if row.get("weixinid") else None) or None,
            quitdt=quitdt if isinstance(quitdt, date) else None,
        )

    def ping(self) -> bool:
        rows = self._execute_select("SELECT 1 AS ok", ())
        return bool(rows and rows[0].get("ok") == 1)

    def get_active_by_id(self, oa_admin_id: int) -> OaAdminRecord:
        cols = ", ".join(f"`{c}`" for c in _SAFE_COLUMNS)
        sql = (
            f"SELECT {cols} FROM {self._table()} "
            f"WHERE `id` = %s AND {self._active_clause()} LIMIT 1"
        )
        rows = self._execute_select(sql, (oa_admin_id,))
        if not rows:
            raise OaUserNotFoundError(
                "OA user not found or not active",
                oa_admin_id=oa_admin_id,
            )
        return self._row_to_record(rows[0])

    def get_active_by_username(self, username: str) -> OaAdminRecord:
        cols = ", ".join(f"`{c}`" for c in _SAFE_COLUMNS)
        sql = (
            f"SELECT {cols} FROM {self._table()} "
            f"WHERE `user` = %s AND {self._active_clause()} LIMIT 1"
        )
        rows = self._execute_select(sql, (username,))
        if not rows:
            raise OaUserNotFoundError("OA user not found or not active")
        return self._row_to_record(rows[0])

    def list_active(self) -> list[OaAdminRecord]:
        cols = ", ".join(f"`{c}`" for c in _SAFE_COLUMNS)
        sql = (
            f"SELECT {cols} FROM {self._table()} "
            f"WHERE {self._active_clause()} ORDER BY `sort`, `id`"
        )
        rows = self._execute_select(sql, ())
        return [self._row_to_record(row) for row in rows if str(row.get("user") or "").strip()]
