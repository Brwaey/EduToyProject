from sqlalchemy import func, or_, select

from .m2_common import (
    REV_KEYS,
    columns,
    evidence_view,
    material_view,
    node_view,
    object_view,
    owned,
    redact_snapshot,
)
from .models import Project, Record, RecordRevision
from .models_m2 import (
    Action,
    ActionRecord,
    EvidenceReference,
    GraphLayout,
    GraphNode,
    GraphRelation,
    Reflection,
    ResearchItem,
    Revision,
)
from .security import Problem


def page_objects(
    db,
    owner,
    model,
    page=1,
    page_size=20,
    q="",
    project_id=None,
    unassigned=False,
    deleted=False,
    status=None,
    kind=None,
    priority=None,
    direction_id=None,
):
    clauses = [
        model.owner_id == owner,
        model.deleted_at.is_not(None) if deleted else model.deleted_at.is_(None),
    ]
    if q.strip():
        clauses.append(model.title.contains(q.strip(), autoescape=True))
    if project_id:
        owned(db, Project, owner, project_id)
        clauses.append(model.project_id == str(project_id))
    if unassigned:
        clauses.append(model.project_id.is_(None))
    if status:
        clauses.append(model.status == status)
    if kind:
        clauses.append(model.kind == kind)
    if priority:
        clauses.append(model.details["priority"].as_string() == priority)
    if direction_id:
        owned(db, ResearchItem, owner, direction_id, True)
        clauses.append(model.direction_id == str(direction_id))
    total = db.scalar(select(func.count()).select_from(model).where(*clauses))
    rows = db.scalars(
        select(model)
        .where(*clauses)
        .order_by(model.updated_at.desc(), model.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [object_view(db, r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


class GraphIndex:
    """A bounded number of SQL queries, including at 500 nodes / 1000 relations."""

    def __init__(self, db, owner, include_archived=False):
        self.db, self.owner = db, owner
        self.projects = {
            p.id: p for p in db.scalars(select(Project).where(Project.owner_id == owner))
        }
        self.records = {r.id: r for r in db.scalars(select(Record).where(Record.owner_id == owner))}
        self.items = {
            r.id: r for r in db.scalars(select(ResearchItem).where(ResearchItem.owner_id == owner))
        }
        self.registry = {
            n.id: n for n in db.scalars(select(GraphNode).where(GraphNode.owner_id == owner))
        }
        self.relations = list(
            db.scalars(
                select(GraphRelation)
                .where(GraphRelation.owner_id == owner, GraphRelation.deleted_at.is_(None))
                .order_by(GraphRelation.created_at, GraphRelation.id)
            )
        )
        self.nodes = {}
        self.objects = {}
        for node in self.registry.values():
            obj = (
                self.records.get(node.record_id) if node.record_id else self.items.get(node.item_id)
            )
            self.objects[node.id] = obj
            if obj.deleted_at:
                continue
            view = node_view(db, obj, node.id, self.projects)
            if view["archived"] and not include_archived:
                continue
            self.nodes[node.id] = view
        self.live = [
            r for r in self.relations if r.source_id in self.nodes and r.target_id in self.nodes
        ]
        connected = {n for r in self.live for n in (r.source_id, r.target_id)}
        self.nodes = {
            k: v for k, v in self.nodes.items() if v["kind"] != "record" or k in connected
        }
        self.evidence = {}
        for e in db.scalars(
            select(EvidenceReference)
            .join(GraphRelation, EvidenceReference.relation_id == GraphRelation.id)
            .where(GraphRelation.owner_id == owner, GraphRelation.deleted_at.is_(None))
        ):
            self.evidence.setdefault(e.relation_id, []).append(e)

    def edge(self, r):
        a, b = self.nodes[r.source_id], self.nodes[r.target_id]
        evidence = [evidence_view(self.db, self.owner, e) for e in self.evidence.get(r.id, [])]
        return {
            **columns(r),
            "source": a,
            "target": b,
            "evidence": evidence,
            "archived": a["archived"] or b["archived"],
            "available": True,
            "needs_review": a["version"] != r.source_version
            or b["version"] != r.target_version
            or any(e["needs_review"] for e in evidence),
        }


def graph(
    db,
    owner,
    scope="all",
    project_id=None,
    q="",
    kind=None,
    status=None,
    needs_review=False,
    focus_node_id=None,
    depth=1,
    include_archived=False,
    limit=150,
):
    scope_key(db, owner, scope, project_id)
    index = GraphIndex(db, owner, include_archived)
    all_edges = {r.id: index.edge(r) for r in index.live}
    selected = {
        k
        for k, v in index.nodes.items()
        if (
            scope == "all"
            or (scope == "unassigned" and v["project_id"] is None)
            or (scope == "project" and v["project_id"] == str(project_id))
        )
    }
    local = set(selected)
    if scope == "project":
        selected.update(
            n
            for r in index.live
            if r.source_id in local or r.target_id in local
            for n in (r.source_id, r.target_id)
        )
    if focus_node_id:
        owned(db, GraphNode, owner, focus_node_id)
        focus = str(focus_node_id)
        selected = {focus} if focus in index.nodes else set()
        for _ in range(depth):
            selected |= {
                n
                for r in index.live
                if r.source_id in selected or r.target_id in selected
                for n in (r.source_id, r.target_id)
            }
    if q.strip():
        selected = {
            k for k in selected if q.strip().casefold() in index.nodes[k]["title"].casefold()
        }
    if kind:
        selected = {k for k in selected if index.nodes[k]["kind"] == kind}
    if status:
        selected = {k for k in selected if index.nodes[k]["status"] == status}
    if needs_review:
        selected &= {
            n
            for e in all_edges.values()
            if e["needs_review"]
            for n in (e["source_id"], e["target_id"])
        }
    ordered = sorted(
        selected,
        key=lambda k: (
            k != str(focus_node_id),
            k not in local,
            index.nodes[k]["kind"],
            index.nodes[k]["title"],
            k,
        ),
    )
    visible = set(ordered[:limit])
    nodes = [
        {
            **index.nodes[k],
            "external": scope == "project" and index.nodes[k]["project_id"] != str(project_id),
        }
        for k in ordered[:limit]
    ]
    return {
        "nodes": nodes,
        "edges": [
            e for e in all_edges.values() if e["source_id"] in visible and e["target_id"] in visible
        ],
        "total_nodes": len(selected),
        "truncated": len(selected) > limit,
    }


def candidates(
    db,
    owner,
    q="",
    kind=None,
    project_id=None,
    unassigned=False,
    unlinked=False,
    include_archived=False,
    page=1,
    page_size=20,
):
    if project_id:
        owned(db, Project, owner, project_id)
    index = GraphIndex(db, owner, include_archived)
    node_ids = {
        ("record", n.record_id) if n.record_id else ("research_item", n.item_id): n.id
        for n in index.registry.values()
    }
    values = []
    for obj in list(index.records.values()) + list(index.items.values()):
        if obj.deleted_at:
            continue
        ref_kind = "record" if isinstance(obj, Record) else "research_item"
        nid = node_ids.get((ref_kind, obj.id), ref_kind + ":" + obj.id)
        view = node_view(db, obj, nid, index.projects)
        if not include_archived and view["archived"]:
            continue
        if kind and view["kind"] != kind:
            continue
        if project_id and obj.project_id != str(project_id):
            continue
        if unassigned and obj.project_id is not None:
            continue
        if unlinked and (ref_kind != "record" or nid in index.nodes):
            continue
        if q.strip() and q.strip().casefold() not in obj.title.casefold():
            continue
        values.append(view)
    values.sort(key=lambda v: (v["kind"], v["title"], v["id"]))
    return {
        "items": values[(page - 1) * page_size : page * page_size],
        "total": len(values),
        "page": page,
        "page_size": page_size,
    }


def scope_key(db, owner, scope, project_id=None):
    if scope == "project":
        if not project_id:
            raise Problem(422, "project_required", "请选择项目")
        owned(db, Project, owner, project_id)
        return "project:" + str(project_id)
    if project_id:
        raise Problem(422, "invalid_scope", "该视图不需要指定项目")
    return scope


def layout_get(db, owner, scope, project_id=None):
    key = scope_key(db, owner, scope, project_id)
    layout = db.scalar(
        select(GraphLayout).where(GraphLayout.owner_id == owner, GraphLayout.scope_key == key)
    )
    return (
        {"version": layout.version, "positions": layout.positions}
        if layout
        else {"version": 0, "positions": {}}
    )


def materials(db, owner, start_at, end_at, project_id=None, q="", page=1, page_size=20):
    if start_at >= end_at:
        raise Problem(422, "invalid_range", "结束时间必须晚于开始时间")
    if project_id:
        owned(db, Project, owner, project_id)
    result = []
    for kind, model, revmodel in [
        ("record", Record, RecordRevision),
        ("action", Action, Revision),
        ("research_item", ResearchItem, Revision),
    ]:
        key = "record_id" if kind == "record" else REV_KEYS[model]
        query = (
            select(revmodel, model)
            .join(model, getattr(revmodel, key) == model.id)
            .where(
                model.owner_id == owner,
                model.deleted_at.is_(None),
                revmodel.created_at >= start_at,
                revmodel.created_at < end_at,
            )
        )
        if project_id:
            query = query.where(model.project_id == str(project_id))
        if q.strip():
            query = query.where(model.title.contains(q.strip(), autoescape=True))
        latest = {}
        for rev, obj in db.execute(query):
            if obj.id not in latest or rev.version > latest[obj.id][0].version:
                latest[obj.id] = (rev, obj)
        for rev, obj in latest.values():
            result.append(
                (
                    rev.created_at,
                    material_view(db, owner, {"kind": kind, "id": obj.id, "revision_id": rev.id}),
                )
            )
    from .growth_queries import period_materials

    result.extend(period_materials(db, owner, start_at, end_at, project_id, q))
    result.sort(key=lambda v: (v[0], v[1]["id"]), reverse=True)
    return {
        "items": [v[1] for v in result[(page - 1) * page_size : page * page_size]],
        "total": len(result),
        "page": page,
        "page_size": page_size,
    }


def history(db, owner, model, object_id):
    obj = owned(db, model, owner, object_id, True)
    rows = db.scalars(
        select(Revision)
        .where(getattr(Revision, REV_KEYS[model]) == obj.id)
        .order_by(Revision.version.desc())
    )
    return [{**columns(r), "snapshot": redact_snapshot(db, owner, r.snapshot)} for r in rows]


def record_context(db, owner, record_id):
    owned(db, Record, owner, record_id)
    node = db.scalar(
        select(GraphNode).where(GraphNode.record_id == str(record_id), GraphNode.owner_id == owner)
    )
    relations = (
        list(
            db.scalars(
                select(GraphRelation).where(
                    GraphRelation.owner_id == owner,
                    GraphRelation.deleted_at.is_(None),
                    or_(GraphRelation.source_id == node.id, GraphRelation.target_id == node.id),
                )
            )
        )
        if node
        else []
    )
    actions = db.scalars(
        select(Action)
        .join(ActionRecord, ActionRecord.action_id == Action.id)
        .where(
            ActionRecord.record_id == str(record_id),
            Action.owner_id == owner,
            Action.deleted_at.is_(None),
        )
    )
    reflections = [
        r
        for r in db.scalars(
            select(Reflection).where(Reflection.owner_id == owner, Reflection.deleted_at.is_(None))
        )
        if any(m["kind"] == "record" and m["id"] == str(record_id) for m in r.materials)
    ]
    return {
        "relations": [object_view(db, r) for r in relations],
        "actions": [object_view(db, a) for a in actions],
        "reflections": [object_view(db, r) for r in reflections],
    }
