"""Fixed material selection, output validation and redacted projections."""

import json

from sqlalchemy import select

from .m2_common import evidence_content, owned, writable
from .models import Project, Record, RecordRevision, Source, SourceVersion
from .models_ai import AISuggestion, AISuggestionEvent, AITaskInput
from .models_m2 import ResearchItem, Revision
from .schemas_ai import DraftOutput, RelationsOutput
from .security import Problem

FIELDS = ("context", "actions", "collaboration", "observations", "interpretation", "next_steps")


def input_rows(db, task_id):
    return list(
        db.scalars(
            select(AITaskInput)
            .where(AITaskInput.task_id == task_id)
            .order_by(AITaskInput.material_key)
        )
    )


def material_content(db, row):
    if row.record_id:
        rev = db.get(RecordRevision, row.record_revision_id)
        content = evidence_content(db, rev, row.source_version_id, row.field_path)
    else:
        rev = db.get(Revision, row.item_revision_id)
        if row.field_path in ("title", "description"):
            content = rev.snapshot.get(row.field_path, "")
        elif row.field_path.startswith("details."):
            content = rev.snapshot.get("details", {}).get(row.field_path[8:], "")
        else:
            raise Problem(422, "invalid_material", "研究内容字段无效")
    if not isinstance(content, str):
        raise Problem(422, "invalid_material", "仅支持文本字段")
    if row.start is not None:
        if row.end > len(content):
            raise Problem(422, "invalid_material", "片段超出原文范围")
        content = content[row.start : row.end]
    return content


def select_inputs(db, owner, value):
    if value.kind == "record_draft" and (
        len(value.objects) != 1 or value.objects[0].kind != "record"
    ):
        raise Problem(422, "invalid_selection", "整理时请选择一条记录")
    if value.kind == "relation_suggestions" and (
        len(value.objects) < 2 or not any(o.kind == "record" for o in value.objects)
    ):
        raise Problem(422, "invalid_selection", "请选择至少两个对象，其中包含一条科研记录")
    seen, rows = set(), []
    for index, selection in enumerate(value.objects):
        identity = (selection.kind, str(selection.id))
        if identity in seen:
            raise Problem(422, "duplicate_selection", "不能重复选择对象")
        seen.add(identity)
        model = Record if selection.kind == "record" else ResearchItem
        obj = owned(db, model, owner, selection.id)
        writable(db, obj)
        if obj.version != selection.version:
            raise Problem(409, "version_conflict", "所选材料已更新，请重新预览")
        rev = (
            db.scalar(
                select(RecordRevision).where(
                    RecordRevision.record_id == obj.id, RecordRevision.version == obj.version
                )
            )
            if model is Record
            else db.scalar(
                select(Revision).where(Revision.item_id == obj.id, Revision.version == obj.version)
            )
        )
        picks = set()
        for pick in selection.materials:
            fingerprint = (pick.field_path, str(pick.source_version_id), pick.start, pick.end)
            if fingerprint in picks:
                raise Problem(422, "duplicate_selection", "不能重复选择材料")
            picks.add(fingerprint)
            if model is ResearchItem and (
                pick.source_version_id
                or pick.field_path
                not in {
                    "title",
                    "description",
                    *[
                        "details." + k
                        for k, v in obj.details.items()
                        if isinstance(v, str) and k != "kind"
                    ],
                }
            ):
                raise Problem(422, "invalid_material", "研究内容字段无效")
            row = AITaskInput(
                object_key=f"o{index + 1}",
                material_key=f"m{len(rows) + 1:03d}",
                record_id=obj.id if model is Record else None,
                record_revision_id=rev.id if model is Record else None,
                item_id=obj.id if model is ResearchItem else None,
                item_revision_id=rev.id if model is ResearchItem else None,
                source_version_id=str(pick.source_version_id) if pick.source_version_id else None,
                field_path=pick.field_path,
                start=pick.start,
                end=pick.end,
            )
            if not material_content(db, row).strip():
                raise Problem(422, "empty_material", "请选择有内容的材料")
            rows.append(row)
    projection = inputs_view(db, owner, rows)
    if projection["characters"] > 32000:
        raise Problem(413, "ai_input_too_large", "材料超过 32,000 字符，请缩小选择范围")
    return rows, projection


def inputs_view(db, owner, rows):
    objects, materials = {}, []
    for row in rows:
        obj = owned(
            db, Record if row.record_id else ResearchItem, owner, row.record_id or row.item_id, True
        )
        deleted = bool(obj.deleted_at)
        rev = (
            db.get(RecordRevision, row.record_revision_id)
            if row.record_id
            else db.get(Revision, row.item_revision_id)
        )
        project = db.get(Project, obj.project_id) if obj.project_id else None
        objects[row.object_key] = dict(
            key=row.object_key,
            kind="record" if row.record_id else "research_item",
            id=obj.id,
            title="来源已删除" if deleted else rev.snapshot["title"],
            version=rev.version,
            current_version=obj.version,
            project_id=obj.project_id,
            deleted=deleted,
            archived=bool(project and project.archived),
            current=None
            if deleted
            else (
                {"title": obj.title, "record_type": obj.record_type, "fields": obj.fields}
                if row.record_id
                else {"title": obj.title, "description": obj.description, "details": obj.details}
            ),
        )
        current_text = None
        if not deleted:
            if row.source_version_id:
                source_version = db.get(SourceVersion, row.source_version_id)
                source = db.get(Source, source_version.source_id)
                latest = db.scalar(
                    select(SourceVersion).where(
                        SourceVersion.source_id == source.id,
                        SourceVersion.version == source.current_version,
                    )
                )
                current_text = latest.content
            elif row.field_path.startswith("fields."):
                current_text = obj.fields.get(row.field_path[7:], "")
            elif row.field_path.startswith("details."):
                current_text = obj.details.get(row.field_path[8:], "")
            else:
                current_text = getattr(obj, row.field_path, "")
        materials.append(
            dict(
                key=row.material_key,
                object_key=row.object_key,
                field_path=row.field_path,
                source_version_id=row.source_version_id,
                text=None if deleted else material_content(db, row),
                current_text=current_text,
                unavailable=deleted,
            )
        )
    return dict(
        objects=list(objects.values()),
        materials=materials,
        characters=sum(len(m["text"] or "") for m in materials),
    )


def task_view(db, task):
    inputs = inputs_view(db, task.owner_id, input_rows(db, task.id))
    result = {
        key: getattr(task, key)
        for key in (
            "id",
            "kind",
            "status",
            "model",
            "endpoint",
            "config_version",
            "parent_id",
            "created_at",
            "started_at",
            "finished_at",
            "error_code",
            "error_message",
            "usage",
        )
    }
    result.update(
        inputs=inputs,
        needs_review=any(o["version"] != o["current_version"] for o in inputs["objects"]),
        unavailable=any(o["deleted"] for o in inputs["objects"]),
        suggestion_ids=list(
            db.scalars(
                select(AISuggestion.id)
                .where(AISuggestion.task_id == task.id)
                .order_by(AISuggestion.created_at, AISuggestion.id)
            )
        ),
    )
    return result


def suggestion_view(db, suggestion, task):
    t = task_view(db, task)
    redacted = t["unavailable"]
    result = {
        key: getattr(suggestion, key)
        for key in (
            "id",
            "task_id",
            "kind",
            "version",
            "status",
            "record_id",
            "record_revision_id",
            "relation_id",
            "relation_revision_id",
            "created_at",
            "decided_at",
        )
    }
    result.update(
        original=None if redacted else suggestion.original,
        accepted=None if redacted else suggestion.accepted,
        task=t,
        events=[
            dict(
                operation=e.operation,
                created_at=e.created_at,
                details={} if redacted else e.details,
            )
            for e in db.scalars(
                select(AISuggestionEvent)
                .where(AISuggestionEvent.suggestion_id == suggestion.id)
                .order_by(AISuggestionEvent.created_at, AISuggestionEvent.id)
            )
        ],
    )
    return result


def resolve_citations(db, rows, citations, whole=False):
    by_key = {r.material_key: r for r in rows}
    result = []
    for c in citations:
        row = by_key.get(c.material)
        if row is None or not row.record_id:
            raise Problem(422, "ai_invalid_citation", "引用必须来自所选科研记录或原始材料")
        text = material_content(db, row)
        start, end = None, None
        if c.quote:
            offset = -1
            for _ in range(c.occurrence):
                offset = text.find(c.quote, offset + 1)
                if offset < 0:
                    raise Problem(422, "ai_invalid_citation", "引用片段与选定原文不一致")
            start = (row.start or 0) + offset
            end = start + len(c.quote)
        elif not whole:
            raise Problem(422, "ai_invalid_citation", "请提供可核对的原文片段")
        elif row.start is not None:
            start, end = row.start, row.end
        result.append(
            dict(
                record_revision_id=row.record_revision_id,
                source_version_id=row.source_version_id,
                field_path=row.field_path,
                start=start,
                end=end,
                quote=c.quote if c.quote else text if start is not None else "",
                stance="context",
            )
        )
    return result


def validate_relation(db, rows, candidate):
    keys = {r.object_key for r in rows}
    if (
        candidate.source not in keys
        or candidate.target not in keys
        or candidate.source == candidate.target
    ):
        raise Problem(422, "ai_invalid_endpoint", "关系端点必须是选中的两个不同对象")
    if not candidate.reason.strip():
        raise Problem(422, "ai_invalid_output", "关系需要理由")
    return {**candidate.model_dump(), "evidence": resolve_citations(db, rows, candidate.citations)}


def validate_output(db, task, text):
    rows = input_rows(db, task.id)
    text = text.strip()
    if text.startswith("```json\n") and text.endswith("```"):
        text = text[8:-3].strip()
    raw = json.loads(text)
    if task.kind == "record_draft":
        value = DraftOutput.model_validate(raw)
        evidence = {
            k: resolve_citations(db, rows, f.citations, whole=k in ("title", "record_type"))
            for k, f in value.fields.items()
        }
        return [{**value.model_dump(), "evidence_by_field": evidence}]
    value = RelationsOutput.model_validate(raw)
    seen = set()
    results = []
    for candidate in value.relations:
        key = (candidate.source, candidate.target, candidate.relation_type)
        if key in seen:
            raise Problem(422, "ai_invalid_output", "模型重复返回相同关系")
        seen.add(key)
        results.append(validate_relation(db, rows, candidate))
    return results
