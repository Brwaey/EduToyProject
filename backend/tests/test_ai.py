import json
import sqlite3
import threading
import time
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from conftest import ORIGIN, register
from fastapi.testclient import TestClient
from mock_model_server import server
from sqlalchemy import select, text
from test_m2 import item
from test_records import create

from app.config import ROOT, Settings
from app.db import make_engine
from app.main import create_app
from app.models_ai import AIConfig, AITask
from app.schemas_ai import normalize_url
from scripts.backup import backup

P = "/api/v1/ai"


@pytest.fixture
def provider():
    s = server()
    thread = threading.Thread(target=s.serve_forever, daemon=True)
    thread.start()
    yield s
    s.shutdown()
    s.server_close()
    thread.join()


def configure(c, provider, model="test-model"):
    current = c.get(P + "/config").json()
    r = c.put(
        P + "/config",
        json={
            "expected_version": current["version"],
            "url": f"http://127.0.0.1:{provider.server_port}/v1",
            "model": model,
            "api_key": "test-secret-12345",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def selected(r, **extra):
    return {
        "kind": "record",
        "id": r["id"],
        "version": r["version"],
        "materials": [{"field_path": "body"}],
        **extra,
    }


def submit(c, cfg, objects, kind="record_draft", request_id=None):
    response = c.post(
        P + "/tasks",
        json={
            "request_id": request_id or str(uuid4()),
            "config_version": cfg["version"],
            "kind": kind,
            "objects": objects,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def wait(c, t, status=None):
    for _ in range(150):
        value = c.get(P + "/tasks/" + t["id"]).json()
        if value["status"] in (status,) if status else value["status"] not in ("queued", "running"):
            return value
        time.sleep(0.03)
    raise AssertionError(value)


def suggestion(c, t):
    t = wait(c, t)
    assert t["status"] == "succeeded", t
    return c.get(P + "/suggestions/" + t["suggestion_ids"][0]).json()


def accept(c, s, **extras):
    value = {
        "expected_version": s["version"],
        "current_versions": {
            o["key"]: o["current_version"] for o in s["task"]["inputs"]["objects"]
        },
        **extras,
    }
    return c.post(P + "/suggestions/" + s["id"] + "/accept", json=value)


def test_config_encryption_url_key_changes_and_isolation(auth, app, provider):
    cfg = configure(auth, provider)
    assert cfg["has_key"] and cfg["key_available"] and "api_key" not in cfg
    assert (
        normalize_url("https://example.com/custom/")
        == "https://example.com/custom/chat/completions"
    )
    assert (
        normalize_url("http://[::1]:8888/chat/completions") == "http://[::1]:8888/chat/completions"
    )
    for url in [
        "http://example.com/v1",
        "https://user:password@site/v1",
        "https://site/v1?key=secret",
        "https://site/v1#fragment",
        "file:///tmp/foo",
    ]:
        with pytest.raises(ValueError):
            normalize_url(url)
    with app.state.sessions() as db:
        c = db.scalar(select(AIConfig))
        assert "test-secret" not in c.encrypted_key
    r = auth.put(
        P + "/config",
        json={
            "expected_version": cfg["version"],
            "url": "https://new.example/v1",
            "model": "test-model",
        },
    )
    assert r.status_code == 422
    r = auth.put(
        P + "/config",
        json={"expected_version": cfg["version"], "url": cfg["endpoint"], "model": "other"},
    )
    assert r.status_code == 200
    old_key = app.state.settings.ai_key_file.read_bytes()
    app.state.settings.ai_key_file.unlink()
    assert not auth.get(P + "/config").json()["key_available"]
    create(auth, body="主密钥缺失不影响手动记录")
    configure_response = auth.put(
        P + "/config",
        json={
            "expected_version": r.json()["version"],
            "url": cfg["endpoint"],
            "model": "other",
            "api_key": "new-secret",
        },
    )
    assert configure_response.status_code == 503 and not app.state.settings.ai_key_file.exists()
    app.state.settings.ai_key_file.write_bytes(old_key)
    register(auth, "second_user")
    assert not auth.get(P + "/config").json()["has_key"]


def test_draft_http_selection_accept_history_and_idempotency(auth, app, provider):
    cfg = configure(auth, provider)
    r = create(
        auth,
        title="原题目",
        body="中文结果😀：本次未见提升。",
        fields={"interpretation": "不能丢失的个人判断"},
    )
    request = str(uuid4())
    t = submit(auth, cfg, [selected(r)], request_id=request)
    assert submit(auth, cfg, [selected(r)], request_id=request)["id"] == t["id"]
    s = suggestion(auth, t)
    assert len(provider.calls) == 1
    path, header, payload = provider.calls[0]
    assert path == "/v1/chat/completions" and header == "Bearer test-secret-12345"
    assert payload["stream"] is False and payload["model"] == "test-model"
    assert (
        "不能丢失" not in payload["messages"][-1]["content"]
        and "原题目" not in payload["messages"][-1]["content"]
    )
    res = accept(auth, s, fields={"observations": "经过核对：本次未见提升。"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "edited_accepted"
    repeat = accept(auth, s, fields={"observations": "经过核对：本次未见提升。"})
    assert repeat.json()["record_revision_id"] == res.json()["record_revision_id"]
    record = auth.get("/api/v1/records/" + r["id"]).json()
    assert record["version"] == 2 and record["title"] == "原题目" and record["body"] == r["body"]
    assert record["fields"]["interpretation"] == "不能丢失的个人判断"
    assert len(auth.get("/api/v1/records/" + r["id"] + "/revisions").json()) == 2
    assert (
        auth.get("/api/v1/records/" + r["id"] + "/sources").json()[0]["versions"][0]["content"]
        == r["body"]
    )


@pytest.mark.parametrize(
    "model,code",
    [
        ("unauthorized", "ai_auth_failed"),
        ("limited", "ai_rate_limited"),
        ("invalid", "ai_invalid_output"),
        ("badcite", "ai_invalid_citation"),
        ("bad-response", "ai_invalid_response"),
        ("huge", "ai_response_too_large"),
        ("truncated", "ai_incomplete_output"),
        ("redirect", "ai_http_error"),
    ],
)
def test_provider_errors_preserve_data(auth, provider, model, code):
    cfg = configure(auth, provider, model)
    r = create(auth)
    t = wait(auth, submit(auth, cfg, [selected(r)]))
    assert t["status"] == "failed" and t["error_code"] == code, t
    assert not t["suggestion_ids"]
    assert "do not expose" not in json.dumps(t)
    assert auth.get("/api/v1/auth/me").status_code == 200
    assert auth.get("/api/v1/records/" + r["id"]).json()["version"] == 1


def test_relations_only_accepted_enter_graph_and_duplicate_blocked(auth, provider):
    cfg = configure(auth, provider)
    r = create(auth)
    q = item(auth)
    inputs = [
        selected(r),
        {
            "kind": "research_item",
            "id": q["id"],
            "version": q["version"],
            "materials": [{"field_path": "title"}],
        },
    ]
    s = suggestion(auth, submit(auth, cfg, inputs, "relation_suggestions"))
    assert not auth.get("/api/v1/graph").json()["edges"]
    candidate = {k: v for k, v in s["original"].items() if k != "evidence"}
    response = accept(auth, s, relation=candidate)
    assert response.status_code == 200, response.text
    assert len(auth.get("/api/v1/graph").json()["edges"]) == 1
    assert accept(auth, s, relation=candidate).status_code == 200
    s2 = suggestion(auth, submit(auth, cfg, inputs, "relation_suggestions"))
    assert accept(auth, s2, relation=candidate).json()["error"]["code"] == "duplicate_relation"
    assert (
        auth.post(
            P + "/suggestions/" + s2["id"] + "/reject", json={"expected_version": 1}
        ).status_code
        == 200
    )
    assert len(auth.get("/api/v1/graph").json()["edges"]) == 1


def test_stale_review_deletion_redaction_restore(auth, provider):
    cfg = configure(auth, provider)
    r = create(auth, body="证据原文")
    s = suggestion(auth, submit(auth, cfg, [selected(r)]))
    auth.patch(
        "/api/v1/records/" + r["id"], json={"expected_version": 1, "body": "证据新文"}
    ).json()
    assert accept(auth, s, fields={"observations": "证据原文"}).status_code == 409
    s = auth.get(P + "/suggestions/" + s["id"]).json()
    assert s["task"]["needs_review"] and s["task"]["inputs"]["materials"][0]["text"] == "证据原文"
    assert (
        accept(auth, s, fields={"observations": "证据原文"}).json()["error"]["code"]
        == "ai_review_required"
    )
    assert accept(auth, s, fields={"observations": "证据原文"}, reviewed=True).status_code == 200
    r = auth.get("/api/v1/records/" + r["id"]).json()
    s2 = suggestion(auth, submit(auth, cfg, [selected(r)]))
    deleted = auth.request(
        "DELETE", "/api/v1/records/" + r["id"], json={"expected_version": r["version"]}
    ).json()
    hidden = auth.get(P + "/suggestions/" + s2["id"]).json()
    assert hidden["original"] is None and hidden["task"]["inputs"]["materials"][0]["text"] is None
    assert accept(auth, s2, fields={"observations": "证据新文"}).status_code == 409
    auth.post(
        "/api/v1/records/" + r["id"] + "/restore", json={"expected_version": deleted["version"]}
    )
    assert auth.get(P + "/suggestions/" + s2["id"]).json()["original"] is not None


def test_running_does_not_lock_records_cancel_and_retry(auth, provider):
    cfg = configure(auth, provider, "slow")
    r = create(auth)
    t = wait(auth, submit(auth, cfg, [selected(r)]), status="running")
    started = time.monotonic()
    create(auth, body="模型等待中正常保存")
    assert time.monotonic() - started < 1.5
    assert auth.post(P + "/tasks/" + t["id"] + "/cancel").json()["status"] == "cancelled"
    cfg = configure(auth, provider)
    request = {"request_id": str(uuid4()), "config_version": cfg["version"]}
    retry = auth.post(P + "/tasks/" + t["id"] + "/retry", json=request).json()
    assert auth.post(P + "/tasks/" + t["id"] + "/retry", json=request).json()["id"] == retry["id"]
    assert wait(auth, retry)["status"] == "succeeded"
    assert auth.get(P + "/tasks/" + t["id"]).json()["status"] == "cancelled"


def test_batch_rollback_and_foreign_tasks(auth, provider):
    cfg = configure(auth, provider)
    r = create(auth)
    s = suggestion(auth, submit(auth, cfg, [selected(r)]))
    response = auth.post(
        P + "/suggestions/reject-batch", json={"suggestions": {s["id"]: 1, str(uuid4()): 1}}
    )
    assert response.status_code == 404
    assert auth.get(P + "/suggestions/" + s["id"]).json()["status"] == "pending"
    register(auth, "other_owner")
    assert auth.get(P + "/tasks/" + s["task_id"]).status_code == 404
    assert auth.get(P + "/suggestions/" + s["id"]).status_code == 404
    assert accept(auth, s, fields={"title": "越权"}).status_code == 404
    assert auth.get(P + "/tasks").json()["total"] == 0
    configure(auth, provider)
    response = auth.post(P + "/preview", json={"kind": "record_draft", "objects": [selected(r)]})
    assert response.status_code == 404


def test_input_limits_invalid_sources_and_empty_relations(auth, provider):
    cfg = configure(auth, provider, "empty-relations")
    r = create(auth, body="x" * 32001)
    assert (
        auth.post(
            P + "/preview", json={"kind": "record_draft", "objects": [selected(r)]}
        ).status_code
        == 413
    )
    bad = selected(r, materials=[{"field_path": "content", "source_version_id": str(uuid4())}])
    assert (
        auth.post(P + "/preview", json={"kind": "record_draft", "objects": [bad]}).status_code
        == 422
    )
    q = item(auth)
    trimmed = selected(r, materials=[{"field_path": "body", "start": 0, "end": 10}])
    inputs = [
        trimmed,
        {
            "kind": "research_item",
            "id": q["id"],
            "version": 1,
            "materials": [{"field_path": "title"}],
        },
    ]
    t = wait(auth, submit(auth, cfg, inputs, "relation_suggestions"))
    assert t["status"] == "succeeded" and not t["suggestion_ids"]


def test_timeout(auth, app, provider):
    app.state.settings.ai_timeout = 0.15
    cfg = configure(auth, provider, "timeout")
    r = create(auth)
    t = wait(auth, submit(auth, cfg, [selected(r)]))
    assert t["error_code"] == "ai_timeout"


def test_restart_queue_config_changes_and_backup(tmp_path, provider):
    settings = Settings(
        db_path=str(tmp_path / "test.sqlite3"),
        ai_key_path=str(tmp_path / "test.key"),
        ai_worker_enabled=False,
    )
    app = create_app(settings)
    with TestClient(app, headers={"Origin": ORIGIN}) as c:
        register(c)
        cfg = configure(c, provider)
        r = create(c)
        tasks = [submit(c, cfg, [selected(r)]) for _ in range(5)]
        full = c.post(
            P + "/tasks",
            json={
                "request_id": str(uuid4()),
                "config_version": cfg["version"],
                "kind": "record_draft",
                "objects": [selected(r)],
            },
        )
        assert full.json()["error"]["code"] == "ai_queue_full"
        with app.state.sessions() as db:
            task = db.get(AITask, tasks[0]["id"])
            task.status = "running"
            db.commit()
        cfg = configure(c, provider, "changed")
        cookie = c.cookies.get("yanji_session")
    settings.ai_worker_enabled = True
    with TestClient(create_app(settings), headers={"Origin": ORIGIN}) as c:
        c.cookies.set("yanji_session", cookie)
        assert c.get(P + "/tasks/" + tasks[0]["id"]).json()["error_code"] == "ai_interrupted"
        assert wait(c, tasks[1])["error_code"] == "ai_config_changed"
        assert c.get(P + "/config").json()["key_available"]
    assert not provider.calls
    backup(settings.database_path, tmp_path / "backup.sqlite3")
    with sqlite3.connect(tmp_path / "backup.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM ai_tasks").fetchone()[0] == 5
        assert not db.execute("PRAGMA foreign_key_check").fetchall()


def test_upgrade_from_m2_retains_records(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "old.sqlite3"),
        ai_key_path=str(tmp_path / "key"),
        ai_worker_enabled=False,
    )
    engine = make_engine(settings)
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend/migrations"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0002_m2")
        conn.execute(
            text(
                "INSERT INTO users (id,username,display_name,password_hash,created_at) VALUES ('owner','legacy','旧用户','hash','2026-01-01')"
            )
        )
    engine.dispose()
    with TestClient(create_app(settings)):
        with sqlite3.connect(settings.database_path) as db:
            assert db.execute("SELECT username FROM users").fetchone()[0] == "legacy"
            assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003_m3"
            assert not db.execute("PRAGMA foreign_key_check").fetchall()


def test_acceptance_failure_rolls_back_record_and_status(auth, provider, monkeypatch):
    from app import records
    from app.security import Problem

    cfg = configure(auth, provider)
    r = create(auth)
    s = suggestion(auth, submit(auth, cfg, [selected(r)]))
    original = records.edit_record

    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise Problem(503, "test_failure", "写入失败")

    monkeypatch.setattr(records, "edit_record", fail_after_write)
    assert accept(auth, s, fields={"observations": "一次失败写入"}).status_code == 503
    assert auth.get("/api/v1/records/" + r["id"]).json()["version"] == 1
    assert len(auth.get("/api/v1/records/" + r["id"] + "/revisions").json()) == 1
    assert auth.get(P + "/suggestions/" + s["id"]).json()["status"] == "pending"


def test_concurrent_acceptance_creates_one_revision(auth, app, provider):
    from concurrent.futures import ThreadPoolExecutor

    cfg = configure(auth, provider)
    r = create(auth)
    s = suggestion(auth, submit(auth, cfg, [selected(r)]))

    def run():
        c = TestClient(
            app, headers={"Origin": ORIGIN, "X-CSRF-Token": auth.headers["X-CSRF-Token"]}
        )
        c.cookies.set("yanji_session", auth.cookies.get("yanji_session"))
        try:
            return accept(c, s, fields={"observations": "并发采纳"}).json()
        finally:
            c.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert results[0]["record_revision_id"] == results[1]["record_revision_id"]
    assert len(auth.get("/api/v1/records/" + r["id"] + "/revisions").json()) == 2


def test_source_quotes_partial_unicode_and_provenance(auth, provider):
    cfg = configure(auth, provider)
    r = create(auth, body="😀重复；😀重复；其他")
    sources = auth.get("/api/v1/records/" + r["id"] + "/sources").json()
    source = sources[0]
    version = source["versions"][0]
    choice = selected(
        r,
        materials=[
            {"field_path": "content", "source_version_id": version["id"], "start": 4, "end": 7}
        ],
    )
    s = suggestion(auth, submit(auth, cfg, [choice]))
    evidence = s["original"]["evidence_by_field"]["observations"][0]
    assert evidence["quote"] == "😀重复" and evidence["start"] == 4 and evidence["end"] == 7
    assert evidence["source_version_id"] == version["id"]
    auth.post(
        "/api/v1/sources/" + source["id"] + "/versions",
        json={"expected_version": 1, "content": "最新来源"},
    )
    updated = auth.get(P + "/suggestions/" + s["id"]).json()
    assert updated["task"]["needs_review"]
    assert updated["task"]["inputs"]["materials"][0]["text"] == "😀重复"
    assert updated["task"]["inputs"]["materials"][0]["current_text"] == "最新来源"


def test_clear_config_cancels_queue_and_monotonic_version(tmp_path, provider):
    app = create_app(
        Settings(
            db_path=str(tmp_path / "q.sqlite3"),
            ai_key_path=str(tmp_path / "q.key"),
            ai_worker_enabled=False,
        )
    )
    with TestClient(app, headers={"Origin": ORIGIN}) as c:
        register(c)
        cfg = configure(c, provider)
        r = create(c)
        task = submit(c, cfg, [selected(r)])
        response = c.request("DELETE", P + "/config", json={"expected_version": cfg["version"]})
        assert response.status_code == 204
        assert c.get(P + "/tasks/" + task["id"]).json()["status"] == "cancelled"
        empty = c.get(P + "/config").json()
        assert not empty["has_key"] and empty["version"] > cfg["version"]
        again = configure(c, provider)
        assert again["version"] > empty["version"]
    assert not provider.calls
