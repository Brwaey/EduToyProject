"""AI commands run in the same short write transaction as business mutations."""

import hashlib
import json

from sqlalchemy import func, select, update

from . import m2_commands, records
from .ai_credentials import decrypt
from .ai_data import input_rows, inputs_view, select_inputs, validate_relation
from .db import now
from .m2_common import owned
from .models import Record, RecordRevision
from .models_ai import AIConfig, AISuggestionEvent, AITask, AITaskInput
from .models_m2 import Revision
from .schemas import RecordPatch
from .schemas_m2 import RelationCreate
from .security import Problem


def create_task(db, settings, owner, value, kind=None, parent=None):
    kind = kind or value.kind
    payload = {
        **value.model_dump(mode="json"),
        "kind": kind,
        "parent": parent.id if parent else None,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    prior = db.scalar(
        select(AITask).where(AITask.owner_id == owner, AITask.request_id == str(value.request_id))
    )
    if prior:
        if prior.request_hash != digest:
            raise Problem(409, "request_conflict", "该请求标识已用于不同任务")
        return prior
    config = db.get(AIConfig, owner)
    decrypt(settings, db, config)
    if config.version != value.config_version:
        raise Problem(409, "version_conflict", "模型配置已变化，请重新确认")
    count = db.scalar(
        select(func.count())
        .select_from(AITask)
        .where(AITask.owner_id == owner, AITask.status == "queued")
    )
    if count >= 5:
        raise Problem(409, "ai_queue_full", "已有 5 个排队任务，请等待或取消后再试")
    if parent:
        if parent.status not in ("failed", "cancelled"):
            raise Problem(
                409, "ai_task_state", "只有失败或取消的任务可以重试；重新生成请重新选择材料"
            )
        rows = []
        for old in input_rows(db, parent.id):
            rows.append(
                AITaskInput(
                    **{
                        k: getattr(old, k)
                        for k in (
                            "object_key",
                            "material_key",
                            "record_id",
                            "record_revision_id",
                            "item_id",
                            "item_revision_id",
                            "source_version_id",
                            "field_path",
                            "start",
                            "end",
                        )
                    }
                )
            )
        view = inputs_view(db, owner, rows)
        if any(o["deleted"] or o["archived"] for o in view["objects"]):
            raise Problem(409, "ai_input_unavailable", "请恢复输入对象及项目后重试")
    elif kind == "connection_test":
        rows = []
    else:
        rows, _ = select_inputs(db, owner, value)
    task = AITask(
        owner_id=owner,
        request_id=str(value.request_id),
        request_hash=digest,
        kind=kind,
        config_version=config.version,
        endpoint=config.endpoint,
        model=config.model,
        parent_id=parent.id if parent else None,
        target_record_id=rows[0].record_id if kind == "record_draft" else None,
    )
    db.add(task)
    db.flush()
    for row in rows:
        row.task_id = task.id
    db.add_all(rows)
    db.flush()
    return task


def cancel_task(db, task):
    if task.status in ("queued", "running"):
        task.status = "cancelled"
        task.finished_at = now()
    db.flush()
    return task


def clear_config(db, owner, version):
    config = db.get(AIConfig, owner)
    if not config or config.version != version:
        raise Problem(409, "version_conflict", "模型配置已变化")
    config.encrypted_key = None
    config.endpoint = config.model = ""
    config.version += 1
    config.test_status = "untested"
    config.updated_at = now()
    db.execute(
        update(AITask)
        .where(AITask.owner_id == owner, AITask.status.in_(["queued", "running"]))
        .values(status="cancelled", finished_at=now())
    )
    db.flush()


def reject(db, suggestion, expected):
    if suggestion.status == "rejected":
        return suggestion
    if suggestion.status != "pending" or suggestion.version != expected:
        raise Problem(409, "version_conflict", "建议已处理，请刷新")
    suggestion.status = "rejected"
    suggestion.version += 1
    suggestion.decided_at = now()
    db.add(AISuggestionEvent(suggestion_id=suggestion.id, operation="rejected"))
    db.flush()
    return suggestion


def accept(db, owner, suggestion, value):
    if suggestion.status in ("accepted", "edited_accepted"):
        return suggestion
    if suggestion.status != "pending" or suggestion.version != value.expected_version:
        raise Problem(409, "version_conflict", "建议已处理，请刷新")
    task = owned(db, AITask, owner, suggestion.task_id)
    rows = input_rows(db, task.id)
    view = inputs_view(db, owner, rows)
    if any(o["deleted"] or o["archived"] for o in view["objects"]):
        raise Problem(409, "ai_input_unavailable", "来源或目标已删除或归档，请恢复后采纳")
    actual = {o["key"]: o["current_version"] for o in view["objects"]}
    if actual != value.current_versions:
        raise Problem(409, "version_conflict", "材料再次变化，请重新载入并核对，当前输入已保留")
    stale = any(o["version"] != o["current_version"] for o in view["objects"])
    if stale and not value.reviewed:
        raise Problem(409, "ai_review_required", "材料已更新，请核对旧依据仍适用后确认")
    modified = False
    if suggestion.kind == "record_draft":
        if not value.fields or value.relation:
            raise Problem(422, "invalid_acceptance", "请至少选择一个整理字段")
        original = suggestion.original["fields"]
        record = owned(db, Record, owner, task.target_record_id)
        fields = dict(record.fields)
        changes = {"expected_version": record.version}
        for key, content in value.fields.items():
            if key not in original:
                raise Problem(422, "invalid_acceptance", "只能采用本次建议的字段")
            if content.strip() and not original[key]["citations"]:
                raise Problem(422, "ai_invalid_citation", "该字段没有引用，请通过手动编辑填写")
            modified |= content != original[key]["value"]
            if key in ("title", "record_type"):
                changes[key] = content
            else:
                fields[key] = content
        if any(k not in ("title", "record_type") for k in value.fields):
            changes["fields"] = fields
        record = records.edit_record(db, owner, record.id, RecordPatch.model_validate(changes))
        db.flush()
        rev = db.scalar(
            select(RecordRevision).where(
                RecordRevision.record_id == record.id, RecordRevision.version == record.version
            )
        )
        rev.operation = "ai_accept"
        rev.snapshot = {**rev.snapshot, "ai_suggestion_id": suggestion.id}
        suggestion.record_id = record.id
        suggestion.record_revision_id = rev.id
        suggestion.accepted = {
            "fields": value.fields,
            "evidence_by_field": {
                k: suggestion.original["evidence_by_field"][k] for k in value.fields
            },
        }
    else:
        if not value.relation or value.fields is not None:
            raise Problem(422, "invalid_acceptance", "请填写要采纳的关系")
        validated = validate_relation(db, rows, value.relation)
        modified = any(
            validated[k] != suggestion.original[k] for k in type(value.relation).model_fields
        )
        objects = {o["key"]: {"kind": o["kind"], "id": o["id"]} for o in view["objects"]}
        relation = m2_commands.relation_save(
            db,
            owner,
            RelationCreate(
                request_id=suggestion.id,
                source=objects[value.relation.source],
                target=objects[value.relation.target],
                relation_type=value.relation.relation_type,
                reason=value.relation.reason,
                evidence=validated["evidence"],
            ),
        )
        rev = db.scalar(
            select(Revision).where(
                Revision.relation_id == relation.id, Revision.version == relation.version
            )
        )
        rev.operation = "ai_accept"
        rev.snapshot = {**rev.snapshot, "ai_suggestion_id": suggestion.id}
        suggestion.relation_id = relation.id
        suggestion.relation_revision_id = rev.id
        suggestion.accepted = validated
    if stale:
        db.add(
            AISuggestionEvent(
                suggestion_id=suggestion.id,
                operation="reviewed",
                details={"current_versions": actual},
            )
        )
    suggestion.status = "edited_accepted" if modified else "accepted"
    suggestion.version += 1
    suggestion.decided_at = now()
    db.add(
        AISuggestionEvent(
            suggestion_id=suggestion.id,
            operation=suggestion.status,
            details={"record_id": suggestion.record_id, "relation_id": suggestion.relation_id},
        )
    )
    db.flush()
    return suggestion
