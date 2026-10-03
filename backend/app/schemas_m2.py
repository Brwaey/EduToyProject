from datetime import date, datetime, timezone
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from .schemas import Input, RecordCreate, VersionInput

Kind = Literal["question", "finding", "direction"]
RelationType = Literal[
    "related", "subquestion", "derived_from", "tests", "supports", "challenges", "extends", "reuses"
]
ActionStatus = Literal["planned", "in_progress", "blocked", "paused", "completed", "cancelled"]
ShortText = Annotated[str, Field(max_length=20000)]


class QuestionDetails(Input):
    kind: Literal["question"] = "question"
    motivation: ShortText = ""
    hypothesis: ShortText = ""
    uncertainty: ShortText = ""


class FindingDetails(Input):
    kind: Literal["finding"] = "finding"
    statement_type: Literal["observation", "interpretation", "hypothesis"] = "observation"
    conditions: ShortText = ""
    uncertainty: ShortText = ""


class DirectionDetails(Input):
    kind: Literal["direction"] = "direction"
    question: ShortText = ""
    rationale: ShortText = ""
    supporting: ShortText = ""
    opposing: ShortText = ""
    uncertainty: ShortText = ""
    resources: ShortText = ""
    effort: ShortText = ""
    minimal_action: ShortText = ""
    priority: Literal["high", "normal", "low"] = "normal"
    pause_reason: ShortText = ""
    restart_condition: ShortText = ""


ItemDetails = Annotated[
    QuestionDetails | FindingDetails | DirectionDetails, Field(discriminator="kind")
]
ITEM_STATUSES = {
    "question": ("exploring", "paused", "answered"),
    "finding": ("tentative", "reviewed", "withdrawn"),
    "direction": ("candidate", "focus", "paused", "closed"),
}


class EvidenceInput(Input):
    record_revision_id: UUID
    source_version_id: UUID | None = None
    field_path: str = Field(default="body", max_length=100)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    quote: str = Field(default="", max_length=20000)
    stance: Literal["context", "supporting", "opposing"] = "context"

    @model_validator(mode="after")
    def positions(self):
        if (self.start is None) != (self.end is None):
            raise ValueError("引用起止位置必须同时填写")
        if self.start is not None and self.end <= self.start:
            raise ValueError("引用结束位置必须晚于起点")
        if self.quote and self.start is None:
            raise ValueError("引用片段需要提供位置")
        return self


class ItemInput(Input):
    kind: Kind
    title: str = Field(min_length=1, max_length=200)
    project_id: UUID | None = None
    description: ShortText = ""
    status: str = ""
    details: ItemDetails
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def valid(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("标题不能为空")
        if self.details.kind != self.kind:
            raise ValueError("内容类型不匹配")
        if not self.status:
            self.status = ITEM_STATUSES[self.kind][0]
        if self.status not in ITEM_STATUSES[self.kind]:
            raise ValueError("状态不适用于该类型")
        if self.kind == "finding" and self.status == "reviewed" and not self.evidence:
            raise ValueError("已核对的发现至少需要一项证据")
        return self


class ItemCreate(ItemInput):
    request_id: UUID


class ItemEdit(ItemInput, VersionInput):
    pass


class ObjectRef(Input):
    kind: Literal["record", "research_item"]
    id: UUID


class RelationInput(Input):
    source: ObjectRef
    target: ObjectRef
    relation_type: RelationType = "related"
    reason: ShortText = ""
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def valid(self):
        if self.relation_type != "related" and not self.reason.strip():
            raise ValueError("请填写关系理由")
        if self.source == self.target:
            raise ValueError("不能关联对象自身")
        return self


class RelationCreate(RelationInput):
    request_id: UUID


class RelationEdit(RelationInput, VersionInput):
    pass


class ReviewInput(VersionInput):
    evidence: list[EvidenceInput] | None = Field(default=None, max_length=50)


class ActionDetails(Input):
    research_goal: ShortText = ""
    learning_goal: ShortText = ""
    completion_criteria: ShortText = ""
    expected_date: date | None = None
    effort: ShortText = ""
    pause_reason: ShortText = ""
    restart_condition: ShortText = ""


class ResultRef(Input):
    record_id: UUID
    record_revision_id: UUID


class ActionInput(Input):
    title: str = Field(min_length=1, max_length=200)
    project_id: UUID | None = None
    direction_id: UUID | None = None
    origin_reflection_id: UUID | None = None
    status: ActionStatus = "planned"
    details: ActionDetails = Field(default_factory=ActionDetails)
    results: list[ResultRef] = Field(default_factory=list, max_length=100)

    @field_validator("title")
    @classmethod
    def nonempty(cls, v):
        if not v.strip():
            raise ValueError("标题不能为空")
        return v.strip()


class ActionCreate(ActionInput):
    request_id: UUID


class ActionEdit(ActionInput, VersionInput):
    pass


class CompleteInput(VersionInput):
    request_id: UUID
    result_summary: str = Field(min_length=1, max_length=20000)
    records: list[ResultRef] = Field(default_factory=list, max_length=100)
    new_record: RecordCreate | None = None
    link_direction: bool = False

    @field_validator("result_summary")
    @classmethod
    def nonempty(cls, v):
        if not v.strip():
            raise ValueError("请填写一句结果说明")
        return v.strip()


class ReopenInput(VersionInput):
    request_id: UUID
    reason: str = Field(min_length=1, max_length=20000)

    @field_validator("reason")
    @classmethod
    def nonempty(cls, v):
        if not v.strip():
            raise ValueError("请填写重新开启的原因")
        return v.strip()


class MaterialRef(Input):
    kind: Literal["record", "action", "research_item"]
    id: UUID
    revision_id: UUID


class ReflectionDetails(Input):
    expectations: ShortText = ""
    actual: ShortText = ""
    known: ShortText = ""
    unknown: ShortText = ""
    explanations: ShortText = ""
    reusable: ShortText = ""
    progress: ShortText = ""
    understanding: ShortText = ""
    blockers: ShortText = ""
    next_steps: ShortText = ""
    decision: Literal["continue", "adjust", "pause", "finish"] = "continue"
    reason: ShortText = ""
    restart_condition: ShortText = ""


class ReflectionInput(Input):
    kind: Literal["attempt", "period"]
    title: str = Field(min_length=1, max_length=200)
    project_id: UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str = Field(default="UTC", max_length=80)
    details: ReflectionDetails = Field(default_factory=ReflectionDetails)
    materials: list[MaterialRef] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def valid(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("标题不能为空")
        if self.kind == "period" and (not self.start_at or not self.end_at):
            raise ValueError("周期复盘需要日期范围")
        if bool(self.start_at) != bool(self.end_at):
            raise ValueError("起止时间必须同时提供")
        if self.start_at:
            if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
                raise ValueError("时间必须包含时区")
            self.start_at = self.start_at.astimezone(timezone.utc)
            self.end_at = self.end_at.astimezone(timezone.utc)
            if self.end_at <= self.start_at:
                raise ValueError("结束时间必须晚于开始时间")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("时区无效") from None
        return self


class ReflectionCreate(ReflectionInput):
    request_id: UUID


class ReflectionEdit(ReflectionInput, VersionInput):
    pass


class Position(Input):
    x: float = Field(ge=-1000000, le=1000000, allow_inf_nan=False)
    y: float = Field(ge=-1000000, le=1000000, allow_inf_nan=False)


class LayoutInput(Input):
    scope: Literal["all", "project", "unassigned"] = "all"
    project_id: UUID | None = None
    expected_version: int = Field(ge=0)
    positions: dict[UUID, Position] = Field(max_length=150)


# Explicit response models also serve the generated TypeScript contract.
class EvidenceOut(BaseModel):
    id: str
    record_revision_id: str
    source_version_id: str | None
    record_id: str
    record_title: str
    record_version: int
    field_path: str
    start: int | None
    end: int | None
    quote: str
    stance: str
    availability: Literal["available", "deleted"]
    needs_review: bool
    content: str


class VersionedOut(BaseModel):
    id: str
    version: int
    created_at: str
    updated_at: str
    deleted_at: str | None
    archived: bool = False


class ItemOut(VersionedOut):
    kind: Kind
    title: str
    project_id: str | None
    description: str
    status: str
    details: ItemDetails
    evidence: list[EvidenceOut]
    needs_review: bool


class NodeOut(BaseModel):
    id: str
    object_id: str
    object_kind: Literal["record", "research_item"]
    kind: Literal["record", "question", "finding", "direction"]
    title: str
    project_id: str | None
    project_name: str
    status: str
    version: int
    archived: bool
    external: bool = False


class RelationOut(VersionedOut):
    source_id: str
    target_id: str
    source: NodeOut | None
    target: NodeOut | None
    relation_type: RelationType
    reason: str
    source_version: int
    target_version: int
    evidence: list[EvidenceOut]
    needs_review: bool
    available: bool


class ResultOut(BaseModel):
    record_id: str
    record_revision_id: str
    title: str
    version: int
    deleted: bool
    snapshot: dict | None


class ActionOut(VersionedOut):
    title: str
    project_id: str | None
    direction_id: str | None
    direction_title: str | None
    direction_deleted: bool
    origin_reflection_id: str | None
    status: ActionStatus
    details: ActionDetails
    result_summary: str
    completed_at: str | None
    results: list[ResultOut]


class MaterialOut(BaseModel):
    kind: str
    id: str
    revision_id: str
    title: str
    version: int
    deleted: bool
    snapshot: dict | None


class ReflectionOut(VersionedOut):
    title: str
    project_id: str | None
    kind: Literal["attempt", "period"]
    start_at: str | None
    end_at: str | None
    timezone: str
    details: ReflectionDetails
    materials: list[MaterialOut]


class HistoryOut(BaseModel):
    id: str
    version: int
    operation: str
    created_at: str
    snapshot: dict


class LayoutOut(BaseModel):
    version: int
    positions: dict[str, Position]


class GraphOut(BaseModel):
    nodes: list[NodeOut]
    edges: list[RelationOut]
    total_nodes: int
    truncated: bool


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class ContextOut(BaseModel):
    relations: list[RelationOut]
    actions: list[ActionOut]
    reflections: list[ReflectionOut]
