from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .schemas import Input, VersionInput
from .schemas_growth import ContributionInput, ContributionType
from .schemas_m2 import ActionDetails, RelationType

TaskKind = Literal[
    "record_draft",
    "relation_suggestions",
    "contribution_candidates",
    "connection_test",
    "action_candidates",
    "reflection_draft",
]
DraftField = Literal[
    "title",
    "record_type",
    "context",
    "actions",
    "collaboration",
    "observations",
    "interpretation",
    "next_steps",
]


def normalize_url(value: str) -> str:
    try:
        p = urlsplit(value.strip())
        port = p.port
        if (
            not p.hostname
            or p.username
            or p.password
            or p.query
            or p.fragment
            or "?" in value
            or "#" in value
            or "\\" in value
            or any(c.isspace() for c in value.strip())
        ):
            raise ValueError()
        if p.scheme != "https" and not (
            p.scheme == "http" and p.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError()
        if port is not None and port < 1:
            raise ValueError()
        path = p.path.rstrip("/")
        if not path.endswith("/chat/completions"):
            path += "/chat/completions"
        return urlunsplit((p.scheme, p.netloc, path, "", ""))
    except ValueError:
        raise ValueError(
            "请输入 HTTPS 地址或本机 HTTP 地址，不能包含凭据、查询参数或片段"
        ) from None


class ConfigSave(Input):
    expected_version: int = Field(ge=0)
    url: str = Field(max_length=2048)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=8192, repr=False)

    @field_validator("url")
    @classmethod
    def url_valid(cls, value):
        return normalize_url(value)

    @field_validator("model")
    @classmethod
    def model_valid(cls, value):
        if not value.strip():
            raise ValueError("模型名不能为空")
        return value

    @field_validator("api_key")
    @classmethod
    def key_valid(cls, value):
        if value is not None and (not value.strip() or "\n" in value or "\r" in value):
            raise ValueError("API Key 格式无效")
        return value


class MaterialPick(Input):
    field_path: str = Field(default="body", max_length=100)
    source_version_id: UUID | None = None
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def range_valid(self):
        if (self.start is None) != (self.end is None) or (
            self.start is not None and self.end <= self.start
        ):
            raise ValueError("片段范围无效")
        return self


class Selection(Input):
    kind: Literal["record", "research_item", "action", "reflection", "contribution", "growth_entry"]
    id: UUID
    version: int = Field(ge=1)
    revision_id: UUID | None = None
    current_version: int | None = Field(default=None, ge=1)
    materials: list[MaterialPick] = Field(min_length=1, max_length=30)


class PlanningParameters(Input):
    goal: str = Field(default="", max_length=4000)
    constraints: str = Field(default="", max_length=4000)


class PreviewInput(Input):
    kind: Literal[
        "record_draft",
        "relation_suggestions",
        "contribution_candidates",
        "action_candidates",
        "reflection_draft",
    ]
    parameters: PlanningParameters = Field(default_factory=PlanningParameters)
    target_reflection_id: UUID | None = None
    objects: list[Selection] = Field(min_length=1, max_length=20)


class TaskCreate(PreviewInput):
    request_id: UUID
    config_version: int = Field(ge=1)


class TaskRequest(Input):
    request_id: UUID
    config_version: int = Field(ge=1)


class Citation(Input):
    material: str = Field(max_length=10)
    quote: str = Field(default="", max_length=20000)
    occurrence: int = Field(default=1, ge=1, le=32000)


class FieldSuggestion(Input):
    value: str = Field(max_length=20000)
    citations: list[Citation] = Field(default_factory=list, max_length=20)


class DraftOutput(Input):
    fields: dict[DraftField, FieldSuggestion]
    questions: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_fields(self):
        if not self.fields or not any(v.value.strip() for v in self.fields.values()):
            raise ValueError("没有可用的整理字段")
        for key, value in self.fields.items():
            if value.value.strip() and not value.citations:
                raise ValueError("非空字段需要引用")
            if key == "title" and len(value.value) > 200:
                raise ValueError("标题过长")
            if key == "record_type" and value.value not in (
                "note",
                "paper",
                "experiment",
                "ai",
                "idea",
            ):
                raise ValueError("记录类型无效")
        return self


class RelationCandidate(Input):
    source: str = Field(max_length=10)
    target: str = Field(max_length=10)
    relation_type: RelationType
    reason: str = Field(min_length=1, max_length=20000)
    uncertainty: str = Field(default="", max_length=20000)
    citations: list[Citation] = Field(min_length=1, max_length=20)


class RelationsOutput(Input):
    relations: list[RelationCandidate] = Field(max_length=10)


ContributionField = Literal["title", "personal_role", "reason", "ai_help", "others_help", "impact"]


class ContributionCandidate(Input):
    contribution_type: ContributionType
    fields: dict[ContributionField, FieldSuggestion]
    uncertainty: str = Field(default="", max_length=20000)
    questions: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid(self):
        if (
            "title" not in self.fields
            or not self.fields["title"].value.strip()
            or len(self.fields["title"].value) > 200
        ):
            raise ValueError("贡献候选需要一句话标题")
        if any(f.value.strip() and not f.citations for f in self.fields.values()):
            raise ValueError("贡献事实字段需要原文引用")
        return self


class ContributionsOutput(Input):
    contributions: list[ContributionCandidate] = Field(max_length=10)


ReflectionField = Literal["progress", "understanding", "blockers", "next_steps"]


class ActionCandidate(Input):
    title: str = Field(min_length=1, max_length=200)
    research_goal: str = Field(min_length=1, max_length=20000)
    learning_goal: str = Field(default="", max_length=20000)
    completion_criteria: str = Field(min_length=1, max_length=20000)
    effort: str = Field(default="", max_length=20000)
    reason: str = Field(min_length=1, max_length=20000)
    uncertainty: str = Field(default="", max_length=20000)
    citations: list[Citation] = Field(min_length=1, max_length=20)

    @field_validator("title", "research_goal", "completion_criteria", "reason")
    @classmethod
    def nonempty(cls, v):
        if not v.strip():
            raise ValueError("行动标题、目标、标准和理由不能为空")
        return v


class ActionsOutput(Input):
    actions: list[ActionCandidate] = Field(max_length=5)


class ReflectionOutput(Input):
    fields: dict[ReflectionField, FieldSuggestion]
    questions: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid(self):
        if not self.fields and not self.questions:
            raise ValueError("请提供复盘草稿或待补充问题")
        if any(f.value.strip() and not f.citations for f in self.fields.values()):
            raise ValueError("非空复盘字段需要引用")
        return self


class ActionAcceptance(Input):
    title: str = Field(min_length=1, max_length=200)
    project_id: UUID | None = None
    direction_id: UUID | None = None
    origin_reflection_id: UUID | None = None
    details: ActionDetails


class ReflectionFieldAcceptance(Input):
    mode: Literal["append", "replace"]
    text: str = Field(max_length=20000)
    final_text: str = Field(max_length=20000)


class ReflectionAcceptance(VersionInput):
    fields: dict[ReflectionField, ReflectionFieldAcceptance]


class AcceptInput(VersionInput):
    current_versions: dict[str, int]
    reviewed: bool = False
    fields: dict[DraftField, str] | None = None
    relation: RelationCandidate | None = None
    contribution: ContributionInput | None = None
    action: ActionAcceptance | None = None
    reflection: ReflectionAcceptance | None = None


class BatchReject(Input):
    suggestions: dict[UUID, int] = Field(min_length=1, max_length=100)


class ConfigOut(Input):
    version: int
    endpoint: str
    model: str
    has_key: bool
    key_available: bool
    test_status: str


class AIMaterialOut(Input):
    key: str
    object_key: str
    field_path: str
    source_version_id: str | None
    text: str | None
    current_text: str | None
    unavailable: bool


class AIObjectOut(Input):
    key: str
    kind: str
    id: str
    title: str
    version: int
    current_version: int
    selected_current_version: int | None = None
    project_id: str | None
    deleted: bool
    archived: bool
    current: dict | None
    revision_id: str | None = None
    evidence_label: str | None = None


class PreviewOut(Input):
    parameters: dict = Field(default_factory=dict)
    objects: list[AIObjectOut]
    materials: list[AIMaterialOut]
    characters: int


class TaskOut(Input):
    id: str
    kind: TaskKind
    status: str
    model: str
    endpoint: str
    config_version: int
    parent_id: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    error_code: str | None
    error_message: str | None
    usage: dict | None
    parameters: dict = Field(default_factory=dict)
    target_reflection_id: str | None = None
    inputs: PreviewOut
    needs_review: bool
    unavailable: bool
    suggestion_ids: list[str]


class SuggestionOut(Input):
    id: str
    task_id: str
    kind: str
    version: int
    status: str
    original: dict | None
    planning: ActionCandidate | ReflectionOutput | None = None
    accepted: dict | None
    record_id: str | None
    record_revision_id: str | None
    relation_id: str | None
    relation_revision_id: str | None
    contribution_id: str | None = None
    contribution_revision_id: str | None = None
    action_id: str | None = None
    action_revision_id: str | None = None
    reflection_id: str | None = None
    reflection_revision_id: str | None = None
    created_at: str
    decided_at: str | None
    events: list[dict]
    task: TaskOut


class TaskPage(Input):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int


class SuggestionPage(Input):
    items: list[SuggestionOut]
    total: int
    page: int
    page_size: int


class AIMaterialOption(Input):
    label: str
    text: str
    pick: MaterialPick


class AIMaterialDetail(Input):
    kind: str
    id: str
    title: str
    project_id: str | None
    version: int
    current_version: int
    revision_id: str
    evidence_label: str | None = None
    options: list[AIMaterialOption]
    related: list[dict] = Field(default_factory=list)


class AIMaterialPage(Input):
    items: list[dict]
    total: int
    page: int
    page_size: int
