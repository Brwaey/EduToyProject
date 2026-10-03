"""M2 business objects; graph nodes are references, never copies of record content."""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, new_id, now


class OwnedVersioned:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
    deleted_at: Mapped[str | None] = mapped_column(String(40), default=None)


class ResearchItem(OwnedVersioned, Base):
    __tablename__ = "research_items"
    __table_args__ = (
        CheckConstraint("kind IN ('question','finding','direction')", name="ck_item_kind"),
    )
    kind: Mapped[str] = mapped_column(String(20))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (
        CheckConstraint("(record_id IS NOT NULL) != (item_id IS NOT NULL)", name="ck_node_target"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    record_id: Mapped[str | None] = mapped_column(ForeignKey("records.id"), unique=True)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("research_items.id"), unique=True)


class GraphRelation(OwnedVersioned, Base):
    __tablename__ = "graph_relations"
    __table_args__ = (
        CheckConstraint("source_id != target_id", name="ck_relation_self"),
        CheckConstraint(
            "relation_type IN ('related','subquestion','derived_from','tests','supports','challenges','extends','reuses')",
            name="ck_relation_type",
        ),
        Index(
            "uq_relation_live",
            "source_id",
            "target_id",
            "relation_type",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_question_parent",
            "source_id",
            unique=True,
            sqlite_where=text("deleted_at IS NULL AND relation_type = 'subquestion'"),
        ),
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id"), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text, default="")
    source_version: Mapped[int] = mapped_column(Integer)
    target_version: Mapped[int] = mapped_column(Integer)


class Action(OwnedVersioned, Base):
    __tablename__ = "actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','in_progress','blocked','paused','completed','cancelled')",
            name="ck_action_status",
        ),
    )
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    direction_id: Mapped[str | None] = mapped_column(ForeignKey("research_items.id"), index=True)
    origin_reflection_id: Mapped[str | None] = mapped_column(
        ForeignKey("reflections.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="planned")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[str | None] = mapped_column(String(40))


class ActionRecord(Base):
    __tablename__ = "action_records"
    __table_args__ = (UniqueConstraint("action_id", "record_id", name="uq_action_record"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"), index=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("records.id"), index=True)
    record_revision_id: Mapped[str] = mapped_column(ForeignKey("record_revisions.id"))


class Reflection(OwnedVersioned, Base):
    __tablename__ = "reflections"
    __table_args__ = (CheckConstraint("kind IN ('attempt','period')", name="ck_reflection_kind"),)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[str | None] = mapped_column(String(40))
    end_at: Mapped[str | None] = mapped_column(String(40))
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    materials: Mapped[list] = mapped_column(JSON, default=list)


class EvidenceReference(Base):
    __tablename__ = "evidence_references"
    __table_args__ = (
        CheckConstraint(
            "(item_id IS NOT NULL) + (relation_id IS NOT NULL) = 1", name="ck_evidence_parent"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("research_items.id"), index=True)
    relation_id: Mapped[str | None] = mapped_column(ForeignKey("graph_relations.id"), index=True)
    record_revision_id: Mapped[str] = mapped_column(ForeignKey("record_revisions.id"))
    source_version_id: Mapped[str | None] = mapped_column(ForeignKey("source_versions.id"))
    field_path: Mapped[str] = mapped_column(String(100), default="body")
    start: Mapped[int | None] = mapped_column(Integer)
    end: Mapped[int | None] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text, default="")
    stance: Mapped[str] = mapped_column(String(20), default="context")
    reviewed_record_version: Mapped[int] = mapped_column(Integer)


class Revision(Base):
    __tablename__ = "m2_revisions"
    __table_args__ = (
        CheckConstraint(
            "(item_id IS NOT NULL) + (relation_id IS NOT NULL) + (action_id IS NOT NULL) + (reflection_id IS NOT NULL) = 1",
            name="ck_revision_parent",
        ),
        UniqueConstraint("item_id", "version", name="uq_item_revision"),
        UniqueConstraint("relation_id", "version", name="uq_relation_revision"),
        UniqueConstraint("action_id", "version", name="uq_action_revision"),
        UniqueConstraint("reflection_id", "version", name="uq_reflection_revision"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("research_items.id"), index=True)
    relation_id: Mapped[str | None] = mapped_column(ForeignKey("graph_relations.id"), index=True)
    action_id: Mapped[str | None] = mapped_column(ForeignKey("actions.id"), index=True)
    reflection_id: Mapped[str | None] = mapped_column(ForeignKey("reflections.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(40))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class GraphLayout(Base):
    __tablename__ = "graph_layouts"
    __table_args__ = (UniqueConstraint("owner_id", "scope_key", name="uq_layout_scope"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    scope_key: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    positions: Mapped[dict] = mapped_column(JSON, default=dict)


class MutationRequest(Base):
    __tablename__ = "mutation_requests"
    __table_args__ = (
        UniqueConstraint("owner_id", "operation", "request_id", name="uq_mutation_request"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    operation: Mapped[str] = mapped_column(String(100))
    request_id: Mapped[str] = mapped_column(String(36))
    digest: Mapped[str] = mapped_column(String(64))
    result_id: Mapped[str] = mapped_column(String(36))
