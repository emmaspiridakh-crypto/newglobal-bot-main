import json
import pathlib
from typing import Any

import libsql_client

import config

TRANSCRIPTS_DIR = pathlib.Path(__file__).parent.parent / "data" / "transcripts"
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    fields TEXT,
    claimed_by INTEGER,
    panel_message_id INTEGER,
    opened_at TEXT
);
"""

_CREATE_ORDERS_TABLE = """
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_channel_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    fields TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    orders_message_id INTEGER,
    ticket_panel_message_id INTEGER,
    created_by INTEGER,
    created_at TEXT
);
"""


class TicketStore:
    """
    Async ticket store backed by Turso (libsql). One row per open ticket;
    the row is deleted once the ticket closes.
    """

    def __init__(self) -> None:
        self._client: libsql_client.Client | None = None

    async def init(self) -> None:
        self._client = libsql_client.create_client(
            url=config.TURSO_URL, auth_token=config.TURSO_AUTH_TOKEN
        )
        await self._client.execute(_CREATE_TABLE)
        await self._client.execute(_CREATE_ORDERS_TABLE)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def create(self, channel_id: int, **fields: Any) -> None:
        await self._client.execute(
            """
            INSERT INTO tickets
                (channel_id, customer_id, kind, fields, claimed_by, panel_message_id, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                channel_id,
                fields.get("customer_id"),
                fields.get("kind"),
                json.dumps(fields.get("fields")) if fields.get("fields") else None,
                fields.get("claimed_by"),
                fields.get("panel_message_id"),
                fields.get("opened_at"),
            ],
        )

    async def get(self, channel_id: int) -> dict[str, Any] | None:
        result = await self._client.execute(
            "SELECT customer_id, kind, fields, claimed_by, panel_message_id, opened_at "
            "FROM tickets WHERE channel_id = ?",
            [channel_id],
        )
        if not result.rows:
            return None
        row = result.rows[0]
        return {
            "customer_id": row[0],
            "kind": row[1],
            "fields": json.loads(row[2]) if row[2] else None,
            "claimed_by": row[3],
            "panel_message_id": row[4],
            "opened_at": row[5],
        }

    async def update(self, channel_id: int, **fields: Any) -> None:
        if not fields:
            return
        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values())
        values.append(channel_id)
        await self._client.execute(
            f"UPDATE tickets SET {columns} WHERE channel_id = ?", values
        )

    async def delete(self, channel_id: int) -> None:
        await self._client.execute(
            "DELETE FROM tickets WHERE channel_id = ?", [channel_id]
        )

    async def list_all(self) -> list[dict[str, Any]]:
        result = await self._client.execute(
            "SELECT channel_id, customer_id, kind, fields, claimed_by FROM tickets"
        )
        tickets = []
        for row in result.rows:
            tickets.append(
                {
                    "channel_id": row[0],
                    "customer_id": row[1],
                    "kind": row[2],
                    "fields": json.loads(row[3]) if row[3] else None,
                    "claimed_by": row[4],
                }
            )
        return tickets


class OrderStore:
    """Async store for /place-order orders, backed by the same Turso client."""

    def __init__(self, ticket_store: "TicketStore") -> None:
        self._ticket_store = ticket_store

    @property
    def _client(self):
        return self._ticket_store._client

    async def create(self, **fields: Any) -> int:
        result = await self._client.execute(
            """
            INSERT INTO orders
                (ticket_channel_id, customer_id, kind, fields, status,
                 orders_message_id, ticket_panel_message_id, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                fields.get("ticket_channel_id"),
                fields.get("customer_id"),
                fields.get("kind"),
                json.dumps(fields.get("fields")) if fields.get("fields") else None,
                fields.get("status", "pending"),
                fields.get("orders_message_id"),
                fields.get("ticket_panel_message_id"),
                fields.get("created_by"),
                fields.get("created_at"),
            ],
        )
        return result.last_insert_rowid

    async def get(self, order_id: int) -> dict[str, Any] | None:
        result = await self._client.execute(
            "SELECT ticket_channel_id, customer_id, kind, fields, status, "
            "orders_message_id, ticket_panel_message_id, created_by, created_at "
            "FROM orders WHERE order_id = ?",
            [order_id],
        )
        if not result.rows:
            return None
        row = result.rows[0]
        return {
            "order_id": order_id,
            "ticket_channel_id": row[0],
            "customer_id": row[1],
            "kind": row[2],
            "fields": json.loads(row[3]) if row[3] else None,
            "status": row[4],
            "orders_message_id": row[5],
            "ticket_panel_message_id": row[6],
            "created_by": row[7],
            "created_at": row[8],
        }

    async def update(self, order_id: int, **fields: Any) -> None:
        if not fields:
            return
        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values())
        values.append(order_id)
        await self._client.execute(
            f"UPDATE orders SET {columns} WHERE order_id = ?", values
        )

    async def delete(self, order_id: int) -> None:
        await self._client.execute(
            "DELETE FROM orders WHERE order_id = ?", [order_id]
        )


store = TicketStore()
order_store = OrderStore(store)


# --------------------------------------------------------------------------
# Simple synchronous JSON key-value stores.
#
# Separate from the Turso-backed TicketStore/OrderStore above — used by
# cogs that just need to persist a small dict (bot status, join-ping config,
# reviews, suggestions) without a database round-trip.
# --------------------------------------------------------------------------

_STORES_DIR = pathlib.Path(__file__).parent.parent / "data" / "stores"
_STORES_DIR.mkdir(parents=True, exist_ok=True)


def _store_path(name: str) -> pathlib.Path:
    return _STORES_DIR / f"{name}.json"


def get_store(name: str) -> dict:
    """Loads (or creates) the named JSON store and returns it as a dict."""
    path = _store_path(name)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(name: str, data: dict) -> None:
    """Writes the given dict back to the named JSON store."""
    path = _store_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
