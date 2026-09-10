"""User management routes (admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_client_ip, require_roles
from app.models.user import User, UserRole
from app.core.config import get_settings
from app.integrations.oa.exceptions import OaNotConfiguredError
from app.schemas.user import OaSyncResult, UserCreate, UserPasswordReset, UserResponse, UserUpdate
from app.services.exceptions import DomainValidationError
from app.services.user import UserAlreadyExistsError, UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user (admin only)",
)
def create_user(
    body: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> User:
    service = UserService(db)
    try:
        user = service.create_user(
            body,
            actor_id=current_user.id,
            ip_address=get_client_ip(request),
        )
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with this {exc.field} already exists",
        ) from exc
    db.commit()
    db.refresh(user)
    return user


@router.get(
    "",
    response_model=list[UserResponse],
    summary="List users (admin only)",
)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[User]:
    return UserService(db).list_users()


@router.post(
    "/sync-from-oa",
    response_model=OaSyncResult,
    summary="Sync active OA directory users into local users (admin only, OA read-only)",
)
def sync_users_from_oa(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> OaSyncResult:
    if not get_settings().oa_mysql_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OA MySQL is not configured",
        )
    try:
        result = UserService(db).sync_users_from_oa(
            actor_id=current_user.id,
            ip_address=get_client_ip(request),
        )
    except OaNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    db.commit()
    return result


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user (admin only)",
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> User:
    user = UserService(db).get_user(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update a user (admin only)",
)
def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> User:
    service = UserService(db)
    user = service.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        updated = service.update_user(
            user,
            body,
            actor_id=current_user.id,
            ip_address=get_client_ip(request),
        )
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with this {exc.field} already exists",
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    db.refresh(updated)
    return updated


@router.post(
    "/{user_id}/reset-password",
    response_model=UserResponse,
    summary="Reset a user's password (admin only)",
)
def reset_password(
    user_id: int,
    body: UserPasswordReset,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> User:
    service = UserService(db)
    user = service.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    updated = service.reset_password(
        user,
        body.password,
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(updated)
    return updated


@router.delete(
    "/{user_id}",
    response_model=UserResponse,
    summary="Deactivate a user (soft delete, admin only)",
)
def deactivate_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> User:
    """Soft-delete by setting status=INACTIVE. Hard delete is blocked by FKs."""
    service = UserService(db)
    user = service.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        updated = service.deactivate_user(
            user,
            actor_id=current_user.id,
            ip_address=get_client_ip(request),
        )
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    db.refresh(updated)
    return updated
