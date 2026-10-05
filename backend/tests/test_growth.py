"""M4 regression scenarios prepared for the deferred centralized test run."""

import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import test_ai
from alembic import command
from alembic.config import Config
from conftest import ORIGIN, register
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table, select
from test_ai import (
    accept,
    configure,
    selected,
    submit,
    suggestion,
    wait,
)
from test_m2 import action, delete, evidence, post
from test_records import create, project

from app import growth_commands, growth_data
from app.config import ROOT, Settings
from app.db import make_engine, migration_head
from app.main import create_app
from app.models_growth import GrowthActionLink
from app.security import Problem, passwords

P = "/api/v1"
provider = test_ai.provider  # Reuse the local HTTP fixture without contacting real services.


def contribution(c, **values):
    return post(
        c,
        "/contributions",
        dict(
            request_id=str(uuid4()),
            title="我补充了对照条件",
            occurred_on="2026-01-05",
            confirmed=True,
            **values,
        ),
    )


def tag(c, name="实验设计"):
    return post(c, "/ability-tags", {"request_id": str(uuid4()), "name": name})


def ability(c, t, **values):
    payload = dict(
        request_id=str(uuid4()),
        title="复核实验设置",
        occurred_on="2026-01-05",
        kind="ability_instance",
        tag_ids=[t["id"]],
        details={"kind": "ability_instance", "basis_type": "self_report"},
    )
    return post(c, "/growth-entries", payload | values)


def edit_payload(c):
    keys = ("title", "occurred_on", "project_id", "question_id", "contribution_type", "details")
    return {k: c[k] for k in keys} | {
        "expected_version": c["version"],
        "confirmed": True,
        "evidence": [
            {
                k: e[k]
                for k in (
                    "record_revision_id",
                    "m2_revision_id",
                    "contribution_revision_id",
                    "source_version_id",
                    "field_path",
                    "start",
                    "end",
                    "quote",
                    "purpose",
                )
            }
            for e in c["evidence"]
        ],
    }


def test_self_report_confirmation_idempotency_and_history(auth):
    payload = dict(
        request_id=str(uuid4()), title="排除了一种解释", occurred_on="2020-01-01", confirmed=False
    )
    assert auth.post(P + "/contributions", json=payload).status_code == 422
    payload["confirmed"] = True
    c = post(auth, "/contributions", payload)
    assert post(auth, "/contributions", payload)["id"] == c["id"]
    assert c["evidence_status"] == "self_report" and c["confirmed_at"]
    changed = auth.patch(
        P + "/contributions/" + c["id"],
        json=edit_payload(c)
        | {
            "details": {
                "personal_role": "我核对了条件",
                "ai_help": "提示评估口径",
                "others_help": "同学复核",
                "impact": "",
            }
        },
    )
    assert changed.status_code == 200, changed.text
    assert auth.patch(P + "/contributions/" + c["id"], json=edit_payload(c)).status_code == 409
    assert len(auth.get(P + "/contributions/" + c["id"] + "/revisions").json()) == 2
    delete(auth, "/contributions/" + c["id"], 2)
    assert auth.get(P + "/contributions").json()["total"] == 0
    restored = post(auth, "/contributions/" + c["id"] + "/restore", {"expected_version": 3})
    assert restored["id"] == c["id"] and restored["version"] == 4


def test_fixed_evidence_review_deleted_placeholder_and_restore(auth):
    r = create(auth, body="我补充了对照条件。")
    c = contribution(auth, evidence=[evidence(auth, r)])
    assert c["evidence_status"] == "attached"
    auth.patch(
        P + "/records/" + r["id"], json={"expected_version": 1, "body": "我新增了第三组对照。"}
    )
    current = auth.get(P + "/contributions/" + c["id"]).json()
    assert current["needs_review"] and current["evidence"][0]["content"] == r["body"]
    reviewed = post(
        auth,
        "/contributions/" + c["id"] + "/review",
        {"expected_version": 1, "current_versions": current["current_versions"]},
    )
    assert not reviewed["needs_review"]
    delete(auth, "/records/" + r["id"], 2)
    unavailable = auth.get(P + "/contributions/" + c["id"]).json()
    assert unavailable["evidence_status"] == "unavailable"
    assert unavailable["evidence"][0]["content"] is None
    assert unavailable["evidence"][0]["source"]["snapshot"] is None
    assert (
        auth.patch(
            P + "/contributions/" + c["id"],
            json=edit_payload(unavailable) | {"title": "保留文字和占位依据"},
        ).status_code
        == 200
    )
    new_payload = edit_payload(unavailable) | {"request_id": str(uuid4())}
    new_payload.pop("expected_version")
    assert auth.post(P + "/contributions", json=new_payload).status_code == 409
    post(auth, "/records/" + r["id"] + "/restore", {"expected_version": 3})
    assert auth.get(P + "/contributions/" + c["id"]).json()["evidence"][0]["content"] == r["body"]


def test_evidence_ownership_and_quote_validation(auth, app):
    r = create(auth, body="对照😀对照")
    with TestClient(app, headers={"Origin": ORIGIN}) as other:
        register(other, "growth_other")
        foreign = create(other)
        bad = dict(
            request_id=str(uuid4()),
            title="越权",
            occurred_on="2026-01-01",
            confirmed=True,
            evidence=[evidence(other, foreign)],
        )
        assert auth.post(P + "/contributions", json=bad).status_code == 404
        c = contribution(auth, evidence=[evidence(auth, r)])
        for suffix in ("", "/revisions"):
            assert other.get(P + "/contributions/" + c["id"] + suffix).status_code == 404
        assert (
            other.post(
                P + "/contributions/" + c["id"] + "/restore", json={"expected_version": 1}
            ).status_code
            == 404
        )
        assert (
            other.get(P + "/growth/context", params={"kind": "record", "id": r["id"]}).status_code
            == 404
        )
        assert (
            other.get(
                P + "/growth/material",
                params={
                    "kind": "record",
                    "id": r["id"],
                    "revision_id": c["evidence"][0]["record_revision_id"],
                },
            ).status_code
            == 404
        )
    good = evidence(auth, r) | {"field_path": "body", "start": 3, "end": 5, "quote": "对照"}
    c = contribution(auth, evidence=[good])
    assert c["evidence"][0]["quote"] == "对照"
    assert (
        auth.patch(
            P + "/contributions/" + c["id"],
            json=edit_payload(c) | {"evidence": [good | {"quote": "伪造"}]},
        ).status_code
        == 422
    )
    assert auth.get(P + "/contributions/" + c["id"]).json()["version"] == 1


def test_tag_uniqueness_archive_history_and_full_range_counts(auth):
    t = tag(auth)
    for day in range(1, 24):
        ability(auth, t, occurred_on=f"2026-01-{day:02}")
    tags = auth.get(P + "/ability-tags?date_from=2026-01-02&date_to=2026-01-23").json()
    assert tags[0]["instance_count"] == 22
    assert tags[0]["latest_instance"]["occurred_on"] == "2026-01-23"
    update = {
        "expected_version": 1,
        "name": "对照设计",
        "description": "新的名称",
        "archived": True,
    }
    assert auth.patch(P + "/ability-tags/" + t["id"], json=update).status_code == 200
    assert auth.get(P + "/ability-tags").json() == []
    assert (
        auth.post(
            P + "/ability-tags", json={"request_id": str(uuid4()), "name": " 对照设计 "}
        ).status_code
        == 409
    )
    assert (
        auth.get(P + "/ability-tags/" + t["id"] + "/revisions").json()[-1]["snapshot"]["name"]
        == "实验设计"
    )
    assert (
        auth.patch(
            P + "/ability-tags/" + t["id"], json=update | {"expected_version": 2, "archived": False}
        ).status_code
        == 200
    )


def test_ability_basis_requires_real_material_or_completed_action(auth):
    t, c = tag(auth), contribution(auth)
    req = dict(
        request_id=str(uuid4()),
        kind="ability_instance",
        title="任务实践",
        occurred_on="2026-01-05",
        tag_ids=[t["id"]],
        details={"kind": "ability_instance", "basis_type": "material"},
        evidence=[{"contribution_revision_id": c["revision_id"]}],
    )
    assert auth.post(P + "/growth-entries", json=req).status_code == 422
    assert auth.get(P + "/growth-entries").json()["total"] == 0
    a = action(auth)
    done = post(
        auth,
        "/actions/" + a["id"] + "/complete",
        {"request_id": str(uuid4()), "expected_version": 1, "result_summary": "完成对照，仍未提升"},
    )
    rev = auth.get(P + "/actions/" + a["id"] + "/revisions").json()[0]
    entry = ability(
        auth,
        t,
        evidence=[{"m2_revision_id": rev["id"]}],
        details={
            "kind": "ability_instance",
            "basis_type": "task_practice",
            "completion_mode": "assisted",
        },
    )
    assert entry["details"]["completion_mode"] == "assisted" and done["status"] == "completed"


def test_understanding_requires_two_views_and_preserves_evidence_roles(auth):
    r = create(auth)
    payload = dict(
        request_id=str(uuid4()),
        kind="understanding_change",
        title="如何判断实验结果",
        occurred_on="2026-01-05",
        details={"kind": "understanding_change", "before": "一次结果即可", "after": ""},
        evidence=[evidence(auth, r) | {"purpose": "trigger"}],
    )
    assert auth.post(P + "/growth-entries", json=payload).status_code == 422
    payload["details"]["after"] = "需要复核设置与多次对照"
    e = post(auth, "/growth-entries", payload)
    assert e["evidence"][0]["purpose"] == "trigger"
    assert not e["tags"]


def test_growth_reflection_mutual_references_review_and_period_dates(auth):
    r = create(auth)
    c = contribution(auth, evidence=[evidence(auth, r)])
    reflection = post(
        auth,
        "/reflections",
        {
            "request_id": str(uuid4()),
            "kind": "attempt",
            "title": "本次复盘",
            "materials": [{"kind": "contribution", "id": c["id"], "revision_id": c["revision_id"]}],
        },
    )
    rev = auth.get(P + "/reflections/" + reflection["id"] + "/revisions").json()[0]
    e = ability(auth, tag(auth), evidence=[{"m2_revision_id": rev["id"]}])
    updated = auth.patch(
        P + "/reflections/" + reflection["id"],
        json={
            "expected_version": 1,
            "kind": "attempt",
            "title": "回看成长",
            "materials": [{"kind": "growth_entry", "id": e["id"], "revision_id": e["revision_id"]}],
        },
    )
    assert updated.status_code == 200, updated.text
    auth.patch(P + "/records/" + r["id"], json={"expected_version": 1, "body": "新的理解"})
    current = auth.get(P + "/growth-entries/" + e["id"]).json()
    assert current["needs_review"]
    reviewed = post(
        auth,
        "/growth-entries/" + e["id"] + "/review",
        {"expected_version": 1, "current_versions": current["current_versions"]},
    )
    assert not reviewed["needs_review"]
    fixed = reviewed["evidence"][0]["source"]["snapshot"]
    assert fixed["references"][0]["snapshot"] is None  # bounded projection
    today = datetime.now(timezone.utc)
    materials = auth.get(
        P + "/reflections/materials",
        params={
            "start_at": (today - timedelta(days=1)).isoformat(),
            "end_at": (today + timedelta(days=1)).isoformat(),
        },
    ).json()
    row = next(m for m in materials["items"] if m["id"] == c["id"])
    assert row["occurred_on"] == "2026-01-05"  # occurrence date is not query time


def test_growth_action_transaction_and_idempotency(auth, app, monkeypatch):
    c = contribution(auth)
    payload = {
        "request_id": str(uuid4()),
        "expected_version": 1,
        "revision_id": c["revision_id"],
        "action": {"request_id": str(uuid4()), "title": "再验证一次"},
    }
    original = growth_commands.receipt

    def fail(*args, **kwargs):
        raise Problem(503, "test_failure", "模拟事务末尾失败")

    monkeypatch.setattr(growth_commands, "receipt", fail)
    assert auth.post(P + "/contributions/" + c["id"] + "/actions", json=payload).status_code == 503
    assert auth.get(P + "/actions").json()["total"] == 0
    with app.state.sessions() as db:
        assert not list(db.scalars(select(GrowthActionLink)))
    monkeypatch.setattr(growth_commands, "receipt", original)
    a = post(auth, "/contributions/" + c["id"] + "/actions", payload)
    assert post(auth, "/contributions/" + c["id"] + "/actions", payload)["id"] == a["id"]
    assert a["growth_origin"]["revision_id"] == c["revision_id"]


def test_archived_project_and_foreign_tag_rejected(auth, app):
    p = project(auth)
    c = contribution(auth, project_id=p["id"])
    auth.patch(P + "/projects/" + p["id"], json={"archived": True})
    assert auth.get(P + "/contributions").json()["total"] == 0
    assert auth.get(P + "/contributions?include_archived=true").json()["total"] == 1
    assert auth.patch(P + "/contributions/" + c["id"], json=edit_payload(c)).status_code == 409
    with TestClient(app, headers={"Origin": ORIGIN}) as other:
        register(other, "other_tag")
        t = tag(other)
        assert auth.get(P + "/growth-entries?tag_id=" + t["id"]).status_code == 404
        assert auth.get(P + "/ability-tags/" + t["id"] + "/revisions").status_code == 404


def test_ai_contribution_confirmation_citations_and_idempotency(auth, provider):
    cfg = configure(auth, provider)
    r = create(auth, body="我补充了对照条件，AI 提示检查口径，结果仍待核对。")
    s = suggestion(auth, submit(auth, cfg, [selected(r)], kind="contribution_candidates"))
    fields = s["original"]["fields"]
    payload = {
        "title": fields["title"]["value"],
        "occurred_on": "2026-01-05",
        "contribution_type": "validation",
        "details": {"personal_role": "我核对了三个条件"},
        "evidence": s["original"]["evidence"],
        "confirmed": True,
    }
    assert accept(auth, s, contribution=payload | {"confirmed": False}).status_code == 422
    assert accept(auth, s, contribution=payload | {"evidence": []}).status_code == 422
    result = accept(auth, s, contribution=payload)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "edited_accepted"
    assert (
        accept(auth, s, contribution=payload).json()["contribution_id"]
        == result.json()["contribution_id"]
    )
    assert auth.get(P + "/contributions").json()["total"] == 1
    h = auth.get(P + "/contributions/" + result.json()["contribution_id"] + "/revisions").json()[0]
    assert "personal_role" in h["snapshot"]["user_supplement_fields"]
    assert h["snapshot"]["ai_suggestion_id"] == s["id"]
    assert provider.calls[-1][2]["stream"] is False


@pytest.mark.parametrize(
    "model,status", [("badcite", "failed"), ("empty-contributions", "succeeded")]
)
def test_ai_contribution_empty_or_invalid_has_no_partial_candidates(auth, provider, model, status):
    cfg = configure(auth, provider, model=model)
    r = create(auth)
    task = wait(auth, submit(auth, cfg, [selected(r)], kind="contribution_candidates"))
    assert task["status"] == status and task["suggestion_ids"] == []
    assert auth.get(P + "/contributions").json()["total"] == 0


def test_ai_contribution_acceptance_rolls_back(auth, provider, monkeypatch):
    cfg = configure(auth, provider)
    s = suggestion(
        auth, submit(auth, cfg, [selected(create(auth))], kind="contribution_candidates")
    )
    original = growth_data.freeze

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise Problem(503, "test_failure", "模拟采纳失败")

    monkeypatch.setattr(growth_data, "freeze", fail)
    result = accept(
        auth,
        s,
        contribution={
            "title": "贡献",
            "occurred_on": "2026-01-05",
            "confirmed": True,
            "evidence": s["original"]["evidence"],
        },
    )
    assert result.status_code == 503
    assert auth.get(P + "/contributions").json()["total"] == 0
    assert auth.get(P + "/ai/suggestions/" + s["id"]).json()["status"] == "pending"


def test_m3_upgrade_preserves_existing_ai_rows_and_foreign_keys(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "legacy.sqlite3"),
        ai_key_path=str(tmp_path / "legacy.key"),
        ai_worker_enabled=False,
    )
    engine = make_engine(settings)
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend/migrations"))
    owner, task, candidate = (str(uuid4()) for _ in range(3))
    record_id, revision_id, source_id, source_version_id = (str(uuid4()) for _ in range(4))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0003_m3")
        meta = MetaData()

        def insert(table_name, **values):
            conn.execute(Table(table_name, meta, autoload_with=conn).insert().values(**values))

        insert(
            "users",
            id=owner,
            username="legacy",
            display_name="旧用户",
            password_hash=passwords.hash("research-12345"),
            created_at="2026-01-01T00:00:00Z",
        )
        insert(
            "records",
            id=record_id,
            owner_id=owner,
            title="旧实验",
            body="原文",
            record_type="experiment",
            work_status="finished",
            outcome_status="unsupported",
            fields={},
            version=1,
            request_id=str(uuid4()),
            request_hash="fixture",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        insert(
            "sources",
            id=source_id,
            record_id=record_id,
            kind="text",
            name="旧原文",
            current_version=1,
            created_at="2026-01-01T00:00:00Z",
        )
        insert(
            "source_versions",
            id=source_version_id,
            source_id=source_id,
            version=1,
            content="原文",
            created_at="2026-01-01T00:00:00Z",
        )
        insert(
            "record_revisions",
            id=revision_id,
            record_id=record_id,
            version=1,
            operation="create",
            snapshot={"title": "旧实验", "body": "原文"},
            created_at="2026-01-01T00:00:00Z",
        )
        insert(
            "ai_configs",
            owner_id=owner,
            version=1,
            endpoint="https://example.invalid/chat/completions",
            model="legacy-model",
            encrypted_key="fixture-ciphertext",
            test_status="untested",
            updated_at="2026-01-01T00:00:00Z",
        )
        insert(
            "ai_tasks",
            id=task,
            owner_id=owner,
            request_id=str(uuid4()),
            request_hash="fixture",
            kind="relation_suggestions",
            status="succeeded",
            config_version=1,
            endpoint="https://example.invalid/chat/completions",
            model="legacy-model",
            prompt_version="m3.v1",
            created_at="2026-01-01T00:00:00Z",
        )
        insert(
            "ai_suggestions",
            id=candidate,
            owner_id=owner,
            task_id=task,
            version=1,
            kind="relation_suggestions",
            status="rejected",
            original={"fixture": "preserved"},
            created_at="2026-01-01T00:00:00Z",
        )
        insert(
            "ai_suggestion_events",
            id=str(uuid4()),
            suggestion_id=candidate,
            operation="reject",
            details={},
            created_at="2026-01-01T00:00:00Z",
        )
    engine.dispose()
    with TestClient(create_app(settings), headers={"Origin": ORIGIN}) as c:
        response = c.post(
            P + "/auth/login", json={"username": "legacy", "password": "research-12345"}
        )
        assert response.status_code == 200
        with sqlite3.connect(settings.database_path) as db:
            assert (
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == migration_head()
            )
            assert (
                db.execute(
                    "SELECT original FROM ai_suggestions WHERE id=?", (candidate,)
                ).fetchone()[0]
                == '{"fixture": "preserved"}'
            )
            assert db.execute("SELECT count(*) FROM ai_suggestion_events").fetchone()[0] == 1
            assert (
                db.execute("SELECT body FROM records WHERE id=?", (record_id,)).fetchone()[0]
                == "原文"
            )
            assert (
                db.execute(
                    "SELECT content FROM source_versions WHERE id=?", (source_version_id,)
                ).fetchone()[0]
                == "原文"
            )
            assert db.execute("SELECT count(*) FROM record_revisions").fetchone()[0] == 1
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
            assert db.execute("SELECT count(*) FROM contributions").fetchone()[0] == 0
