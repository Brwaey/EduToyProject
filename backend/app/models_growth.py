"""M4 versioned contributions, growth and fixed evidence; no generated scores."""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, new_id, now
from .models_m2 import OwnedVersioned


class Contribution(OwnedVersioned, Base):
    __tablename__ = "contributions"
    title: Mapped[str] = mapped_column(String(200))
    contribution_type: Mapped[str] = mapped_column(String(30))
    occurred_on: Mapped[str] = mapped_column(String(10), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    question_id: Mapped[str | None] = mapped_column(ForeignKey("research_items.id"), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    confirmed_at: Mapped[str] = mapped_column(String(40), default=now)


class AbilityTag(OwnedVersioned, Base):
    __tablename__ = "ability_tags"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_ability_name"),)
    name: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class GrowthEntry(OwnedVersioned, Base):
    __tablename__ = "growth_entries"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('ability_instance','understanding_change')", name="ck_growth_kind"
        ),
    )
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    occurred_on: Mapped[str] = mapped_column(String(10), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    question_id: Mapped[str | None] = mapped_column(ForeignKey("research_items.id"), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class GrowthEntryTag(Base):
    __tablename__ = "growth_entry_tags"
    entry_id: Mapped[str] = mapped_column(ForeignKey("growth_entries.id"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("ability_tags.id"), primary_key=True)


class GrowthRevision(Base):
    __tablename__ = "growth_revisions"
    __table_args__ = (
        CheckConstraint(
            "(contribution_id IS NOT NULL) + (entry_id IS NOT NULL) + (tag_id IS NOT NULL) = 1",
            name="ck_growth_revision_parent",
        ),
        UniqueConstraint("contribution_id", "version", name="uq_contribution_revision"),
        UniqueConstraint("entry_id", "version", name="uq_growth_revision"),
        UniqueConstraint("tag_id", "version", name="uq_tag_revision"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    contribution_id: Mapped[str | None] = mapped_column(ForeignKey("contributions.id"), index=True)
    entry_id: Mapped[str | None] = mapped_column(ForeignKey("growth_entries.id"), index=True)
    tag_id: Mapped[str | None] = mapped_column(ForeignKey("ability_tags.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(40))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class GrowthEvidence(Base):
    __tablename__ = "growth_evidence"
    __table_args__ = (
        CheckConstraint(
            "(contribution_id IS NOT NULL) != (entry_id IS NOT NULL)",
            name="ck_growth_evidence_parent",
        ),
        CheckConstraint(
            "(record_revision_id IS NOT NULL) + (m2_revision_id IS NOT NULL) + (contribution_revision_id IS NOT NULL) = 1",
            name="ck_growth_evidence_target",
        ),
        CheckConstraint(
            "source_version_id IS NULL OR record_revision_id IS NOT NULL",
            name="ck_growth_source_record",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    contribution_id: Mapped[str | None] = mapped_column(ForeignKey("contributions.id"), index=True)
    entry_id: Mapped[str | None] = mapped_column(ForeignKey("growth_entries.id"), index=True)
    record_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("record_revisions.id"), index=True
    )
    m2_revision_id: Mapped[str | None] = mapped_column(ForeignKey("m2_revisions.id"), index=True)
    contribution_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("growth_revisions.id"), index=True
    )
    source_version_id: Mapped[str | None] = mapped_column(ForeignKey("source_versions.id"))
    field_path: Mapped[str] = mapped_column(String(100), default="body")
    start: Mapped[int | None] = mapped_column(Integer)
    end: Mapped[int | None] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(String(20), default="context")
    reviewed_version: Mapped[int] = mapped_column(Integer)
    reviewed_dependencies: Mapped[dict] = mapped_column(JSON, default=dict)


class GrowthActionLink(Base):
    __tablename__ = "growth_action_links"
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("growth_revisions.id"), index=True)
