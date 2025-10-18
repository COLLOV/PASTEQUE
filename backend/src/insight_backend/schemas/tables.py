from pydantic import BaseModel


class TableInfo(BaseModel):
    name: str
    path: str


class ColumnInfo(BaseModel):
    name: str
    dtype: str | None = None

