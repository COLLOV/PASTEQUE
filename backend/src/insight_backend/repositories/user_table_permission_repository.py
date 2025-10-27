from __future__ import annotations

import logging
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from ..models.user_table_permission import UserTablePermission


log = logging.getLogger("insight.repositories.user_table_permission")


class UserTablePermissionRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_allowed_tables(self, user_id: UUID | int) -> list[str]:
        rows = (
            self.session.query(UserTablePermission.table_name)
            .filter(UserTablePermission.user_id == user_id)
            .all()
        )
        tables = [row[0] for row in rows]
        log.debug("Loaded %d table permissions for user_id=%s", len(tables), user_id)
        return tables

    def set_allowed_tables(self, user_id: UUID | int, table_names: Iterable[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for name in table_names:
            cleaned = name.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(cleaned)

        existing = (
            self.session.query(UserTablePermission)
            .filter(UserTablePermission.user_id == user_id)
            .all()
        )
        existing_map = {perm.table_name.casefold(): perm for perm in existing}
        desired_keys = {name.casefold() for name in normalized}

        # Remove permissions no longer desired
        for key, perm in existing_map.items():
            if key not in desired_keys:
                self.session.delete(perm)
                log.info(
                    "Revoked table permission user_id=%s table=%s",
                    user_id,
                    perm.table_name,
                )

        # Add missing permissions
        for name in normalized:
            key = name.casefold()
            if key in existing_map:
                continue
            perm = UserTablePermission(user_id=user_id, table_name=name)
            self.session.add(perm)
            log.info("Granted table permission user_id=%s table=%s", user_id, name)

        return sorted(normalized, key=lambda value: value.casefold())
