"""Aggregator for versioned API routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    action_items,
    agent,
    ai_runs,
    auth,
    change_proposals,
    dashboard,
    gantt,
    issues,
    me,
    notifications,
    plan_drafts,
    planning,
    progress,
    projects,
    risks,
    tasks,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(users.router)
api_router.include_router(projects.router)
api_router.include_router(planning.router)
api_router.include_router(tasks.router)
api_router.include_router(gantt.router)
api_router.include_router(progress.router)
api_router.include_router(issues.router)
api_router.include_router(action_items.router)
api_router.include_router(dashboard.router)
api_router.include_router(agent.router)
api_router.include_router(ai_runs.router)


@api_router.get("/meta", tags=["meta"], summary="API surface metadata")
async def meta() -> dict[str, str]:
    return {"api_version": "v1"}


api_router.include_router(change_proposals.router)
api_router.include_router(plan_drafts.router)
api_router.include_router(notifications.router)
api_router.include_router(risks.router)
