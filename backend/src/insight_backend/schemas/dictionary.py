from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional


class DictionaryColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    type: Optional[str] = None
    synonyms: List[str] = Field(default_factory=list)
    unit: Optional[str] = None
    example: Optional[str] = None
    pii: Optional[bool] = None
    nullable: Optional[bool] = None
    enum: Optional[List[str]] = None


class DictionaryTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str = Field(..., min_length=1)
    title: Optional[str] = None
    description: Optional[str] = None
    columns: List[DictionaryColumn] = Field(default_factory=list)


class DictionaryTableSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str
    has_dictionary: bool
    columns_count: int
