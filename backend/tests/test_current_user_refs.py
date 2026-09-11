"""Regression for get_current_user and batch_find_users $ref aliases."""

from __future__ import annotations

import pytest

from app.services.agent_commands import resolve_refs


def test_resolve_refs_accepts_id_and_user_id_aliases():
    results = {
        "current_user": {
            "data": {"id": 1, "user_id": 1, "name": "管理员", "username": "admin"},
        }
    }
    assert resolve_refs({"$ref": "current_user.id"}, results) == 1
    assert resolve_refs({"$ref": "current_user.user_id"}, results) == 1
    assert resolve_refs({"owner_id": {"$ref": "current_user.id"}}, results) == {"owner_id": 1}


def test_resolve_refs_user_id_only_payload_still_supports_id():
    results = {"cu": {"data": {"user_id": 9, "name": "甲"}}}
    assert resolve_refs({"$ref": "cu.id"}, results) == 9


def test_resolve_refs_batch_find_users_by_display_name():
    """Matches exploratory NLRP3 failure: resolve_owners.王辰.id → user_id."""
    results = {
        "resolve_owners": {
            "data": {
                "resolved": [
                    {"name": "王辰", "input": "王辰", "user_id": 2, "username": "wangchen"},
                    {"name": "霍华兴", "input": "霍华兴", "id": 3, "user_id": 3},
                ],
                "ambiguous": [],
                "not_found": [],
            }
        }
    }
    assert resolve_refs({"$ref": "resolve_owners.王辰.id"}, results) == 2
    assert resolve_refs({"$ref": "resolve_owners.霍华兴.user_id"}, results) == 3
    assert resolve_refs(
        {
            "owner_ids": [
                {"$ref": "resolve_owners.王辰.id"},
                {"$ref": "resolve_owners.霍华兴.id"},
            ]
        },
        results,
    ) == {"owner_ids": [2, 3]}


def test_resolve_refs_missing_field_still_raises():
    results = {"cu": {"data": {"user_id": 9}}}
    with pytest.raises(KeyError):
        resolve_refs({"$ref": "cu.missing"}, results)


def test_resolve_refs_ambiguous_name_still_raises():
    results = {
        "resolve_owners": {
            "data": {
                "resolved": [],
                "ambiguous": [{"input": "王辰", "candidates": [{"user_id": 2}, {"user_id": 9}]}],
                "not_found": [],
            }
        }
    }
    with pytest.raises(KeyError):
        resolve_refs({"$ref": "resolve_owners.王辰.id"}, results)
