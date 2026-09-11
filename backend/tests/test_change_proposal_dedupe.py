"""Plan-change notification dedupe key shape (outbox UNIQUE)."""

from __future__ import annotations

from app.models.notification import PLAN_CHANGE


def test_plan_change_dedupe_key_format():
    proposal_id = "cp_test_001"
    assert f"{PLAN_CHANGE}:{proposal_id}" == "PLAN_CHANGE:cp_test_001"
