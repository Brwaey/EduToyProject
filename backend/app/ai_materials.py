"""Explicit, fixed-version text adapters; never traverse referenced material bodies."""

from sqlalchemy import select

from .growth_data import MODELS, archived, latest_revision, reference_summary, revision
from .m2_common import evidence_content, owned, writable
from .models import Project, SourceVersion
from .models_ai import AITaskInput
from .security import Problem

KINDS = {
    "record": "record",
    "research_item": "item",
    "action": "action",
    "reflection": "reflection",
    "contribution": "contribution",
    "growth_entry": "entry",
}
NEW_TASKS = {"action_candidates", "reflection_draft"}
REFLECTION_FIELDS = ("progress", "understanding", "blockers", "next_steps")
DETAIL_FIELDS = {
    "action": {
        "research_goal",
        "learning_goal",
        "completion_criteria",
        "expected_date",
        "effort",
        "pause_reason",
        "restart_condition",
    },
    "reflection": {
        "expectations",
        "actual",
        "known",
        "unknown",
        "explanations",
        "reusable",
        "progress",
        "understanding",
        "blockers",
        "next_steps",
        "reason",
        "restart_condition",
    },
    "contribution": {"personal_role", "reason", "ai_help", "others_help", "impact", "next_steps"},
    "growth_entry": {
        "situation",
        "attempts",
        "learned",
        "completion_mode",
        "basis_type",
        "difficulties",
        "next_steps",
        "before",
        "after",
        "trigger",
        "uncertainty",
    },
}


def identity(row):
    for kind, key in KINDS.items():
        if getattr(row, key + "_id"):
            return kind, getattr(row, key + "_id"), getattr(row, key + "_revision_id")
    raise Problem(422, "invalid_material", "材料对象无效")


def row_objects(db, owner, row):
    kind, object_id, revision_id = identity(row)
    obj, rev = revision(db, owner, kind, object_id, revision_id)
    return kind, obj, rev


def fields(kind, snapshot):
    result = {"title": snapshot.get("title", "")}
    if kind == "record":
        result["body"] = snapshot.get("body", "")
        result.update(
            {
                "fields." + k: v
                for k, v in snapshot.get("fields", {}).items()
                if k
                in (
                    "context",
                    "actions",
                    "collaboration",
                    "observations",
                    "interpretation",
                    "next_steps",
                )
            }
        )
    else:
        if kind == "research_item":
            result["description"] = snapshot.get("description", "")
        if kind == "action":
            result["result_summary"] = snapshot.get("result_summary", "")
        allowed = DETAIL_FIELDS.get(kind, set(snapshot.get("details", {})) - {"kind"})
        result.update(
            {"details." + k: v for k, v in snapshot.get("details", {}).items() if k in allowed}
        )
    return {k: v for k, v in result.items() if isinstance(v, str)}


def evidence_label(kind, snapshot):
    if kind in ("contribution", "growth_entry"):
        return (
            "用户自述／待补依据"
            if not snapshot.get("evidence")
            else "用户表述／已附材料，未自动发送下层依据"
        )
    return None


def content(db, row):
    kind, object_id, revision_id = identity(row)
    obj = db.get(MODELS[kind], object_id)
    _, rev = revision(db, obj.owner_id, kind, object_id, revision_id)
    if kind == "record":
        value = evidence_content(db, rev, row.source_version_id, row.field_path)
    else:
        if row.source_version_id or row.field_path not in fields(kind, rev.snapshot):
            raise Problem(422, "invalid_material", "材料字段无效")
        value = fields(kind, rev.snapshot)[row.field_path]
    if row.start is not None:
        if row.end > len(value):
            raise Problem(422, "invalid_material", "片段超出原文范围")
        value = value[row.start : row.end]
    return value


def selection_rows(db, owner, value):
    new = value.kind in NEW_TASKS
    if not new and (
        value.target_reflection_id or value.parameters.goal or value.parameters.constraints
    ):
        raise Problem(422, "invalid_selection", "该任务不支持规划参数")
    if value.kind == "action_candidates" and not value.parameters.goal.strip():
        raise Problem(422, "invalid_selection", "请填写这次希望解决什么")
    if value.kind != "reflection_draft" and value.target_reflection_id:
        raise Problem(422, "invalid_selection", "只有复盘整理需要目标复盘")
    if value.kind == "record_draft" and (
        len(value.objects) != 1 or value.objects[0].kind != "record"
    ):
        raise Problem(422, "invalid_selection", "整理时请选择一条记录")
    if value.kind == "relation_suggestions" and (
        len(value.objects) < 2 or not any(o.kind == "record" for o in value.objects)
    ):
        raise Problem(422, "invalid_selection", "请选择至少两个对象，其中包含科研记录")
    rows, seen = [], set()
    for i, pick in enumerate(value.objects):
        if not new and pick.kind not in (
            {"record", "research_item"} if value.kind == "relation_suggestions" else {"record"}
        ):
            raise Problem(422, "invalid_selection", "此任务不支持所选对象类型")
        if not new and (pick.revision_id or pick.current_version):
            raise Problem(422, "invalid_selection", "此任务只使用当前材料")
        obj = owned(db, MODELS[pick.kind], owner, pick.id)
        writable(db, obj)
        if obj.version != (
            pick.current_version if pick.current_version is not None else pick.version
        ):
            raise Problem(409, "version_conflict", "材料已变化，请重新预览")
        rev = (
            revision(db, owner, pick.kind, obj.id, pick.revision_id)[1]
            if pick.revision_id
            else latest_revision(db, obj)
        )
        if rev.version != pick.version:
            raise Problem(409, "version_conflict", "固定修订与版本不匹配")
        ident = (pick.kind, obj.id)
        if ident in seen:
            raise Problem(422, "duplicate_selection", "不能重复选择对象")
        seen.add(ident)
        unique = set()
        for field in pick.materials:
            fingerprint = (field.field_path, str(field.source_version_id), field.start, field.end)
            if fingerprint in unique:
                raise Problem(422, "duplicate_selection", "不能重复选择字段")
            unique.add(fingerprint)
            key = KINDS[pick.kind]
            row = AITaskInput(
                object_key=f"o{i + 1}",
                material_key=f"m{len(rows) + 1:03}",
                selected_current_version=obj.version if new else None,
                **{key + "_id": obj.id, key + "_revision_id": rev.id},
                **field.model_dump(mode="json"),
            )
            if not content(db, row).strip():
                raise Problem(422, "empty_material", "请选择有内容的字段")
            rows.append(row)
    if value.kind == "reflection_draft":
        validate_reflection(db, owner, value, rows)
    return rows


def validate_reflection(db, owner, value, rows):
    target_rows = [r for r in rows if r.reflection_id == str(value.target_reflection_id)]
    if not target_rows:
        raise Problem(422, "invalid_selection", "请选择已保存的目标周期复盘")
    _, target, rev = row_objects(db, owner, target_rows[0])
    if target.kind != "period" or rev.version != target.version:
        raise Problem(422, "invalid_selection", "请使用已保存周期复盘的当前版本")
    if not any(target.details.get(k, "").strip() for k in REFLECTION_FIELDS) or not any(
        r.field_path in {"details." + k for k in REFLECTION_FIELDS} for r in target_rows
    ):
        raise Problem(422, "reflection_text_required", "请先写下并保存自己的周判断，再勾选相关字段")
    allowed = {(m["kind"], m["id"], m["revision_id"]) for m in target.materials}
    for row in rows:
        if row in target_rows:
            if row.field_path not in {"details." + k for k in REFLECTION_FIELDS}:
                raise Problem(422, "invalid_material", "复盘自身只选择四项整理字段")
        elif identity(row) not in allowed:
            raise Problem(422, "invalid_selection", "请先将该固定材料加入复盘并保存")


def projection(db, owner, rows):
    objects, materials = {}, []
    for row in rows:
        kind, obj, rev = row_objects(db, owner, row)
        deleted = bool(obj.deleted_at)
        current = fields(
            kind,
            {
                "title": obj.title,
                "body": getattr(obj, "body", ""),
                "fields": getattr(obj, "fields", {}),
                "details": getattr(obj, "details", {}),
                "description": getattr(obj, "description", ""),
                "result_summary": getattr(obj, "result_summary", ""),
            },
        )
        obj_current = {
            "title": obj.title,
            "record_type": getattr(obj, "record_type", None),
            "fields": getattr(obj, "fields", {}),
            "details": getattr(obj, "details", {}),
            "description": getattr(obj, "description", ""),
        }
        objects[row.object_key] = dict(
            key=row.object_key,
            kind=kind,
            id=obj.id,
            title="来源已删除" if deleted else rev.snapshot.get("title", ""),
            version=rev.version,
            current_version=obj.version,
            selected_current_version=row.selected_current_version or rev.version,
            revision_id=rev.id,
            project_id=obj.project_id,
            deleted=deleted,
            archived=archived(db, obj),
            current=None if deleted else obj_current,
            evidence_label=evidence_label(kind, rev.snapshot),
        )
        latest = current.get(row.field_path, "")
        if row.source_version_id and not deleted:
            source = db.get(SourceVersion, row.source_version_id)
            latest = db.scalar(
                select(SourceVersion.content)
                .where(SourceVersion.source_id == source.source_id)
                .order_by(SourceVersion.version.desc())
                .limit(1)
            )
        materials.append(
            dict(
                key=row.material_key,
                object_key=row.object_key,
                field_path=row.field_path,
                source_version_id=row.source_version_id,
                text=None if deleted else content(db, row),
                current_text=None if deleted else latest,
                unavailable=deleted,
            )
        )
    return dict(
        objects=list(objects.values()),
        materials=materials,
        characters=sum(len(m["text"] or "") for m in materials),
    )


def detail(db, owner, kind, object_id, revision_id=None):
    if kind not in KINDS:
        raise Problem(422, "invalid_material", "不支持的材料类型")
    obj = owned(db, MODELS[kind], owner, object_id)
    writable(db, obj)
    rev = (
        revision(db, owner, kind, obj.id, revision_id)[1]
        if revision_id
        else latest_revision(db, obj)
    )
    options = [
        dict(label=k, text=v, pick={"field_path": k})
        for k, v in fields(kind, rev.snapshot).items()
        if v.strip()
    ]
    if kind == "record":
        for sid in rev.snapshot.get("source_version_ids", []):
            source = db.get(SourceVersion, sid)
            if source and source.content.strip():
                options.append(
                    dict(
                        label="原始材料 v" + str(source.version),
                        text=source.content,
                        pick={"field_path": "body", "source_version_id": source.id},
                    )
                )
    return dict(
        kind=kind,
        id=obj.id,
        title=rev.snapshot["title"],
        project_id=obj.project_id,
        version=rev.version,
        current_version=obj.version,
        revision_id=rev.id,
        evidence_label=evidence_label(kind, rev.snapshot),
        options=options,
        related=[
            reference_summary(db, owner, r["kind"], r["id"], r["revision_id"])
            for r in rev.snapshot.get("materials", [])
        ]
        if kind == "reflection"
        else [],
    )


def catalog(db, owner, task_kind, kind=None, q="", project_id=None, page=1, page_size=20):
    allowed = (
        list(KINDS)
        if task_kind in NEW_TASKS
        else (["record", "research_item"] if task_kind == "relation_suggestions" else ["record"])
    )
    if task_kind not in NEW_TASKS | {
        "record_draft",
        "relation_suggestions",
        "contribution_candidates",
    }:
        raise Problem(422, "ai_task_kind", "不支持的任务")
    if project_id:
        owned(db, Project, owner, project_id)
    rows = []
    for k in allowed:
        if kind and k != kind:
            continue
        model = MODELS[k]
        stmt = select(model).where(model.owner_id == owner, model.deleted_at.is_(None))
        if q.strip():
            stmt = stmt.where(model.title.contains(q.strip(), autoescape=True))
        if project_id:
            stmt = stmt.where(model.project_id == str(project_id))
        for obj in db.scalars(stmt):
            if not archived(db, obj):
                rows.append(
                    dict(
                        kind=k,
                        id=obj.id,
                        title=obj.title,
                        project_id=obj.project_id,
                        version=obj.version,
                        updated_at=obj.updated_at,
                    )
                )
    rows.sort(key=lambda r: (r["updated_at"], r["id"]), reverse=True)
    return dict(
        items=rows[(page - 1) * page_size : page * page_size],
        total=len(rows),
        page=page,
        page_size=page_size,
    )
