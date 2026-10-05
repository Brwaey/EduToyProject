"""Prepared M4 populated-database upgrade scenario; execution deferred."""

import sqlite3
from uuid import uuid4

from alembic import command
from alembic.config import Config
from conftest import ORIGIN
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table

from app.config import ROOT, Settings
from app.db import make_engine, migration_head
from app.main import create_app
from app.security import passwords


def test_m4_upgrade_preserves_inputs_suggestions_events_and_growth(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "m4.sqlite3"),
        ai_key_path=str(tmp_path / "key"),
        ai_worker_enabled=False,
    )
    engine = make_engine(settings)
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend/migrations"))
    ids = {
        k: str(uuid4())
        for k in (
            "owner",
            "record",
            "revision",
            "source",
            "source_version",
            "task",
            "input",
            "suggestion",
            "event",
            "contribution",
            "growth_revision",
        )
    }
    stamp = "2026-01-01T00:00:00Z"
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0004_m4")
        metadata = MetaData()

        def insert(table_name, **data):
            conn.execute(Table(table_name, metadata, autoload_with=conn).insert().values(**data))

        insert(
            "users",
            id=ids["owner"],
            username="legacy_m4",
            display_name="旧版本测试",
            password_hash=passwords.hash("research-12345"),
            created_at=stamp,
        )
        insert(
            "records",
            id=ids["record"],
            owner_id=ids["owner"],
            title="旧实验",
            body="固定依据😀",
            fields={},
            record_type="note",
            work_status="in_progress",
            outcome_status="none",
            version=1,
            request_id=str(uuid4()),
            request_hash="fixture",
            created_at=stamp,
            updated_at=stamp,
        )
        insert(
            "sources",
            id=ids["source"],
            record_id=ids["record"],
            kind="text",
            name="原文",
            current_version=1,
            created_at=stamp,
        )
        insert(
            "source_versions",
            id=ids["source_version"],
            source_id=ids["source"],
            version=1,
            content="固定依据😀",
            created_at=stamp,
        )
        insert(
            "record_revisions",
            id=ids["revision"],
            record_id=ids["record"],
            version=1,
            operation="create",
            snapshot={
                "title": "旧实验",
                "body": "固定依据😀",
                "source_version_ids": [ids["source_version"]],
            },
            created_at=stamp,
        )
        insert(
            "contributions",
            id=ids["contribution"],
            owner_id=ids["owner"],
            title="旧贡献",
            contribution_type="choice",
            occurred_on="2026-01-01",
            confirmed_at=stamp,
            details={"personal_role": "本人判断"},
            version=1,
            created_at=stamp,
            updated_at=stamp,
        )
        insert(
            "growth_revisions",
            id=ids["growth_revision"],
            contribution_id=ids["contribution"],
            version=1,
            operation="create",
            snapshot={"title": "旧贡献", "evidence": []},
            created_at=stamp,
        )
        insert(
            "ai_configs",
            owner_id=ids["owner"],
            version=1,
            endpoint="https://example.invalid/chat/completions",
            model="fixture",
            encrypted_key="fixture-ciphertext",
            test_status="untested",
            updated_at=stamp,
        )
        insert(
            "ai_tasks",
            id=ids["task"],
            owner_id=ids["owner"],
            request_id=str(uuid4()),
            request_hash="fixture",
            kind="contribution_candidates",
            status="succeeded",
            config_version=1,
            endpoint="https://example.invalid/chat/completions",
            model="fixture",
            prompt_version="m4.contributions.v1",
            created_at=stamp,
        )
        insert(
            "ai_task_inputs",
            id=ids["input"],
            task_id=ids["task"],
            record_id=ids["record"],
            record_revision_id=ids["revision"],
            source_version_id=ids["source_version"],
            object_key="o1",
            material_key="m001",
            field_path="body",
        )
        insert(
            "ai_suggestions",
            id=ids["suggestion"],
            owner_id=ids["owner"],
            task_id=ids["task"],
            version=1,
            kind="contribution_candidates",
            status="accepted",
            original={"preserved": True},
            accepted={"title": "旧贡献"},
            contribution_id=ids["contribution"],
            contribution_revision_id=ids["growth_revision"],
            created_at=stamp,
        )
        insert(
            "ai_suggestion_events",
            id=ids["event"],
            suggestion_id=ids["suggestion"],
            operation="accepted",
            details={},
            created_at=stamp,
        )
    engine.dispose()
    with TestClient(create_app(settings), headers={"Origin": ORIGIN}) as c:
        assert (
            c.post(
                "/api/v1/auth/login", json={"username": "legacy_m4", "password": "research-12345"}
            ).status_code
            == 200
        )
        assert c.get("/api/v1/health/ready").json()["schema"] == migration_head()
        with sqlite3.connect(settings.database_path) as db:
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
            assert (
                db.execute(
                    "SELECT record_revision_id FROM ai_task_inputs WHERE id=?", (ids["input"],)
                ).fetchone()[0]
                == ids["revision"]
            )
            assert db.execute("SELECT parameters FROM ai_tasks").fetchone()[0] == "{}"
            assert db.execute("SELECT count(*) FROM ai_suggestion_events").fetchone()[0] == 1
            assert (
                db.execute("SELECT contribution_revision_id FROM ai_suggestions").fetchone()[0]
                == ids["growth_revision"]
            )
            assert db.execute("SELECT count(*) FROM ai_adoptions").fetchone()[0] == 0
            assert (
                db.execute("SELECT encrypted_key FROM ai_configs").fetchone()[0]
                == "fixture-ciphertext"
            )
