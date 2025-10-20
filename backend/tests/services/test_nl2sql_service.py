import pytest

from insight_backend.services.nl2sql_service import _ensure_required_prefix


def test_ensure_required_prefix_accepts_cte_reference() -> None:
    sql = (
        "WITH recent AS (\n"
        "    SELECT id FROM files.tickets LIMIT 5\n"
        ")\n"
        "SELECT recent.id, u.id\n"
        "FROM recent\n"
        "JOIN files.users AS u ON u.id = recent.id\n"
        "LIMIT 5"
    )

    _ensure_required_prefix(sql)


def test_ensure_required_prefix_rejects_unprefixed_table() -> None:
    sql = "SELECT id FROM tickets LIMIT 5"

    with pytest.raises(RuntimeError):
        _ensure_required_prefix(sql)
