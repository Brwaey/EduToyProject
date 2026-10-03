from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from . import growth_commands as commands
from . import growth_data as data
from . import growth_queries as queries
from .m2_common import object_view as action_view
from .m2_common import owned
from .models_growth import AbilityTag, Contribution, GrowthEntry
from .schemas import VersionInput
from .schemas_growth import (
    AbilityTagOut,
    ContributionCreate,
    ContributionEdit,
    ContributionType,
    GrowthActionCreate,
    GrowthContextOut,
    GrowthCreate,
    GrowthEdit,
    GrowthHistoryOut,
    GrowthKind,
    GrowthMaterialOut,
    GrowthObjectOut,
    GrowthPage,
    GrowthReview,
    MaterialPage,
    TagCreate,
    TagEdit,
)
from .schemas_m2 import ActionOut
from .security import Identity, current_user, db_session

Db = Annotated[Session, Depends(db_session)]
Who = Annotated[Identity, Depends(current_user)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
router = APIRouter(prefix="/api/v1", tags=["M4 Growth"])


def filters(
    q: str = "",
    project_id: UUID | None = None,
    unassigned: bool = False,
    deleted: bool = False,
    include_archived: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
    evidence_status: Literal["self_report", "attached", "needs_review", "unavailable"]
    | None = None,
):
    return dict(
        q=q,
        project_id=project_id,
        unassigned=unassigned,
        deleted=deleted,
        include_archived=include_archived,
        date_from=date_from,
        date_to=date_to,
        evidence_status=evidence_status,
    )


@router.get("/contributions", response_model=GrowthPage)
def contributions(
    db: Db,
    who: Who,
    f: Annotated[dict, Depends(filters)],
    page: PageNumber = 1,
    page_size: PageSize = 20,
    contribution_type: ContributionType | None = None,
):
    return queries.page(
        db, who.user.id, Contribution, page, page_size, contribution_type=contribution_type, **f
    )


@router.get("/growth-entries", response_model=GrowthPage)
def entries(
    db: Db,
    who: Who,
    f: Annotated[dict, Depends(filters)],
    page: PageNumber = 1,
    page_size: PageSize = 20,
    kind: GrowthKind | None = None,
    tag_id: UUID | None = None,
):
    return queries.page(
        db, who.user.id, GrowthEntry, page, page_size, kind=kind, tag_id=tag_id, **f
    )


def finish(db, obj):
    result = data.object_view(db, obj)
    db.commit()
    return result


@router.post("/contributions", response_model=GrowthObjectOut, status_code=201)
def create_contribution(value: ContributionCreate, db: Db, who: Who):
    return finish(db, commands.contribution_save(db, who.user.id, value))


@router.patch("/contributions/{object_id}", response_model=GrowthObjectOut)
def edit_contribution(object_id: UUID, value: ContributionEdit, db: Db, who: Who):
    return finish(db, commands.contribution_save(db, who.user.id, value, str(object_id)))


@router.post("/growth-entries", response_model=GrowthObjectOut, status_code=201)
def create_entry(value: GrowthCreate, db: Db, who: Who):
    return finish(db, commands.entry_save(db, who.user.id, value))


@router.patch("/growth-entries/{object_id}", response_model=GrowthObjectOut)
def edit_entry(object_id: UUID, value: GrowthEdit, db: Db, who: Who):
    return finish(db, commands.entry_save(db, who.user.id, value, str(object_id)))


@router.get("/ability-tags", response_model=list[AbilityTagOut])
def tags(db: Db, who: Who, f: Annotated[dict, Depends(filters)], archived: bool = False):
    return queries.tag_list(db, who.user.id, archived, **f)


def finish_tag(db, obj):
    result = {k: v for k, v in data.columns(obj).items() if k != "deleted_at"}
    db.commit()
    return result


@router.post("/ability-tags", response_model=AbilityTagOut, status_code=201)
def create_tag(value: TagCreate, db: Db, who: Who):
    return finish_tag(db, commands.tag_save(db, who.user.id, value))


@router.patch("/ability-tags/{object_id}", response_model=AbilityTagOut)
def edit_tag(object_id: UUID, value: TagEdit, db: Db, who: Who):
    return finish_tag(db, commands.tag_save(db, who.user.id, value, str(object_id)))


@router.get("/ability-tags/{object_id}/revisions", response_model=list[GrowthHistoryOut])
def tag_history(object_id: UUID, db: Db, who: Who):
    return data.history(db, who.user.id, AbilityTag, object_id)


@router.get("/growth/materials", response_model=MaterialPage)
def materials(
    db: Db,
    who: Who,
    q: str = "",
    project_id: UUID | None = None,
    kind: Literal["record", "action", "reflection", "contribution"] | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    return queries.materials(db, who.user.id, q, project_id, kind, page, page_size)


@router.get("/growth/material", response_model=GrowthMaterialOut)
def material(
    db: Db,
    who: Who,
    kind: Literal[
        "record", "action", "reflection", "contribution", "growth_entry", "research_item"
    ],
    id: UUID,
    revision_id: UUID,
):
    return data.material_view(db, who.user.id, kind, id, revision_id)


@router.get("/growth/context", response_model=GrowthContextOut)
def context(
    db: Db, who: Who, kind: Literal["record", "action", "reflection", "research_item"], id: UUID
):
    return queries.context(db, who.user.id, kind, id)


def lifecycle(path, model):
    def detail(object_id: UUID, db: Db, who: Who, include_deleted: bool = False):
        return data.object_view(db, owned(db, model, who.user.id, object_id, include_deleted))

    def remove(object_id: UUID, value: VersionInput, db: Db, who: Who):
        return finish(
            db, commands.lifecycle(db, who.user.id, model, object_id, value.expected_version, True)
        )

    def restore(object_id: UUID, value: VersionInput, db: Db, who: Who):
        return finish(
            db, commands.lifecycle(db, who.user.id, model, object_id, value.expected_version, False)
        )

    def revisions(object_id: UUID, db: Db, who: Who):
        return data.history(db, who.user.id, model, object_id)

    def review(object_id: UUID, value: GrowthReview, db: Db, who: Who):
        return finish(db, commands.review(db, who.user.id, model, object_id, value))

    def action(object_id: UUID, value: GrowthActionCreate, db: Db, who: Who):
        result = action_view(db, commands.create_action(db, who.user.id, model, object_id, value))
        db.commit()
        return result

    for suffix, method, handler, response in [
        ("", "GET", detail, GrowthObjectOut),
        ("", "DELETE", remove, GrowthObjectOut),
        ("/restore", "POST", restore, GrowthObjectOut),
        ("/revisions", "GET", revisions, list[GrowthHistoryOut]),
        ("/review", "POST", review, GrowthObjectOut),
        ("/actions", "POST", action, ActionOut),
    ]:
        router.add_api_route(
            path + "/{object_id}" + suffix,
            handler,
            methods=[method],
            response_model=response,
            name=model.__name__ + "_" + handler.__name__,
        )


lifecycle("/contributions", Contribution)
lifecycle("/growth-entries", GrowthEntry)
