"""M3 persistent tasks and user-confirmed AI suggestions."""

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, new_id, now


class AIConfig(Base):
    __tablename__ = "ai_configs"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    endpoint: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(200), default="")
    encrypted_key: Mapped[str | None] = mapped_column(Text)
    test_status: Mapped[str] = mapped_column(String(30), default="untested")
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class AITask(Base):
    __tablename__ = "ai_tasks"
    __table_args__ = (
        UniqueConstraint("owner_id", "request_id", name="uq_ai_request"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_ai_task_status",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    config_version: Mapped[int] = mapped_column(Integer)
    endpoint: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(50), default="m3.v1")
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("ai_tasks.id"))
    target_record_id: Mapped[str | None] = mapped_column(ForeignKey("records.id"))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    target_reflection_id: Mapped[str | None] = mapped_column(ForeignKey("reflections.id"))
    usage: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    started_at: Mapped[str | None] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40))


class AITaskInput(Base):
    __tablename__ = "ai_task_inputs"
    __table_args__ = (
        UniqueConstraint("task_id", "material_key", name="uq_ai_material"),
        CheckConstraint(
            "(record_id IS NOT NULL AND record_revision_id IS NOT NULL AND item_id IS NULL AND item_revision_id IS NULL AND action_id IS NULL AND action_revision_id IS NULL AND reflection_id IS NULL AND reflection_revision_id IS NULL AND contribution_id IS NULL AND contribution_revision_id IS NULL AND entry_id IS NULL AND entry_revision_id IS NULL) OR (record_id IS NULL AND record_revision_id IS NULL AND item_id IS NOT NULL AND item_revision_id IS NOT NULL AND action_id IS NULL AND action_revision_id IS NULL AND reflection_id IS NULL AND reflection_revision_id IS NULL AND contribution_id IS NULL AND contribution_revision_id IS NULL AND entry_id IS NULL AND entry_revision_id IS NULL AND source_version_id IS NULL) OR (record_id IS NULL AND record_revision_id IS NULL AND item_id IS NULL AND item_revision_id IS NULL AND action_id IS NOT NULL AND action_revision_id IS NOT NULL AND reflection_id IS NULL AND reflection_revision_id IS NULL AND contribution_id IS NULL AND contribution_revision_id IS NULL AND entry_id IS NULL AND entry_revision_id IS NULL AND source_version_id IS NULL) OR (record_id IS NULL AND record_revision_id IS NULL AND item_id IS NULL AND item_revision_id IS NULL AND action_id IS NULL AND action_revision_id IS NULL AND reflection_id IS NOT NULL AND reflection_revision_id IS NOT NULL AND contribution_id IS NULL AND contribution_revision_id IS NULL AND entry_id IS NULL AND entry_revision_id IS NULL AND source_version_id IS NULL) OR (record_id IS NULL AND record_revision_id IS NULL AND item_id IS NULL AND item_revision_id IS NULL AND action_id IS NULL AND action_revision_id IS NULL AND reflection_id IS NULL AND reflection_revision_id IS NULL AND contribution_id IS NOT NULL AND contribution_revision_id IS NOT NULL AND entry_id IS NULL AND entry_revision_id IS NULL AND source_version_id IS NULL) OR (record_id IS NULL AND record_revision_id IS NULL AND item_id IS NULL AND item_revision_id IS NULL AND action_id IS NULL AND action_revision_id IS NULL AND reflection_id IS NULL AND reflection_revision_id IS NULL AND contribution_id IS NULL AND contribution_revision_id IS NULL AND entry_id IS NOT NULL AND entry_revision_id IS NOT NULL AND source_version_id IS NULL)",
            name="ck_ai_input_target",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("ai_tasks.id"), index=True)
    object_key: Mapped[str] = mapped_column(String(10))
    material_key: Mapped[str] = mapped_column(String(10))
    record_id: Mapped[str | None] = mapped_column(ForeignKey("records.id"))
    record_revision_id: Mapped[str | None] = mapped_column(ForeignKey("record_revisions.id"))
    selected_current_version: Mapped[int | None] = mapped_column(Integer)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("research_items.id"))
    item_revision_id: Mapped[str | None] = mapped_column(ForeignKey("m2_revisions.id"))
    action_id: Mapped[str | None] = mapped_column(ForeignKey("actions.id"))
    action_revision_id: Mapped[str | None] = mapped_column(ForeignKey("m2_revisions.id"))
    reflection_id: Mapped[str | None] = mapped_column(ForeignKey("reflections.id"))
    reflection_revision_id: Mapped[str | None] = mapped_column(ForeignKey("m2_revisions.id"))
    contribution_id: Mapped[str | None] = mapped_column(ForeignKey("contributions.id"))
    contribution_revision_id: Mapped[str | None] = mapped_column(ForeignKey("growth_revisions.id"))
    entry_id: Mapped[str | None] = mapped_column(ForeignKey("growth_entries.id"))
    entry_revision_id: Mapped[str | None] = mapped_column(ForeignKey("growth_revisions.id"))
    source_version_id: Mapped[str | None] = mapped_column(ForeignKey("source_versions.id"))
    field_path: Mapped[str] = mapped_column(String(100))
    start: Mapped[int | None] = mapped_column(Integer)
    end: Mapped[int | None] = mapped_column(Integer)


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','accepted','edited_accepted','rejected')",
            name="ck_ai_suggestion_status",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("ai_tasks.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    original: Mapped[dict] = mapped_column(JSON)
    accepted: Mapped[dict | None] = mapped_column(JSON)
    record_id: Mapped[str | None] = mapped_column(ForeignKey("records.id"))
    record_revision_id: Mapped[str | None] = mapped_column(ForeignKey("record_revisions.id"))
    relation_id: Mapped[str | None] = mapped_column(ForeignKey("graph_relations.id"))
    relation_revision_id: Mapped[str | None] = mapped_column(ForeignKey("m2_revisions.id"))
    contribution_id: Mapped[str | None] = mapped_column(ForeignKey("contributions.id"))
    contribution_revision_id: Mapped[str | None] = mapped_column(ForeignKey("growth_revisions.id"))
    action_id: Mapped[str | None] = mapped_column(ForeignKey("actions.id"))
    action_revision_id: Mapped[str | None] = mapped_column(ForeignKey("m2_revisions.id"))
    reflection_id: Mapped[str | None] = mapped_column(ForeignKey("reflections.id"))
    reflection_revision_id: Mapped[str | None] = mapped_column(ForeignKey("m2_revisions.id"))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    decided_at: Mapped[str | None] = mapped_column(String(40))


class AISuggestionEvent(Base):
    __tablename__ = "ai_suggestion_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    suggestion_id: Mapped[str] = mapped_column(ForeignKey("ai_suggestions.id"), index=True)
    operation: Mapped[str] = mapped_column(String(30))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class AIAdoption(Base):
    __tablename__ = "ai_adoptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    suggestion_id: Mapped[str] = mapped_column(ForeignKey("ai_suggestions.id"), unique=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("m2_revisions.id"), index=True)
    final_content: Mapped[dict] = mapped_column(JSON)
    review_info: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class AIAdoptionCitation(Base):
    __tablename__ = "ai_adoption_citations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    adoption_id: Mapped[str] = mapped_column(ForeignKey("ai_adoptions.id"), index=True)
    input_id: Mapped[str] = mapped_column(ForeignKey("ai_task_inputs.id"))
    field: Mapped[str] = mapped_column(String(50))
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
