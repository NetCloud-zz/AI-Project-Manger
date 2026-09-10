"""Current-user routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserResponse, summary="Get the authenticated user")
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
