"""Equal task owners for assistant queries. Copyright 2024–2026 Jack Zhang."""

from sqlalchemy import inspect, select
from sqlalchemy.orm import object_session

from app.models.planning import TaskParticipant
from app.models.user import User


def task_owners(task: object) -> list:
    owner = getattr(task, "owner", None)
    people = {owner.id: owner} if owner is not None else {}
    db = object_session(task) if inspect(task, raiseerr=False) is not None else None
    if db is not None:
        for user in db.scalars(
            select(User)
            .join(TaskParticipant, TaskParticipant.user_id == User.id)
            .where(TaskParticipant.task_id == task.id, TaskParticipant.role == "OWNER")
        ):
            people[user.id] = user
    return list(people.values())
