"""M5-A scenarios prepared for centralized testing; use only the local HTTP fixture."""

import json
from uuid import uuid4

import pytest
import test_ai
from conftest import register
from test_ai import accept, configure, suggestion, wait
from test_growth import ability, contribution, tag
from test_m2 import action, delete, item, post
from test_records import create

from app import m2_commands
from app.security import Problem

P = "/api/v1"
provider = test_ai.provider


def pick(c, kind, obj, field, revision_id=None):
    d = c.get(
        P + f"/ai/materials/{kind}/{obj['id']}",
        params={"revision_id": revision_id} if revision_id else {},
    ).json()
    return dict(
        kind=kind,
        id=obj["id"],
        version=d["version"],
        current_version=d["current_version"],
        revision_id=d["revision_id"],
        materials=[{"field_path": field}],
    )


def task(c, cfg, objects, kind="action_candidates", **extra):
    data = (
        dict(
            kind=kind,
            config_version=cfg["version"],
            request_id=str(uuid4()),
            objects=objects,
            parameters={"goal": "检查评估条件", "constraints": "仅用已有数据"}
            if kind == "action_candidates"
            else {},
        )
        | extra
    )
    r = c.post(P + "/ai/tasks", json=data)
    assert r.status_code == 202, r.text
    return r.json(), data


def weekly(c, materials=None):
    return post(
        c,
        "/reflections",
        dict(
            request_id=str(uuid4()),
            kind="period",
            title="本周判断",
            start_at="2026-09-27T16:00:00Z",
            end_at="2026-10-04T16:00:00Z",
            timezone="Asia/Shanghai",
            details={"progress": "我补充了对照条件。", "understanding": "仍不能确定原因。"},
            materials=materials or [],
        ),
    )


def action_payload(**extra):
    return dict(
        title="核对两组条件",
        details={"research_goal": "澄清条件影响", "completion_criteria": "保留两组设置与结果"},
        **extra,
    )


def test_mixed_materials_and_action_adoption_are_explicit(auth, provider):
    cfg = configure(auth, provider)
    r = create(
        auth, body="中文😀重复片段。重复片段。", fields={"interpretation": "隐藏判断不得发送"}
    )
    q, a, f, c = item(auth), action(auth), weekly(auth), contribution(auth)
    g = ability(auth, tag(auth))
    objects = [
        pick(auth, "record", r, "body"),
        pick(auth, "research_item", q, "title"),
        pick(auth, "action", a, "title"),
        pick(auth, "reflection", f, "details.progress"),
        pick(auth, "contribution", c, "title"),
        pick(auth, "growth_entry", g, "title"),
    ]
    t, payload = task(auth, cfg, objects)
    assert auth.post(P + "/ai/tasks", json=payload).json()["id"] == t["id"]
    s = suggestion(auth, t)
    sent = provider.calls[0][2]["messages"][-1]["content"]
    assert "隐藏判断不得发送" not in sent and "用户自述" in sent
    assert len(json.loads(sent)["objects"]) == 6 and len(provider.calls) == 1
    result = accept(auth, s, action=action_payload())
    assert result.status_code == 200, result.text
    adopted = auth.get(P + "/actions/" + result.json()["action_id"]).json()
    assert (
        adopted["status"] == "planned" and not adopted["result_summary"] and not adopted["results"]
    )
    assert adopted["ai_adoptions"][0]["citations"][0]["quote"] == r["body"]
    assert accept(auth, s, action=action_payload()).json()["action_id"] == adopted["id"]
    assert auth.get(P + "/records/" + r["id"]).json()["version"] == 1


def test_action_direction_restriction_and_atomic_failure(auth, provider, monkeypatch):
    cfg = configure(auth, provider)
    r, d = create(auth), item(auth, "direction")
    t, _ = task(auth, cfg, [pick(auth, "record", r, "body")])
    s = suggestion(auth, t)
    assert accept(auth, s, action=action_payload(direction_id=d["id"])).status_code == 422
    original = m2_commands.freeze

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise Problem(503, "fixture_failure", "模拟原子保存失败")

    monkeypatch.setattr(m2_commands, "freeze", fail)
    assert accept(auth, s, action=action_payload()).status_code == 503
    assert auth.get(P + "/actions").json()["total"] == 0
    assert auth.get(P + "/ai/suggestions/" + s["id"]).json()["status"] == "pending"


@pytest.mark.parametrize(
    "model,expected",
    [("empty-actions", "succeeded"), ("too-many-actions", "failed"), ("badcite", "failed")],
)
def test_candidate_limits_and_no_partial_output(auth, provider, model, expected):
    cfg = configure(auth, provider, model)
    t, _ = task(auth, cfg, [pick(auth, "record", create(auth), "body")])
    result = wait(auth, t)
    assert result["status"] == expected and not result["suggestion_ids"]


def test_period_draft_uses_linked_old_revision_and_selected_fields(auth, provider):
    cfg = configure(auth, provider)
    r = create(auth, body="过去的观察")
    old = auth.get(P + f"/records/{r['id']}/revisions").json()[0]["id"]
    f = weekly(auth, [dict(kind="record", id=r["id"], revision_id=old)])
    auth.patch(P + "/records/" + r["id"], json={"expected_version": 1, "body": "后来改动未被选中"})
    objects = [
        pick(auth, "reflection", f, "details.progress"),
        pick(auth, "record", r, "body", old),
    ]
    t, _ = task(auth, cfg, objects, kind="reflection_draft", target_reflection_id=f["id"])
    s = suggestion(auth, t)
    sent = provider.calls[0][2]["messages"][-1]["content"]
    assert "过去的观察" in sent and "后来改动未被选中" not in sent
    assert "仍不能确定原因" not in sent
    assert not s["task"]["needs_review"]  # An intentionally selected old version is not a new race.
    auth.patch(P + "/records/" + r["id"], json={"expected_version": 2, "title": "生成后又更新"})
    s = auth.get(P + "/ai/suggestions/" + s["id"]).json()
    fields = {
        "progress": {
            "mode": "append",
            "text": "补充核对",
            "final_text": "我补充了对照条件。\n\n补充核对",
        },
        "blockers": {"mode": "replace", "text": "待排除设置差异", "final_text": "待排除设置差异"},
    }
    assert accept(auth, s, reflection={"expected_version": 1, "fields": fields}).status_code == 409
    result = accept(auth, s, reviewed=True, reflection={"expected_version": 1, "fields": fields})
    assert result.status_code == 200, result.text
    final = auth.get(P + "/reflections/" + f["id"]).json()
    assert final["version"] == 2 and final["details"]["progress"].endswith("\n\n补充核对")
    assert final["details"]["understanding"] == f["details"]["understanding"]
    assert final["start_at"] == f["start_at"] and final["materials"][0]["revision_id"] == old
    assert len(final["ai_adoptions"]) == 1


def test_draft_requires_personal_text_and_linked_materials(auth):
    f, r = weekly(auth), create(auth)
    body = dict(
        kind="reflection_draft",
        target_reflection_id=f["id"],
        objects=[pick(auth, "reflection", f, "details.progress"), pick(auth, "record", r, "body")],
    )
    assert auth.post(P + "/ai/preview", json=body).status_code == 422
    body["objects"] = [pick(auth, "reflection", f, "title")]
    assert auth.post(P + "/ai/preview", json=body).status_code == 422


def test_stale_deleted_and_cross_account_inputs(auth, provider):
    cfg = configure(auth, provider)
    r = create(auth)
    t, _ = task(auth, cfg, [pick(auth, "record", r, "body")])
    s = suggestion(auth, t)
    auth.patch(P + "/records/" + r["id"], json={"expected_version": 1, "title": "材料变化"})
    assert accept(auth, s, reviewed=True, action=action_payload()).status_code == 409
    s = auth.get(P + "/ai/suggestions/" + s["id"]).json()
    assert accept(auth, s, action=action_payload()).status_code == 409
    delete(auth, "/records/" + r["id"], 2)
    assert accept(auth, s, reviewed=True, action=action_payload()).status_code == 409
    register(auth, "different_reader")
    assert auth.get(P + "/ai/materials/record/" + r["id"]).status_code == 404
    assert auth.get(P + "/ai/tasks/" + t["id"]).status_code == 404


def test_object_and_character_boundaries(auth):
    objects = [pick(auth, "record", create(auth, body="依据"), "body") for _ in range(21)]
    for n, status in ((1, 200), (20, 200), (21, 422)):
        response = auth.post(
            P + "/ai/preview",
            json={
                "kind": "action_candidates",
                "parameters": {"goal": "检查"},
                "objects": objects[:n],
            },
        )
        assert response.status_code == status
    r = create(auth, body="😀" * 32000)
    response = auth.post(
        P + "/ai/preview",
        json={
            "kind": "action_candidates",
            "parameters": {"goal": "检查"},
            "objects": [pick(auth, "record", r, "body")],
        },
    )
    assert response.status_code == 413
