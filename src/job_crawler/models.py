"""Validated contracts shared by adapters, filters and exporters."""

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Source(Model):
    source_id: str
    company_id: str
    company: str
    url: str = ""
    notes: str = ""

    @field_validator("source_id")
    @classmethod
    def safe_identifier(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
            raise ValueError("来源 ID 只允许字母数字、点、横线和下划线，最多80字符")
        return value

    @field_validator("source_id", "company_id", "company")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        value = value.strip()
        if value:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
                raise ValueError("expected public http(s) URL without credentials")
        return value


class Binding(Model):
    adapter: str
    version: str = "1"
    company_name: str = ""
    enabled: bool = True


class Job(Model):
    source_id: str
    source_key: str
    company: str
    title: str
    source_url: str
    apply_url: str = ""
    work_type: str = "校招"
    unit: str = ""
    batch: str = ""
    category_raw: str = ""
    category_primary: str = ""
    category_secondary: str = ""
    education: str = ""
    location: str = ""
    address: str = ""
    duties: str = ""
    requirements: str = ""
    published: str = ""
    deadline: str = ""
    visible: bool = True
    closed: bool = False
    collected_at: datetime
    evidence: list[str] = Field(default_factory=list)
    field_sources: dict[str, str] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source_id}:{self.source_key}"


class Issue(Model):
    code: str
    message: str
    source_id: str = ""
    job_key: str = ""
    url: str = ""


class Scope(Model):
    name: str
    expected: int | None = None
    listed: int = 0
    unique: int = 0
    details: int = 0
    skipped_expired: int = 0
    unit: str = "岗位"
    terminal: bool = False
    evidence: list[str] = Field(default_factory=list)


class Collection(Model):
    jobs: list[Job] = Field(default_factory=list)
    scopes: list[Scope] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)
    scope_description: str = ""

    def coverage_issues(self) -> list[Issue]:
        issues = list(self.issues)
        if not self.scopes:
            issues.append(Issue(code="scope_unknown", message="未证明目录范围"))
        for scope in self.scopes:
            if (
                not scope.terminal
                or scope.listed != scope.unique
                or scope.details + scope.skipped_expired != scope.unique
                or (scope.expected is not None and scope.unique != scope.expected)
            ):
                issues.append(Issue(code="coverage_mismatch", message=scope.model_dump_json()))
        return issues


class Selection(Model):
    kind: Literal["include", "exclude", "review"]
    reason: str


class SourceReport(Model):
    source_id: str
    company: str
    adapter: str = ""
    coverage: Literal["complete", "partial", "blocked"] = "blocked"
    scope_description: str = ""
    scopes: list[Scope] = Field(default_factory=list)
    collected: int = 0
    selected: int = 0
    exported: int = 0
    review: int = 0
    excluded: dict[str, int] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)
