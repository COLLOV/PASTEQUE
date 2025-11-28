from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class TicketContextMetadataResponse(BaseModel):
  table: str
  text_column: str
  date_column: str
  date_min: date | None = None
  date_max: date | None = None
  total_count: int
