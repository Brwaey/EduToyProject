from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from . import export_data
from .schemas_exports import ExportCandidates, ExportDownload, ExportPreview, ExportSelection
from .security import Identity, Problem, current_user, db_session

router = APIRouter(prefix="/api/v1/exports", tags=["M5 business export"])
Db = Annotated[Session, Depends(db_session)]
Who = Annotated[Identity, Depends(current_user)]


@router.get("/candidates", response_model=ExportCandidates)
def candidates(
    db: Db,
    who: Who,
    kind: str = "record",
    q: str = "",
    include_archived: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return export_data.candidates(db, who.user.id, kind, q, include_archived, page, page_size)


@router.post("/preview", response_model=ExportPreview)
def preview(value: ExportSelection, db: Db, who: Who):
    result, _ = export_data.build(db, who.user.id, value)
    db.rollback()  # End the explicit read snapshot before serializing/transmitting.
    return result


@router.post(
    "/download",
    response_class=Response,
    responses={
        200: {
            "description": "预览对应的业务文件",
            "content": {
                "application/json": {"schema": {"type": "string", "format": "binary"}},
                "text/markdown": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
)
def download(value: ExportDownload, db: Db, who: Who):
    preview, content = export_data.build(db, who.user.id, value)
    db.rollback()
    if preview["fingerprint"] != value.fingerprint:
        raise Problem(409, "export_changed", "内容或引用状态已变化，请重新预览后下载")
    return Response(
        content,
        media_type="application/json" if value.format == "json" else "text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{preview["filename"]}"'},
    )
