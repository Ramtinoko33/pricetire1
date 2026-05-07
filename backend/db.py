"""
db.py — Módulo de ligação ao PostgreSQL via asyncpg.

Uso:
    from db import get_db, init_schema, row, rows

    pool = await get_db()
    async with pool.acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM suppliers WHERE id = $1", sid)
        supplier = row(r)
"""

import asyncpg
import json
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def _init_conn(conn: asyncpg.Connection):
    """Registar codecs JSON/JSONB para cada ligação do pool."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def get_db() -> asyncpg.Pool:
    """Retorna o pool de ligações (cria na primeira chamada)."""
    global _pool
    if _pool is None:
        database_url = os.environ["DATABASE_URL"]
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            init=_init_conn,
        )
        logger.info("PostgreSQL pool criado.")
    return _pool


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool fechado.")


async def init_schema():
    """Cria tabelas e índices se não existirem (idempotente)."""
    schema_sql = (Path(__file__).parent / "schema.sql").read_text()
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(schema_sql)
        # Migrations incrementais — ADD COLUMN IF NOT EXISTS é idempotente
        await conn.execute(
            "ALTER TABLE job_items ADD COLUMN IF NOT EXISTS indice_encontrado TEXT"
        )
    logger.info("Schema PostgreSQL inicializado.")


# ---------------------------------------------------------------------------
# Helpers de conversão asyncpg.Record → dict
# ---------------------------------------------------------------------------

def row(r) -> Optional[dict]:
    """Converte um asyncpg.Record em dict (ou None se r for None)."""
    return dict(r) if r else None


def rows(rs) -> list:
    """Converte uma lista de asyncpg.Record em lista de dicts."""
    return [dict(r) for r in rs]
