from datetime import datetime

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    ok: bool
    details: str | None = None


class DimensionCount(BaseModel):
    label: str
    count: int


class DimensionBreakdown(BaseModel):
    field: str
    label: str
    counts: list[DimensionCount] = Field(default_factory=list)


class DataSourceOverview(BaseModel):
    source: str
    title: str
    total_rows: int
    columns: list[DimensionBreakdown] = Field(default_factory=list)


class DataOverviewResponse(BaseModel):
    generated_at: datetime
    sources: list[DataSourceOverview] = Field(default_factory=list)
