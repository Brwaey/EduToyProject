"""M5 exports: deferred functional checks against isolated migrated SQLite."""

import json

from conftest import register
from test_growth import contribution
from test_m2 import delete, evidence, item, post, ref, relation
from test_records import create, project

from app import export_data

P = "/api/v1/exports"


def preview(c, **extra):
    value = dict(format="json", scope="all") | extra
    response = c.post(P + "/preview", json=value)
    assert response.status_code == 200, response.text
    return value, response.json()


def download(c, value, p):
    r = c.post(P + "/download", json=value | {"fingerprint": p["fingerprint"]})
    assert r.status_code == 200, r.text
    return r


def test_export_current_fixed_revisions_and_cross_project_stubs(auth):
    pa, pb = project(auth), post(auth, "/projects", {"name": "另一个项目"})
    r = create(auth, project_id=pb["id"], body="旧版依据内容")
    e = evidence(auth, r)
    q = item(auth, project_id=pa["id"], evidence=[e])
    d = item(auth, "direction", project_id=pb["id"], description="普通邻居正文不应扩展")
    relation(auth, ref(q), ref(d))
    auth.patch(
        "/api/v1/records/" + r["id"], json={"expected_version": 1, "body": "新版正文不替换旧依据"}
    )
    value, p = preview(auth, scope="projects", project_ids=[pa["id"]])
    data = download(auth, value, p).json()
    assert len(p["cross_project_evidence"]) == 1
    assert next(o for o in data["fixed_versions"] if o["id"] == r["id"])["body"] == "旧版依据内容"
    assert "普通邻居正文不应扩展" not in json.dumps(data, ensure_ascii=False)
    assert any(o["id"] == d["id"] for o in data["links"])
    assert all(o["id"] != r["id"] for o in data["objects"])
    assert "新版正文不替换旧依据" not in json.dumps(data, ensure_ascii=False)
    # Even an already-stale fixed reference detects another current-version change.
    auth.patch("/api/v1/records/" + r["id"], json={"expected_version": 2, "title": "再次变化"})
    assert (
        auth.post(P + "/download", json=value | {"fingerprint": p["fingerprint"]}).status_code
        == 409
    )


def test_export_preview_fingerprint_and_deleted_placeholder(auth):
    r = create(auth, body="删除后不可恢复正文")
    c = contribution(auth, evidence=[evidence(auth, r)])
    value, p = preview(auth, scope="selected", objects=[{"kind": "contribution", "id": c["id"]}])
    assert (
        preview(auth, scope="selected", objects=[{"kind": "contribution", "id": c["id"]}])[1][
            "fingerprint"
        ]
        == p["fingerprint"]
    )
    delete(auth, "/records/" + r["id"], 1)
    stale = auth.post(P + "/download", json=value | {"fingerprint": p["fingerprint"]})
    assert stale.status_code == 409
    fresh = auth.post(P + "/preview", json=value).json()
    text = download(auth, value, fresh).text
    assert "删除后不可恢复正文" not in text and "来源已删除" in text
    assert fresh["unavailable"]


def test_export_never_exposes_application_secrets_and_checks_owner(auth):
    r = create(auth)
    value, p = preview(auth)
    data = download(auth, value, p).json()
    assert data["format_version"] == "yanji.business.v1"
    for secret in (
        "password_hash",
        "csrf_token",
        "encrypted_key",
        "owner_id",
        "request_hash",
        "prompt_version",
        "api_key",
    ):
        assert secret not in json.dumps(data)
    register(auth, "export_other")
    assert auth.post(
        P + "/download", json=value | {"fingerprint": p["fingerprint"]}
    ).status_code in (409, 422)
    assert (
        auth.post(
            P + "/preview",
            json={"scope": "selected", "objects": [{"kind": "record", "id": r["id"]}]},
        ).status_code
        == 404
    )


def test_markdown_scope_safety_and_limits(auth, monkeypatch):
    r = create(
        auth,
        body='<script>alert("x")</script> [危险](javascript:alert(1)) ![图](https://example.invalid/a)',
    )
    value, p = preview(
        auth, format="markdown", scope="selected", objects=[{"kind": "record", "id": r["id"]}]
    )
    output = download(auth, value, p)
    assert "attachment" in output.headers["content-disposition"]
    assert "# 研迹研究材料" in output.text and "<script>" not in output.text
    assert "[危险](javascript:" not in output.text and "固定依据附录" in output.text
    assert (
        auth.post(
            P + "/preview", json={"format": "markdown", "types": ["contribution"]}
        ).status_code
        == 422
    )
    monkeypatch.setattr(export_data, "MAX_BYTES", 100)
    assert auth.post(P + "/preview", json=value).status_code == 413


def test_empty_range_and_archived_projects(auth):
    assert auth.post(P + "/preview", json={}).json()["error"]["code"] == "export_empty"
    p = project(auth)
    create(auth, project_id=p["id"])
    auth.patch("/api/v1/projects/" + p["id"], json={"archived": True})
    assert auth.post(P + "/preview", json={}).status_code == 422
    value, result = preview(auth, include_archived=True)
    assert result["archived_content"] and download(auth, value, result).status_code == 200
