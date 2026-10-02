import logging
import re
from contextlib import asynccontextmanager
from pathlib import PurePath
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from . import records
from .config import Settings
from .db import make_engine, make_session_factory, migrate, now
from .models import LoginSession, Project, Record, RecordRevision, SourceVersion, User
from .schemas import (
    AuthOut,
    ErrorOut,
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
log = logging.getLogger("yanji")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        migrate(engine, settings)
        yield
        engine.dispose()

    app = FastAPI(
        title="研迹 API",
        version="0.1.0",
        lifespan=lifespan,
        responses={
            status: {"model": ErrorOut}
            for status in (400, 401, 403, 404, 405, 409, 413, 422, 500, 503)
        },
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = make_session_factory(engine)

    def error(request, status, code, message):
        request_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=status,
            headers={
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": request_id,
                }
            },
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin", "").rstrip("/")
            if origin not in settings.allowed_origins:
                return error(request, 403, "origin_failed", "请求来源不被允许")
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return error(request, exc.status, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def http_handler(request, exc):
        code = "not_found" if exc.status_code == 404 else "http_error"
        return error(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unexpected_handler(request, exc):
        # Do not log submitted research material or credentials.
        log.error("Unhandled %s request=%s", type(exc).__name__, request.state.request_id)
        return error(request, 500, "internal_error", "服务暂时无法完成操作，请稍后重试")

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_handler(request, exc):
        return error(
            request,
            422,
            "validation_error",
            "输入格式不正确："
            + "; ".join(
                ".".join(str(p) for p in item["loc"]) + " " + item["msg"]
                for item in exc.errors()[:3]
            ),
        )

    @app.exception_handler(OperationalError)
    async def operational_handler(request, exc):
        if "locked" in str(exc.orig).lower() or "busy" in str(exc.orig).lower():
            return error(
                request,
                503,
                "database_busy",
                "数据库正在保存其他内容，请稍后重试，当前输入已保留",
            )
        log.error("Database operation failed request=%s", request.state.request_id)
        return error(request, 503, "database_unavailable", "数据库暂不可用，请检查服务状态")

    @app.exception_handler(IntegrityError)
    async def integrity_handler(request, exc):
        return error(request, 409, "integrity_conflict", "数据存在冲突，请刷新后重试")

    prefix = "/api/v1"

    @app.get(prefix + "/health/live")
    def live():
        return {"status": "ok"}

    @app.get(prefix + "/health/ready")
    def ready(db: Db):
        version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if version != "0001_m1":
            raise Problem(503, "migration_required", "数据库结构需要升级")
        return {"status": "ready", "schema": version}

    def revoke_previous(request, db):
        token = request.cookies.get(COOKIE)
        if token:
            session = db.get(LoginSession, token_hash(token))
            if session:
                db.delete(session)

    @app.post(prefix + "/auth/register", response_model=AuthOut, status_code=201)
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
        session = issue_session(db, user, response, settings.secure_cookie)
        db.commit()
        return AuthOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token)

    @app.post(prefix + "/auth/login", response_model=AuthOut)
    def login(value: LoginInput, request: Request, response: Response, db: Db):
        user = db.scalar(select(User).where(User.username == value.username))
        if user is None or not passwords.verify(value.password, user.password_hash):
            raise Problem(401, "invalid_credentials", "用户名或密码不正确")
        revoke_previous(request, db)
        session = issue_session(db, user, response, settings.secure_cookie)
        db.commit()
        return AuthOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token)

    @app.get(prefix + "/auth/me", response_model=AuthOut)
    def me(who: Who):
        return AuthOut(user=UserOut.model_validate(who.user), csrf_token=who.session.csrf_token)

    @app.post(prefix + "/auth/logout", status_code=204)
    def logout(response: Response, db: Db, who: Who):
        db.delete(who.session)
        db.commit()
        response.delete_cookie(
            COOKIE,
            path="/",
            httponly=True,
            samesite="lax",
            secure=settings.secure_cookie,
        )

    @app.get(prefix + "/projects", response_model=list[ProjectOut])
    def projects(db: Db, who: Who):
        return db.scalars(
            select(Project)
            .where(Project.owner_id == who.user.id)
            .order_by(Project.archived, Project.created_at)
        ).all()

    @app.post(prefix + "/projects", response_model=ProjectOut, status_code=201)
    def create_project(value: ProjectInput, db: Db, who: Who):
        project = Project(owner_id=who.user.id, **value.model_dump())
        db.add(project)
        db.commit()
        return project

    @app.get(prefix + "/projects/{project_id}", response_model=ProjectOut)
    def get_project(project_id: UUID, db: Db, who: Who):
        return records.project_for(db, who.user.id, str(project_id))

    @app.patch(prefix + "/projects/{project_id}", response_model=ProjectOut)
    def patch_project(project_id: UUID, value: ProjectPatch, db: Db, who: Who):
        project = records.project_for(db, who.user.id, str(project_id))
        for key, item in value.model_dump(exclude_unset=True).items():
            setattr(project, key, item)
        project.updated_at = now()
        db.commit()
        return project

    @app.get(prefix + "/records", response_model=RecordList)
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

    @app.post(prefix + "/records", response_model=RecordOut, status_code=201)
    def create_record(value: RecordCreate, db: Db, who: Who):
        return records.create_record(db, who.user.id, value)

    @app.post(prefix + "/records/import", response_model=RecordOut, status_code=201)
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
        return records.create_record(db, who.user.id, value)

    @app.get(prefix + "/records/{record_id}", response_model=RecordOut)
    def get_record(record_id: UUID, db: Db, who: Who, include_deleted: bool = False):
        return records.record_for(db, who.user.id, str(record_id), include_deleted)

    @app.patch(prefix + "/records/{record_id}", response_model=RecordOut)
    def patch_record(record_id: UUID, value: RecordPatch, db: Db, who: Who):
        return records.edit_record(db, who.user.id, str(record_id), value)

    @app.delete(prefix + "/records/{record_id}", response_model=RecordOut)
    def delete_record(record_id: UUID, value: VersionInput, db: Db, who: Who):
        return records.set_deleted(db, who.user.id, str(record_id), value.expected_version, True)

    @app.post(prefix + "/records/{record_id}/restore", response_model=RecordOut)
    def restore_record(record_id: UUID, value: VersionInput, db: Db, who: Who):
        return records.set_deleted(db, who.user.id, str(record_id), value.expected_version, False)

    @app.get(prefix + "/records/{record_id}/revisions", response_model=list[RevisionOut])
    def revisions(record_id: UUID, db: Db, who: Who):
        records.record_for(db, who.user.id, str(record_id), include_deleted=True)
        return db.scalars(
            select(RecordRevision)
            .where(RecordRevision.record_id == str(record_id))
            .order_by(RecordRevision.version.desc())
        ).all()

    @app.get(prefix + "/records/{record_id}/sources", response_model=list[SourceOut])
    def sources(record_id: UUID, db: Db, who: Who):
        records.record_for(db, who.user.id, str(record_id))
        return records.sources_for(db, str(record_id))

    @app.post(
        prefix + "/records/{record_id}/sources",
        response_model=RecordOut,
        status_code=201,
    )
    def source_add(record_id: UUID, value: SourceAdd, db: Db, who: Who):
        return records.append_source(db, who.user.id, str(record_id), value)

    @app.get(prefix + "/sources/{source_id}/versions", response_model=list[SourceVersionOut])
    def source_versions(source_id: UUID, db: Db, who: Who):
        source, _ = records.source_for(db, who.user.id, str(source_id))
        return db.scalars(
            select(SourceVersion)
            .where(SourceVersion.source_id == source.id)
            .order_by(SourceVersion.version.desc())
        ).all()

    @app.post(
        prefix + "/sources/{source_id}/versions",
        response_model=RecordOut,
        status_code=201,
    )
    def source_revise(source_id: UUID, value: SourceRevise, db: Db, who: Who):
        return records.revise_source(db, who.user.id, str(source_id), value)

    return app
