"""All record/source mutations share a transaction and versioned snapshot."""

import hashlib
import json

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .db import now
from .models import Project, Record, RecordRevision, Source, SourceVersion
from .schemas import RecordCreate, RecordOut, SourceInput, SourceOut
from .security import Problem


def project_for(db: Session, owner: str, project_id: str, writable=False) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner))
    if project is None:
        raise Problem(404, "not_found", "项目不存在")
    if writable and project.archived:
        raise Problem(409, "project_archived", "请先恢复已归档项目")
    return project


def record_for(db: Session, owner: str, record_id: str, include_deleted=False) -> Record:
    record = db.scalar(select(Record).where(Record.id == record_id, Record.owner_id == owner))
    if record is None or (record.deleted_at and not include_deleted):
        raise Problem(404, "not_found", "记录不存在")
    return record


def source_for(db: Session, owner: str, source_id: str) -> tuple[Source, Record]:
    source = db.get(Source, source_id)
    if source is None:
        raise Problem(404, "not_found", "来源不存在")
    return source, record_for(db, owner, source.record_id)


def writable(db: Session, record: Record):
    if record.project_id:
        project_for(db, record.owner_id, record.project_id, writable=True)


def sources_for(db: Session, record_id: str) -> list[SourceOut]:
    sources = db.scalars(
        select(Source).where(Source.record_id == record_id).order_by(Source.created_at, Source.id)
    ).all()
    result = []
    for source in sources:
        versions = db.scalars(
            select(SourceVersion)
            .where(SourceVersion.source_id == source.id)
            .order_by(SourceVersion.version.desc())
        ).all()
        result.append(
            SourceOut(
                id=source.id,
                record_id=source.record_id,
                kind=source.kind,
                name=source.name,
                current_version=source.current_version,
                created_at=source.created_at,
                versions=versions,
            )
        )
    return result


def snapshot(db: Session, record: Record, operation: str):
    db.flush()
    value = RecordOut.model_validate(record).model_dump(mode="json")
    value["source_version_ids"] = list(
        db.scalars(
            select(SourceVersion.id)
            .join(Source, Source.id == SourceVersion.source_id)
            .where(
                Source.record_id == record.id,
                SourceVersion.version == Source.current_version,
            )
            .order_by(Source.id)
        )
    )
    db.add(
        RecordRevision(
            record_id=record.id,
            version=record.version,
            operation=operation,
            snapshot=value,
        )
    )


def add_source_row(db: Session, record: Record, value: SourceInput) -> Source:
    source = Source(record_id=record.id, kind=value.kind, name=value.name)
    db.add(source)
    db.flush()
    db.add(SourceVersion(source_id=source.id, version=1, content=value.content))
    db.flush()
    return source


def create_record(db: Session, owner: str, value: RecordCreate) -> Record:
    payload = value.model_dump(mode="json")
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    request_id = str(value.request_id)

    def prior():
        existing = db.scalar(
            select(Record).where(Record.owner_id == owner, Record.request_id == request_id)
        )
        if existing is not None and existing.request_hash != digest:
            raise Problem(409, "request_conflict", "该请求标识已用于其他内容，请使用新的请求标识")
        return existing

    existing = prior()
    if existing is not None:
        return existing
    project_id = str(value.project_id) if value.project_id else None
    if project_id:
        project_for(db, owner, project_id, writable=True)
    record = Record(
        owner_id=owner,
        project_id=project_id,
        title=value.title.strip() or value.body.strip().splitlines()[0][:80],
        body=value.body,
        record_type=value.record_type,
        work_status=value.work_status,
        outcome_status=value.outcome_status,
        fields=value.fields.model_dump(),
        request_id=request_id,
        request_hash=digest,
    )
    db.add(record)
    db.flush()
    original = value.sources or [
        SourceInput(content=value.body if value.body.strip() else value.title)
    ]
    for source in original:
        add_source_row(db, record, source)
    snapshot(db, record, "create")
    db.flush()
    return record


def advance(db: Session, record: Record, expected: int, changes: dict | None = None) -> Record:
    writable(db, record)
    changes = dict(changes or {})
    result = db.execute(
        update(Record)
        .where(
            Record.id == record.id,
            Record.owner_id == record.owner_id,
            Record.version == expected,
        )
        .values(**changes, version=expected + 1, updated_at=now())
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise Problem(409, "version_conflict", "记录已在其他页面更新，请重新载入后再保存")
    db.refresh(record)
    return record


def edit_record(db: Session, owner: str, record_id: str, value) -> Record:
    record = record_for(db, owner, record_id)
    changes = value.model_dump(mode="json", exclude_unset=True, exclude={"expected_version"})
    if changes.get("project_id"):
        project_for(db, owner, changes["project_id"], writable=True)
    title = changes.get("title", record.title)
    body = changes.get("body", record.body)
    if not (title.strip() or body.strip()):
        raise Problem(422, "empty_record", "请至少填写标题或正文")
    if "title" in changes:
        changes["title"] = title.strip() or body.strip().splitlines()[0][:80]
    advance(db, record, value.expected_version, changes)
    snapshot(db, record, "edit")
    db.flush()
    return record


def set_deleted(db: Session, owner: str, record_id: str, expected: int, deleted: bool):
    record = record_for(db, owner, record_id, include_deleted=True)
    if bool(record.deleted_at) == deleted:
        raise Problem(409, "state_conflict", "记录状态已变化，请刷新后重试")
    advance(db, record, expected, {"deleted_at": now() if deleted else None})
    snapshot(db, record, "delete" if deleted else "restore")
    db.flush()
    return record


def append_source(db: Session, owner: str, record_id: str, value):
    record = record_for(db, owner, record_id)
    advance(db, record, value.expected_version)
    add_source_row(db, record, SourceInput(**value.model_dump(exclude={"expected_version"})))
    snapshot(db, record, "source_add")
    db.flush()
    return record


def revise_source(db: Session, owner: str, source_id: str, value):
    source, record = source_for(db, owner, source_id)
    checked = SourceInput(kind=source.kind, name=source.name, content=value.content)
    advance(db, record, value.expected_version)
    source.current_version += 1
    db.add(
        SourceVersion(source_id=source.id, version=source.current_version, content=checked.content)
    )
    snapshot(db, record, "source_revise")
    db.flush()
    return record
