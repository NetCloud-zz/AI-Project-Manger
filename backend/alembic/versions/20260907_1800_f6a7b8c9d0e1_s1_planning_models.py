"""S1 project planning model and explicitly labelled migration snapshots.

Revision ID: 20260907_1800_f6a7b8c9d0e1
Revises: 20260907_1700_e5f6a7b8c9d0
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_1800_f6a7b8c9d0e1"
down_revision: str | None = "20260907_1700_e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        for name in ("created_at", "updated_at")
    ]


def project_key() -> sa.Column:
    return sa.Column(
        "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "project_members",
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(20), nullable=False, server_default="CONTRIBUTOR"),
        sa.Column("receive_notifications", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("role IN ('CONTRIBUTOR', 'OBSERVER')", name="ck_member_role"),
        *timestamps(),
    )
    op.create_table(
        "task_participants",
        sa.Column(
            "task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(20), nullable=False, server_default="COLLABORATOR"),
        sa.CheckConstraint("role IN ('COLLABORATOR', 'WATCHER')", name="ck_participant_role"),
        *timestamps(),
    )
    op.create_table(
        "work_calendars",
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("weekdays", sa.JSON(), nullable=False),
        sa.Column("exceptions", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_calendar_version"),
        *timestamps(),
    )
    op.create_table(
        "milestones",
        sa.Column("id", sa.Integer(), primary_key=True),
        project_key(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("deliverable", sa.Text()),
        sa.Column("acceptance_criteria", sa.Text()),
        sa.Column("target_date", sa.Date()),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLANNED"),
        sa.Column("achieved_date", sa.Date()),
        sa.CheckConstraint(
            "status IN ('PLANNED', 'ACHIEVED', 'CANCELLED')", name="ck_milestone_status"
        ),
        *timestamps(),
    )
    op.create_table(
        "task_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        project_key(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("task_groups.id", ondelete="RESTRICT")),
        *timestamps(),
    )
    op.create_table(
        "branch_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        project_key(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("legacy_root_id", sa.Integer(), unique=True),
        sa.Column(
            "entry_task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="RESTRICT", name="fk_branch_entry"),
        ),
        sa.Column(
            "exit_task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="RESTRICT", name="fk_branch_exit"),
        ),
        *timestamps(),
    )
    op.create_table(
        "branch_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("branch_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("group_id", "name", name="uq_branch_option_name"),
        *timestamps(),
    )
    op.create_table(
        "plan_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        project_key(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_plan_version"),
        *timestamps(),
    )
    for table in ("milestones", "task_groups", "branch_groups", "plan_versions"):
        op.create_index(f"ix_{table}_project_id", table, ["project_id"])
    op.create_index("ix_branch_options_group_id", "branch_options", ["group_id"])
    with op.batch_alter_table("tasks") as batch:
        for name in ("description", "deliverable", "acceptance_criteria"):
            batch.add_column(sa.Column(name, sa.Text()))
        for name in ("planned_duration_days", "remaining_duration_days"):
            batch.add_column(sa.Column(name, sa.Integer()))
        for name in (
            "actual_start_date",
            "actual_finish_date",
            "earliest_start_date",
            "fixed_start_date",
            "fixed_due_date",
        ):
            batch.add_column(sa.Column(name, sa.Date()))
        batch.add_column(sa.Column("branch_suspended_status", sa.String(16)))
        for name, target in [
            ("calendar_id", "work_calendars.project_id"),
            ("milestone_id", "milestones.id"),
            ("task_group_id", "task_groups.id"),
            ("branch_option_id", "branch_options.id"),
        ]:
            batch.add_column(sa.Column(name, sa.Integer()))
            table, column = target.split(".")
            batch.create_foreign_key(
                f"fk_tasks_{name}", table, [name], [column], ondelete="RESTRICT"
            )
        batch.create_check_constraint(
            "ck_task_planned_duration",
            "planned_duration_days IS NULL OR planned_duration_days >= 1",
        )
        batch.create_check_constraint(
            "ck_task_remaining_duration",
            "remaining_duration_days IS NULL OR remaining_duration_days >= 0",
        )
    with op.batch_alter_table("task_links") as batch:
        batch.add_column(sa.Column("lag_days", sa.Integer(), nullable=False, server_default="0"))
        batch.create_check_constraint("ck_link_lag", "lag_days >= 0")
    op.execute(
        "INSERT INTO project_members (project_id,user_id) SELECT id,owner_id FROM projects UNION SELECT project_id,user_id FROM project_owners UNION SELECT project_id,owner_id FROM tasks"
    )
    op.execute(
        "INSERT INTO work_calendars (project_id,name,timezone,weekdays,exceptions,version) SELECT id,'项目工作日历','Asia/Shanghai','[0,1,2,3,4]','{}',1 FROM projects"
    )
    op.execute(
        "INSERT INTO branch_groups (project_id,name,legacy_root_id) SELECT project_id,'历史单任务分支 #' || CAST(branch_root_id AS VARCHAR),branch_root_id FROM tasks WHERE branch_root_id IS NOT NULL GROUP BY project_id,branch_root_id"
    )
    op.execute(
        "INSERT INTO branch_options (group_id,name,is_selected) SELECT g.id,COALESCE(t.branch_label,'路线') || ' #' || CAST(t.id AS VARCHAR),t.is_active_branch FROM tasks t JOIN branch_groups g ON t.branch_root_id=g.legacy_root_id"
    )
    op.execute(
        "UPDATE tasks SET branch_option_id=(SELECT o.id FROM branch_options o JOIN branch_groups g ON o.group_id=g.id WHERE g.legacy_root_id=tasks.branch_root_id AND o.name=COALESCE(tasks.branch_label,'路线') || ' #' || CAST(tasks.id AS VARCHAR)) WHERE branch_root_id IS NOT NULL"
    )
    if op.get_context().as_sql:
        op.execute("""INSERT INTO plan_versions (project_id,version,kind,reason,snapshot)
            SELECT p.id,1,'MIGRATION_BASELINE','迁移时基准，非原始立项计划',
                json_build_object('project',row_to_json(p),
                    'project_owners',COALESCE((SELECT json_agg(po) FROM project_owners po WHERE po.project_id=p.id),'[]'::json),
                    'members',COALESCE((SELECT json_agg(m) FROM project_members m WHERE m.project_id=p.id),'[]'::json),
                    'participants','[]'::json,'milestones','[]'::json,'task_groups','[]'::json,
                    'tasks',COALESCE((SELECT json_agg(t) FROM tasks t WHERE t.project_id=p.id),'[]'::json),
                    'links',COALESCE((SELECT json_agg(l) FROM task_links l WHERE l.project_id=p.id),'[]'::json),
                    'calendar',(SELECT row_to_json(c) FROM work_calendars c WHERE c.project_id=p.id),
                    'branch_groups',COALESCE((SELECT json_agg(g) FROM branch_groups g WHERE g.project_id=p.id),'[]'::json),
                    'branch_options',COALESCE((SELECT json_agg(o) FROM branch_options o JOIN branch_groups g ON g.id=o.group_id WHERE g.project_id=p.id),'[]'::json))
            FROM projects p""")
    else:
        bind = op.get_bind()
        versions = sa.table(
            "plan_versions",
            sa.column("project_id"),
            sa.column("version"),
            sa.column("kind"),
            sa.column("reason"),
            sa.column("snapshot", sa.JSON()),
        )
        for project in bind.execute(sa.text("SELECT * FROM projects")).mappings().all():
            pid = project["id"]
            snapshot: dict = {"project": dict(project)}
            for key, table in [
                ("project_owners", "project_owners"),
                ("members", "project_members"),
                ("tasks", "tasks"),
                ("links", "task_links"),
                ("calendar", "work_calendars"),
                ("branch_groups", "branch_groups"),
            ]:
                rows = (
                    bind.execute(
                        sa.text(f"SELECT * FROM {table} WHERE project_id=:pid"), {"pid": pid}
                    )
                    .mappings()
                    .all()
                )
                snapshot[key] = (
                    (dict(rows[0]) if rows else None)
                    if key == "calendar"
                    else [dict(row) for row in rows]
                )
            options = (
                bind.execute(
                    sa.text(
                        "SELECT o.* FROM branch_options o JOIN branch_groups g ON g.id=o.group_id WHERE g.project_id=:pid"
                    ),
                    {"pid": pid},
                )
                .mappings()
                .all()
            )
            snapshot["branch_options"] = [dict(row) for row in options]
            snapshot.update(participants=[], milestones=[], task_groups=[])
            calendar = snapshot["calendar"]
            if isinstance(calendar, dict):
                for key in ("weekdays", "exceptions"):
                    if isinstance(calendar[key], str):
                        calendar[key] = json.loads(calendar[key])
            bind.execute(
                versions.insert().values(
                    project_id=pid,
                    version=1,
                    kind="MIGRATION_BASELINE",
                    reason="迁移时基准，非原始立项计划",
                    snapshot=json.loads(json.dumps(snapshot, default=str)),
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("task_links") as batch:
        batch.drop_constraint("ck_link_lag", type_="check")
        batch.drop_column("lag_days")
    with op.batch_alter_table("tasks") as batch:
        for name in ("calendar_id", "milestone_id", "task_group_id", "branch_option_id"):
            batch.drop_constraint(f"fk_tasks_{name}", type_="foreignkey")
            batch.drop_column(name)
        for name in ("ck_task_planned_duration", "ck_task_remaining_duration"):
            batch.drop_constraint(name, type_="check")
        for name in (
            "description",
            "deliverable",
            "acceptance_criteria",
            "planned_duration_days",
            "remaining_duration_days",
            "actual_start_date",
            "actual_finish_date",
            "earliest_start_date",
            "fixed_start_date",
            "fixed_due_date",
            "branch_suspended_status",
        ):
            batch.drop_column(name)
    for table in (
        "plan_versions",
        "branch_options",
        "branch_groups",
        "task_groups",
        "milestones",
        "work_calendars",
        "task_participants",
        "project_members",
    ):
        op.drop_table(table)
