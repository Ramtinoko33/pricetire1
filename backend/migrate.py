#!/usr/bin/env python3
"""
migrate.py — Migra dados do MongoDB (antigo) para o PostgreSQL (novo).

Uso (Railway ou local):
    DATABASE_URL=postgresql://... MONGO_URL=mongodb+srv://... python3 migrate.py

Segurança:
    - Nunca apaga dados do MongoDB.
    - Usa INSERT ... ON CONFLICT DO NOTHING — pode ser executado várias vezes.
    - Regista progresso e erros no terminal.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

# ── dependências ─────────────────────────────────────────────────────────────
try:
    import asyncpg
    from pymongo import MongoClient
    from bson import ObjectId
except ImportError as e:
    print(f"Dependência em falta: {e}")
    print("Instala com: pip install asyncpg pymongo dnspython")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("migrate")

# ── config ────────────────────────────────────────────────────────────────────
MONGO_URL    = os.environ["MONGO_URL"]
MONGO_DB     = os.environ.get("DB_NAME", "pneu_price_scout")
DATABASE_URL = os.environ["DATABASE_URL"]


# ── helpers ───────────────────────────────────────────────────────────────────
def to_str(v) -> str:
    """Converte ObjectId ou qualquer valor para string."""
    if isinstance(v, ObjectId):
        return str(v)
    return str(v) if v is not None else None


def to_dt(v):
    """Converte string ISO ou datetime para datetime com fuso UTC."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def safe_json(v):
    """Garante que um valor é serializável como JSON (dict/list ou None)."""
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return None


async def init_pg_codecs(conn: asyncpg.Connection):
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json",  encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


# ── migrações por colecção ────────────────────────────────────────────────────
async def migrate_suppliers(mongo_db, pg: asyncpg.Connection):
    docs = list(mongo_db.suppliers.find({}))
    log.info(f"suppliers: {len(docs)} documentos encontrados no MongoDB")
    ok = skip = 0
    for d in docs:
        doc_id = d.get("id") or to_str(d.get("_id"))
        try:
            await pg.execute(
                """
                INSERT INTO suppliers
                    (id, name, url_login, url_search, username, password, password_raw,
                     selectors, is_active, status, last_test, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT (id) DO NOTHING
                """,
                doc_id,
                d.get("name", ""),
                d.get("url_login", ""),
                d.get("url_search", ""),
                d.get("username", ""),
                d.get("password", ""),
                d.get("password_raw"),
                safe_json(d.get("selectors")) or {},
                bool(d.get("is_active", True)),
                str(d.get("status", "active")),
                to_dt(d.get("last_test")),
                to_dt(d.get("created_at")) or datetime.now(timezone.utc),
            )
            ok += 1
        except Exception as e:
            log.warning(f"  suppliers [{doc_id}] ignorado: {e}")
            skip += 1
    log.info(f"suppliers: {ok} migrados, {skip} ignorados")


async def migrate_jobs(mongo_db, pg: asyncpg.Connection):
    docs = list(mongo_db.jobs.find({}))
    log.info(f"jobs: {len(docs)} documentos encontrados no MongoDB")
    ok = skip = 0
    for d in docs:
        doc_id = d.get("id") or to_str(d.get("_id"))
        try:
            await pg.execute(
                """
                INSERT INTO jobs
                    (id, filename, status, total_items, processed_items, found_items,
                     matched_items, total_savings, threshold_euro, threshold_percent,
                     created_at, started_at, completed_at, finished_at,
                     error_message, last_error,
                     type, supplier_id, supplier_name, payload, attempts)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)
                ON CONFLICT (id) DO NOTHING
                """,
                doc_id,
                d.get("filename"),
                str(d.get("status", "pending")),
                int(d.get("total_items", 0)),
                int(d.get("processed_items", 0)),
                int(d.get("found_items", 0)),
                int(d.get("matched_items", 0)),
                float(d.get("total_savings", 0.0)),
                float(d.get("threshold_euro", 5.0)),
                float(d.get("threshold_percent", 10.0)),
                to_dt(d.get("created_at")) or datetime.now(timezone.utc),
                to_dt(d.get("started_at")),
                to_dt(d.get("completed_at")),
                to_dt(d.get("finished_at")),
                d.get("error_message"),
                d.get("last_error"),
                d.get("type"),
                d.get("supplier_id"),
                d.get("supplier_name"),
                safe_json(d.get("payload")),
                int(d.get("attempts", 0)),
            )
            ok += 1
        except Exception as e:
            log.warning(f"  jobs [{doc_id}] ignorado: {e}")
            skip += 1
    log.info(f"jobs: {ok} migrados, {skip} ignorados")


async def migrate_job_items(mongo_db, pg: asyncpg.Connection):
    docs = list(mongo_db.job_items.find({}))
    log.info(f"job_items: {len(docs)} documentos encontrados no MongoDB")
    ok = skip = 0
    for d in docs:
        doc_id = d.get("id") or to_str(d.get("_id"))
        try:
            await pg.execute(
                """
                INSERT INTO job_items
                    (id, job_id, ref_id, medida, marca, modelo, indice, meu_preco,
                     melhor_preco, melhor_fornecedor, melhor_marca, modelo_encontrado,
                     match_type, economia_euro, economia_percent,
                     status, supplier_prices, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                ON CONFLICT (id) DO NOTHING
                """,
                doc_id,
                d.get("job_id"),
                d.get("ref_id"),
                d.get("medida"),
                d.get("marca"),
                d.get("modelo"),
                d.get("indice"),
                float(d.get("meu_preco", 0)),
                float(d["melhor_preco"]) if d.get("melhor_preco") is not None else None,
                d.get("melhor_fornecedor"),
                d.get("melhor_marca"),
                d.get("modelo_encontrado"),
                d.get("match_type"),
                float(d["economia_euro"]) if d.get("economia_euro") is not None else None,
                float(d["economia_percent"]) if d.get("economia_percent") is not None else None,
                str(d.get("status", "pending")),
                safe_json(d.get("supplier_prices")) or {},
                to_dt(d.get("created_at")) or datetime.now(timezone.utc),
            )
            ok += 1
        except Exception as e:
            log.warning(f"  job_items [{doc_id}] ignorado: {e}")
            skip += 1
    log.info(f"job_items: {ok} migrados, {skip} ignorados")


async def migrate_prices(mongo_db, pg: asyncpg.Connection):
    docs = list(mongo_db.prices.find({}))
    log.info(f"prices: {len(docs)} documentos encontrados no MongoDB")
    ok = skip = 0
    for d in docs:
        doc_id = d.get("id") or to_str(d.get("_id"))
        try:
            await pg.execute(
                """
                INSERT INTO prices
                    (id, job_id, item_id, supplier_id, supplier_name, price, status, found_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (id) DO NOTHING
                """,
                doc_id,
                d.get("job_id"),
                d.get("item_id"),
                d.get("supplier_id"),
                d.get("supplier_name"),
                float(d["price"]) if d.get("price") is not None else None,
                str(d.get("status", "found")),
                to_dt(d.get("found_at")) or datetime.now(timezone.utc),
            )
            ok += 1
        except Exception as e:
            log.warning(f"  prices [{doc_id}] ignorado: {e}")
            skip += 1
    log.info(f"prices: {ok} migrados, {skip} ignorados")


async def migrate_scraped_prices(mongo_db, pg: asyncpg.Connection):
    docs = list(mongo_db.scraped_prices.find({}))
    log.info(f"scraped_prices: {len(docs)} documentos encontrados no MongoDB")
    ok = skip = 0
    for d in docs:
        doc_id = d.get("id") or to_str(d.get("_id"))
        if not doc_id:
            doc_id = str(uuid.uuid4())
        try:
            await pg.execute(
                """
                INSERT INTO scraped_prices
                    (id, medida, marca, modelo, price, supplier_name, supplier_id,
                     load_index, scraped_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (id) DO NOTHING
                """,
                doc_id,
                d.get("medida"),
                d.get("marca"),
                d.get("modelo"),
                float(d["price"]) if d.get("price") is not None else None,
                d.get("supplier_name"),
                d.get("supplier_id"),
                d.get("load_index"),
                to_dt(d.get("scraped_at")) or datetime.now(timezone.utc),
            )
            ok += 1
        except Exception as e:
            log.warning(f"  scraped_prices [{doc_id}] ignorado: {e}")
            skip += 1
    log.info(f"scraped_prices: {ok} migrados, {skip} ignorados")


async def migrate_logs(mongo_db, pg: asyncpg.Connection):
    docs = list(mongo_db.logs.find({}))
    log.info(f"logs: {len(docs)} documentos encontrados no MongoDB")
    ok = skip = 0
    for d in docs:
        doc_id = d.get("id") or to_str(d.get("_id"))
        try:
            await pg.execute(
                """
                INSERT INTO logs
                    (id, job_id, supplier_id, level, message, screenshot_path, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (id) DO NOTHING
                """,
                doc_id,
                d.get("job_id"),
                d.get("supplier_id"),
                str(d.get("level", "INFO")),
                d.get("message", ""),
                d.get("screenshot_path"),
                to_dt(d.get("created_at")) or datetime.now(timezone.utc),
            )
            ok += 1
        except Exception as e:
            log.warning(f"  logs [{doc_id}] ignorado: {e}")
            skip += 1
    log.info(f"logs: {ok} migrados, {skip} ignorados")


# ── main ──────────────────────────────────────────────────────────────────────
async def main():
    log.info("=== Iniciando migração MongoDB → PostgreSQL ===")

    # Ligar ao MongoDB
    log.info(f"Ligando ao MongoDB: {MONGO_URL[:40]}...")
    mongo_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    mongo_db = mongo_client[MONGO_DB]
    log.info(f"MongoDB OK — base de dados: {MONGO_DB}")

    # Ligar ao PostgreSQL
    log.info("Ligando ao PostgreSQL...")
    pg_conn = await asyncpg.connect(DATABASE_URL)
    await init_pg_codecs(pg_conn)
    log.info("PostgreSQL OK")

    # Criar schema
    schema_sql = (Path(__file__).parent / "schema.sql").read_text()
    await pg_conn.execute(schema_sql)
    log.info("Schema criado/verificado")

    # Migrar colecções pela ordem correta (jobs antes de job_items por FK)
    await migrate_suppliers(mongo_db, pg_conn)
    await migrate_jobs(mongo_db, pg_conn)
    await migrate_job_items(mongo_db, pg_conn)
    await migrate_prices(mongo_db, pg_conn)
    await migrate_scraped_prices(mongo_db, pg_conn)
    await migrate_logs(mongo_db, pg_conn)

    await pg_conn.close()
    mongo_client.close()
    log.info("=== Migração concluída ===")


from pathlib import Path

if __name__ == "__main__":
    asyncio.run(main())
