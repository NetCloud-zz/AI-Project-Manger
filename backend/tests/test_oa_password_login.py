"""Username/password login verified against OA `pass` (unsalted MD5)."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base
from app.core.security import hash_password
from app.integrations.oa.client import OaAdminRecord, OaMySQLClient
from app.integrations.oa.exceptions import OaUnavailableError
from app.integrations.oa.password import verify_oa_password
from app.models.user import User, UserRole, UserStatus
from app.services.auth import AuthenticationError, AuthService, LoginUnavailableError

OA_PASSWORD = "Oa-Secret-2026"


def _md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()  # noqa: S324


def _record(oa_id: int = 7, user: str = "zhangsan") -> OaAdminRecord:
    return OaAdminRecord(
        id=oa_id,
        user=user,
        name="测试用户",
        status=1,
        email=None,
        mobile=None,
        deptname="研发部",
        ranking=None,
        num=None,
        type=None,
        weixinid=None,
        quitdt=None,
    )


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def settings():
    return get_settings().model_copy(
        update={
            "OA_MYSQL_HOST": "oa.example.invalid",
            "OA_MYSQL_USER": "reader",
            "OA_MYSQL_PASSWORD": "x",
            "OA_MYSQL_DATABASE": "oa",
            "OA_PASSWORD_LOGIN_ENABLED": True,
        }
    )


@pytest.fixture
def oa_calls(monkeypatch):
    """Fake OA directory: one active user ``zhangsan`` (id 7) with OA_PASSWORD."""
    calls: list[dict] = []

    def fake_verify(self, *, password, oa_admin_id=None, username=None):
        calls.append({"oa_admin_id": oa_admin_id, "username": username})
        matches_user = oa_admin_id == 7 or username == "zhangsan"
        if matches_user and verify_oa_password(password, _md5(OA_PASSWORD)):
            return _record()
        return None

    monkeypatch.setattr(OaMySQLClient, "verify_active_password", fake_verify)
    return calls


def _linked_user(db: Session, *, status: UserStatus = UserStatus.ACTIVE) -> User:
    user = User(
        name="测试用户",
        username="zhangsan",
        password_hash=hash_password("local-pass"),
        role=UserRole.MEMBER,
        status=status,
        oa_admin_id=7,
    )
    db.add(user)
    db.flush()
    return user


def test_verify_oa_password_matches_md5_case_insensitively():
    assert verify_oa_password(OA_PASSWORD, _md5(OA_PASSWORD).upper())
    assert not verify_oa_password("wrong", _md5(OA_PASSWORD))
    assert not verify_oa_password(OA_PASSWORD, None)
    assert not verify_oa_password("", _md5(""))


def test_client_verify_never_returns_hash(monkeypatch, settings):
    row = {"id": 7, "user": "zhangsan", "name": "测试用户", "status": 1, "pass": _md5(OA_PASSWORD)}
    captured: list[str] = []

    def fake_select(self, sql, params):
        captured.append(sql)
        return [row]

    monkeypatch.setattr(OaMySQLClient, "_execute_select", fake_select)
    client = OaMySQLClient(settings)

    record = client.verify_active_password(password=OA_PASSWORD, oa_admin_id=7)
    assert record is not None and record.id == 7
    assert not hasattr(record, "pass")
    assert "`status` IN (0, 1)" in captured[0]
    assert client.verify_active_password(password="wrong", oa_admin_id=7) is None


def test_linked_user_logs_in_with_oa_password(db, settings, oa_calls):
    user = _linked_user(db)
    token, logged_in = AuthService(db, settings).login(username="zhangsan", password=OA_PASSWORD)
    assert token
    assert logged_in.id == user.id
    assert oa_calls == [{"oa_admin_id": 7, "username": None}]


def test_linked_user_local_password_is_rejected(db, settings, oa_calls):
    _linked_user(db)
    with pytest.raises(AuthenticationError):
        AuthService(db, settings).login(username="zhangsan", password="local-pass")


def test_unknown_local_user_is_created_from_oa(db, settings, oa_calls):
    _token, user = AuthService(db, settings).login(username="zhangsan", password=OA_PASSWORD)
    assert user.oa_admin_id == 7
    assert user.role == UserRole.MEMBER
    assert oa_calls == [{"oa_admin_id": None, "username": "zhangsan"}]


def test_default_password_is_refused_without_querying_oa(db, settings, oa_calls):
    _linked_user(db)
    with pytest.raises(AuthenticationError, match="初始密码"):
        AuthService(db, settings).login(username="zhangsan", password="123456")
    assert oa_calls == []


def test_locally_deactivated_user_is_refused(db, settings, oa_calls):
    _linked_user(db, status=UserStatus.INACTIVE)
    with pytest.raises(AuthenticationError):
        AuthService(db, settings).login(username="zhangsan", password=OA_PASSWORD)


def test_oa_outage_does_not_fall_back_to_local_password(db, settings, monkeypatch):
    _linked_user(db)

    def boom(self, **_kwargs):
        raise OaUnavailableError("down")

    monkeypatch.setattr(OaMySQLClient, "verify_active_password", boom)
    with pytest.raises(LoginUnavailableError):
        AuthService(db, settings).login(username="zhangsan", password="local-pass")


def test_local_only_user_keeps_local_password(db, settings, oa_calls):
    db.add(
        User(
            name="本地管理员",
            username="admin",
            password_hash=hash_password("local-pass"),
            role=UserRole.ADMIN,
        )
    )
    db.flush()
    _token, user = AuthService(db, settings).login(username="admin", password="local-pass")
    assert user.username == "admin"
    assert oa_calls == []


def test_disabled_flag_keeps_local_login(db, settings, oa_calls):
    _linked_user(db)
    off = settings.model_copy(update={"OA_PASSWORD_LOGIN_ENABLED": False})
    _token, user = AuthService(db, off).login(username="zhangsan", password="local-pass")
    assert user.username == "zhangsan"
    assert oa_calls == []
