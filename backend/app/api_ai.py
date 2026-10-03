from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import ai_commands as commands
from .ai_credentials import config_view, save_config
from .ai_data import select_inputs, suggestion_view, task_view
from .m2_common import owned
from .models import Record
from .models_ai import AISuggestion, AITask, AITaskInput
from .models_m2 import ResearchItem
from .schemas import VersionInput
from .schemas_ai import (
    AcceptInput,
    BatchReject,
    ConfigOut,
    ConfigSave,
    PreviewInput,
    PreviewOut,
    SuggestionOut,
    SuggestionPage,
    TaskCreate,
    TaskOut,
    TaskPage,
    TaskRequest,
)
from .security import Identity, current_user, db_session

Db = Annotated[Session, Depends(db_session)]
Who = Annotated[Identity, Depends(current_user)]
Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=100)]
router = APIRouter(prefix="/api/v1/ai", tags=["M3 AI"])


@router.get("/config", response_model=ConfigOut)
def get_config(request: Request, db: Db, who: Who):
    return config_view(request.app.state.settings, db, who.user.id)


@router.put("/config", response_model=ConfigOut)
def put_config(value: ConfigSave, request: Request, db: Db, who: Who):
    result = save_config(request.app.state.settings, db, who.user.id, value)
    db.commit()
    return result


@router.delete("/config", status_code=204)
def delete_config(value: VersionInput, db: Db, who: Who):
    commands.clear_config(db, who.user.id, value.expected_version)
    db.commit()


def finish_task(db, task):
    result = task_view(db, task)
    db.commit()
    return result


@router.post("/config/test", response_model=TaskOut, status_code=202)
def test_config(value: TaskRequest, request: Request, db: Db, who: Who):
    return finish_task(
        db,
        commands.create_task(
            db, request.app.state.settings, who.user.id, value, kind="connection_test"
        ),
    )


@router.post("/preview", response_model=PreviewOut)
def preview(value: PreviewInput, db: Db, who: Who):
    return select_inputs(db, who.user.id, value)[1]


@router.post("/tasks", response_model=TaskOut, status_code=202)
def create_task(value: TaskCreate, request: Request, db: Db, who: Who):
    return finish_task(db, commands.create_task(db, request.app.state.settings, who.user.id, value))


def project_condition(owner, project):
    return (
        select(AITaskInput.task_id)
        .outerjoin(Record, AITaskInput.record_id == Record.id)
        .outerjoin(ResearchItem, AITaskInput.item_id == ResearchItem.id)
        .where(
            or_(
                (Record.owner_id == owner) & (Record.project_id == str(project)),
                (ResearchItem.owner_id == owner) & (ResearchItem.project_id == str(project)),
            )
        )
    )


@router.get("/tasks", response_model=TaskPage)
def list_tasks(
    db: Db,
    who: Who,
    page: Page = 1,
    page_size: Size = 20,
    kind: str | None = None,
    status: str | None = None,
    project_id: UUID | None = None,
):
    conditions = [AITask.owner_id == who.user.id]
    if kind:
        conditions.append(AITask.kind == kind)
    if status:
        conditions.append(AITask.status == status)
    if project_id:
        conditions.append(AITask.id.in_(project_condition(who.user.id, project_id)))
    total = db.scalar(select(func.count()).select_from(AITask).where(*conditions))
    rows = db.scalars(
        select(AITask)
        .where(*conditions)
        .order_by(AITask.created_at.desc(), AITask.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return dict(items=[task_view(db, t) for t in rows], total=total, page=page, page_size=page_size)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: UUID, db: Db, who: Who):
    return task_view(db, owned(db, AITask, who.user.id, task_id))


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel_task(task_id: UUID, db: Db, who: Who):
    return finish_task(db, commands.cancel_task(db, owned(db, AITask, who.user.id, task_id)))


@router.post("/tasks/{task_id}/retry", response_model=TaskOut, status_code=202)
def retry_task(task_id: UUID, value: TaskRequest, request: Request, db: Db, who: Who):
    parent = owned(db, AITask, who.user.id, task_id)
    return finish_task(
        db,
        commands.create_task(
            db, request.app.state.settings, who.user.id, value, kind=parent.kind, parent=parent
        ),
    )


def view_suggestion(db, owner, s):
    return suggestion_view(db, s, owned(db, AITask, owner, s.task_id))


@router.get("/suggestions", response_model=SuggestionPage)
def list_suggestions(
    db: Db,
    who: Who,
    page: Page = 1,
    page_size: Size = 20,
    kind: str | None = None,
    status: str | None = None,
    project_id: UUID | None = None,
):
    conditions = [AISuggestion.owner_id == who.user.id]
    if kind:
        conditions.append(AISuggestion.kind == kind)
    if status:
        conditions.append(AISuggestion.status == status)
    if project_id:
        conditions.append(AISuggestion.task_id.in_(project_condition(who.user.id, project_id)))
    total = db.scalar(select(func.count()).select_from(AISuggestion).where(*conditions))
    rows = db.scalars(
        select(AISuggestion)
        .where(*conditions)
        .order_by(AISuggestion.created_at.desc(), AISuggestion.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return dict(
        items=[view_suggestion(db, who.user.id, s) for s in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/suggestions/reject-batch", response_model=list[SuggestionOut])
def batch_reject(value: BatchReject, db: Db, who: Who):
    result = []
    for key, version in value.suggestions.items():
        s = owned(db, AISuggestion, who.user.id, key)
        commands.reject(db, s, version)
        result.append(view_suggestion(db, who.user.id, s))
    db.commit()
    return result


@router.get("/suggestions/{suggestion_id}", response_model=SuggestionOut)
def get_suggestion(suggestion_id: UUID, db: Db, who: Who):
    return view_suggestion(db, who.user.id, owned(db, AISuggestion, who.user.id, suggestion_id))


@router.post("/suggestions/{suggestion_id}/accept", response_model=SuggestionOut)
def accept(suggestion_id: UUID, value: AcceptInput, db: Db, who: Who):
    s = commands.accept(db, who.user.id, owned(db, AISuggestion, who.user.id, suggestion_id), value)
    result = view_suggestion(db, who.user.id, s)
    db.commit()
    return result


@router.post("/suggestions/{suggestion_id}/reject", response_model=SuggestionOut)
def reject(suggestion_id: UUID, value: VersionInput, db: Db, who: Who):
    s = commands.reject(
        db, owned(db, AISuggestion, who.user.id, suggestion_id), value.expected_version
    )
    result = view_suggestion(db, who.user.id, s)
    db.commit()
    return result
