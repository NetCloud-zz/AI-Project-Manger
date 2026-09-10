"""AIRun status APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.ai_run import AIRunType
from app.models.user import User
from app.schemas.ai_run import AIRunResponse
from app.services.ai_run import AIRunService

router = APIRouter(prefix="/ai-runs", tags=["ai-runs"])


@router.get("/latest/by-resource", response_model=AIRunResponse | None)
def latest_ai_run(
    resource_type: str = Query(..., min_length=1, max_length=64),
    resource_id: str = Query(..., min_length=1, max_length=64),
    run_type: AIRunType | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIRunResponse | None:
    del current_user
    run = AIRunService(db).latest(
        resource_type=resource_type,
        resource_id=resource_id,
        run_type=run_type,
    )
    if run is None:
        return None
    return AIRunResponse.model_validate(run)


@router.get("/{run_id}", response_model=AIRunResponse)
def get_ai_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIRunResponse:
    del current_user
    run = AIRunService(db).get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found")
    return AIRunResponse.model_validate(run)
