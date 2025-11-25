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
  kind: str = "category"
  counts: list[DimensionCount] = Field(default_factory=list)


class DataSourceOverview(BaseModel):
  source: str
  title: str
  total_rows: int
  dimensions: list[DimensionBreakdown] = Field(default_factory=list)


class DataOverviewResponse(BaseModel):
  generated_at: datetime
  sources: list[DataSourceOverview] = Field(default_factory=list)


class ExplorerColumnConfig(BaseModel):
  name: str
  label: str
  type: str | None = None
  hidden: bool = False


class ExplorerTableConfig(BaseModel):
  table: str
  title: str
  columns: list[ExplorerColumnConfig] = Field(default_factory=list)


class ExplorerColumnsConfigResponse(BaseModel):
  tables: list[ExplorerTableConfig] = Field(default_factory=list)


class UpdateExplorerColumnsRequest(BaseModel):
  hidden_columns: list[str] = Field(default_factory=list)
