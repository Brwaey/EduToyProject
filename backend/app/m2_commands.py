"""Commands run inside the request transaction; never commit a partial workflow."""

from sqlalchemy import select

from . import records
from .db import now
from .m2_common import (
    advance,
    check_project,
    freeze,
    node_for,
    node_object,
    owned,
    receipt,
    replace_evidence,
    replay,
    resolve_ref,
    review_evidence,
    revision_for,
    set_results,
    writable,
)
from .models import RecordRevision
from .models_m2 import Action, GraphRelation, Reflection, ResearchItem
from .schemas_m2 import ObjectRef, RelationCreate, ResultRef
from .security import Problem


def item_save(db, owner, value, item_id=None):
    if item_id is None:
        prior, digest = replay(db, owner, "item.create", value)
        if prior:
            return owned(db, ResearchItem, owner, prior.result_id, True)
    check_project(db, owner, value.project_id)
    data = value.model_dump(mode="json", exclude={"evidence", "request_id", "expected_version"})
    was_reviewed = False
    if item_id:
        obj = owned(db, ResearchItem, owner, item_id)
        was_reviewed = obj.status == "reviewed"
        if obj.kind != value.kind:
            raise Problem(422, "immutable_kind", "创建后不能修改对象类型")
        advance(db, obj, value.expected_version, data)
    else:
        obj = ResearchItem(owner_id=owner, **data)
        db.add(obj)
        db.flush()
        node_for(db, obj)
    replace_evidence(db, owner, obj, value.evidence)
    if obj.kind == "finding" and obj.status == "reviewed" and not was_reviewed:
        review_evidence(db, owner, obj)
    freeze(db, obj, "edit" if item_id else "create")
    if item_id is None:
        receipt(db, owner, "item.create", value, digest, obj)
    return obj


def relation_check(db, owner, a, b, kind, exclude=None):
    if a.id == b.id:
        raise Problem(422, "self_relation", "不能关联自身")
    query = select(GraphRelation).where(
        GraphRelation.owner_id == owner, GraphRelation.deleted_at.is_(None)
    )
    active = [r for r in db.scalars(query) if r.id != exclude]
    if any(r.source_id == a.id and r.target_id == b.id and r.relation_type == kind for r in active):
        raise Problem(409, "duplicate_relation", "该关系已存在")
    if kind == "subquestion":
        aa = node_object(db, owner, a.id)
        bb = node_object(db, owner, b.id)
        if (
            not isinstance(aa, ResearchItem)
            or not isinstance(bb, ResearchItem)
            or aa.kind != "question"
            or bb.kind != "question"
        ):
            raise Problem(422, "invalid_subquestion", "子问题只能连接两个研究问题")
        parents = {r.source_id: r.target_id for r in active if r.relation_type == "subquestion"}
        if a.id in parents:
            raise Problem(409, "parent_exists", "该问题已有父问题，请先修改或删除原关系")
        current = b.id
        seen = set()
        while current:
            if current == a.id or current in seen:
                raise Problem(409, "question_cycle", "子问题不能形成循环")
            seen.add(current)
            current = parents.get(current)


def relation_save(db, owner, value, relation_id=None):
    if relation_id is None:
        prior, digest = replay(db, owner, "relation.create", value)
        if prior:
            return owned(db, GraphRelation, owner, prior.result_id, True)
    obj = owned(db, GraphRelation, owner, relation_id) if relation_id else None
    if obj:
        relation_writable(db, obj)
    aa = resolve_ref(db, owner, value.source, True)
    bb = resolve_ref(db, owner, value.target, True)
    a = node_for(db, aa)
    b = node_for(db, bb)
    relation_check(db, owner, a, b, value.relation_type, relation_id)
    data = {
        "source_id": a.id,
        "target_id": b.id,
        "relation_type": value.relation_type,
        "reason": value.reason,
        "source_version": aa.version,
        "target_version": bb.version,
    }
    if obj:
        advance(db, obj, value.expected_version, data)
    else:
        obj = GraphRelation(owner_id=owner, **data)
        db.add(obj)
        db.flush()
    replace_evidence(db, owner, obj, value.evidence)
    freeze(db, obj, "edit" if relation_id else "create")
    if relation_id is None:
        receipt(db, owner, "relation.create", value, digest, obj)
    return obj


def relation_writable(db, obj, allow_deleted_endpoints=False):
    for node in (obj.source_id, obj.target_id):
        endpoint = node_object(db, obj.owner_id, node, allow_deleted_endpoints)
        writable(db, endpoint)


def review(db, owner, model, object_id, value):
    obj = owned(db, model, owner, object_id)
    changes = {}
    if isinstance(obj, GraphRelation):
        relation_writable(db, obj)
        changes = {
            "source_version": node_object(db, owner, obj.source_id).version,
            "target_version": node_object(db, owner, obj.target_id).version,
        }
    advance(db, obj, value.expected_version, changes)
    if value.evidence is not None:
        if (
            isinstance(obj, ResearchItem)
            and obj.kind == "finding"
            and obj.status == "reviewed"
            and not value.evidence
        ):
            raise Problem(422, "evidence_required", "已核对的发现需要证据")
        replace_evidence(db, owner, obj, value.evidence)
    review_evidence(db, owner, obj)
    freeze(db, obj, "review")
    return obj


def set_deleted(db, owner, model, object_id, expected, deleted):
    obj = owned(db, model, owner, object_id, True)
    if bool(obj.deleted_at) == deleted:
        raise Problem(409, "state_conflict", "状态已变化，请刷新后重试")
    if isinstance(obj, GraphRelation):
        relation_writable(db, obj, allow_deleted_endpoints=deleted)
        if not deleted:
            a = node_for(db, node_object(db, owner, obj.source_id))
            b = node_for(db, node_object(db, owner, obj.target_id))
            relation_check(db, owner, a, b, obj.relation_type, obj.id)
    advance(db, obj, expected, {"deleted_at": now() if deleted else None})
    freeze(db, obj, "delete" if deleted else "restore")
    return obj


def action_save(db, owner, value, action_id=None):
    if action_id is None:
        prior, digest = replay(db, owner, "action.create", value)
        if prior:
            return owned(db, Action, owner, prior.result_id, True)
    obj = owned(db, Action, owner, action_id) if action_id else None
    if not obj and value.status == "completed":
        raise Problem(422, "use_complete", "请通过结项操作填写结果")
    if obj:
        if (obj.status in ("completed", "cancelled") and value.status != obj.status) or (
            obj.status != "completed" and value.status == "completed"
        ):
            raise Problem(409, "use_status_command", "请使用结项或重新开启操作")
    data = value.model_dump(mode="json", exclude={"request_id", "expected_version", "results"})
    if value.direction_id:
        direction = owned(
            db,
            ResearchItem,
            owner,
            value.direction_id,
            deleted=bool(obj and obj.direction_id == str(value.direction_id)),
        )
        if direction.kind != "direction":
            raise Problem(422, "invalid_direction", "请选择一个候选方向")
        if not obj and "project_id" not in value.model_fields_set:
            data["project_id"] = direction.project_id
    if value.origin_reflection_id:
        owned(
            db,
            Reflection,
            owner,
            value.origin_reflection_id,
            deleted=bool(obj and obj.origin_reflection_id == str(value.origin_reflection_id)),
        )
    check_project(db, owner, data["project_id"])
    if obj:
        advance(db, obj, value.expected_version, data)
    else:
        obj = Action(owner_id=owner, **data)
        db.add(obj)
        db.flush()
    set_results(db, owner, obj, value.results)
    freeze(db, obj, "edit" if action_id else "create")
    if action_id is None:
        receipt(db, owner, "action.create", value, digest, obj)
    return obj


def complete(db, owner, action_id, value):
    operation = "action.complete:" + str(action_id)
    prior, digest = replay(db, owner, operation, value)
    if prior:
        return owned(db, Action, owner, prior.result_id, True)
    action = owned(db, Action, owner, action_id)
    if action.status in ("completed", "cancelled"):
        raise Problem(409, "state_conflict", "该行动已结项，请重新开启后再完成")
    advance(
        db,
        action,
        value.expected_version,
        {"status": "completed", "result_summary": value.result_summary, "completed_at": now()},
    )
    results = list(value.records)
    new_record = None
    if value.new_record:
        new_record = records.create_record(db, owner, value.new_record)
        if new_record.deleted_at:
            raise Problem(409, "source_deleted", "该请求对应的记录已删除")
        revision = db.scalar(
            select(RecordRevision).where(
                RecordRevision.record_id == new_record.id,
                RecordRevision.version == new_record.version,
            )
        )
        results.append(ResultRef(record_id=new_record.id, record_revision_id=revision.id))
    set_results(db, owner, action, results, replace=False)
    if value.link_direction:
        if not new_record or not action.direction_id:
            raise Problem(422, "invalid_link", "同时关联方向需要新建结果记录并关联有效方向")
        direction = owned(db, ResearchItem, owner, action.direction_id)
        relation_save(
            db,
            owner,
            RelationCreate(
                request_id=value.request_id,
                source=ObjectRef(kind="record", id=new_record.id),
                target=ObjectRef(kind="research_item", id=direction.id),
            ),
        )
    freeze(db, action, "complete")
    receipt(db, owner, operation, value, digest, action)
    return action


def reopen(db, owner, action_id, value):
    operation = "action.reopen:" + str(action_id)
    prior, digest = replay(db, owner, operation, value)
    if prior:
        return owned(db, Action, owner, prior.result_id, True)
    action = owned(db, Action, owner, action_id)
    if action.status not in ("completed", "cancelled"):
        raise Problem(409, "state_conflict", "仅已完成或已取消的行动可重新开启")
    advance(db, action, value.expected_version, {"status": "in_progress", "completed_at": None})
    freeze(db, action, "reopen", {"reopen_reason": value.reason})
    receipt(db, owner, operation, value, digest, action)
    return action


def reflection_save(db, owner, value, reflection_id=None):
    if reflection_id is None:
        prior, digest = replay(db, owner, "reflection.create", value)
        if prior:
            return owned(db, Reflection, owner, prior.result_id, True)
    check_project(db, owner, value.project_id)
    previous = owned(db, Reflection, owner, reflection_id) if reflection_id else None
    for ref in value.materials:
        obj, _ = revision_for(db, owner, ref.kind, ref.id, ref.revision_id)
        if obj.deleted_at and not (previous and ref.model_dump(mode="json") in previous.materials):
            raise Problem(409, "source_deleted", "已删除内容不能加入复盘")
    data = value.model_dump(mode="json", exclude={"request_id", "expected_version"})
    # Normalize serialized timestamps to the same +00:00 format used by record revisions.
    for key in ("start_at", "end_at"):
        data[key] = getattr(value, key).isoformat() if getattr(value, key) else None
    if reflection_id:
        obj = owned(db, Reflection, owner, reflection_id)
        if obj.kind != value.kind:
            raise Problem(422, "immutable_kind", "不能修改复盘类型")
        advance(db, obj, value.expected_version, data)
    else:
        obj = Reflection(owner_id=owner, **data)
        db.add(obj)
        db.flush()
    freeze(db, obj, "edit" if reflection_id else "create")
    if reflection_id is None:
        receipt(db, owner, "reflection.create", value, digest, obj)
    return obj
