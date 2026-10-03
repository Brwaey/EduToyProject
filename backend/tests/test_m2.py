import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from alembic import command
from alembic.config import Config
from conftest import ORIGIN, register
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_records import create, project

from app import m2_commands, records
from app.config import ROOT, Settings
from app.db import make_engine, make_session_factory
from app.m2_common import node_for
from app.main import create_app
from app.models import User
from app.models_m2 import Action, GraphRelation, ResearchItem
from app.schemas import RecordCreate
from app.security import passwords
from scripts.backup import backup

P = "/api/v1"


def post(c, path, data):
    r = c.post(P + path, json=data)
    assert r.status_code in (200, 201), r.text
    return r.json()


def item(c, kind="question", **values):
    return post(
        c,
        "/research-items",
        {
            "request_id": str(uuid4()),
            "kind": kind,
            "title": "研究" + kind,
            "details": {"kind": kind},
            **values,
        },
    )


def ref(obj, kind="research_item"):
    return {"kind": kind, "id": obj["id"]}


def relation(c, a, b, kind="related", **extra):
    return post(
        c,
        "/relations",
        {
            "request_id": str(uuid4()),
            "source": a,
            "target": b,
            "relation_type": kind,
            "reason": "验证关联依据",
            **extra,
        },
    )


def action(c, **extra):
    return post(c, "/actions", {"request_id": str(uuid4()), "title": "检查评估口径", **extra})


def edit_item(c, i, **changes):
    data = {k: i[k] for k in ("kind", "title", "project_id", "description", "status", "details")}
    data.update(expected_version=i["version"], evidence=[])
    data.update(changes)
    return c.patch(P + "/research-items/" + i["id"], json=data)


def evidence(c, r):
    return {"record_revision_id": c.get(P + f"/records/{r['id']}/revisions").json()[0]["id"]}


def delete(c, path, version):
    return c.request("DELETE", P + path, json={"expected_version": version})


def test_graph_opt_in_cross_project_delete_restore(auth):
    pa = project(auth)
    pb = post(auth, "/projects", {"name": "项目 B"})
    r = create(auth, project_id=pa["id"])
    q = item(auth, project_id=pa["id"])
    d = item(auth, "direction", project_id=pb["id"])
    assert len(auth.get(P + "/graph").json()["nodes"]) == 2
    edge = relation(auth, ref(r, "record"), ref(q))
    cross = relation(auth, ref(d), ref(q), "derived_from")
    graph = auth.get(P + "/graph", params={"scope": "project", "project_id": pa["id"]}).json()
    assert (
        len(graph["nodes"]) == 3
        and [n for n in graph["nodes"] if n["external"]][0]["object_id"] == d["id"]
    )
    assert auth.get(P + "/graph/candidates?unlinked=true").json()["total"] == 0
    assert delete(auth, "/relations/" + edge["id"], 1).status_code == 200
    assert (
        len(auth.get(P + "/graph").json()["nodes"]) == 2
        and auth.get(P + "/records/" + r["id"]).status_code == 200
    )
    post(auth, "/relations/" + edge["id"] + "/restore", {"expected_version": 2})
    delete(auth, "/records/" + r["id"], 1)
    assert len(auth.get(P + "/graph").json()["nodes"]) == 2
    post(auth, "/records/" + r["id"] + "/restore", {"expected_version": 2})
    assert len(auth.get(P + "/graph").json()["nodes"]) == 3
    assert auth.get(P + "/relations/" + edge["id"]).json()["needs_review"]
    assert edit_item(auth, q, project_id=pb["id"]).status_code == 200
    assert auth.get(P + "/relations/" + cross["id"]).json()["available"]


def test_relation_rules_cycles_and_history(auth):
    a = item(auth, title="A")
    b = item(auth, title="B")
    c = item(auth, title="C")
    e = relation(auth, ref(a), ref(b), "subquestion")
    for source, target, kind, code in [
        (ref(a), ref(b), "subquestion", 409),
        (ref(a), ref(c), "subquestion", 409),
        (ref(b), ref(a), "subquestion", 409),
        (ref(a), ref(a), "related", 422),
    ]:
        r = auth.post(
            P + "/relations",
            json={
                "request_id": str(uuid4()),
                "source": source,
                "target": target,
                "relation_type": kind,
                "reason": "test",
            },
        )
        assert r.status_code == code, r.text
    relation(auth, ref(a), ref(b), "supports")
    relation(auth, ref(b), ref(a), "supports")
    r = create(auth)
    assert (
        auth.post(
            P + "/relations",
            json={
                "request_id": str(uuid4()),
                "source": ref(r, "record"),
                "target": ref(a),
                "relation_type": "subquestion",
                "reason": "x",
            },
        ).status_code
        == 422
    )
    assert (
        auth.patch(
            P + "/relations/" + e["id"],
            json={
                "expected_version": 1,
                "source": ref(a),
                "target": ref(c),
                "relation_type": "derived_from",
                "reason": "另一个起点",
            },
        ).status_code
        == 200
    )
    assert len(auth.get(P + "/relations/" + e["id"] + "/revisions").json()) == 2


def test_evidence_validation_review_and_redaction(auth):
    r = create(auth, body="中文片段🧪可引用")
    source = auth.get(P + f"/records/{r['id']}/sources").json()[0]
    e = {
        **evidence(auth, r),
        "source_version_id": source["versions"][0]["id"],
        "start": 0,
        "end": 4,
        "quote": "中文片段",
    }
    f = item(auth, "finding", evidence=[e])
    assert f["evidence"][0]["content"] == "中文片段🧪可引用"
    assert (
        auth.post(
            P + "/research-items",
            json={
                "request_id": str(uuid4()),
                "kind": "finding",
                "title": "bad",
                "details": {"kind": "finding"},
                "evidence": [{**e, "quote": "不匹配"}],
            },
        ).status_code
        == 422
    )
    post(auth, f"/sources/{source['id']}/versions", {"expected_version": 1, "content": "新材料"})
    changed = auth.get(P + "/research-items/" + f["id"]).json()
    assert changed["needs_review"] and changed["evidence"][0]["content"] == "中文片段🧪可引用"
    reviewed = post(auth, "/research-items/" + f["id"] + "/review", {"expected_version": 1})
    assert not reviewed["needs_review"] and reviewed["version"] == 2
    delete(auth, "/records/" + r["id"], 2)
    deleted = auth.get(P + "/research-items/" + f["id"]).json()
    assert (
        deleted["evidence"][0]["availability"] == "deleted"
        and deleted["evidence"][0]["quote"] == ""
    )
    assert "中文片段" not in auth.get(P + "/research-items/" + f["id"] + "/revisions").text
    post(auth, "/records/" + r["id"] + "/restore", {"expected_version": 3})
    assert (
        auth.get(P + "/research-items/" + f["id"]).json()["evidence"][0]["content"]
        == "中文片段🧪可引用"
    )


def test_action_completion_atomic_idempotent_reopen(auth, monkeypatch):
    d = item(auth, "direction")
    a = action(auth, direction_id=d["id"])
    value = {
        "expected_version": 1,
        "request_id": str(uuid4()),
        "result_summary": "统一口径后仍需进一步验证",
        "new_record": {"request_id": str(uuid4()), "title": "行动结果", "body": "观察到差异"},
        "link_direction": True,
    }
    original = m2_commands.freeze

    def fail(db, obj, *args):
        if isinstance(obj, Action):
            raise m2_commands.Problem(503, "injected", "注入错误")
        return original(db, obj, *args)

    monkeypatch.setattr(m2_commands, "freeze", fail)
    assert auth.post(P + "/actions/" + a["id"] + "/complete", json=value).status_code == 503
    assert (
        auth.get(P + "/records").json()["total"] == 0
        and auth.get(P + "/relations").json()["total"] == 0
    )
    assert auth.get(P + "/actions/" + a["id"]).json()["version"] == 1
    monkeypatch.setattr(m2_commands, "freeze", original)
    done = post(auth, "/actions/" + a["id"] + "/complete", value)
    replay = post(auth, "/actions/" + a["id"] + "/complete", value)
    assert done == replay and done["status"] == "completed" and len(done["results"]) == 1
    assert (
        auth.get(P + "/records").json()["total"] == 1
        and auth.get(P + "/research-items/" + d["id"]).json()["status"] == "candidate"
    )
    reopened = post(
        auth,
        "/actions/" + a["id"] + "/reopen",
        {"expected_version": 2, "request_id": str(uuid4()), "reason": "增加对照"},
    )
    assert (
        reopened["status"] == "in_progress"
        and reopened["result_summary"] == value["result_summary"]
    )
    assert len(auth.get(P + "/actions/" + a["id"] + "/revisions").json()) == 3
    simple = action(auth)
    assert (
        post(
            auth,
            "/actions/" + simple["id"] + "/complete",
            {"expected_version": 1, "request_id": str(uuid4()), "result_summary": "一句说明"},
        )["results"]
        == []
    )
    delete(auth, "/research-items/" + d["id"], 1)
    assert auth.get(P + "/actions/" + a["id"]).json()["direction_deleted"]


def test_reflection_fixed_material_time_and_explicit_action(auth):
    r = create(auth)
    a = action(auth)
    start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    materials = auth.get(
        P + "/reflections/materials", params={"start_at": start, "end_at": end}
    ).json()["items"]
    assert len(materials) == 2
    selected = [{k: m[k] for k in ("kind", "id", "revision_id")} for m in materials]
    f = post(
        auth,
        "/reflections",
        {
            "request_id": str(uuid4()),
            "kind": "period",
            "title": "本周认识",
            "timezone": "Asia/Shanghai",
            "start_at": start,
            "end_at": end,
            "materials": selected,
            "details": {"understanding": "需要统一条件"},
        },
    )
    auth.patch(P + "/records/" + r["id"], json={"expected_version": 1, "body": "后来的新认识"})
    fixed = auth.get(P + "/reflections/" + f["id"]).json()
    record = next(m for m in fixed["materials"] if m["kind"] == "record")
    assert record["version"] == 1 and record["snapshot"]["body"] == r["body"]
    assert auth.get(P + "/actions/" + a["id"]).json()["version"] == 1
    delete(auth, "/records/" + r["id"], 2)
    fixed = auth.get(P + "/reflections/" + f["id"]).json()
    assert next(m for m in fixed["materials"] if m["kind"] == "record")["snapshot"] is None
    assert (
        len(
            auth.get(
                P + "/reflections/materials", params={"start_at": start, "end_at": end}
            ).json()["items"]
        )
        == 1
    )
    assert (
        auth.get(
            P + "/reflections/materials", params={"start_at": end, "end_at": start}
        ).status_code
        == 422
    )
    assert action(auth, origin_reflection_id=f["id"])["origin_reflection_id"] == f["id"]


def test_account_isolation_all_m2_surfaces(auth, app):
    r = create(auth)
    q = item(auth)
    d = item(auth, "direction")
    e = relation(auth, ref(r, "record"), ref(q))
    a = action(auth)
    f = post(
        auth, "/reflections", {"request_id": str(uuid4()), "kind": "attempt", "title": "尝试复盘"}
    )
    node = auth.get(P + "/graph").json()["nodes"][0]["id"]
    with TestClient(app, headers={"Origin": ORIGIN}) as b:
        register(b, "another")
        for group, obj in [
            ("research-items", q),
            ("relations", e),
            ("actions", a),
            ("reflections", f),
        ]:
            base = "/" + group + "/" + obj["id"]
            for suffix in ("", "/revisions"):
                assert b.get(P + base + suffix).status_code == 404
            assert (
                delete(b, base, 1).status_code == 404
                and b.post(P + base + "/restore", json={"expected_version": 1}).status_code == 404
            )
        assert (
            b.get(P + "/graph").json()["nodes"] == []
            and b.get(P + "/graph", params={"focus_node_id": node}).status_code == 404
        )
        assert b.get(P + "/records/" + r["id"] + "/context").status_code == 404
        assert (
            b.put(
                P + "/graph/layout",
                json={"expected_version": 0, "positions": {node: {"x": 1, "y": 2}}},
            ).status_code
            == 404
        )
        assert (
            b.post(
                P + "/research-items",
                json={
                    "request_id": str(uuid4()),
                    "kind": "finding",
                    "title": "bad",
                    "details": {"kind": "finding"},
                    "evidence": [evidence(auth, r)],
                },
            ).status_code
            == 404
        )
        assert (
            b.post(
                P + "/actions",
                json={"request_id": str(uuid4()), "title": "x", "direction_id": d["id"]},
            ).status_code
            == 404
        )


def test_layout_conflict_archive_and_item_versions(auth):
    p = project(auth)
    q = item(auth, project_id=p["id"])
    r = create(auth)
    e = relation(auth, ref(r, "record"), ref(q))
    node = next(n for n in auth.get(P + "/graph").json()["nodes"] if n["object_id"] == q["id"])
    payload = {
        "scope": "project",
        "project_id": p["id"],
        "expected_version": 0,
        "positions": {node["id"]: {"x": 123, "y": 456}},
    }
    assert (
        auth.put(P + "/graph/layout", json=payload).status_code == 200
        and auth.put(P + "/graph/layout", json=payload).status_code == 409
    )
    assert (
        auth.get(P + "/graph/layout", params={"scope": "project", "project_id": p["id"]}).json()[
            "positions"
        ][node["id"]]["x"]
        == 123
    )
    assert auth.get(P + "/research-items/" + q["id"]).json()["version"] == 1
    assert (
        edit_item(auth, q, title="新标题").status_code == 200
        and edit_item(auth, q, title="过期修改").status_code == 409
    )
    auth.patch(P + "/projects/" + p["id"], json={"archived": True})
    assert (
        auth.get(P + "/graph").json()["nodes"] == []
        and len(auth.get(P + "/graph?include_archived=true").json()["nodes"]) == 2
    )
    assert (
        auth.post(P + "/relations/" + e["id"] + "/review", json={"expected_version": 1}).status_code
        == 409
    )
    assert edit_item(auth, {**q, "version": 2}, title="不允许").status_code == 409


def test_m1_migration_preserves_data_and_m2_restart(tmp_path):
    settings = Settings(db_path=str(tmp_path / "upgrade.sqlite3"))
    engine = make_engine(settings)
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001_m1")
    with make_session_factory(engine)() as db:
        user = User(
            username="legacy",
            display_name="原有账号",
            password_hash=passwords.hash("research-12345"),
        )
        db.add(user)
        db.flush()
        rec = records.create_record(
            db, user.id, RecordCreate(request_id=uuid4(), body="旧版本原始材料")
        )
        db.commit()
        rid = rec.id
    engine.dispose()
    with TestClient(create_app(settings), headers={"Origin": ORIGIN}) as c:
        login = post(c, "/auth/login", {"username": "legacy", "password": "research-12345"})
        c.headers["X-CSRF-Token"] = login["csrf_token"]
        assert (
            c.get(P + "/records/" + rid).json()["body"] == "旧版本原始材料"
            and c.get(P + "/graph").json()["nodes"] == []
        )
        q = item(c)
        relation(c, ref({"id": rid}, "record"), ref(q))
        cookies = dict(c.cookies)
        node = c.get(P + "/graph").json()["nodes"][0]["id"]
        c.put(
            P + "/graph/layout",
            json={"expected_version": 0, "positions": {node: {"x": 20, "y": 40}}},
        )
    with TestClient(create_app(settings)) as c:
        c.cookies.update(cookies)
        assert len(c.get(P + "/graph").json()["nodes"]) == 2
        assert (
            c.get(P + "/graph/layout").json()["positions"][node]["y"] == 40
            and len(c.get(P + "/records/" + rid + "/revisions").json()) == 1
        )
    backup_path = tmp_path / "m2-backup.sqlite3"
    backup(settings.database_path, backup_path)
    with TestClient(create_app(Settings(db_path=str(backup_path)))) as c:
        c.cookies.update(cookies)
        assert len(c.get(P + "/graph").json()["nodes"]) == 2
        assert c.get(P + "/graph/layout").json()["positions"][node]["y"] == 40
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_graph_large_dataset_is_bounded_and_paginated(auth, app):
    with app.state.sessions() as db:
        owner = db.scalar(select(User.id))
        nodes = []
        for i in range(500):
            obj = ResearchItem(
                owner_id=owner,
                kind="question",
                title=f"问题 {i:04}",
                status="exploring",
                details={"kind": "question"},
            )
            db.add(obj)
            db.flush()
            nodes.append(node_for(db, obj))
        for i in range(1000):
            db.add(
                GraphRelation(
                    owner_id=owner,
                    source_id=nodes[i % 500].id,
                    target_id=nodes[(i % 500 + 1 + i // 500) % 500].id,
                    relation_type="related",
                    reason="",
                    source_version=1,
                    target_version=1,
                )
            )
        db.commit()
    graph = auth.get(P + "/graph").json()
    assert graph["total_nodes"] == 500 and graph["truncated"] and len(graph["nodes"]) == 150
    assert all(e["source_id"] in {n["id"] for n in graph["nodes"]} for e in graph["edges"])
    candidates = auth.get(P + "/graph/candidates?page=5&page_size=100").json()
    assert candidates["total"] == 500 and len(candidates["items"]) == 100
    assert (
        len(
            auth.get(P + "/graph", params={"focus_node_id": graph["nodes"][0]["id"]}).json()[
                "nodes"
            ]
        )
        < 150
    )


def test_explicit_evidence_review_survives_edit_and_drift_is_not_auto_confirmed(auth):
    r = create(auth)
    e = evidence(auth, r)
    f = item(auth, "finding", status="reviewed", evidence=[e])
    changed = auth.patch(
        P + "/records/" + r["id"], json={"expected_version": 1, "body": "新的观察"}
    )
    assert changed.status_code == 200
    assert auth.get(P + "/research-items/" + f["id"]).json()["needs_review"]
    edited = edit_item(auth, f, title="只改措辞", evidence=[e]).json()
    assert edited["needs_review"]
    reviewed = post(auth, "/research-items/" + f["id"] + "/review", {"expected_version": 2})
    assert not reviewed["needs_review"]
    edited = edit_item(auth, reviewed, title="保留已复核的依据", evidence=[e]).json()
    assert not edited["needs_review"] and edited["evidence"][0]["record_version"] == 1


def test_concurrent_duplicate_relation_and_compound_completion(auth, app):
    from concurrent.futures import ThreadPoolExecutor

    a, b = item(auth), item(auth)
    data = {"request_id": str(uuid4()), "source": ref(a), "target": ref(b)}
    cookie, headers = dict(auth.cookies), dict(auth.headers)

    def submit(path, payload):
        # The fixture already started the single application and migrated the DB.
        # These clients model simultaneous requests, not simultaneous server starts.
        c = TestClient(app, headers=headers)
        try:
            c.cookies.update(cookie)
            r = c.post(P + path, json=payload)
            return r.status_code, r.json()
        finally:
            c.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit("/relations", data), range(2)))
    assert all(status == 201 for status, _ in results)
    assert results[0][1]["id"] == results[1][1]["id"]
    assert auth.get(P + "/relations").json()["total"] == 1
    d = item(auth, "direction")
    act = action(auth, direction_id=d["id"])
    payload = {
        "expected_version": 1,
        "request_id": str(uuid4()),
        "result_summary": "一次结项",
        "new_record": {"request_id": str(uuid4()), "body": "不能重复创建的记录"},
        "link_direction": True,
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: submit("/actions/" + act["id"] + "/complete", payload), range(2))
        )
    assert all(status == 200 for status, _ in results)
    assert results[0][1]["results"] == results[1][1]["results"]
    assert auth.get(P + "/records").json()["total"] == 1
    assert auth.get(P + "/relations").json()["total"] == 2
    assert len(auth.get(P + "/actions/" + act["id"] + "/revisions").json()) == 2


def test_deleted_references_preserve_user_edits_but_cannot_be_newly_attached(auth):
    r = create(auth, body="固定旧依据")
    e = {**evidence(auth, r), "field_path": "body", "start": 0, "end": 2, "quote": "固定"}
    f = item(auth, "finding", evidence=[e])
    result = {"record_id": r["id"], "record_revision_id": e["record_revision_id"]}
    a = action(auth, results=[result])
    material = {"kind": "record", "id": r["id"], "revision_id": e["record_revision_id"]}
    reflection = post(
        auth,
        "/reflections",
        {"request_id": str(uuid4()), "kind": "attempt", "title": "复盘", "materials": [material]},
    )
    delete(auth, "/records/" + r["id"], 1)
    redacted_e = {**e, "quote": ""}
    updated = edit_item(auth, f, evidence=[redacted_e], title="自己的判断仍可更新")
    assert updated.status_code == 200 and updated.json()["evidence"][0]["content"] == ""
    assert (
        auth.patch(
            P + "/actions/" + a["id"],
            json={"expected_version": 1, "title": "仍保留执行判断", "results": [result]},
        ).status_code
        == 200
    )
    updated = auth.patch(
        P + "/reflections/" + reflection["id"],
        json={
            "expected_version": 1,
            "kind": "attempt",
            "title": "更新复盘文字",
            "materials": [material],
        },
    )
    assert updated.status_code == 200 and updated.json()["materials"][0]["snapshot"] is None
    for path, payload in [
        (
            "/research-items",
            {
                "kind": "finding",
                "title": "新发现",
                "details": {"kind": "finding"},
                "evidence": [redacted_e],
            },
        ),
        ("/actions", {"title": "新行动", "results": [result]}),
        ("/reflections", {"kind": "attempt", "title": "新复盘", "materials": [material]}),
    ]:
        assert auth.post(P + path, json={"request_id": str(uuid4()), **payload}).status_code == 409
    post(auth, "/records/" + r["id"] + "/restore", {"expected_version": 2})
    restored = auth.get(P + "/research-items/" + f["id"]).json()
    assert restored["evidence"][0]["quote"] == "固定" and restored["needs_review"]
