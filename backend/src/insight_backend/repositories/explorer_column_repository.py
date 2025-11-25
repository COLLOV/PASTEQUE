from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, Set

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models.explorer_column import ExplorerHiddenColumn


class ExplorerColumnRepository:
  """Manage explorer column visibility configuration."""

  def __init__(self, session: Session):
    self.session = session

  def get_hidden_columns(self) -> Dict[str, Set[str]]:
    """Return mapping table_name -> set of hidden column names."""
    stmt = select(ExplorerHiddenColumn.table_name, ExplorerHiddenColumn.column_name)
    rows = self.session.execute(stmt).all()
    mapping: Dict[str, Set[str]] = defaultdict(set)
    for table_name, column_name in rows:
      mapping[table_name].add(column_name)
    return mapping

  def set_hidden_columns(self, table_name: str, hidden_columns: Iterable[str]) -> list[str]:
    """Replace hidden columns for a table and return the normalized list."""
    normalized = sorted({col.strip() for col in hidden_columns if col.strip()})

    stmt = delete(ExplorerHiddenColumn).where(ExplorerHiddenColumn.table_name == table_name)
    self.session.execute(stmt)

    for col in normalized:
      self.session.add(ExplorerHiddenColumn(table_name=table_name, column_name=col))

    self.session.flush()
    return normalized

