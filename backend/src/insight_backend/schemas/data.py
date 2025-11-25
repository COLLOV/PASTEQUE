from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    ok: bool
    details: str | None = None


class ValueCount(BaseModel):
    label: str
    count: int


class FieldBreakdown(BaseModel):
    field: str
    label: str
    kind: Literal["date", "text", "number", "boolean", "unknown"] = "text"
    non_null: int = 0
    missing_values: int = 0
    unique_values: int = 0
    counts: list[ValueCount] = Field(default_factory=list)
    truncated: bool = False
    hidden: bool = False


class DataSourceOverview(BaseModel):
    source: str
    title: str
    total_rows: int
    field_count: int = 0
    fields: list[FieldBreakdown] = Field(default_factory=list)


class DataOverviewResponse(BaseModel):
    generated_at: datetime
    sources: list[DataSourceOverview] = Field(default_factory=list)


class UpdateHiddenFieldsRequest(BaseModel):
    hidden_fields: list[str] = Field(default_factory=list)


class HiddenFieldsResponse(BaseModel):
    source: str
    hidden_fields: list[str] = Field(default_factory=list)
