from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, new_id, now


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(80))
    expires_at: Mapped[str] = mapped_column(String(40), index=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class Record(Base):
    __tablename__ = "records"
    __table_args__ = (
        UniqueConstraint("owner_id", "request_id", name="uq_record_request"),
        CheckConstraint("version >= 1", name="ck_record_version"),
        CheckConstraint(
            "record_type IN ('note','paper','experiment','ai','idea')",
            name="ck_record_type",
        ),
        CheckConstraint(
            "work_status IN ('planned','in_progress','blocked','paused','finished')",
            name="ck_work_status",
        ),
        CheckConstraint(
            "outcome_status IN ('none','inconclusive','unsupported','preliminary','not_applicable')",
            name="ck_outcome_status",
        ),
        Index("ix_record_owner_updated", "owner_id", "updated_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    record_type: Mapped[str] = mapped_column(String(20), default="note")
    work_status: Mapped[str] = mapped_column(String(20), default="in_progress")
    outcome_status: Mapped[str] = mapped_column(String(20), default="none")
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    request_id: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
    deleted_at: Mapped[str | None] = mapped_column(String(40), default=None)


class RecordRevision(Base):
    __tablename__ = "record_revisions"
    __table_args__ = (UniqueConstraint("record_id", "version", name="uq_record_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    record_id: Mapped[str] = mapped_column(ForeignKey("records.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(40))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (CheckConstraint("kind IN ('text','file','link')", name="ck_source_kind"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    record_id: Mapped[str] = mapped_column(ForeignKey("records.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200))
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class SourceVersion(Base):
    __tablename__ = "source_versions"
    __table_args__ = (UniqueConstraint("source_id", "version", name="uq_source_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
