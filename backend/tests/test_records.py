import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from alembic.util.exc import CommandError
from conftest import ORIGIN, register
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app import records
from app.config import ROOT, Settings
from app.db import migration_head
from app.main import create_app
from app.models import LoginSession, Record, RecordRevision, Source, SourceVersion, User
from scripts.backup import backup

P = "/api/v1"


def create(client, **kwargs):
    response = client.post(
        P + "/records",
        json={"request_id": str(uuid4()), "body": "今天发现评估口径不一致。", **kwargs},
    )
    assert response.status_code == 201, response.text
    return response.json()


def project(client):
    response = client.post(
        P + "/projects", json={"name": "模型评估", "description": "研究评估方法"}
    )
    assert response.status_code == 201
    return response.json()


def test_startup_health_and_foreign_keys(client, app):
    assert client.get(P + "/health/ready").json()["schema"] == migration_head()
    schema = client.get("/openapi.json").json()
    assert (
        schema["paths"][P + "/records"]["post"]["responses"]["422"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        == "#/components/schemas/ErrorOut"
    )
    with app.state.engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "delete"
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO sources(id,record_id,kind,name,current_version,created_at) VALUES('x','missing','text','test',1,'now')"
                )
            )


def test_auth_lifecycle_security(client, app):
    auth = register(client)
    cookie = client.cookies.get("yanji_session")
    assert client.get(P + "/auth/me").json()["user"] == auth["user"]
    assert (
        client.post(
            P + "/projects", json={"name": "x"}, headers={"X-CSRF-Token": "bad"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            P + "/projects",
            json={"name": "x"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    with app.state.sessions() as db:
        user = db.scalar(select(User))
        session = db.scalar(select(LoginSession))
        assert user.password_hash.startswith("$argon2")
        assert cookie != session.token_hash
    assert client.post(P + "/auth/logout").status_code == 204
    assert client.get(P + "/auth/me").status_code == 401
    client.cookies.set("yanji_session", cookie)
    assert client.get(P + "/auth/me").status_code == 401
    client.cookies.clear()
    wrong = client.post(
        P + "/auth/login", json={"username": "researcher", "password": "wrong-password"}
    )
    assert wrong.status_code == 401
    login = client.post(
        P + "/auth/login", json={"username": "RESEARCHER", "password": "research-12345"}
    )
    assert login.status_code == 200
    assert "httponly" in login.headers["set-cookie"].lower()
    with app.state.sessions() as db:
        for session in db.scalars(select(LoginSession)):
            session.expires_at = "2000-01-01T00:00:00+00:00"
        db.commit()
    assert client.get(P + "/auth/me").status_code == 401


def test_registration_validation(client):
    register(client)
    assert (
        client.post(
            P + "/auth/register",
            json={
                "username": "researcher",
                "display_name": "甲",
                "password": "research-12345",
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            P + "/auth/register",
            json={"username": "b", "display_name": "", "password": "123"},
        ).status_code
        == 422
    )


def test_record_snapshots_and_source_immutability(auth):
    r = create(auth)
    source = auth.get(P + f"/records/{r['id']}/sources").json()[0]
    old_source_id = source["versions"][0]["id"]
    edited = auth.patch(
        P + f"/records/{r['id']}",
        json={
            "expected_version": 1,
            "body": "整理后的正文",
            "fields": {"interpretation": "应先统一评估口径"},
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2
    assert (
        auth.patch(
            P + f"/records/{r['id']}", json={"expected_version": 1, "body": "过时内容"}
        ).status_code
        == 409
    )
    sources = auth.get(P + f"/records/{r['id']}/sources").json()
    assert sources[0]["versions"][0]["content"] == r["body"]
    revision = auth.get(P + f"/records/{r['id']}/revisions").json()
    assert [v["version"] for v in revision] == [2, 1]
    assert revision[1]["snapshot"]["body"] == r["body"]
    assert revision[1]["snapshot"]["source_version_ids"] == [old_source_id]
    revised = auth.post(
        P + f"/sources/{source['id']}/versions",
        json={"expected_version": 2, "content": "修正后的原始材料"},
    )
    assert revised.status_code == 201
    versions = auth.get(P + f"/sources/{source['id']}/versions").json()
    assert len(versions) == 2 and versions[1]["id"] == old_source_id
    revision = auth.get(P + f"/records/{r['id']}/revisions").json()
    assert revision[0]["snapshot"]["source_version_ids"] == [versions[0]["id"]]


def test_sources_validate_links_and_version(auth):
    r = create(auth)
    endpoint = P + f"/records/{r['id']}/sources"
    assert (
        auth.post(
            endpoint,
            json={
                "expected_version": 1,
                "kind": "link",
                "content": "javascript:alert(1)",
            },
        ).status_code
        == 422
    )
    assert (
        auth.post(
            endpoint,
            json={
                "expected_version": 1,
                "kind": "link",
                "content": "https://user:secret@example.com",
            },
        ).status_code
        == 422
    )
    response = auth.post(
        endpoint,
        json={
            "expected_version": 1,
            "kind": "link",
            "name": "论文",
            "content": "https://example.com/paper",
        },
    )
    assert response.status_code == 201 and response.json()["version"] == 2
    assert (
        auth.post(endpoint, json={"expected_version": 1, "content": "过时版本"}).status_code == 409
    )
    source = auth.get(endpoint).json()[-1]
    assert (
        auth.post(
            P + f"/sources/{source['id']}/versions",
            json={"expected_version": 2, "content": "file:///etc/passwd"},
        ).status_code
        == 422
    )
    assert auth.get(P + f"/records/{r['id']}").json()["version"] == 2


def test_account_isolation_all_routes(auth, app):
    p = project(auth)
    r = create(auth, project_id=p["id"])
    source = auth.get(P + f"/records/{r['id']}/sources").json()[0]
    with TestClient(app, headers={"Origin": ORIGIN}) as other:
        register(other, "another")
        assert other.get(P + "/records").json()["total"] == 0
        for path in [
            f"/projects/{p['id']}",
            f"/records/{r['id']}",
            f"/records/{r['id']}/revisions",
            f"/records/{r['id']}/sources",
            f"/sources/{source['id']}/versions",
        ]:
            assert other.get(P + path).status_code == 404, path
        assert other.get(P + "/records", params={"project_id": p["id"]}).status_code == 404
        assert (
            other.patch(
                P + f"/records/{r['id']}",
                json={"expected_version": 1, "title": "hijack"},
            ).status_code
            == 404
        )
        assert (
            other.request(
                "DELETE", P + f"/records/{r['id']}", json={"expected_version": 1}
            ).status_code
            == 404
        )
        assert (
            other.post(P + f"/records/{r['id']}/restore", json={"expected_version": 1}).status_code
            == 404
        )
        assert (
            other.post(
                P + f"/records/{r['id']}/sources",
                json={"expected_version": 1, "content": "hijack"},
            ).status_code
            == 404
        )
        assert (
            other.post(
                P + f"/sources/{source['id']}/versions",
                json={"expected_version": 1, "content": "hijack"},
            ).status_code
            == 404
        )
        assert other.patch(P + f"/projects/{p['id']}", json={"name": "hijack"}).status_code == 404
        assert (
            other.post(
                P + "/records",
                json={"request_id": str(uuid4()), "body": "x", "project_id": p["id"]},
            ).status_code
            == 404
        )
        assert (
            other.post(
                P + "/records",
                json={"request_id": str(uuid4()), "body": "x", "owner_id": r["id"]},
            ).status_code
            == 422
        )


def test_project_archive_and_restore(auth):
    p = project(auth)
    r = create(auth)
    url = P + f"/records/{r['id']}"
    assert auth.patch(url, json={"expected_version": 1, "project_id": p["id"]}).status_code == 200
    assert auth.get(P + "/records?unassigned=true").json()["total"] == 0
    assert auth.patch(P + f"/projects/{p['id']}", json={"archived": True}).status_code == 200
    assert auth.patch(url, json={"expected_version": 2, "title": "修改"}).status_code == 409
    assert (
        auth.post(
            P + "/records",
            json={"request_id": str(uuid4()), "body": "x", "project_id": p["id"]},
        ).status_code
        == 409
    )
    assert (
        auth.patch(
            P + f"/projects/{p['id']}", json={"archived": False, "name": "新名称"}
        ).status_code
        == 200
    )
    assert auth.patch(url, json={"expected_version": 2, "project_id": None}).status_code == 200
    assert auth.get(P + "/records?unassigned=true").json()["total"] == 1


def test_delete_restore(auth):
    r = create(auth)
    url = P + f"/records/{r['id']}"
    assert auth.request("DELETE", url, json={"expected_version": 1}).status_code == 200
    assert auth.get(url).status_code == 404
    assert auth.get(P + "/records").json()["total"] == 0
    assert auth.get(P + "/records?deleted=true").json()["items"][0]["id"] == r["id"]
    assert auth.get(url + "/sources").status_code == 404
    assert auth.post(url + "/restore", json={"expected_version": 1}).status_code == 409
    restored = auth.post(url + "/restore", json={"expected_version": 2})
    assert restored.status_code == 200 and restored.json()["version"] == 3
    assert auth.get(url + "/sources").json()[0]["versions"][0]["content"] == r["body"]
    assert len(auth.get(url + "/revisions").json()) == 3


def test_idempotent_create_and_import(auth):
    payload = {"request_id": str(uuid4()), "title": "同一次请求"}
    a = auth.post(P + "/records", json=payload)
    b = auth.post(P + "/records", json=payload)
    assert a.json()["id"] == b.json()["id"]
    assert auth.post(P + "/records", json={**payload, "title": "其他内容"}).status_code == 409
    key = str(uuid4())
    a = auth.post(
        P + "/records/import",
        data={"request_id": key},
        files={"file": ("原文.md", "# 中文标题\n原文内容".encode())},
    )
    b = auth.post(
        P + "/records/import",
        data={"request_id": key},
        files={"file": ("原文.md", "# 中文标题\n原文内容".encode())},
    )
    assert a.status_code == 201 and a.json()["id"] == b.json()["id"]
    assert a.json()["title"] == "中文标题"
    assert auth.get(P + "/records").json()["total"] == 2


@pytest.mark.parametrize(
    "filename,content,status",
    [
        ("empty.txt", b"  ", 422),
        ("large.txt", b"a" * 1048577, 413),
        ("binary.md", b"\xff\xfe", 422),
        ("bad.pdf", b"pdf", 422),
        ("null.txt", b"a\x00b", 422),
        ("bom.md", b"\xef\xbb\xbf# title\ntext", 201),
        ("notes.txt", "中文文本".encode(), 201),
    ],
)
def test_import_validation(auth, filename, content, status):
    response = auth.post(
        P + "/records/import",
        data={"request_id": str(uuid4())},
        files={"file": (filename, content)},
    )
    assert response.status_code == status, response.text
    assert auth.get(P + "/records").json()["total"] == (1 if status == 201 else 0)


def test_search_filters_and_pagination(auth):
    p = project(auth)
    create(
        auth,
        title="第一次",
        project_id=p["id"],
        record_type="experiment",
        work_status="finished",
        outcome_status="inconclusive",
        fields={"interpretation": "需要重复实验验证稳定性"},
    )
    create(auth, title="第二次", body="100% coverage_with_underscore")
    assert auth.get(P + "/records", params={"q": "稳定性"}).json()["total"] == 1
    response = auth.get(
        P + "/records",
        params={
            "project_id": p["id"],
            "record_type": "experiment",
            "work_status": "finished",
            "outcome_status": "inconclusive",
        },
    )
    assert response.json()["total"] == 1
    assert auth.get(P + "/records", params={"q": "%"}).json()["total"] == 1
    assert auth.get(P + "/records", params={"q": "不存在"}).json()["total"] == 0
    a = auth.get(P + "/records?page_size=1&page=1").json()
    b = auth.get(P + "/records?page_size=1&page=2").json()
    assert a["total"] == b["total"] == 2 and a["items"][0]["id"] != b["items"][0]["id"]


def test_atomic_rollback(auth, app, monkeypatch):
    def fail(*args):
        raise records.Problem(503, "injected_failure", "测试写入失败")

    monkeypatch.setattr(records, "snapshot", fail)
    response = auth.post(
        P + "/records", json={"request_id": str(uuid4()), "body": "不能留下半条数据"}
    )
    assert response.status_code == 503
    with app.state.sessions() as db:
        for model in (Record, Source, SourceVersion, RecordRevision):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_unexpected_error_contract_and_rollback(app, monkeypatch):
    def fail(*args):
        raise RuntimeError("private input must not appear in the response")

    monkeypatch.setattr(records, "snapshot", fail)
    with TestClient(app, raise_server_exceptions=False, headers={"Origin": ORIGIN}) as client:
        register(client)
        response = client.post(
            P + "/records", json={"request_id": str(uuid4()), "body": "私有科研材料"}
        )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        assert "private input" not in response.text
        assert client.get(P + "/unknown").json()["error"]["code"] == "not_found"
        with app.state.sessions() as db:
            assert db.scalar(select(func.count()).select_from(Record)) == 0


def test_concurrent_version_update(auth, app):
    r = create(auth)

    def write(title):
        with app.state.sessions() as db:
            owner = db.scalar(select(User.id))
            try:
                from app.schemas import RecordPatch

                updated = records.edit_record(
                    db, owner, r["id"], RecordPatch(expected_version=1, title=title)
                )
                db.commit()
                return updated.version
            except records.Problem as e:
                return e.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(write, ["第一处修改", "第二处修改"]))
    assert result.count(2) == 1 and result.count("version_conflict") == 1
    assert len(auth.get(P + f"/records/{r['id']}/revisions").json()) == 2


def test_busy_database_preserves_record(auth, app):
    r = create(auth)
    lock = sqlite3.connect(app.state.settings.database_path)
    try:
        lock.execute("BEGIN IMMEDIATE")
        response = auth.patch(
            P + f"/records/{r['id']}", json={"expected_version": 1, "title": "锁测试"}
        )
        assert response.status_code == 503 and response.json()["error"]["code"] == "database_busy"
    finally:
        lock.rollback()
        lock.close()
    assert auth.get(P + f"/records/{r['id']}").json()["version"] == 1


def test_restart_backup_and_working_directory(auth, app, tmp_path, monkeypatch):
    r = create(auth)
    saved_cookies = dict(auth.cookies)
    path = app.state.settings.database_path
    monkeypatch.chdir(tmp_path)
    assert Settings(_env_file=None).database_path == ROOT / "data/edutoy.sqlite3"
    assert (
        Settings(db_path="data/another.sqlite3", _env_file=None).database_path
        == ROOT / "data/another.sqlite3"
    )
    restarted = create_app(Settings(db_path=str(path)))
    with TestClient(restarted) as client:
        client.cookies.update(saved_cookies)
        assert client.get(P + f"/records/{r['id']}").json()["body"] == r["body"]
    destination = tmp_path / "backup.sqlite3"
    backup(path, destination)
    with pytest.raises(ValueError):
        backup(path, destination)
    restored = create_app(Settings(db_path=str(destination)))
    with TestClient(restored) as client:
        client.cookies.update(saved_cookies)
        assert client.get(P + f"/records/{r['id']}/revisions").json()[0]["version"] == 1


def test_invalid_migration_does_not_replace_data(tmp_path):
    path = tmp_path / "broken.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version VALUES('unknown_revision')")
    with pytest.raises(CommandError), TestClient(create_app(Settings(db_path=str(path)))):
        pass
    with sqlite3.connect(path) as conn:
        assert (
            conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "unknown_revision"
        )
