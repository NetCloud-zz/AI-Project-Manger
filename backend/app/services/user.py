"""User management business logic."""

from __future__ import annotations

import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.integrations.oa.client import OaAdminRecord, OaMySQLClient
from app.integrations.oa.exceptions import OaNotConfiguredError
from app.models.user import User, UserRole, UserStatus
from app.repositories.user import UserRepository
from app.schemas.user import OaSyncResult, UserCreate, UserUpdate
from app.services.audit import AuditService
from app.services.exceptions import DomainValidationError


class UserAlreadyExistsError(Exception):
    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"User with this {field} already exists")


class UserService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = UserRepository(db)
        self.audit = AuditService(db)

    def create_user(
        self,
        data: UserCreate,
        *,
        actor_id: int | None = None,
        ip_address: str | None = None,
    ) -> User:
        if self.repo.get_by_username(data.username):
            raise UserAlreadyExistsError("username")
        if data.email and self.repo.get_by_email(data.email):
            raise UserAlreadyExistsError("email")

        user = User(
            name=data.name,
            username=data.username,
            email=data.email,
            mobile=data.mobile,
            department=data.department,
            wechat_user_id=data.wechat_user_id,
            role=data.role,
            password_hash=hash_password(data.password),
        )
        self.repo.add(user)
        self.audit.record(
            action="user.create",
            resource_type="user",
            resource_id=str(user.id),
            user_id=actor_id,
            new_value=self.audit.user_to_dict(user),
            ip_address=ip_address,
        )
        return user

    def update_user(
        self,
        user: User,
        data: UserUpdate,
        *,
        actor_id: int | None = None,
        ip_address: str | None = None,
    ) -> User:
        old_snapshot = self.audit.user_to_dict(user)
        updates = data.model_dump(exclude_unset=True)

        if "email" in updates and updates["email"]:
            existing = self.repo.get_by_email(updates["email"])
            if existing and existing.id != user.id:
                raise UserAlreadyExistsError("email")

        if "status" in updates and updates["status"] == UserStatus.INACTIVE:
            self._guard_deactivate(user, actor_id=actor_id)
        if "role" in updates and updates["role"] != UserRole.ADMIN:
            self._guard_demote_last_admin(user, new_role=updates["role"])

        for field, value in updates.items():
            setattr(user, field, value)

        self.repo.save(user)
        self.audit.record(
            action="user.update",
            resource_type="user",
            resource_id=str(user.id),
            user_id=actor_id,
            old_value=old_snapshot,
            new_value=self.audit.user_to_dict(user),
            ip_address=ip_address,
        )
        if "role" in updates:
            self.audit.record(
                action="user.role_change",
                resource_type="user",
                resource_id=str(user.id),
                user_id=actor_id,
                old_value={"role": old_snapshot["role"]},
                new_value={"role": user.role.value},
                ip_address=ip_address,
            )
        if "status" in updates and updates["status"] != old_snapshot["status"]:
            self.audit.record(
                action="user.status_change",
                resource_type="user",
                resource_id=str(user.id),
                user_id=actor_id,
                old_value={"status": old_snapshot["status"]},
                new_value={"status": user.status.value},
                ip_address=ip_address,
            )
        return user

    def reset_password(
        self,
        user: User,
        password: str,
        *,
        actor_id: int | None = None,
        ip_address: str | None = None,
    ) -> User:
        user.password_hash = hash_password(password)
        self.repo.save(user)
        self.audit.record(
            action="user.password_reset",
            resource_type="user",
            resource_id=str(user.id),
            user_id=actor_id,
            new_value={"password_reset": True},
            ip_address=ip_address,
        )
        return user

    def deactivate_user(
        self,
        user: User,
        *,
        actor_id: int | None = None,
        ip_address: str | None = None,
    ) -> User:
        """Soft-delete: set status=INACTIVE. Hard delete is blocked by FKs."""
        return self.update_user(
            user,
            UserUpdate(status=UserStatus.INACTIVE),
            actor_id=actor_id,
            ip_address=ip_address,
        )

    def list_users(self) -> list[User]:
        return self.repo.list_all()

    def get_user(self, user_id: int) -> User | None:
        return self.repo.get_by_id(user_id)

    def ensure_user_from_oa(
        self,
        record: OaAdminRecord,
        *,
        actor_id: int | None = None,
        ip_address: str | None = None,
        default_role: UserRole = UserRole.MEMBER,
    ) -> tuple[User, bool]:
        """Upsert a local user from an OA admin row. Returns (user, created)."""
        existing = self.repo.get_by_oa_admin_id(record.id)
        if existing is None:
            existing = self.repo.get_by_username(record.user)

        email = self._safe_email_for(record.email, exclude_user_id=existing.id if existing else None)
        weixin = record.weixinid or None

        if existing is None:
            user = User(
                name=record.name[:100],
                username=record.user[:64],
                email=email,
                mobile=(record.mobile[:32] if record.mobile else None),
                department=(record.deptname[:128] if record.deptname else None),
                wechat_user_id=(weixin[:128] if weixin else None),
                oa_admin_id=record.id,
                role=default_role,
                status=UserStatus.ACTIVE,
                # Unusable random password; login is via OA SSO (or admin reset).
                password_hash=hash_password(secrets.token_urlsafe(32)),
            )
            self.repo.add(user)
            self.audit.record(
                action="user.create_from_oa",
                resource_type="user",
                resource_id=str(user.id),
                user_id=actor_id,
                new_value=self.audit.user_to_dict(user),
                ip_address=ip_address,
            )
            return user, True

        old_snapshot = self.audit.user_to_dict(existing)
        existing.name = record.name[:100]
        existing.username = record.user[:64]
        if email is not None:
            existing.email = email
        if record.mobile:
            existing.mobile = record.mobile[:32]
        if record.deptname:
            existing.department = record.deptname[:128]
        if weixin and not existing.wechat_user_id:
            existing.wechat_user_id = weixin[:128]
        existing.oa_admin_id = record.id
        # Never auto-reactivate a locally deactivated account via SSO/sync.
        # Admins must explicitly set status=ACTIVE again.
        self.repo.save(existing)
        self.audit.record(
            action="user.sync_from_oa",
            resource_type="user",
            resource_id=str(existing.id),
            user_id=actor_id,
            old_value=old_snapshot,
            new_value=self.audit.user_to_dict(existing),
            ip_address=ip_address,
        )
        return existing, False

    def sync_users_from_oa(
        self,
        *,
        actor_id: int | None = None,
        ip_address: str | None = None,
    ) -> OaSyncResult:
        """Pull active OA admins into local users (identity only; roles stay local)."""
        client = OaMySQLClient(self.settings)
        try:
            records = client.list_active()
        except OaNotConfiguredError:
            raise

        created = updated = skipped = 0
        for record in records:
            if not record.user:
                skipped += 1
                continue
            try:
                _user, was_created = self.ensure_user_from_oa(
                    record,
                    actor_id=actor_id,
                    ip_address=ip_address,
                )
            except UserAlreadyExistsError:
                skipped += 1
                continue
            if was_created:
                created += 1
            else:
                updated += 1

        self.audit.record(
            action="user.oa_sync",
            resource_type="oa_directory",
            resource_id="osri_admin",
            user_id=actor_id,
            new_value={
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "total_oa": len(records),
            },
            ip_address=ip_address,
        )
        return OaSyncResult(
            created=created,
            updated=updated,
            skipped=skipped,
            total_oa=len(records),
        )

    def _safe_email_for(self, email: str | None, *, exclude_user_id: int | None) -> str | None:
        if not email:
            return None
        # Soft-validate: skip malformed addresses rather than fail SSO.
        if "@" not in email or len(email) > 255:
            return None
        existing = self.repo.get_by_email(email)
        if existing and existing.id != exclude_user_id:
            return None
        return email

    def _count_active_admins(self) -> int:
        stmt = select(func.count()).select_from(User).where(
            User.role == UserRole.ADMIN,
            User.status == UserStatus.ACTIVE,
        )
        return int(self.db.scalar(stmt) or 0)

    def _guard_deactivate(self, user: User, *, actor_id: int | None) -> None:
        if actor_id is not None and user.id == actor_id:
            msg = "You cannot deactivate your own account"
            raise DomainValidationError(msg)
        if (
            user.role == UserRole.ADMIN
            and user.status == UserStatus.ACTIVE
            and self._count_active_admins() <= 1
        ):
            msg = "Cannot deactivate the last active administrator"
            raise DomainValidationError(msg)

    def _guard_demote_last_admin(self, user: User, *, new_role: UserRole) -> None:
        if user.role != UserRole.ADMIN or user.status != UserStatus.ACTIVE:
            return
        if new_role == UserRole.ADMIN:
            return
        if self._count_active_admins() <= 1:
            msg = "Cannot demote the last active administrator"
            raise DomainValidationError(msg)
