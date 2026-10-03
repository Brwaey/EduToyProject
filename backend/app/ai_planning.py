"""M5 outputs and atomic adoption into existing action/reflection services."""

from sqlalchemy import select

from . import m2_commands
from .ai_materials import content, row_objects
from .growth_data import latest_revision
from .m2_common import owned
from .models_ai import AIAdoption, AIAdoptionCitation, AITaskInput
from .models_m2 import Action, Reflection, Revision
from .schemas_ai import ActionsOutput, ReflectionOutput
from .schemas_m2 import ActionCreate, ReflectionEdit
from .security import Problem


def citations(db, rows, values):
    by_key = {r.material_key: r for r in rows}
    result = []
    for c in values:
        row = by_key.get(c.material)
        if row is None or not c.quote:
            raise Problem(422, "ai_invalid_citation", "请引用本次选定材料的原文片段")
        text = content(db, row)
        offset = -1
        for _ in range(c.occurrence):
            offset = text.find(c.quote, offset + 1)
            if offset < 0:
                raise Problem(422, "ai_invalid_citation", "引用与原文不一致")
        start = (row.start or 0) + offset
        result.append(dict(input_id=row.id, start=start, end=start + len(c.quote), quote=c.quote))
    return result


def validate_output(db, task, rows, raw):
    if task.kind == "action_candidates":
        value = ActionsOutput.model_validate(raw)
        return [
            {**a.model_dump(), "evidence_by_field": {"reason": citations(db, rows, a.citations)}}
            for a in value.actions
        ]
    value = ReflectionOutput.model_validate(raw)
    return [
        {
            **value.model_dump(),
            "evidence_by_field": {
                k: citations(db, rows, f.citations) for k, f in value.fields.items()
            },
        }
    ]


def accept_planning(db, owner, suggestion, task, rows, view, value):
    original = suggestion.original
    if suggestion.kind == "action_candidates":
        p = value.action.model_dump(mode="json")
        directions = {
            o["id"]
            for o in view["objects"]
            if o["kind"] == "research_item" and o["current"]["details"].get("kind") == "direction"
        }
        reflections = {o["id"] for o in view["objects"] if o["kind"] == "reflection"}
        if (p["direction_id"] and p["direction_id"] not in directions) or (
            p["origin_reflection_id"] and p["origin_reflection_id"] not in reflections
        ):
            raise Problem(422, "invalid_acceptance", "只能关联本次选定的方向或复盘")
        if (
            not p["details"]["research_goal"].strip()
            or not p["details"]["completion_criteria"].strip()
        ):
            raise Problem(422, "invalid_acceptance", "请明确研究目标与完成标准")
        obj = m2_commands.action_save(
            db, owner, ActionCreate(request_id=suggestion.id, status="planned", results=[], **p)
        )
        suggestion.action_id = obj.id
        selected = {"reason": original["evidence_by_field"]["reason"]}
        modified = (
            p["title"] != original["title"]
            or any(
                p["details"][k] != original[k]
                for k in ("research_goal", "learning_goal", "completion_criteria", "effort")
            )
            or bool(p["details"]["expected_date"])
        )
        final = {
            **p,
            "proposal_reason": original["reason"],
            "proposal_uncertainty": original["uncertainty"],
        }
    else:
        obj = owned(db, Reflection, owner, task.target_reflection_id)
        if obj.kind != "period" or obj.version != value.reflection.expected_version:
            raise Problem(409, "version_conflict", "目标复盘已更新，请重新核对当前文字")
        if not value.reflection.fields:
            raise Problem(422, "invalid_acceptance", "至少选择一个字段")
        details = dict(obj.details)
        selected = {}
        final = {}
        modified = False
        for key, field in value.reflection.fields.items():
            if key not in original["fields"] or not original["evidence_by_field"].get(key):
                raise Problem(422, "ai_invalid_citation", "只能采纳有依据的本次草稿字段")
            previous = details.get(key, "")
            expected = (
                (
                    previous + "\n\n" + field.text
                    if previous and field.text
                    else previous or field.text
                )
                if field.mode == "append"
                else field.text
            )
            if field.final_text != expected:
                raise Problem(
                    409, "version_conflict", "最终文本与当前内容不匹配，请重新预览追加或替换结果"
                )
            details[key] = field.final_text
            selected[key] = original["evidence_by_field"][key]
            final[key] = field.model_dump()
            modified |= field.text != original["fields"][key]["value"] or field.mode == "append"
        p = {
            k: getattr(obj, k)
            for k in ("kind", "title", "project_id", "start_at", "end_at", "timezone", "materials")
        }
        obj = m2_commands.reflection_save(
            db, owner, ReflectionEdit(expected_version=obj.version, details=details, **p), obj.id
        )
        suggestion.reflection_id = obj.id
    rev = latest_revision(db, obj)
    rev.operation = "ai_accept"
    rev.snapshot = {**rev.snapshot, "ai_suggestion_id": suggestion.id}
    if isinstance(obj, Action):
        suggestion.action_revision_id = rev.id
    else:
        suggestion.reflection_revision_id = rev.id
    adoption = AIAdoption(
        owner_id=owner,
        suggestion_id=suggestion.id,
        revision_id=rev.id,
        final_content=final,
        review_info={
            "reviewed": value.reviewed,
            "current_versions": value.current_versions,
            "user_modified": modified,
        },
    )
    db.add(adoption)
    db.flush()
    for field, refs in selected.items():
        for ref in refs:
            # Validate persisted mapping again before using it for formal provenance.
            row = db.get(AITaskInput, ref["input_id"])
            if not row or row.task_id != task.id:
                raise Problem(422, "ai_invalid_citation", "采纳引用无效")
            row_objects(db, owner, row)
            db.add(AIAdoptionCitation(adoption_id=adoption.id, field=field, **ref))
    suggestion.accepted = final
    db.flush()
    return modified


def adoption_view(db, owner, adoption):
    refs = []
    for c in db.scalars(
        select(AIAdoptionCitation)
        .where(AIAdoptionCitation.adoption_id == adoption.id)
        .order_by(AIAdoptionCitation.id)
    ):
        row = db.get(AITaskInput, c.input_id)
        kind, obj, rev = row_objects(db, owner, row)
        deleted = bool(obj.deleted_at)
        refs.append(
            dict(
                kind=kind,
                id=obj.id,
                revision_id=rev.id,
                version=rev.version,
                title="来源已删除" if deleted else rev.snapshot.get("title", ""),
                field=c.field,
                field_path=row.field_path,
                source_version_id=row.source_version_id,
                quote=None if deleted else c.quote,
                deleted=deleted,
                needs_review=deleted
                or obj.version
                != adoption.review_info.get("current_versions", {}).get(
                    row.object_key, rev.version
                ),
            )
        )
    return dict(
        id=adoption.id,
        suggestion_id=adoption.suggestion_id,
        revision_id=adoption.revision_id,
        created_at=adoption.created_at,
        final_content=adoption.final_content,
        review_info=adoption.review_info,
        citations=refs,
    )


def adoptions_for(db, owner, obj=None, revision_id=None):
    stmt = select(AIAdoption).where(AIAdoption.owner_id == owner)
    if revision_id:
        stmt = stmt.where(AIAdoption.revision_id == revision_id)
    else:
        key = Revision.action_id if isinstance(obj, Action) else Revision.reflection_id
        stmt = stmt.join(Revision, AIAdoption.revision_id == Revision.id).where(key == obj.id)
    return [adoption_view(db, owner, a) for a in db.scalars(stmt.order_by(AIAdoption.created_at))]
