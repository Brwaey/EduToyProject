from sqlalchemy import Text, select

from . import growth_data as data
from .m2_common import columns, owned
from .models import Project
from .models_growth import AbilityTag, Contribution, GrowthEntry, GrowthEntryTag, GrowthRevision
from .security import Problem


def filtered(
    db,
    owner,
    model,
    q="",
    project_id=None,
    unassigned=False,
    deleted=False,
    include_archived=False,
    date_from=None,
    date_to=None,
    kind=None,
    contribution_type=None,
    tag_id=None,
    evidence_status=None,
):
    if project_id and unassigned:
        raise Problem(422, "invalid_scope", "项目与未归类不能同时选择")
    if date_from and date_to and date_from > date_to:
        raise Problem(422, "invalid_range", "结束日期不能早于开始日期")
    if project_id:
        owned(db, Project, owner, project_id)
    conditions = [
        model.owner_id == owner,
        model.deleted_at.is_not(None) if deleted else model.deleted_at.is_(None),
    ]
    if not include_archived:
        conditions.append(
            ~model.project_id.in_(select(Project.id).where(Project.archived.is_(True)))
            | model.project_id.is_(None)
        )
    if project_id:
        conditions.append(model.project_id == str(project_id))
    if unassigned:
        conditions.append(model.project_id.is_(None))
    if q.strip():
        conditions.append(
            model.title.contains(q.strip(), autoescape=True)
            | model.details.cast(Text).contains(q.strip(), autoescape=True)
        )
    if date_from:
        conditions.append(model.occurred_on >= str(date_from))
    if date_to:
        conditions.append(model.occurred_on <= str(date_to))
    if kind and model is GrowthEntry:
        conditions.append(model.kind == kind)
    if contribution_type and model is Contribution:
        conditions.append(model.contribution_type == contribution_type)
    if tag_id:
        owned(db, AbilityTag, owner, tag_id)
        if model is GrowthEntry:
            conditions.append(
                model.id.in_(
                    select(GrowthEntryTag.entry_id).where(GrowthEntryTag.tag_id == str(tag_id))
                )
            )
    rows = list(
        db.scalars(
            select(model)
            .where(*conditions)
            .order_by(model.occurred_on.desc(), model.created_at.desc(), model.id.desc())
        )
    )
    if evidence_status:
        rows = [
            r
            for r in rows
            if data.status_of([data.evidence_view(db, owner, e) for e in data.evidence_rows(db, r)])
            == evidence_status
        ]
    return rows


def page(db, owner, model, page=1, page_size=20, **filters):
    rows = filtered(db, owner, model, **filters)
    return dict(
        items=[data.object_view(db, r) for r in rows[(page - 1) * page_size : page * page_size]],
        total=len(rows),
        page=page,
        page_size=page_size,
    )


def tag_list(db, owner, show_archived_tags=False, **filters):
    entries = filtered(db, owner, GrowthEntry, kind="ability_instance", **filters)
    by_id = {e.id: e for e in entries}
    usage = {}
    for link in db.scalars(
        select(GrowthEntryTag)
        .join(GrowthEntry, GrowthEntryTag.entry_id == GrowthEntry.id)
        .where(GrowthEntry.owner_id == owner)
    ):
        if link.entry_id in by_id:
            usage.setdefault(link.tag_id, set()).add(link.entry_id)
    rows = db.scalars(
        select(AbilityTag).where(AbilityTag.owner_id == owner).order_by(AbilityTag.name)
    )
    result = []
    for tag in rows:
        if tag.archived and not show_archived_tags:
            continue
        ids = usage.get(tag.id, set())
        latest = next((e for e in entries if e.id in ids), None)
        result.append(
            {k: v for k, v in columns(tag).items() if k != "deleted_at"}
            | {
                "instance_count": len(ids),
                "latest_instance": {
                    "id": latest.id,
                    "title": latest.title,
                    "occurred_on": latest.occurred_on,
                }
                if latest
                else None,
            }
        )
    return result


def materials(db, owner, q="", project_id=None, kind=None, page=1, page_size=20):
    if project_id:
        owned(db, Project, owner, project_id)
    rows = []
    for candidate in ("record", "action", "reflection", "contribution"):
        if kind and kind != candidate:
            continue
        model = data.MODELS[candidate]
        stmt = select(model).where(model.owner_id == owner, model.deleted_at.is_(None))
        if project_id:
            stmt = stmt.where(model.project_id == str(project_id))
        if q.strip():
            stmt = stmt.where(model.title.contains(q.strip(), autoescape=True))
        for obj in db.scalars(stmt):
            if not data.archived(db, obj):
                rows.append((obj.updated_at, candidate, obj, data.latest_revision(db, obj)))
    rows.sort(key=lambda r: (r[0], r[2].id), reverse=True)
    return dict(
        items=[
            data.material_view(db, owner, k, o.id, r.id)
            for _, k, o, r in rows[(page - 1) * page_size : page * page_size]
        ],
        total=len(rows),
        page=page,
        page_size=page_size,
    )


def period_materials(db, owner, start_at, end_at, project_id=None, q=""):
    result = []
    for kind, model in (("contribution", Contribution), ("growth_entry", GrowthEntry)):
        stmt = (
            select(GrowthRevision, model)
            .join(model, getattr(GrowthRevision, data.KEYS[model]) == model.id)
            .where(
                model.owner_id == owner,
                model.deleted_at.is_(None),
                GrowthRevision.created_at >= start_at,
                GrowthRevision.created_at < end_at,
            )
        )
        if project_id:
            stmt = stmt.where(model.project_id == str(project_id))
        if q.strip():
            stmt = stmt.where(model.title.contains(q.strip(), autoescape=True))
        latest = {}
        for rev, obj in db.execute(stmt):
            if not data.archived(db, obj) and (
                obj.id not in latest or rev.version > latest[obj.id][0].version
            ):
                latest[obj.id] = (rev, obj)
        result.extend(
            (rev.created_at, data.material_view(db, owner, kind, obj.id, rev.id))
            for rev, obj in latest.values()
        )
    return result


def context(db, owner, kind, object_id):
    target = owned(db, data.MODELS[kind], owner, object_id, True)
    result = {"contributions": [], "entries": []}
    for key, model in (("contributions", Contribution), ("entries", GrowthEntry)):
        for obj in filtered(db, owner, model, include_archived=True):
            match = kind == "research_item" and obj.question_id == target.id
            for e in data.evidence_rows(db, obj):
                k, source, _ = data.evidence_target(db, owner, data.evidence_dict(e))
                match |= k == kind and source.id == target.id
            if match:
                result[key].append(data.object_view(db, obj))
    return result
