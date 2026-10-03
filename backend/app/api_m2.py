from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from . import m2_commands as commands
from . import m2_queries as queries
from .m2_common import object_view, owned
from .models_m2 import Action, GraphLayout, GraphNode, GraphRelation, Reflection, ResearchItem
from .schemas import VersionInput
from .schemas_m2 import (
    ActionCreate,
    ActionEdit,
    ActionOut,
    CompleteInput,
    ContextOut,
    GraphOut,
    HistoryOut,
    ItemCreate,
    ItemEdit,
    ItemOut,
    Kind,
    LayoutInput,
    LayoutOut,
    MaterialOut,
    NodeOut,
    Page,
    ReflectionCreate,
    ReflectionEdit,
    ReflectionOut,
    RelationCreate,
    RelationEdit,
    RelationOut,
    ReopenInput,
    ReviewInput,
)
from .security import Identity, Problem, current_user, db_session

Db = Annotated[Session, Depends(db_session)]
Who = Annotated[Identity, Depends(current_user)]
Scope = Literal["all", "project", "unassigned"]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
router = APIRouter(prefix="/api/v1", tags=["M2"])


def finish(db, obj):
    db.flush()
    value = object_view(db, obj)
    db.commit()
    return value


@router.get("/research-items", response_model=Page[ItemOut])
def list_items(
    db: Db,
    who: Who,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    q: str = "",
    kind: Kind | None = None,
    status: str | None = None,
    priority: Literal["high", "normal", "low"] | None = None,
    project_id: UUID | None = None,
    unassigned: bool = False,
    deleted: bool = False,
):
    return queries.page_objects(
        db,
        who.user.id,
        ResearchItem,
        page,
        page_size,
        q,
        project_id,
        unassigned,
        deleted,
        status,
        kind,
        priority,
    )


@router.post("/research-items", response_model=ItemOut, status_code=201)
def create_item(value: ItemCreate, db: Db, who: Who):
    return finish(db, commands.item_save(db, who.user.id, value))


@router.patch("/research-items/{object_id}", response_model=ItemOut)
def edit_item(object_id: UUID, value: ItemEdit, db: Db, who: Who):
    return finish(db, commands.item_save(db, who.user.id, value, str(object_id)))


@router.post("/research-items/{object_id}/review", response_model=ItemOut)
def review_item(object_id: UUID, value: ReviewInput, db: Db, who: Who):
    return finish(db, commands.review(db, who.user.id, ResearchItem, object_id, value))


@router.get("/relations", response_model=Page[RelationOut])
def list_relations(
    db: Db,
    who: Who,
    node_id: UUID | None = None,
    deleted: bool = False,
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    conditions = [
        GraphRelation.owner_id == who.user.id,
        GraphRelation.deleted_at.is_not(None) if deleted else GraphRelation.deleted_at.is_(None),
    ]
    if node_id:
        owned(db, GraphNode, who.user.id, node_id)
        conditions.append(
            or_(GraphRelation.source_id == str(node_id), GraphRelation.target_id == str(node_id))
        )
    total = db.scalar(select(func.count()).select_from(GraphRelation).where(*conditions))
    rows = db.scalars(
        select(GraphRelation)
        .where(*conditions)
        .order_by(GraphRelation.updated_at.desc(), GraphRelation.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [object_view(db, r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/relations", response_model=RelationOut, status_code=201)
def create_relation(value: RelationCreate, db: Db, who: Who):
    return finish(db, commands.relation_save(db, who.user.id, value))


@router.patch("/relations/{object_id}", response_model=RelationOut)
def edit_relation(object_id: UUID, value: RelationEdit, db: Db, who: Who):
    return finish(db, commands.relation_save(db, who.user.id, value, str(object_id)))


@router.post("/relations/{object_id}/review", response_model=RelationOut)
def review_relation(object_id: UUID, value: ReviewInput, db: Db, who: Who):
    return finish(db, commands.review(db, who.user.id, GraphRelation, object_id, value))


@router.get("/graph", response_model=GraphOut)
def graph(
    db: Db,
    who: Who,
    scope: Scope = "all",
    project_id: UUID | None = None,
    q: str = "",
    kind: Literal["record", "question", "finding", "direction"] | None = None,
    status: str | None = None,
    needs_review: bool = False,
    focus_node_id: UUID | None = None,
    depth: Annotated[int, Query(ge=1, le=3)] = 1,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=150)] = 150,
):
    return queries.graph(
        db,
        who.user.id,
        scope,
        project_id,
        q,
        kind,
        status,
        needs_review,
        focus_node_id,
        depth,
        include_archived,
        limit,
    )


@router.get("/graph/candidates", response_model=Page[NodeOut])
def candidates(
    db: Db,
    who: Who,
    q: str = "",
    kind: Literal["record", "question", "finding", "direction"] | None = None,
    project_id: UUID | None = None,
    unassigned: bool = False,
    unlinked: bool = False,
    include_archived: bool = False,
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    return queries.candidates(
        db,
        who.user.id,
        q,
        kind,
        project_id,
        unassigned,
        unlinked,
        include_archived,
        page,
        page_size,
    )


@router.get("/graph/layout", response_model=LayoutOut)
def get_layout(db: Db, who: Who, scope: Scope = "all", project_id: UUID | None = None):
    return queries.layout_get(db, who.user.id, scope, project_id)


@router.put("/graph/layout", response_model=LayoutOut)
def save_layout(value: LayoutInput, db: Db, who: Who):
    key = queries.scope_key(db, who.user.id, value.scope, value.project_id)
    for node_id in value.positions:
        owned(db, GraphNode, who.user.id, node_id)
    positions = {str(k): v.model_dump() for k, v in value.positions.items()}
    obj = db.scalar(
        select(GraphLayout).where(GraphLayout.owner_id == who.user.id, GraphLayout.scope_key == key)
    )
    if obj:
        result = db.execute(
            update(GraphLayout)
            .where(GraphLayout.id == obj.id, GraphLayout.version == value.expected_version)
            .values(positions={**obj.positions, **positions}, version=value.expected_version + 1)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise Problem(409, "version_conflict", "布局已在其他页面更新，请重新载入布局")
        db.refresh(obj)
    else:
        if value.expected_version != 0:
            raise Problem(409, "version_conflict", "布局版本已变化")
        obj = GraphLayout(owner_id=who.user.id, scope_key=key, positions=positions)
        db.add(obj)
        db.flush()
    result = {"version": obj.version, "positions": obj.positions}
    db.commit()
    return result


@router.get("/actions", response_model=Page[ActionOut])
def list_actions(
    db: Db,
    who: Who,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    q: str = "",
    status: str | None = None,
    project_id: UUID | None = None,
    unassigned: bool = False,
    deleted: bool = False,
    direction_id: UUID | None = None,
):
    return queries.page_objects(
        db,
        who.user.id,
        Action,
        page,
        page_size,
        q,
        project_id,
        unassigned,
        deleted,
        status,
        direction_id=direction_id,
    )


@router.post("/actions", response_model=ActionOut, status_code=201)
def create_action(value: ActionCreate, db: Db, who: Who):
    return finish(db, commands.action_save(db, who.user.id, value))


@router.patch("/actions/{object_id}", response_model=ActionOut)
def edit_action(object_id: UUID, value: ActionEdit, db: Db, who: Who):
    return finish(db, commands.action_save(db, who.user.id, value, str(object_id)))


@router.post("/actions/{object_id}/complete", response_model=ActionOut)
def complete_action(object_id: UUID, value: CompleteInput, db: Db, who: Who):
    return finish(db, commands.complete(db, who.user.id, object_id, value))


@router.post("/actions/{object_id}/reopen", response_model=ActionOut)
def reopen_action(object_id: UUID, value: ReopenInput, db: Db, who: Who):
    return finish(db, commands.reopen(db, who.user.id, object_id, value))


@router.get("/reflections/materials", response_model=Page[MaterialOut])
def reflection_materials(
    db: Db,
    who: Who,
    start_at: datetime,
    end_at: datetime,
    project_id: UUID | None = None,
    q: str = "",
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise Problem(422, "invalid_range", "时间必须包含时区")
    return queries.materials(
        db,
        who.user.id,
        start_at.astimezone(timezone.utc).isoformat(),
        end_at.astimezone(timezone.utc).isoformat(),
        project_id,
        q,
        page,
        page_size,
    )


@router.get("/reflections", response_model=Page[ReflectionOut])
def list_reflections(
    db: Db,
    who: Who,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    q: str = "",
    kind: Literal["attempt", "period"] | None = None,
    project_id: UUID | None = None,
    unassigned: bool = False,
    deleted: bool = False,
):
    return queries.page_objects(
        db, who.user.id, Reflection, page, page_size, q, project_id, unassigned, deleted, kind=kind
    )


@router.post("/reflections", response_model=ReflectionOut, status_code=201)
def create_reflection(value: ReflectionCreate, db: Db, who: Who):
    return finish(db, commands.reflection_save(db, who.user.id, value))


@router.patch("/reflections/{object_id}", response_model=ReflectionOut)
def edit_reflection(object_id: UUID, value: ReflectionEdit, db: Db, who: Who):
    return finish(db, commands.reflection_save(db, who.user.id, value, str(object_id)))


@router.get("/records/{record_id}/context", response_model=ContextOut)
def record_context(record_id: UUID, db: Db, who: Who):
    return queries.record_context(db, who.user.id, record_id)


# Identical ownership/version lifecycle for each business aggregate.
def lifecycle(path, model, out):
    def detail(object_id: UUID, db: Db, who: Who, include_deleted: bool = False):
        return object_view(db, owned(db, model, who.user.id, object_id, include_deleted))

    def delete(object_id: UUID, value: VersionInput, db: Db, who: Who):
        return finish(
            db,
            commands.set_deleted(db, who.user.id, model, object_id, value.expected_version, True),
        )

    def restore(object_id: UUID, value: VersionInput, db: Db, who: Who):
        return finish(
            db,
            commands.set_deleted(db, who.user.id, model, object_id, value.expected_version, False),
        )

    def revisions(object_id: UUID, db: Db, who: Who):
        return queries.history(db, who.user.id, model, object_id)

    for suffix, method, fn, response in [
        ("", "GET", detail, out),
        ("", "DELETE", delete, out),
        ("/restore", "POST", restore, out),
        ("/revisions", "GET", revisions, list[HistoryOut]),
    ]:
        router.add_api_route(
            path + "/{object_id}" + suffix,
            fn,
            methods=[method],
            response_model=response,
            name=model.__name__ + "_" + fn.__name__,
        )


for path, model, out in [
    ("/research-items", ResearchItem, ItemOut),
    ("/relations", GraphRelation, RelationOut),
    ("/actions", Action, ActionOut),
    ("/reflections", Reflection, ReflectionOut),
]:
    lifecycle(path, model, out)
