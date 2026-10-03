from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .schemas import Input, VersionInput
from .schemas_m2 import ActionCreate, Page

ContributionType = Literal[
    "question", "choice", "correction", "validation", "understanding", "connection"
]
GrowthKind = Literal["ability_instance", "understanding_change"]
Text = Annotated[str, Field(max_length=20000)]


class GrowthEvidenceInput(Input):
    record_revision_id: UUID | None = None
    m2_revision_id: UUID | None = None
    contribution_revision_id: UUID | None = None
    source_version_id: UUID | None = None
    field_path: str = Field(default="body", max_length=100)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    quote: Text = ""
    purpose: Literal["context", "before", "trigger", "after"] = "context"

    @model_validator(mode="after")
    def valid(self):
        if (
            sum(
                x is not None
                for x in (
                    self.record_revision_id,
                    self.m2_revision_id,
                    self.contribution_revision_id,
                )
            )
            != 1
        ):
            raise ValueError("请选择一种固定版本依据")
        if (self.start is None) != (self.end is None) or (
            self.start is not None and self.end <= self.start
        ):
            raise ValueError("片段范围无效")
        if not self.record_revision_id and (
            self.source_version_id or self.start is not None or self.quote
        ):
            raise ValueError("行动、复盘和贡献使用完整快照引用")
        return self


class ContributionDetails(Input):
    personal_role: Text = ""
    reason: Text = ""
    ai_help: Text = ""
    others_help: Text = ""
    impact: Text = ""
    next_steps: Text = ""


class GrowthBase(Input):
    title: str = Field(min_length=1, max_length=200)
    occurred_on: date
    project_id: UUID | None = None
    question_id: UUID | None = None
    evidence: list[GrowthEvidenceInput] = Field(default_factory=list, max_length=50)

    @field_validator("title")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("请填写一句话标题")
        return value.strip()


class ContributionInput(GrowthBase):
    contribution_type: ContributionType = "choice"
    details: ContributionDetails = Field(default_factory=ContributionDetails)
    confirmed: Literal[True]


class ContributionCreate(ContributionInput):
    request_id: UUID


class ContributionEdit(ContributionInput, VersionInput):
    pass


class AbilityDetails(Input):
    kind: Literal["ability_instance"] = "ability_instance"
    situation: Text = ""
    attempts: Text = ""
    learned: Text = ""
    completion_mode: Literal["unspecified", "assisted", "independent", "transferred"] = (
        "unspecified"
    )
    basis_type: Literal["self_report", "material", "task_practice"] = "self_report"
    difficulties: Text = ""
    next_steps: Text = ""


class UnderstandingDetails(Input):
    kind: Literal["understanding_change"] = "understanding_change"
    before: Text
    after: Text
    trigger: Text = ""
    uncertainty: Text = ""
    next_steps: Text = ""

    @field_validator("before", "after")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("请分别填写之前和现在的理解")
        return value


class GrowthInput(GrowthBase):
    kind: GrowthKind
    details: Annotated[AbilityDetails | UnderstandingDetails, Field(discriminator="kind")]
    tag_ids: list[UUID] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def valid(self):
        if self.kind != self.details.kind:
            raise ValueError("成长类型与字段不一致")
        if self.kind == "ability_instance" and not self.tag_ids:
            raise ValueError("请选择至少一个能力标签")
        if self.kind == "understanding_change" and self.tag_ids:
            raise ValueError("理解变化不设置能力标签")
        return self


class GrowthCreate(GrowthInput):
    request_id: UUID


class GrowthEdit(GrowthInput, VersionInput):
    pass


class TagInput(Input):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=2000)
    archived: bool = False

    @field_validator("name")
    @classmethod
    def nonempty(cls, v):
        if not v.strip():
            raise ValueError("标签名称不能为空")
        return v.strip()


class TagCreate(TagInput):
    request_id: UUID


class TagEdit(TagInput, VersionInput):
    pass


class GrowthReview(VersionInput):
    current_versions: dict[str, int]


class GrowthActionCreate(VersionInput):
    request_id: UUID
    revision_id: UUID
    action: ActionCreate


class GrowthMaterialOut(Input):
    kind: str
    id: str
    revision_id: str
    title: str
    version: int
    deleted: bool
    archived: bool
    occurred_on: str | None = None
    snapshot: dict | None
    needs_review: bool = False


class GrowthEvidenceOut(GrowthEvidenceInput):
    id: str
    reviewed_version: int
    reviewed_dependencies: dict[str, int] = Field(default_factory=dict)
    source: GrowthMaterialOut
    current_version: int
    availability: Literal["available", "deleted"]
    needs_review: bool
    content: str | None


class GrowthObjectOut(Input):
    id: str
    version: int
    created_at: str
    updated_at: str
    deleted_at: str | None
    title: str
    occurred_on: str
    project_id: str | None
    question_id: str | None
    question_title: str | None
    archived: bool
    kind: str
    contribution_type: str | None = None
    confirmed_at: str | None = None
    details: dict
    evidence: list[GrowthEvidenceOut]
    tags: list[dict] = Field(default_factory=list)
    evidence_status: Literal["self_report", "attached", "needs_review", "unavailable"]
    needs_review: bool
    current_versions: dict[str, int]
    revision_id: str
    actions: list[dict] = Field(default_factory=list)


class AbilityTagOut(Input):
    id: str
    version: int
    name: str
    description: str
    archived: bool
    created_at: str
    updated_at: str
    instance_count: int = 0
    latest_instance: dict | None = None


class GrowthHistoryOut(Input):
    id: str
    version: int
    operation: str
    created_at: str
    snapshot: dict


class GrowthContextOut(Input):
    contributions: list[GrowthObjectOut]
    entries: list[GrowthObjectOut]


GrowthPage = Page[GrowthObjectOut]
MaterialPage = Page[GrowthMaterialOut]
