from pydantic import BaseModel


class IngestResponse(BaseModel):
    ok: bool
    details: str | None = None

