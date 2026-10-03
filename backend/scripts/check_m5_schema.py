"""Offline migration/metadata comparison. No engine, connection or application startup."""

import importlib.util
import re
import sys
from pathlib import Path

from sqlalchemy import CheckConstraint, Column
from sqlalchemy.dialects.sqlite import dialect
from sqlalchemy.schema import CreateIndex, CreateTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import models, models_growth, models_m2  # noqa: F401
from app.config import ROOT
from app.db import migration_head
from app.models_ai import AIAdoption, AIAdoptionCitation, AITaskInput


class Recorder:
    def __init__(self):
        self.sql, self.columns, self.fks, self.checks, self.original = [], {}, {}, {}, {}

    def execute(self, sql):
        self.sql.append(sql)

    def f(self, name):
        return name

    def batch_alter_table(self, name, recreate=None, **kwargs):
        if recreate:
            assert name == "ai_task_inputs" and recreate == "always"
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def drop_constraint(self, name, type_):
        assert name == "ck_ai_input_target" and type_ == "check"

    def add_column(self, col):
        self.columns[col.name] = col

    def create_foreign_key(self, name, target, local, remote):
        self.fks[local[0]] = target + "." + remote[0]

    def create_check_constraint(self, name, expression):
        self.checks[name] = expression

    def create_table(self, name, *items):
        if name == "ai_task_inputs":
            self.original = {c.name: c for c in items if isinstance(c, Column)}

    def create_index(self, *args, **kwargs):
        pass


def load(file):
    spec = importlib.util.spec_from_file_location("frozen_migration", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize(sql):
    return re.sub(r"\s+", " ", str(sql)).strip()


def main():
    folder = ROOT / "backend/migrations/versions"
    capture = Recorder()
    old = load(folder / "0003_m3_ai_configuration_tasks_and_suggestions.py")
    old.op = capture
    old.upgrade()
    migration = load(folder / "0005_m5a_planning_and_exports.py")
    migration.op = capture
    migration.upgrade()
    assert migration.down_revision == "0004_m4" and migration_head() == "0005_m5a"
    table = AITaskInput.__table__
    assert set(capture.original) | set(capture.columns) == set(table.columns.keys())
    for key, col in capture.columns.items():
        expected = table.columns[key]
        assert str(col.type) == str(expected.type) and col.nullable == expected.nullable
        targets = {f.target_fullname for f in expected.foreign_keys}
        assert targets == ({capture.fks[key]} if key in capture.fks else set())
    check = next(
        c
        for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_ai_input_target"
    )
    assert normalize(capture.checks[check.name]) == normalize(check.sqltext)
    for model in (AIAdoption, AIAdoptionCitation):
        ddl = normalize(CreateTable(model.__table__).compile(dialect=dialect()))
        assert ddl in [normalize(s) for s in capture.sql]
        for index in model.__table__.indexes:
            assert normalize(CreateIndex(index).compile(dialect=dialect())) in [
                normalize(s) for s in capture.sql
            ]
    expected = {
        "ALTER TABLE ai_tasks ADD COLUMN parameters JSON NOT NULL DEFAULT '{}'",
        "ALTER TABLE ai_tasks ADD COLUMN target_reflection_id VARCHAR(36) REFERENCES reflections(id)",
        "ALTER TABLE ai_suggestions ADD COLUMN action_id VARCHAR(36) REFERENCES actions(id)",
        "ALTER TABLE ai_suggestions ADD COLUMN action_revision_id VARCHAR(36) REFERENCES m2_revisions(id)",
        "ALTER TABLE ai_suggestions ADD COLUMN reflection_id VARCHAR(36) REFERENCES reflections(id)",
        "ALTER TABLE ai_suggestions ADD COLUMN reflection_revision_id VARCHAR(36) REFERENCES m2_revisions(id)",
    }
    assert expected <= set(capture.sql)
    print(
        "M5-A offline schema check: 6 ALTERs, input columns/FKs/XOR, 2 tables and indexes match; no database opened."
    )


if __name__ == "__main__":
    main()
