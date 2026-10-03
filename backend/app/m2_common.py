"""Ownership, revision and evidence primitives shared by M2 commands and queries."""

import hashlib
import json

from sqlalchemy import inspect, select, update

from . import records
from .db import now
from .models import Project, Record, RecordRevision, SourceVersion
from .models_m2 import (
    Action,
    ActionRecord,
    EvidenceReference,
    GraphNode,
    GraphRelation,
    MutationRequest,
    Reflection,
    ResearchItem,
    Revision,
)
from .security import Problem

MODELS = {
    "research_item": ResearchItem,
    "record": Record,
    "action": Action,
    "reflection": Reflection,
    "relation": GraphRelation,
}
REV_KEYS = {
    ResearchItem: "item_id",
    GraphRelation: "relation_id",
    Action: "action_id",
    Reflection: "reflection_id",
}


def owned(db, model, owner, object_id, deleted=False):
    obj = db.scalar(select(model).where(model.id == str(object_id), model.owner_id == owner))
    if obj is None or (getattr(obj, "deleted_at", None) and not deleted):
        raise Problem(404, "not_found", "对象不存在")
    return obj


def writable(db, obj):
    if getattr(obj, "project_id", None):
        records.project_for(db, obj.owner_id, obj.project_id, writable=True)


def check_project(db, owner, project_id):
    if project_id:
        records.project_for(db, owner, str(project_id), writable=True)


def columns(obj):
    return {
        p.key: getattr(obj, p.key) for p in inspect(type(obj)).column_attrs if p.key != "owner_id"
    }


def evidence_rows(db, obj):
    key = REV_KEYS[type(obj)]
    return list(
        db.scalars(
            select(EvidenceReference)
            .where(getattr(EvidenceReference, key) == obj.id)
            .order_by(EvidenceReference.id)
        )
    )


def evidence_data(row):
    value = columns(row)
    return {k: v for k, v in value.items() if k not in ("item_id", "relation_id")}


def freeze(db, obj, operation, extra=None):
    db.flush()
    value = columns(obj)
    if isinstance(obj, (ResearchItem, GraphRelation)):
        value["evidence"] = [evidence_data(e) for e in evidence_rows(db, obj)]
    if isinstance(obj, Action):
        value["results"] = [
            columns(r)
            for r in db.scalars(select(ActionRecord).where(ActionRecord.action_id == obj.id))
        ]
    if extra:
        value.update(extra)
    rev = Revision(
        **{REV_KEYS[type(obj)]: obj.id}, version=obj.version, operation=operation, snapshot=value
    )
    db.add(rev)
    db.flush()
    return rev


def advance(db, obj, expected, changes=None):
    writable(db, obj)
    model = type(obj)
    result = db.execute(
        update(model)
        .where(model.id == obj.id, model.owner_id == obj.owner_id, model.version == expected)
        .values(**(changes or {}), version=expected + 1, updated_at=now())
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise Problem(409, "version_conflict", "内容已在其他页面更新，请保留当前输入并重新载入")
    db.refresh(obj)


def replay(db, owner, operation, value):
    payload = value.model_dump(mode="json")
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    row = db.scalar(
        select(MutationRequest).where(
            MutationRequest.owner_id == owner,
            MutationRequest.operation == operation,
            MutationRequest.request_id == str(value.request_id),
        )
    )
    if row and row.digest != digest:
        raise Problem(409, "request_conflict", "请求标识已经用于其他内容")
    return row, digest


def receipt(db, owner, operation, value, digest, obj):
    db.add(
        MutationRequest(
            owner_id=owner,
            operation=operation,
            request_id=str(value.request_id),
            digest=digest,
            result_id=obj.id,
        )
    )
    db.flush()


def resolve_ref(db, owner, ref, write=False):
    obj = owned(db, MODELS[ref.kind], owner, ref.id)
    if write:
        writable(db, obj)
    return obj


def node_for(db, obj):
    key = "record_id" if isinstance(obj, Record) else "item_id"
    node = db.scalar(select(GraphNode).where(getattr(GraphNode, key) == obj.id))
    if not node:
        node = GraphNode(owner_id=obj.owner_id, **{key: obj.id})
        db.add(node)
        db.flush()
    return node


def node_object(db, owner, node_id, deleted=False):
    node = owned(db, GraphNode, owner, node_id)
    return owned(
        db,
        Record if node.record_id else ResearchItem,
        owner,
        node.record_id or node.item_id,
        deleted=deleted,
    )


def revision_for(db, owner, kind, object_id, revision_id):
    obj = owned(db, MODELS[kind], owner, object_id, deleted=True)
    rev = db.get(RecordRevision if kind == "record" else Revision, str(revision_id))
    key = "record_id" if kind == "record" else REV_KEYS[type(obj)]
    if not rev or getattr(rev, key) != obj.id:
        raise Problem(404, "not_found", "修订版本不存在")
    return obj, rev


def evidence_content(db, rev, source_id, field):
    if source_id:
        source = db.get(SourceVersion, str(source_id))
        if not source or source.id not in rev.snapshot.get("source_version_ids", []):
            raise Problem(422, "invalid_evidence", "来源版本不属于选定记录快照")
        return source.content
    if field in ("title", "body"):
        return rev.snapshot.get(field, "")
    if field.startswith("fields.") and field[7:] in (
        "context",
        "actions",
        "collaboration",
        "observations",
        "interpretation",
        "next_steps",
    ):
        return rev.snapshot.get("fields", {}).get(field[7:], "")
    raise Problem(422, "invalid_evidence", "引用字段无效")


def replace_evidence(db, owner, obj, values):
    checked = []
    previous = evidence_rows(db, obj)
    for value in values:
        rev = db.get(RecordRevision, str(value.record_revision_id))
        if not rev:
            raise Problem(404, "not_found", "记录版本不存在")
        record = owned(db, Record, owner, rev.record_id, deleted=True)
        payload = value.model_dump(mode="json")
        matching = next(
            (
                old
                for old in previous
                if all(
                    getattr(old, key) == val
                    for key, val in payload.items()
                    if key not in ("quote", "stance")
                )
                and (old.quote == value.quote or (record.deleted_at and not value.quote))
            ),
            None,
        )
        if record.deleted_at:
            # Existing references survive edits to the user's own prose. Never allow
            # a deleted source to be newly attached, nor expose its redacted quote.
            if not matching:
                raise Problem(409, "source_deleted", "请恢复记录后再新增或改变证据引用")
            payload["quote"] = matching.quote
        else:
            content = evidence_content(db, rev, value.source_version_id, value.field_path)
            if value.start is not None and (
                value.end > len(content) or content[value.start : value.end] != value.quote
            ):
                raise Problem(422, "invalid_evidence", "引用片段与原文位置不一致")
        checked.append(
            EvidenceReference(
                **{REV_KEYS[type(obj)]: obj.id},
                **payload,
                reviewed_record_version=matching.reviewed_record_version
                if matching
                else rev.version,
            )
        )
    for old in evidence_rows(db, obj):
        db.delete(old)
    db.add_all(checked)
    db.flush()


def review_evidence(db, owner, obj):
    for e in evidence_rows(db, obj):
        rev = db.get(RecordRevision, e.record_revision_id)
        record = owned(db, Record, owner, rev.record_id)
        e.reviewed_record_version = record.version
    db.flush()


def evidence_view(db, owner, data):
    value = evidence_data(data) if isinstance(data, EvidenceReference) else data
    rev = db.get(RecordRevision, value["record_revision_id"])
    record = owned(db, Record, owner, rev.record_id, deleted=True)
    deleted = bool(record.deleted_at)
    return {
        **value,
        "record_id": record.id,
        "record_title": "来源已删除" if deleted else rev.snapshot["title"],
        "record_version": rev.version,
        "availability": "deleted" if deleted else "available",
        "needs_review": deleted or record.version != value["reviewed_record_version"],
        "quote": "" if deleted else value["quote"],
        "content": ""
        if deleted
        else evidence_content(db, rev, value.get("source_version_id"), value["field_path"]),
    }


def material_view(db, owner, ref):
    obj, rev = revision_for(db, owner, ref["kind"], ref["id"], ref["revision_id"])
    return {
        **ref,
        "title": "来源已删除" if obj.deleted_at else rev.snapshot.get("title", ""),
        "version": rev.version,
        "deleted": bool(obj.deleted_at),
        "snapshot": None if obj.deleted_at else redact_snapshot(db, owner, rev.snapshot),
    }


def redact_snapshot(db, owner, value):
    value = dict(value)
    if "evidence" in value:
        value["evidence"] = [evidence_view(db, owner, e) for e in value["evidence"]]
    if "results" in value:
        value["results"] = [result_view(db, owner, r) for r in value["results"]]
    # Material references always point to record/action/item, so no reflection recursion.
    if "materials" in value:
        value["materials"] = [material_view(db, owner, r) for r in value["materials"]]
    return value


def result_view(db, owner, row):
    value = columns(row) if isinstance(row, ActionRecord) else row
    record, rev = revision_for(db, owner, "record", value["record_id"], value["record_revision_id"])
    return {
        "record_id": record.id,
        "record_revision_id": rev.id,
        "title": "来源已删除" if record.deleted_at else rev.snapshot["title"],
        "version": rev.version,
        "deleted": bool(record.deleted_at),
        "snapshot": None if record.deleted_at else rev.snapshot,
    }


def set_results(db, owner, action, values, replace=True):
    checked = []
    seen = set()
    old = list(db.scalars(select(ActionRecord).where(ActionRecord.action_id == action.id)))
    by_id = {r.record_id: r for r in old}
    for value in values:
        obj, rev = revision_for(db, owner, "record", value.record_id, value.record_revision_id)
        if obj.deleted_at and not (obj.id in by_id and by_id[obj.id].record_revision_id == rev.id):
            raise Problem(409, "source_deleted", "请恢复记录后再关联")
        if obj.id not in seen:
            checked.append((obj, rev))
            seen.add(obj.id)
    if replace:
        for r in old:
            if r.record_id not in seen:
                db.delete(r)
    for obj, rev in checked:
        if obj.id in by_id:
            by_id[obj.id].record_revision_id = rev.id
        else:
            db.add(ActionRecord(action_id=action.id, record_id=obj.id, record_revision_id=rev.id))
    db.flush()


def object_view(db, obj):
    owner = obj.owner_id
    value = columns(obj)
    p = (
        db.get(Project, getattr(obj, "project_id", None))
        if getattr(obj, "project_id", None)
        else None
    )
    value["archived"] = bool(p and p.archived)
    if isinstance(obj, (ResearchItem, GraphRelation)):
        value["evidence"] = [evidence_view(db, owner, e) for e in evidence_rows(db, obj)]
        value["needs_review"] = any(e["needs_review"] for e in value["evidence"])
    if isinstance(obj, GraphRelation):
        a = node_object(db, owner, obj.source_id, True)
        b = node_object(db, owner, obj.target_id, True)
        value["available"] = not (a.deleted_at or b.deleted_at)
        value["source"] = None if a.deleted_at else node_view(db, a, obj.source_id)
        value["target"] = None if b.deleted_at else node_view(db, b, obj.target_id)
        value["needs_review"] |= (
            a.version != obj.source_version
            or b.version != obj.target_version
            or not value["available"]
        )
        value["archived"] = any(v and v["archived"] for v in (value["source"], value["target"]))
    if isinstance(obj, Action):
        direction = db.get(ResearchItem, obj.direction_id) if obj.direction_id else None
        value["direction_title"] = (
            ("方向已删除" if direction.deleted_at else direction.title) if direction else None
        )
        value["direction_deleted"] = bool(direction and direction.deleted_at)
        value["results"] = [
            result_view(db, owner, r)
            for r in db.scalars(select(ActionRecord).where(ActionRecord.action_id == obj.id))
        ]
    if isinstance(obj, Reflection):
        value["materials"] = [material_view(db, owner, r) for r in obj.materials]
    return value


def node_view(db, obj, node_id, projects=None):
    p = (
        (projects or {}).get(obj.project_id)
        if projects is not None
        else (db.get(Project, obj.project_id) if obj.project_id else None)
    )
    return {
        "id": node_id,
        "object_id": obj.id,
        "object_kind": "record" if isinstance(obj, Record) else "research_item",
        "kind": "record" if isinstance(obj, Record) else obj.kind,
        "title": obj.title,
        "project_id": obj.project_id,
        "project_name": p.name if p else "未归类",
        "status": obj.work_status if isinstance(obj, Record) else obj.status,
        "version": obj.version,
        "archived": bool(p and p.archived),
        "external": False,
    }
