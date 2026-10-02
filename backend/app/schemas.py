from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RecordType = Literal["note", "paper", "experiment", "ai", "idea"]
WorkStatus = Literal["planned", "in_progress", "blocked", "paused", "finished"]
OutcomeStatus = Literal["none", "inconclusive", "unsupported", "preliminary", "not_applicable"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorOut(BaseModel):
    error: ErrorDetail


class LoginInput(Input):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize(cls, value):
        return value.lower()


class RegisterInput(LoginInput):
    display_name: str = Field(min_length=1, max_length=80)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    display_name: str


class AuthOut(BaseModel):
    user: UserOut
    csrf_token: str


class ProjectInput(Input):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=10000)

    @field_validator("name")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("项目名称不能为空")
        return value.strip()


class ProjectPatch(Input):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=10000)
    archived: bool | None = None

    @model_validator(mode="after")
    def valid(self):
        for key in self.model_fields_set:
            if getattr(self, key) is None:
                raise ValueError("项目字段不能为 null")
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("项目名称不能为空")
        return self


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    archived: bool
    created_at: str
    updated_at: str


class ExplorationFields(Input):
    context: str = Field(default="", max_length=20000)
    actions: str = Field(default="", max_length=20000)
    collaboration: str = Field(default="", max_length=20000)
    observations: str = Field(default="", max_length=20000)
    interpretation: str = Field(default="", max_length=20000)
    next_steps: str = Field(default="", max_length=20000)


def validate_link(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme not in ("https", "http")
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise ValueError("链接必须是有效的 HTTP 或 HTTPS 地址，且不能包含登录凭据")
    return value


class SourceInput(Input):
    kind: Literal["text", "file", "link"] = "text"
    name: str = Field(default="原始材料", min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1048576)

    @model_validator(mode="after")
    def validate_content(self):
        if not self.content.strip():
            raise ValueError("来源内容不能为空")
        if self.kind == "link":
            validate_link(self.content)
        return self


class RecordCreate(Input):
    request_id: UUID
    project_id: UUID | None = None
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=1048576)
    record_type: RecordType = "note"
    work_status: WorkStatus = "in_progress"
    outcome_status: OutcomeStatus = "none"
    fields: ExplorationFields = Field(default_factory=ExplorationFields)
    sources: list[SourceInput] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def nonempty(self):
        if not (self.title.strip() or self.body.strip()):
            raise ValueError("请至少填写标题或正文")
        return self


class VersionInput(Input):
    expected_version: int = Field(ge=1)


class RecordPatch(VersionInput):
    project_id: UUID | None = None
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=1048576)
    record_type: RecordType | None = None
    work_status: WorkStatus | None = None
    outcome_status: OutcomeStatus | None = None
    fields: ExplorationFields | None = None

    @model_validator(mode="after")
    def no_nulls(self):
        for key in self.model_fields_set - {"project_id"}:
            if getattr(self, key) is None:
                raise ValueError(f"{key} 不能为 null")
        return self


class SourceAdd(SourceInput):
    expected_version: int = Field(ge=1)


class SourceRevise(VersionInput):
    content: str = Field(min_length=1, max_length=1048576)


class SourceVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_id: str
    version: int
    content: str
    created_at: str


class SourceOut(BaseModel):
    id: str
    record_id: str
    kind: str
    name: str
    current_version: int
    created_at: str
    versions: list[SourceVersionOut]


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str | None
    title: str
    body: str
    record_type: RecordType
    work_status: WorkStatus
    outcome_status: OutcomeStatus
    fields: ExplorationFields
    version: int
    deleted_at: str | None
    created_at: str
    updated_at: str


class RecordList(BaseModel):
    items: list[RecordOut]
    total: int
    page: int
    page_size: int


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    record_id: str
    version: int
    operation: str
    snapshot: dict
    created_at: str
