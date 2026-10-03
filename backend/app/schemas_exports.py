from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .schemas import Input as StrictModel

ExportKind = Literal[
    "project",
    "record",
    "research_item",
    "relation",
    "action",
    "reflection",
    "contribution",
    "growth_entry",
    "ability_tag",
]


class ExportRef(StrictModel):
    kind: ExportKind
    id: UUID


class ExportSelection(StrictModel):
    format: Literal["json", "markdown"] = "json"
    scope: Literal["all", "projects", "unassigned", "selected"] = "all"
    project_ids: list[UUID] = Field(default_factory=list, max_length=100)
    objects: list[ExportRef] = Field(default_factory=list, max_length=5000)
    types: list[ExportKind] = Field(default_factory=list)
    include_archived: bool = False

    @model_validator(mode="after")
    def scope_rules(self):
        if self.scope == "projects" and not self.project_ids:
            raise ValueError("请选择至少一个项目")
        if self.scope == "selected" and not self.objects:
            raise ValueError("请选择至少一个对象")
        if self.scope != "projects" and self.project_ids:
            raise ValueError("当前范围不接受项目列表")
        if self.scope != "selected" and self.objects:
            raise ValueError("当前范围不接受对象列表")
        if self.format == "markdown" and any(
            k not in ("record", "reflection")
            for k in [*self.types, *(r.kind for r in self.objects)]
        ):
            raise ValueError("Markdown 仅支持科研记录与复盘")
        if self.types and any(r.kind not in self.types for r in self.objects):
            raise ValueError("所选对象不属于当前导出类型")
        return self


class ExportDownload(ExportSelection):
    fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]+$")


class ExportPreview(StrictModel):
    fingerprint: str
    counts: dict[str, int]
    fixed_versions: int
    entries: int
    bytes: int
    cross_project_evidence: list[dict]
    archived_content: list[dict]
    unavailable: list[dict]
    selection: dict
    filename: str


class ExportCandidates(StrictModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
