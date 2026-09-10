from __future__ import annotations

from typing import Any

import libsql_client

import config

_client: libsql_client.Client | None = None


async def _get_client() -> libsql_client.Client:
    global _client
    if _client is None:
        _client = libsql_client.create_client(
            url=config.TURSO_URL, auth_token=config.TURSO_AUTH_TOKEN
        )
    return _client


async def async_execute(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """Runs a query against the shared Turso client and returns the rows as
    a list of plain dicts (column name -> value), so callers can do
    dict(row) / row["column"] without caring about the underlying driver."""
    client = await _get_client()
    result = await client.execute(sql, params or [])
    return [dict(zip(result.columns, row)) for row in result.rows]


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
