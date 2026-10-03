"""M4 ownership and bounded, deletion-aware read projections."""

from sqlalchemy import select

from .m2_common import columns, evidence_content, owned
from .models import Project, Record, RecordRevision
from .models_growth import (
    AbilityTag,
    Contribution,
    GrowthActionLink,
    GrowthEntry,
    GrowthEntryTag,
    GrowthEvidence,
    GrowthRevision,
)
from .models_m2 import Action, Reflection, ResearchItem, Revision
from .security import Problem

MODELS = {
    "contribution": Contribution,
    "growth_entry": GrowthEntry,
    "record": Record,
    "action": Action,
    "reflection": Reflection,
    "research_item": ResearchItem,
}
KEYS = {Contribution: "contribution_id", GrowthEntry: "entry_id", AbilityTag: "tag_id"}
M2_KEYS = {Action: "action_id", Reflection: "reflection_id", ResearchItem: "item_id"}


def revision(db, owner, kind, object_id, revision_id):
    model = MODELS[kind]
    obj = owned(db, model, owner, object_id, True)
    revmodel = RecordRevision if model is Record else GrowthRevision if model in KEYS else Revision
    key = "record_id" if model is Record else KEYS.get(model) or M2_KEYS[model]
    rev = db.get(revmodel, str(revision_id))
    if not rev or getattr(rev, key) != obj.id:
        raise Problem(404, "not_found", "固定修订不存在")
    return obj, rev


def latest_revision(db, obj):
    model = type(obj)
    revmodel = RecordRevision if model is Record else GrowthRevision if model in KEYS else Revision
    key = "record_id" if model is Record else KEYS.get(model) or M2_KEYS[model]
    return db.scalar(
        select(revmodel).where(getattr(revmodel, key) == obj.id, revmodel.version == obj.version)
    )


def archived(db, obj):
    project = db.get(Project, obj.project_id) if getattr(obj, "project_id", None) else None
    return bool(project and project.archived)


def evidence_rows(db, obj):
    key = "contribution_id" if isinstance(obj, Contribution) else "entry_id"
    return list(
        db.scalars(
            select(GrowthEvidence)
            .where(getattr(GrowthEvidence, key) == obj.id)
            .order_by(GrowthEvidence.id)
        )
    )


def evidence_dict(row):
    if isinstance(row, dict):
        return dict(row)
    return {k: v for k, v in columns(row).items() if k not in ("contribution_id", "entry_id")}


def evidence_target(db, owner, value):
    if value.get("record_revision_id"):
        rev = db.get(RecordRevision, str(value["record_revision_id"]))
        kind, model, key = "record", Record, "record_id"
    elif value.get("m2_revision_id"):
        rev = db.get(Revision, str(value["m2_revision_id"]))
        if rev and rev.action_id:
            kind, model, key = "action", Action, "action_id"
        elif rev and rev.reflection_id:
            kind, model, key = "reflection", Reflection, "reflection_id"
        else:
            raise Problem(422, "invalid_evidence", "请选择行动或复盘修订")
    else:
        rev = db.get(GrowthRevision, str(value.get("contribution_revision_id", "")))
        kind, model, key = "contribution", Contribution, "contribution_id"
    if not rev or not getattr(rev, key):
        raise Problem(404, "not_found", "依据修订不存在")
    obj = owned(db, model, owner, getattr(rev, key), True)
    return kind, obj, rev


def dependency_state(db, owner, rev, acknowledged=None):
    """Iterative status traversal, each immutable revision visited at most once."""
    pending, seen, versions = [rev], set(), {}
    changed = deleted = False
    acknowledged = acknowledged or {}
    while pending:
        current = pending.pop()
        if current.id in seen:
            continue
        seen.add(current.id)
        children = []
        for e in current.snapshot.get("evidence", []):
            _, obj, child = evidence_target(db, owner, e)
            expected = e.get("reviewed_version", e.get("reviewed_record_version", child.version))
            children.append((obj, child, expected))
        for ref in current.snapshot.get("materials", []):
            obj, child = revision(db, owner, ref["kind"], ref["id"], ref["revision_id"])
            children.append((obj, child, child.version))
        for ref in current.snapshot.get("results", []):
            obj, child = revision(db, owner, "record", ref["record_id"], ref["record_revision_id"])
            children.append((obj, child, child.version))
        for obj, child, expected in children:
            versions[child.id] = obj.version
            deleted |= bool(obj.deleted_at)
            changed |= bool(obj.deleted_at) or obj.version != acknowledged.get(child.id, expected)
            if not obj.deleted_at:
                pending.append(child)
    return versions, changed, deleted


def nested_review(db, owner, rev):
    return dependency_state(db, owner, rev)[1]


def reference_summary(db, owner, kind, object_id, revision_id):
    obj, rev = revision(db, owner, kind, object_id, revision_id)
    return dict(
        kind=kind,
        id=obj.id,
        revision_id=rev.id,
        title="来源已删除" if obj.deleted_at else rev.snapshot.get("title", "材料"),
        version=rev.version,
        deleted=bool(obj.deleted_at),
        archived=archived(db, obj),
        occurred_on=rev.snapshot.get("occurred_on"),
        snapshot=None,
        needs_review=bool(obj.deleted_at) or obj.version != rev.version,
    )


def shallow_snapshot(db, owner, value):
    """One level of user text, nested references become authorized summaries."""
    result = {
        k: v
        for k, v in value.items()
        if k not in ("evidence", "materials", "results", "owner_id", "growth_origin")
    }
    refs = []
    for e in value.get("evidence", []):
        kind, obj, rev = evidence_target(db, owner, e)
        refs.append(reference_summary(db, owner, kind, obj.id, rev.id))
    for ref in value.get("materials", []):
        refs.append(reference_summary(db, owner, ref["kind"], ref["id"], ref["revision_id"]))
    for ref in value.get("results", []):
        refs.append(
            reference_summary(db, owner, "record", ref["record_id"], ref["record_revision_id"])
        )
    if value.get("growth_origin"):
        ref = value["growth_origin"]
        refs.append(reference_summary(db, owner, ref["kind"], ref["id"], ref["revision_id"]))
    if refs:
        result["references"] = refs
    return result


def material_view(db, owner, kind, object_id, revision_id):
    obj, rev = revision(db, owner, kind, object_id, revision_id)
    result = reference_summary(db, owner, kind, obj.id, rev.id)
    result["snapshot"] = None if obj.deleted_at else shallow_snapshot(db, owner, rev.snapshot)
    result["needs_review"] |= nested_review(db, owner, rev)
    return result


def evidence_view(db, owner, raw):
    data = evidence_dict(raw)
    kind, obj, rev = evidence_target(db, owner, data)
    source = material_view(db, owner, kind, obj.id, rev.id)
    _, drift, unavailable = dependency_state(db, owner, rev, data.get("reviewed_dependencies"))
    source["needs_review"] = (
        bool(obj.deleted_at) or obj.version != data["reviewed_version"] or drift
    )
    data.update(
        source=source,
        current_version=obj.version,
        availability="deleted" if obj.deleted_at or unavailable else "available",
        needs_review=bool(obj.deleted_at) or obj.version != data["reviewed_version"] or drift,
        content=None,
    )
    if obj.deleted_at:
        data["quote"] = ""
    elif kind == "record":
        data["content"] = evidence_content(
            db, rev, data.get("source_version_id"), data["field_path"]
        )
    return data


def tags_for(db, obj):
    if not isinstance(obj, GrowthEntry):
        return []
    return list(
        db.scalars(
            select(AbilityTag)
            .join(GrowthEntryTag, GrowthEntryTag.tag_id == AbilityTag.id)
            .where(GrowthEntryTag.entry_id == obj.id)
            .order_by(AbilityTag.name)
        )
    )


def freeze(db, obj, operation, extra=None):
    db.flush()
    snapshot = columns(obj)
    if not isinstance(obj, AbilityTag):
        snapshot["evidence"] = [evidence_dict(e) for e in evidence_rows(db, obj)]
        snapshot["tags"] = [{"id": t.id, "name": t.name} for t in tags_for(db, obj)]
    if extra:
        snapshot.update(extra)
    row = GrowthRevision(
        **{KEYS[type(obj)]: obj.id}, version=obj.version, operation=operation, snapshot=snapshot
    )
    db.add(row)
    db.flush()
    return row


def status_of(evidence):
    if not evidence:
        return "self_report"
    if any(e["availability"] == "deleted" for e in evidence):
        return "unavailable"
    if any(e["needs_review"] for e in evidence):
        return "needs_review"
    return "attached"


def review_versions(db, owner, evidence):
    versions = {e["id"]: e["current_version"] for e in evidence}
    for e in evidence:
        _, _, rev = evidence_target(db, owner, e)
        nested, _, _ = dependency_state(db, owner, rev)
        versions.update({e["id"] + ":" + key: value for key, value in nested.items()})
    return versions


def object_view(db, obj):
    value = columns(obj)
    value["kind"] = "contribution" if isinstance(obj, Contribution) else obj.kind
    evidence = [evidence_view(db, obj.owner_id, e) for e in evidence_rows(db, obj)]
    rev = latest_revision(db, obj)
    question = (
        owned(db, ResearchItem, obj.owner_id, obj.question_id, True) if obj.question_id else None
    )
    key = KEYS[type(obj)]
    links = db.execute(
        select(GrowthActionLink, Action)
        .join(Action, Action.id == GrowthActionLink.action_id)
        .join(GrowthRevision, GrowthRevision.id == GrowthActionLink.revision_id)
        .where(
            GrowthActionLink.owner_id == obj.owner_id,
            getattr(GrowthRevision, key) == obj.id,
            Action.deleted_at.is_(None),
        )
    )
    value.update(
        evidence=evidence,
        evidence_status=status_of(evidence),
        needs_review=any(e["needs_review"] for e in evidence),
        current_versions=review_versions(db, obj.owner_id, evidence),
        tags=[{"id": t.id, "name": t.name, "archived": t.archived} for t in tags_for(db, obj)],
        archived=archived(db, obj),
        question_title=("问题已删除" if question.deleted_at else question.title)
        if question
        else None,
        revision_id=rev.id,
        actions=[
            {"id": a.id, "title": a.title, "revision_id": link.revision_id} for link, a in links
        ],
    )
    return value


def history(db, owner, model, object_id):
    obj = owned(db, model, owner, object_id, True)
    rows = db.scalars(
        select(GrowthRevision)
        .where(getattr(GrowthRevision, KEYS[model]) == obj.id)
        .order_by(GrowthRevision.version.desc())
    )
    result = []
    for rev in rows:
        snap = shallow_snapshot(db, owner, rev.snapshot)
        if "evidence" in rev.snapshot:
            snap["evidence"] = [evidence_view(db, owner, e) for e in rev.snapshot["evidence"]]
        result.append(
            dict(
                id=rev.id,
                version=rev.version,
                operation=rev.operation,
                created_at=rev.created_at,
                snapshot=snap,
            )
        )
    return result
