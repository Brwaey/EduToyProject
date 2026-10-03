"""Read-only, bounded business projection. Never serialize ORM rows or raw snapshots."""

import hashlib
import html
import json
import re
from collections import Counter, deque
from urllib.parse import urlparse

from sqlalchemy import select

from .ai_materials import row_objects
from .db import now
from .growth_data import latest_revision, revision
from .m2_common import node_object, owned
from .models import Project, Record, RecordRevision, Source, SourceVersion
from .models_ai import AIAdoption, AIAdoptionCitation, AISuggestion, AITaskInput
from .models_growth import AbilityTag, Contribution, GrowthEntry, GrowthRevision
from .models_m2 import Action, GraphNode, GraphRelation, Reflection, ResearchItem, Revision
from .schemas_growth import AbilityDetails, ContributionDetails, UnderstandingDetails
from .schemas_m2 import (
    ActionDetails,
    DirectionDetails,
    FindingDetails,
    QuestionDetails,
    ReflectionDetails,
)
from .security import Problem

MODELS = dict(
    project=Project,
    record=Record,
    research_item=ResearchItem,
    relation=GraphRelation,
    action=Action,
    reflection=Reflection,
    contribution=Contribution,
    growth_entry=GrowthEntry,
    ability_tag=AbilityTag,
)
DETAILS = set().union(
    *(
        s.model_fields
        for s in (
            AbilityDetails,
            ContributionDetails,
            UnderstandingDetails,
            ActionDetails,
            DirectionDetails,
            FindingDetails,
            QuestionDetails,
            ReflectionDetails,
        )
    )
)
FIELDS = {
    "project": "name description archived",
    "record": "title body record_type work_status outcome_status",
    "research_item": "title kind description status",
    "relation": "relation_type reason source_version target_version",
    "action": "title status result_summary completed_at",
    "reflection": "title kind start_at end_at timezone",
    "contribution": "title contribution_type occurred_on confirmed_at",
    "growth_entry": "title kind occurred_on",
    "ability_tag": "name description archived",
}
RECORD_FIELDS = "context actions collaboration observations interpretation next_steps".split()
MAX_ENTRIES, MAX_BYTES = 5000, 20 * 1024 * 1024


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def selection_data(value):
    data = value.model_dump(mode="json", exclude={"fingerprint"})
    data["types"] = sorted(
        set(data["types"] or (["record", "reflection"] if data["format"] == "markdown" else MODELS))
    )
    data["project_ids"] = sorted(set(data["project_ids"]))
    data["objects"] = sorted(
        {canonical(r): r for r in data["objects"]}.values(), key=lambda r: (r["kind"], r["id"])
    )
    return data


def project_archived(db, obj):
    if isinstance(obj, (Project, AbilityTag)):
        return obj.archived
    p = db.get(Project, obj.project_id) if getattr(obj, "project_id", None) else None
    return bool(p and p.archived)


def visible(db, owner, obj, include_archived):
    if getattr(obj, "deleted_at", None):
        return False
    if isinstance(obj, GraphRelation):
        return all(
            visible(db, owner, node_object(db, owner, key, True), include_archived)
            for key in (obj.source_id, obj.target_id)
        )
    return include_archived or not project_archived(db, obj)


def roots(db, owner, s):
    for key in s["project_ids"]:
        owned(db, Project, owner, key)
    if s["scope"] == "selected":
        values = [
            (r["kind"], owned(db, MODELS[r["kind"]], owner, r["id"], True)) for r in s["objects"]
        ]
        return [(k, o) for k, o in values if visible(db, owner, o, s["include_archived"])]
    result = []
    for kind in s["types"]:
        for obj in db.scalars(
            select(MODELS[kind]).where(MODELS[kind].owner_id == owner).order_by(MODELS[kind].id)
        ):
            if not visible(db, owner, obj, s["include_archived"]):
                continue
            projects = {obj.id if kind == "project" else getattr(obj, "project_id", None)}
            if kind == "relation":
                projects = {
                    node_object(db, owner, key, True).project_id
                    for key in (obj.source_id, obj.target_id)
                }
            if s["scope"] == "projects" and not projects.intersection(s["project_ids"]):
                continue
            if s["scope"] == "unassigned" and (
                kind in ("project", "ability_tag") or None not in projects
            ):
                continue
            result.append((kind, obj))
            if len(result) > MAX_ENTRIES:
                raise Problem(413, "export_too_large", "对象超过 5,000 项，请缩小导出范围")
    return result


class Projection:
    def __init__(self, db, owner, s):
        self.db, self.owner, self.selection = db, owner, s
        self.objects, self.fixed, self.sources, self.links, self.nodes = {}, {}, {}, {}, {}
        self.pending = deque()
        self.cross, self.archived, self.unavailable = {}, {}, {}
        self.root_projects = set()
        self.root_keys = set()
        self.approx_bytes = 0

    def budget(self, value=None):
        size = sum(map(len, (self.objects, self.fixed, self.sources, self.links, self.nodes)))
        if value is not None:
            self.approx_bytes += len(canonical(value).encode())
        if size > MAX_ENTRIES or self.approx_bytes > MAX_BYTES:
            raise Problem(413, "export_too_large", "导出超过 5,000 项或 20 MiB，请缩小范围")

    def link(self, kind, key):
        if not key:
            return None
        obj = owned(self.db, MODELS[kind], self.owner, key, True)
        ref = {"kind": kind, "id": obj.id}
        identity = kind + ":" + obj.id
        if identity in self.root_keys:
            return ref
        if identity not in self.links:
            deleted = bool(getattr(obj, "deleted_at", None))
            self.links[identity] = dict(
                ref,
                title="来源已删除"
                if deleted
                else getattr(obj, "title", getattr(obj, "name", "关系")),
                project_id=getattr(obj, "project_id", None),
                deleted=deleted,
                updated_at=getattr(obj, "updated_at", None),
            )
            if kind == "ability_tag":
                self.links[identity].update(description=obj.description, archived=obj.archived)
            if deleted:
                self.unavailable[identity] = {"kind": kind, "id": obj.id, "title": "来源已删除"}
            if project_archived(self.db, obj):
                self.archived[identity] = {
                    "kind": kind,
                    "id": obj.id,
                    "title": self.links[identity]["title"],
                }
            self.budget(self.links[identity])
        return ref

    def fixed_ref(self, kind, key, revision_id):
        obj, rev = revision(self.db, self.owner, kind, key, revision_id)
        ref = dict(kind=kind, id=obj.id, revision_id=rev.id)
        if rev.id not in self.fixed:
            # Reserve before traversing: historical reflection/growth cycles are finite.
            self.fixed[rev.id] = None
            self.pending.append((kind, obj, rev))
            self.budget()
        return ref

    def evidence(self, e):
        if e.get("record_revision_id"):
            r = self.db.get(RecordRevision, e["record_revision_id"])
            kind, key = "record", r.record_id if r else None
        elif e.get("m2_revision_id"):
            r = self.db.get(Revision, e["m2_revision_id"])
            kind = "action" if r and r.action_id else "reflection"
            key = (r.action_id or r.reflection_id) if r else None
        else:
            r = self.db.get(GrowthRevision, e.get("contribution_revision_id"))
            kind, key = "contribution", r.contribution_id if r else None
        if not r or not key:
            raise Problem(409, "export_reference_invalid", "材料引用不完整，请检查来源")
        ref = self.fixed_ref(kind, key, r.id)
        obj = owned(self.db, MODELS[kind], self.owner, key, True)
        data = {k: e[k] for k in ("field_path", "start", "end", "purpose", "stance") if k in e}
        data.update(
            ref=ref,
            quote="" if obj.deleted_at else e.get("quote", ""),
            unavailable=bool(obj.deleted_at),
        )
        data["reviewed_version"] = e.get(
            "reviewed_version", e.get("reviewed_record_version", r.version)
        )
        data["needs_review"] = bool(obj.deleted_at) or obj.version != data["reviewed_version"]
        if e.get("source_version_id"):
            data["source_version_id"] = e["source_version_id"]
            if e["source_version_id"] not in r.snapshot.get("source_version_ids", []):
                raise Problem(409, "export_reference_invalid", "来源不属于引用的记录版本")
        return data

    def source(self, obj, source_id):
        if source_id in self.sources:
            return source_id
        v = self.db.get(SourceVersion, source_id)
        source = self.db.get(Source, v.source_id) if v else None
        if not source or source.record_id != obj.id:
            raise Problem(409, "export_reference_invalid", "来源版本与记录不匹配")
        self.sources[source_id] = dict(
            id=v.id,
            source_id=source.id,
            record_id=obj.id,
            kind=source.kind,
            name=source.name,
            version=v.version,
            content=v.content,
            created_at=v.created_at,
        )
        self.budget(self.sources[source_id])
        return source_id

    def node(self, key):
        node = owned(self.db, GraphNode, self.owner, key)
        kind = "record" if node.record_id else "research_item"
        ref = self.link(kind, node.record_id or node.item_id)
        if key not in self.nodes:
            self.nodes[key] = dict(id=key, object=ref)
            self.budget(self.nodes[key])
        return key

    def adoptions(self, kind, obj, rev, current):
        values = []
        if kind in ("action", "reflection"):
            q = select(AIAdoption).where(AIAdoption.owner_id == self.owner)
            if current:
                q = q.join(Revision, Revision.id == AIAdoption.revision_id).where(
                    getattr(Revision, kind + "_id") == obj.id
                )
            else:
                q = q.where(AIAdoption.revision_id == rev.id)
            for a in self.db.scalars(q.order_by(AIAdoption.created_at, AIAdoption.id)):
                if current and a.revision_id != rev.id:
                    self.fixed_ref(kind, obj.id, a.revision_id)
                cited = []
                for c in self.db.scalars(
                    select(AIAdoptionCitation)
                    .where(AIAdoptionCitation.adoption_id == a.id)
                    .order_by(AIAdoptionCitation.id)
                ):
                    row = self.db.get(AITaskInput, c.input_id)
                    k, source, r = row_objects(self.db, self.owner, row)
                    cited.append(
                        dict(
                            field=c.field,
                            ref=self.fixed_ref(k, source.id, r.id),
                            source_version_id=row.source_version_id,
                            field_path=row.field_path,
                            start=c.start,
                            end=c.end,
                            quote=None if source.deleted_at else c.quote,
                            unavailable=bool(source.deleted_at),
                            reviewed_version=a.review_info.get("current_versions", {}).get(
                                row.object_key, r.version
                            ),
                            needs_review=bool(source.deleted_at)
                            or source.version
                            != a.review_info.get("current_versions", {}).get(
                                row.object_key, r.version
                            ),
                        )
                    )
                # The final content was schema-validated at adoption; still whitelist here.
                if kind == "action":
                    final = {
                        k: a.final_content.get(k)
                        for k in (
                            "title",
                            "project_id",
                            "direction_id",
                            "origin_reflection_id",
                            "proposal_reason",
                            "proposal_uncertainty",
                        )
                    }
                    final["details"] = {
                        k: v
                        for k, v in a.final_content.get("details", {}).items()
                        if k in ActionDetails.model_fields
                    }
                else:
                    final = {
                        k: {f: v.get(f) for f in ("mode", "text", "final_text")}
                        for k, v in a.final_content.items()
                        if k in ("progress", "understanding", "blockers", "next_steps")
                    }
                values.append(
                    dict(
                        id=a.id,
                        business_revision_id=a.revision_id,
                        created_at=a.created_at,
                        final_content=final,
                        user_modified=a.review_info.get("user_modified", False),
                        citations=cited,
                    )
                )
        if kind == "record":
            # Legacy M3 adoption has record-only references in the selected fields.
            q = select(AISuggestion).where(
                AISuggestion.owner_id == self.owner,
                AISuggestion.record_id == obj.id,
                AISuggestion.status.in_(["accepted", "edited_accepted"]),
            )
            if not current:
                q = q.where(AISuggestion.record_revision_id == rev.id)
            for s in self.db.scalars(q.order_by(AISuggestion.created_at, AISuggestion.id)):
                if current and s.record_revision_id != rev.id:
                    self.fixed_ref(kind, obj.id, s.record_revision_id)
                used = s.accepted.get("fields", s.accepted) if s.accepted else {}
                cited = []
                for field in used:
                    for e in s.accepted.get("evidence_by_field", {}).get(field, []):
                        cited.append(dict(field=field, **self.evidence(e)))
                values.append(
                    dict(
                        business_revision_id=s.record_revision_id,
                        created_at=s.decided_at,
                        fields=[f for f in used if f in ["title", "record_type", *RECORD_FIELDS]],
                        user_modified=s.status == "edited_accepted",
                        citations=cited,
                    )
                )
        return values

    def view(self, kind, obj, rev=None, current=False):
        snap = (
            rev.snapshot
            if rev
            else {
                k: getattr(obj, k, None)
                for k in ("id", "created_at", "updated_at", *FIELDS[kind].split())
            }
        )
        deleted = bool(getattr(obj, "deleted_at", None))
        base = dict(
            kind=kind,
            id=obj.id,
            revision_id=rev.id if rev else None,
            version=rev.version if rev else None,
            current_version=getattr(obj, "version", None),
            archived=project_archived(self.db, obj),
            unavailable=deleted,
        )
        if deleted:
            base["title"] = "来源已删除"
            self.unavailable[kind + ":" + obj.id] = base
            return base
        base.update({k: snap.get(k) for k in (*FIELDS[kind].split(), "created_at", "updated_at")})
        if "kind" in FIELDS[kind].split():
            base["subtype"] = snap.get("kind")
            base["kind"] = kind
        if kind == "contribution" and snap.get("ai_suggestion_id"):
            base["ai_assistance"] = {
                "adopted": True,
                "user_supplement_fields": [
                    k
                    for k in snap.get("user_supplement_fields", [])
                    if k in ("title", "personal_role", "reason", "ai_help", "others_help", "impact")
                ],
            }
        base["project_id"] = snap.get("project_id")
        base["needs_review"] = bool(rev and obj.version != rev.version)
        if project_archived(self.db, obj):
            self.archived[kind + ":" + obj.id] = {
                "kind": kind,
                "id": obj.id,
                "title": base.get("title", base.get("name")),
            }
        if not current and snap.get("project_id") not in self.root_projects:
            self.cross[rev.id] = {
                "kind": kind,
                "id": obj.id,
                "revision_id": rev.id,
                "title": base.get("title"),
                "project_id": snap.get("project_id"),
            }
        if "details" in snap:
            base["details"] = {
                k: v
                for k, v in snap["details"].items()
                if k in DETAILS and isinstance(v, (str, type(None)))
            }
        if kind == "record":
            base["fields"] = {k: snap.get("fields", {}).get(k, "") for k in RECORD_FIELDS}
            base["source_version_ids"] = [
                self.source(obj, key) for key in snap.get("source_version_ids", [])
            ]
        base["links"] = {
            k: self.link(target, snap.get(k))
            for k, target in (
                ("project_id", "project"),
                ("question_id", "research_item"),
                ("direction_id", "research_item"),
                ("origin_reflection_id", "reflection"),
            )
            if snap.get(k)
        }
        if kind == "relation":
            base["source_id"], base["target_id"] = (
                self.node(snap["source_id"]),
                self.node(snap["target_id"]),
            )
        if "tags" in snap:
            base["tags"] = [
                {"id": t["id"], "name": t["name"]}
                for t in snap["tags"]
                if self.link("ability_tag", t["id"])
            ]
        base["evidence"] = [self.evidence(e) for e in snap.get("evidence", [])]
        base["materials"] = [
            self.fixed_ref(r["kind"], r["id"], r["revision_id"]) for r in snap.get("materials", [])
        ]
        base["results"] = [
            self.fixed_ref("record", r["record_id"], r["record_revision_id"])
            for r in snap.get("results", [])
        ]
        if snap.get("growth_origin"):
            r = snap["growth_origin"]
            base["growth_origin"] = self.fixed_ref(r["kind"], r["id"], r["revision_id"])
        adopted = self.adoptions(kind, obj, rev, current)
        if adopted:
            base["ai_adoptions"] = adopted
        return base

    def run(self):
        selected = roots(self.db, self.owner, self.selection)
        if not selected:
            raise Problem(422, "export_empty", "当前范围没有可导出的内容")
        self.root_projects = {
            o.id if k == "project" else getattr(o, "project_id", None) for k, o in selected
        }
        self.root_keys = {k + ":" + o.id for k, o in selected}
        for kind, obj in selected:
            if kind == "project":
                rev = None
            elif kind == "relation":
                rev = self.db.scalar(
                    select(Revision).where(
                        Revision.relation_id == obj.id, Revision.version == obj.version
                    )
                )
            else:
                rev = latest_revision(self.db, obj)
            value = self.view(kind, obj, rev, True)
            self.objects[kind + ":" + obj.id] = value
            self.budget(value)
            if kind == "research_item":
                node = self.db.scalar(
                    select(GraphNode).where(
                        GraphNode.owner_id == self.owner, GraphNode.item_id == obj.id
                    )
                )
                if node:
                    self.node(node.id)
        while self.pending:
            kind, obj, rev = self.pending.popleft()
            value = self.view(kind, obj, rev)
            self.fixed[rev.id] = value
            self.budget(value)
        # Tags attached to in-scope growth remain ordinary references with name/description.
        links = [v for k, v in sorted(self.links.items()) if k not in self.objects]
        return dict(
            format_version="yanji.business.v1",
            selection=self.selection,
            objects=[v for _, v in sorted(self.objects.items())],
            fixed_versions=[v for _, v in sorted(self.fixed.items())],
            source_versions=[v for _, v in sorted(self.sources.items())],
            graph_nodes=[v for _, v in sorted(self.nodes.items())],
            links=links,
        )


def literal(value):
    """User prose remains literal text in readers: no raw HTML/images/active Markdown."""
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", html.escape(str(value or "")))


def markdown(data):
    lines = [
        "# 研迹研究材料",
        "",
        "以下依据保留引用时的版本；用户文字并不代表系统验证。",
        "",
        "## 目录",
        "",
    ]
    for o in data["objects"]:
        lines.append(f"- [{literal(o.get('title', o['kind']))}](#obj-{o['id']})")

    def section(o, anchor):
        lines.extend(
            [
                "",
                f'<a id="{anchor}"></a>',
                f"## {literal(o.get('title', o['kind']))}",
                "",
                f"类型：{o['kind']} · 版本：{o.get('version')}",
            ]
        )
        if o["unavailable"]:
            lines.extend(["", "来源已删除，正文不可用。"])
            return
        for key in (
            "body",
            "record_type",
            "work_status",
            "outcome_status",
            "status",
            "created_at",
            "updated_at",
            "start_at",
            "end_at",
            "timezone",
            "occurred_on",
            "result_summary",
        ):
            if o.get(key):
                lines.extend(["", f"**{key}**", "", literal(o[key])])
        for key, text in {**o.get("fields", {}), **o.get("details", {})}.items():
            if text:
                lines.extend(["", f"**{literal(key)}**", "", literal(text)])
        refs = [
            *o.get("materials", []),
            *o.get("results", []),
            *(e["ref"] for e in o.get("evidence", [])),
        ]
        for a in o.get("ai_adoptions", []):
            lines.extend(["", "AI 采纳说明：仅说明采纳时的修改与依据，不证明后续编辑。"])
            for c in a["citations"]:
                refs.append(c["ref"])
                if c.get("quote"):
                    lines.extend(["", literal(c["quote"])])
        for r in refs:
            lines.extend(["", f"[固定依据 {r['revision_id']}](#rev-{r['revision_id']})"])
        for source_id in o.get("source_version_ids", []):
            lines.extend(["", f"[原始材料](#src-{source_id})"])

    for o in data["objects"]:
        section(o, "obj-" + o["id"])
    lines.extend(["", "# 固定依据附录"])
    for o in data["fixed_versions"]:
        section(o, "rev-" + o["revision_id"])
    for s in data["source_versions"]:
        lines.extend(
            ["", f'<a id="src-{s["id"]}"></a>', f"## {literal(s['name'])} · v{s['version']}", ""]
        )
        if s["kind"] == "link" and urlparse(s["content"]).scheme.lower() in ("http", "https"):
            from urllib.parse import quote

            url = quote(s["content"], safe=":/?=&%#@+;,")
            lines.append(f"[外部引用]({url})")
        else:
            lines.append(literal(s["content"]))
    return "\n".join(lines) + "\n"


def build(db, owner, value):
    s = selection_data(value)
    p = Projection(db, owner, s)
    data = p.run()
    fingerprint = hashlib.sha256(canonical(dict(owner=owner, data=data)).encode()).hexdigest()
    data["exported_at"] = now()
    content = (
        markdown(data)
        if s["format"] == "markdown"
        else json.dumps(data, ensure_ascii=False, indent=2)
    ).encode("utf-8")
    if len(content) > MAX_BYTES:
        raise Problem(413, "export_too_large", "文件超过 20 MiB，请缩小范围")
    filename = "yanji-export." + ("md" if s["format"] == "markdown" else "json")
    preview = dict(
        fingerprint=fingerprint,
        counts=dict(Counter(o["kind"] for o in data["objects"])),
        fixed_versions=len(data["fixed_versions"]) + len(data["source_versions"]),
        entries=sum(
            len(data[k])
            for k in ("objects", "fixed_versions", "source_versions", "links", "graph_nodes")
        ),
        bytes=len(content),
        cross_project_evidence=list(p.cross.values()),
        archived_content=list(p.archived.values()),
        unavailable=list(p.unavailable.values()),
        selection=s,
        filename=filename,
    )
    return preview, content


def candidates(db, owner, kind, q, include_archived, page, size):
    if kind not in MODELS:
        raise Problem(422, "invalid_type", "不支持的导出类型")
    values = []
    for o in db.scalars(
        select(MODELS[kind]).where(MODELS[kind].owner_id == owner).order_by(MODELS[kind].id)
    ):
        title = getattr(o, "title", getattr(o, "name", getattr(o, "reason", "关系")))
        if visible(db, owner, o, include_archived) and q.casefold() in title.casefold():
            values.append(
                dict(kind=kind, id=o.id, title=title, project_id=getattr(o, "project_id", None))
            )
    return dict(
        items=values[(page - 1) * size : page * size], total=len(values), page=page, page_size=size
    )
