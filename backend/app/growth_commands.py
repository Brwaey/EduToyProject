"""Growth writes use caller-owned short transactions and immutable snapshots."""

from sqlalchemy import delete, select

from . import growth_data as data
from .db import now
from .m2_common import advance, check_project, owned, receipt, replay, writable
from .models_growth import (
    AbilityTag,
    Contribution,
    GrowthActionLink,
    GrowthEntry,
    GrowthEntryTag,
    GrowthEvidence,
)
from .models_m2 import ResearchItem
from .security import Problem


def check_question(db, owner, question_id, previous=None):
    if question_id:
        obj = owned(db, ResearchItem, owner, question_id, True)
        if obj.kind != "question":
            raise Problem(422, "invalid_question", "请选择研究问题")
        if not previous or str(question_id) != previous.question_id:
            if obj.deleted_at:
                raise Problem(409, "source_deleted", "请先恢复研究问题")
            writable(db, obj)


def set_evidence(db, owner, obj, values):
    previous = data.evidence_rows(db, obj)
    checked = []
    for value in values:
        payload = value.model_dump(mode="json")
        kind, source, rev = data.evidence_target(db, owner, payload)
        if isinstance(obj, Contribution) and kind == "contribution":
            raise Problem(422, "invalid_evidence", "贡献只能引用记录、行动或复盘")
        if (
            isinstance(obj, Contribution) or obj.kind == "ability_instance"
        ) and value.purpose != "context":
            raise Problem(422, "invalid_evidence", "只有理解变化区分前后依据")
        if (
            isinstance(obj, GrowthEntry)
            and obj.kind == "understanding_change"
            and value.purpose == "context"
        ):
            raise Problem(422, "invalid_evidence", "请选择之前、触发或现在依据")
        old = next(
            (
                e
                for e in previous
                if all(getattr(e, k) == v for k, v in payload.items() if k != "quote")
                and (e.quote == value.quote or (source.deleted_at and not value.quote))
            ),
            None,
        )
        if source.deleted_at:
            if not old:
                raise Problem(409, "source_deleted", "已删除材料不能新增引用")
            payload["quote"] = old.quote
        else:
            if not old:
                writable(db, source)
            if kind == "record":
                content = data.evidence_content(db, rev, value.source_version_id, value.field_path)
                if value.start is not None and (
                    value.end > len(content) or content[value.start : value.end] != value.quote
                ):
                    raise Problem(422, "invalid_evidence", "片段与原文不一致")
                if value.start is None and value.quote:
                    raise Problem(422, "invalid_evidence", "引用片段须提供位置")
        key = "contribution_id" if isinstance(obj, Contribution) else "entry_id"
        checked.append(
            GrowthEvidence(
                **{key: obj.id},
                **payload,
                reviewed_version=old.reviewed_version if old else rev.version,
                reviewed_dependencies=old.reviewed_dependencies if old else {},
            )
        )
    for row in previous:
        db.delete(row)
    db.add_all(checked)
    db.flush()


def contribution_save(db, owner, value, object_id=None, operation=None, extra=None):
    if not object_id:
        prior, digest = replay(db, owner, "contribution.create", value)
        if prior:
            return owned(db, Contribution, owner, prior.result_id, True)
    previous = owned(db, Contribution, owner, object_id) if object_id else None
    check_project(db, owner, value.project_id)
    check_question(db, owner, value.question_id, previous)
    fields = value.model_dump(
        mode="json", exclude={"evidence", "expected_version", "request_id", "confirmed"}
    )
    fields["confirmed_at"] = now()
    if previous:
        advance(db, previous, value.expected_version, fields)
        obj = previous
    else:
        obj = Contribution(owner_id=owner, **fields)
        db.add(obj)
        db.flush()
    set_evidence(db, owner, obj, value.evidence)
    data.freeze(db, obj, operation or ("edit" if previous else "create"), extra)
    if not previous:
        receipt(db, owner, "contribution.create", value, digest, obj)
    return obj


def entry_save(db, owner, value, object_id=None):
    if not object_id:
        prior, digest = replay(db, owner, "growth.create", value)
        if prior:
            return owned(db, GrowthEntry, owner, prior.result_id, True)
    previous = owned(db, GrowthEntry, owner, object_id) if object_id else None
    if previous and previous.kind != value.kind:
        raise Problem(422, "immutable_kind", "不能更改成长条目类型")
    check_project(db, owner, value.project_id)
    check_question(db, owner, value.question_id, previous)
    old_tags = {t.id for t in data.tags_for(db, previous)} if previous else set()
    tags = [owned(db, AbilityTag, owner, tag_id) for tag_id in set(value.tag_ids)]
    if any(t.archived and t.id not in old_tags for t in tags):
        raise Problem(409, "tag_archived", "请恢复能力标签后再新增关联")
    fields = value.model_dump(
        mode="json", exclude={"evidence", "expected_version", "request_id", "tag_ids"}
    )
    if previous:
        advance(db, previous, value.expected_version, fields)
        obj = previous
    else:
        obj = GrowthEntry(owner_id=owner, **fields)
        db.add(obj)
        db.flush()
    set_evidence(db, owner, obj, value.evidence)
    if value.kind == "ability_instance":
        targets = [
            data.evidence_target(db, owner, data.evidence_dict(e))
            for e in data.evidence_rows(db, obj)
        ]
        basis = value.details.basis_type
        if basis == "material" and not any(
            k in ("record", "action", "reflection") for k, _, _ in targets
        ):
            raise Problem(422, "evidence_required", "材料记录需要记录、行动或复盘依据")
        if basis == "task_practice" and not any(
            k == "action"
            and r.snapshot.get("status") == "completed"
            and r.snapshot.get("result_summary", "").strip()
            for k, _, r in targets
        ):
            raise Problem(422, "evidence_required", "任务实践需要包含结项说明的已完成行动快照")
    db.execute(delete(GrowthEntryTag).where(GrowthEntryTag.entry_id == obj.id))
    db.add_all([GrowthEntryTag(entry_id=obj.id, tag_id=t.id) for t in tags])
    data.freeze(db, obj, "edit" if previous else "create")
    if not previous:
        receipt(db, owner, "growth.create", value, digest, obj)
    return obj


def tag_save(db, owner, value, object_id=None):
    if not object_id:
        prior, digest = replay(db, owner, "ability_tag.create", value)
        if prior:
            return owned(db, AbilityTag, owner, prior.result_id)
    other = db.scalar(
        select(AbilityTag).where(AbilityTag.owner_id == owner, AbilityTag.name == value.name)
    )
    if other and other.id != object_id:
        raise Problem(409, "tag_exists", "已有同名能力标签（含已归档标签）")
    fields = value.model_dump(mode="json", exclude={"expected_version", "request_id"})
    if object_id:
        obj = owned(db, AbilityTag, owner, object_id)
        advance(db, obj, value.expected_version, fields)
    else:
        obj = AbilityTag(owner_id=owner, **fields)
        db.add(obj)
    data.freeze(db, obj, "edit" if object_id else "create")
    if not object_id:
        receipt(db, owner, "ability_tag.create", value, digest, obj)
    return obj


def lifecycle(db, owner, model, object_id, expected, deleted):
    obj = owned(db, model, owner, object_id, True)
    advance(db, obj, expected, {"deleted_at": now() if deleted else None})
    data.freeze(db, obj, "delete" if deleted else "restore")
    return obj


def review(db, owner, model, object_id, value):
    obj = owned(db, model, owner, object_id)
    view = data.object_view(db, obj)
    if value.current_versions != view["current_versions"]:
        raise Problem(409, "version_conflict", "依据再次变化，请重新载入核对")
    if any(e["availability"] == "deleted" for e in view["evidence"]):
        raise Problem(409, "source_deleted", "请恢复不可用依据后复核")
    advance(db, obj, value.expected_version)
    for row in data.evidence_rows(db, obj):
        row.reviewed_version = value.current_versions[row.id]
        _, _, rev = data.evidence_target(db, owner, data.evidence_dict(row))
        row.reviewed_dependencies = data.dependency_state(db, owner, rev)[0]
    data.freeze(db, obj, "review")
    return obj


def create_action(db, owner, model, object_id, value):
    from .m2_commands import action_save

    operation = "growth.action:" + str(object_id)
    prior, digest = replay(db, owner, operation, value)
    if prior:
        from .models_m2 import Action

        return owned(db, Action, owner, prior.result_id, True)
    obj = owned(db, model, owner, object_id)
    writable(db, obj)
    rev = data.latest_revision(db, obj)
    if obj.version != value.expected_version or rev.id != str(value.revision_id):
        raise Problem(409, "version_conflict", "成长内容已变化，请重新核对")
    from .models_m2 import MutationRequest

    if db.scalar(
        select(MutationRequest).where(
            MutationRequest.owner_id == owner,
            MutationRequest.operation == "action.create",
            MutationRequest.request_id == str(value.action.request_id),
        )
    ):
        raise Problem(409, "request_conflict", "行动请求标识已使用，请重新创建")
    action = action_save(db, owner, value.action)
    existing = db.get(GrowthActionLink, action.id)
    if existing:
        raise Problem(409, "request_conflict", "该行动已用于其他来源操作")
    # action_save already froze the initial revision; augment before committing.
    from .models_m2 import Revision

    action_rev = db.scalar(
        select(Revision).where(Revision.action_id == action.id, Revision.version == action.version)
    )
    action_rev.snapshot = {
        **action_rev.snapshot,
        "growth_origin": {
            "kind": "contribution" if model is Contribution else "growth_entry",
            "id": obj.id,
            "revision_id": rev.id,
        },
    }
    db.add(GrowthActionLink(action_id=action.id, owner_id=owner, revision_id=rev.id))
    receipt(db, owner, operation, value, digest, action)
    db.flush()
    return action
