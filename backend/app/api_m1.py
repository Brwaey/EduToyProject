import re
from pathlib import PurePath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from . import records
from .db import now
from .models import LoginSession, Project, Record, RecordRevision, SourceVersion, User
from .schemas import (
    AuthOut,
    LoginInput,
    OutcomeStatus,
    ProjectInput,
    ProjectOut,
    ProjectPatch,
    RecordCreate,
    RecordList,
    RecordOut,
    RecordPatch,
    RecordType,
    RegisterInput,
    RevisionOut,
    SourceAdd,
    SourceInput,
    SourceOut,
    SourceRevise,
    SourceVersionOut,
    UserOut,
    VersionInput,
    WorkStatus,
)
from .security import (
    COOKIE,
    Identity,
    Problem,
    current_user,
    db_session,
    issue_session,
    passwords,
    token_hash,
)

Db = Annotated[Session, Depends(db_session)]
Who = Annotated[Identity, Depends(current_user)]
router = APIRouter(prefix="/api/v1")


def revoke_previous(request, db):
    token = request.cookies.get(COOKIE)
    if token:
        session = db.get(LoginSession, token_hash(token))
        if session:
            db.delete(session)


@router.post("/auth/register", response_model=AuthOut, status_code=201)
def register(value: RegisterInput, request: Request, response: Response, db: Db):
    if not value.display_name.strip():
        raise Problem(422, "invalid_name", "显示名称不能为空")
    if db.scalar(select(User).where(User.username == value.username)):
        raise Problem(409, "username_taken", "该用户名已被使用")
    user = User(
        username=value.username,
        display_name=value.display_name.strip(),
        password_hash=passwords.hash(value.password),
    )
    db.add(user)
    db.flush()
    revoke_previous(request, db)
    session = issue_session(db, user, response, request.app.state.settings.secure_cookie)
    db.commit()
    return AuthOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token)


@router.post("/auth/login", response_model=AuthOut)
def login(value: LoginInput, request: Request, response: Response, db: Db):
    user = db.scalar(select(User).where(User.username == value.username))
    if user is None or not passwords.verify(value.password, user.password_hash):
        raise Problem(401, "invalid_credentials", "用户名或密码不正确")
    revoke_previous(request, db)
    session = issue_session(db, user, response, request.app.state.settings.secure_cookie)
    db.commit()
    return AuthOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token)


@router.get("/auth/me", response_model=AuthOut)
def me(who: Who):
    return AuthOut(user=UserOut.model_validate(who.user), csrf_token=who.session.csrf_token)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Db, who: Who):
    db.delete(who.session)
    db.commit()
    response.delete_cookie(
        COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.secure_cookie,
    )


@router.get("/projects", response_model=list[ProjectOut])
def projects(db: Db, who: Who):
    return db.scalars(
        select(Project)
        .where(Project.owner_id == who.user.id)
        .order_by(Project.archived, Project.created_at)
    ).all()


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(value: ProjectInput, db: Db, who: Who):
    project = Project(owner_id=who.user.id, **value.model_dump())
    db.add(project)
    db.commit()
    return project


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: UUID, db: Db, who: Who):
    return records.project_for(db, who.user.id, str(project_id))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def patch_project(project_id: UUID, value: ProjectPatch, db: Db, who: Who):
    project = records.project_for(db, who.user.id, str(project_id))
    for key, item in value.model_dump(exclude_unset=True).items():
        setattr(project, key, item)
    project.updated_at = now()
    db.commit()
    return project


@router.get("/records", response_model=RecordList)
def list_records(
    db: Db,
    who: Who,
    q: str = Query(default="", max_length=200),
    project_id: UUID | None = None,
    unassigned: bool = False,
    deleted: bool = False,
    record_type: RecordType | None = None,
    work_status: WorkStatus | None = None,
    outcome_status: OutcomeStatus | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    conditions = [
        Record.owner_id == who.user.id,
        Record.deleted_at.is_not(None) if deleted else Record.deleted_at.is_(None),
    ]
    if project_id:
        records.project_for(db, who.user.id, str(project_id))
        conditions.append(Record.project_id == str(project_id))
    if unassigned:
        conditions.append(Record.project_id.is_(None))
    for column, value in [
        (Record.record_type, record_type),
        (Record.work_status, work_status),
        (Record.outcome_status, outcome_status),
    ]:
        if value:
            conditions.append(column == value)
    if q.strip():
        conditions.append(
            or_(
                *[
                    column.contains(q.strip(), autoescape=True)
                    for column in (
                        Record.title,
                        Record.body,
                        cast(Record.fields, String),
                    )
                ]
            )
        )
    total = db.scalar(select(func.count()).select_from(Record).where(*conditions))
    items = db.scalars(
        select(Record)
        .where(*conditions)
        .order_by(Record.updated_at.desc(), Record.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return RecordList(items=items, total=total, page=page, page_size=page_size)


@router.post("/records", response_model=RecordOut, status_code=201)
def create_record(value: RecordCreate, db: Db, who: Who):
    result = records.create_record(db, who.user.id, value)
    db.commit()
    return result


@router.post("/records/import", response_model=RecordOut, status_code=201)
def import_record(
    db: Db,
    who: Who,
    file: Annotated[UploadFile, File()],
    request_id: Annotated[UUID, Form()],
    project_id: Annotated[UUID | None, Form()] = None,
    record_type: Annotated[RecordType, Form()] = "note",
):
    name = PurePath((file.filename or "").replace("\\", "/")).name
    if PurePath(name).suffix.lower() not in (".md", ".txt"):
        raise Problem(422, "unsupported_file", "仅支持 .md 和 .txt 文件")
    raw = file.file.read(1048577)
    if len(raw) > 1048576:
        raise Problem(413, "file_too_large", "单个文件不能超过 1 MiB")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Problem(422, "invalid_encoding", "请将文件保存为 UTF-8 编码后重试") from None
    if not content.strip() or "\x00" in content:
        raise Problem(422, "empty_file", "文件为空或包含非文本内容")
    heading = re.search(r"^#{1,6}\s+(.+?)\s*#*\s*$", content, re.MULTILINE)
    title = (heading.group(1) if heading else PurePath(name).stem)[:200]
    value = RecordCreate(
        request_id=request_id,
        project_id=project_id,
        record_type=record_type,
        title=title,
        body=content,
        sources=[SourceInput(kind="file", name=name[:200], content=content)],
    )
    result = records.create_record(db, who.user.id, value)
    db.commit()
    return result


@router.get("/records/{record_id}", response_model=RecordOut)
def get_record(record_id: UUID, db: Db, who: Who, include_deleted: bool = False):
    return records.record_for(db, who.user.id, str(record_id), include_deleted)


@router.patch("/records/{record_id}", response_model=RecordOut)
def patch_record(record_id: UUID, value: RecordPatch, db: Db, who: Who):
    result = records.edit_record(db, who.user.id, str(record_id), value)
    db.commit()
    return result


@router.delete("/records/{record_id}", response_model=RecordOut)
def delete_record(record_id: UUID, value: VersionInput, db: Db, who: Who):
    result = records.set_deleted(db, who.user.id, str(record_id), value.expected_version, True)
    db.commit()
    return result


@router.post("/records/{record_id}/restore", response_model=RecordOut)
def restore_record(record_id: UUID, value: VersionInput, db: Db, who: Who):
    result = records.set_deleted(db, who.user.id, str(record_id), value.expected_version, False)
    db.commit()
    return result


@router.get("/records/{record_id}/revisions", response_model=list[RevisionOut])
def revisions(record_id: UUID, db: Db, who: Who):
    records.record_for(db, who.user.id, str(record_id), include_deleted=True)
    return db.scalars(
        select(RecordRevision)
        .where(RecordRevision.record_id == str(record_id))
        .order_by(RecordRevision.version.desc())
    ).all()


@router.get("/records/{record_id}/sources", response_model=list[SourceOut])
def sources(record_id: UUID, db: Db, who: Who):
    records.record_for(db, who.user.id, str(record_id))
    return records.sources_for(db, str(record_id))


@router.post(
    "/records/{record_id}/sources",
    response_model=RecordOut,
    status_code=201,
)
def source_add(record_id: UUID, value: SourceAdd, db: Db, who: Who):
    result = records.append_source(db, who.user.id, str(record_id), value)
    db.commit()
    return result


@router.get("/sources/{source_id}/versions", response_model=list[SourceVersionOut])
def source_versions(source_id: UUID, db: Db, who: Who):
    source, _ = records.source_for(db, who.user.id, str(source_id))
    return db.scalars(
        select(SourceVersion)
        .where(SourceVersion.source_id == source.id)
        .order_by(SourceVersion.version.desc())
    ).all()


@router.post(
    "/sources/{source_id}/versions",
    response_model=RecordOut,
    status_code=201,
)
def source_revise(source_id: UUID, value: SourceRevise, db: Db, who: Who):
    result = records.revise_source(db, who.user.id, str(source_id), value)
    db.commit()
    return result
