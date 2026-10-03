"""Fixed material selection, output validation and redacted projections."""

import json

from sqlalchemy import select

from .ai_materials import content as material_content
from .ai_materials import projection as inputs_view
from .ai_materials import selection_rows
from .models_ai import AISuggestion, AISuggestionEvent, AITaskInput
from .schemas_ai import ContributionsOutput, DraftOutput, RelationsOutput
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


def select_inputs(db, owner, value):
    rows = selection_rows(db, owner, value)
    projection = inputs_view(db, owner, rows)
    projection["parameters"] = value.parameters.model_dump()
    projection["characters"] += len(value.parameters.goal) + len(value.parameters.constraints)
    if projection["characters"] > 32000:
        raise Problem(413, "ai_input_too_large", "材料与目标限制超过32,000字符，请缩小范围")
    return rows, projection


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
    inputs["parameters"] = task.parameters or {}
    inputs["characters"] += sum(len(v) for v in inputs["parameters"].values() if isinstance(v, str))
    result.update(
        parameters=task.parameters or {},
        target_reflection_id=task.target_reflection_id,
        inputs=inputs,
        needs_review=any(
            o["selected_current_version"] != o["current_version"] for o in inputs["objects"]
        ),
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
            "contribution_id",
            "contribution_revision_id",
            "action_id",
            "action_revision_id",
            "reflection_id",
            "reflection_revision_id",
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
    if not redacted and suggestion.kind in ("action_candidates", "reflection_draft"):
        from .schemas_ai import ActionCandidate, ReflectionOutput

        schema = ActionCandidate if suggestion.kind == "action_candidates" else ReflectionOutput
        result["planning"] = {
            k: v for k, v in suggestion.original.items() if k in schema.model_fields
        }
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
    if task.kind in ("action_candidates", "reflection_draft"):
        from .ai_planning import validate_output as validate_planning

        return validate_planning(db, task, rows, raw)
    if task.kind == "record_draft":
        value = DraftOutput.model_validate(raw)
        evidence = {
            k: resolve_citations(db, rows, f.citations, whole=k in ("title", "record_type"))
            for k, f in value.fields.items()
        }
        return [{**value.model_dump(), "evidence_by_field": evidence}]
    if task.kind == "contribution_candidates":
        value = ContributionsOutput.model_validate(raw)
        results = []
        for candidate in value.contributions:
            by_field = {
                k: resolve_citations(db, rows, f.citations) for k, f in candidate.fields.items()
            }
            unique = {}
            for refs in by_field.values():
                for ref in refs:
                    ref = {k: v for k, v in ref.items() if k != "stance"}
                    ref["purpose"] = "context"
                    from .schemas_growth import GrowthEvidenceInput

                    ref = GrowthEvidenceInput.model_validate(ref).model_dump(mode="json")
                    unique[json.dumps(ref, sort_keys=True)] = ref
            if not unique or len(unique) > 50:
                raise Problem(422, "ai_invalid_citation", "贡献需 1–50 项可定位依据")
            results.append(
                {
                    **candidate.model_dump(),
                    "evidence_by_field": by_field,
                    "evidence": list(unique.values()),
                }
            )
        return results
    if task.kind != "relation_suggestions":
        raise Problem(422, "ai_task_kind", "不支持的 AI 任务类型")
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
