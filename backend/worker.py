import sys
print("=== WORKER STARTING ===", flush=True)
sys.stdout.flush()

import os
import time
import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv()

print("=== IMPORTS OK ===", flush=True)

DATABASE_URL = os.environ["DATABASE_URL"]

print(f"=== DATABASE_URL: {DATABASE_URL[:40]}... ===", flush=True)

try:
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(
        DATABASE_URL,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    conn.autocommit = False
    print("=== POSTGRESQL CONNECTED OK ===", flush=True)
except Exception as e:
    print("=== FAILED TO CONNECT TO POSTGRESQL ===", flush=True)
    print(f"=== POSTGRESQL ERROR: {e} ===", flush=True)
    sys.exit(1)


def _new_conn():
    """Cria uma nova ligação com keepalive activado."""
    return psycopg2.connect(
        DATABASE_URL,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        connect_timeout=15,
    )


def get_conn():
    """Retorna ligação global, reconectando se necessário."""
    global conn
    try:
        conn.cursor().execute("SELECT 1")
    except Exception:
        try:
            conn = _new_conn()
            conn.autocommit = False
        except Exception as e:
            print(f"Reconnect failed: {e}", flush=True)
            raise
    return conn


def claim_job():
    """Atomically claim the oldest queued scrape job (SKIP LOCKED)."""
    c = get_conn()
    try:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'queued' AND type = 'scrape'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
            )
            row = cur.fetchone()
            if row is None:
                c.rollback()
                return None
            cur.execute(
                "UPDATE jobs SET status = 'running', started_at = %s WHERE id = %s",
                (datetime.now(timezone.utc), row["id"]),
            )
            c.commit()
            return dict(row)
    except Exception as e:
        c.rollback()
        print(f"claim_job error: {e}", flush=True)
        return None


def acquire_lock(supplier_id: str, ttl_minutes: int = 10) -> bool:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=ttl_minutes)
    c = get_conn()
    try:
        with c.cursor() as cur:
            # Insert or update: only acquire if not locked or lock expired
            cur.execute(
                """
                INSERT INTO locks (id, locked, expires_at, updated_at)
                VALUES (%s, TRUE, %s, %s)
                ON CONFLICT (id) DO UPDATE
                  SET locked = TRUE, expires_at = %s, updated_at = %s
                WHERE locks.locked = FALSE OR locks.expires_at <= %s
                RETURNING id
                """,
                (supplier_id, expires, now, expires, now, now),
            )
            result = cur.fetchone()
            c.commit()
            return result is not None
    except Exception as e:
        c.rollback()
        print(f"acquire_lock error: {e}", flush=True)
        return False


def release_lock(supplier_id: str):
    c = get_conn()
    try:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE locks SET locked = FALSE, updated_at = %s WHERE id = %s",
                (datetime.now(timezone.utc), supplier_id),
            )
        c.commit()
    except Exception as e:
        c.rollback()
        print(f"release_lock error: {e}", flush=True)


def update_job(job_id: str, **fields):
    c = get_conn()
    set_clauses = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [job_id]
    try:
        with c.cursor() as cur:
            cur.execute(f"UPDATE jobs SET {set_clauses} WHERE id = %s", values)
        c.commit()
    except Exception as e:
        c.rollback()
        print(f"update_job error: {e}", flush=True)


def run_supplier_scrape(supplier_id: str, sizes: list, job_id: str):
    from run_scraper import run_supplier
    run_supplier(supplier_id=supplier_id, sizes=sizes, job_id=job_id)


def main():
    print(f"Worker started at {datetime.now()}", flush=True)
    print(f"PostgreSQL: {DATABASE_URL[:40]}...", flush=True)
    print("-" * 50, flush=True)

    while True:
        try:
            job = claim_job()

            if not job:
                time.sleep(2)
                continue

            supplier_id = job["supplier_id"]
            job_id = job["id"]
            payload = job.get("payload") or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            sizes = payload.get("sizes", [])

            print(f"\n[{datetime.now()}] Processing job {job_id}", flush=True)
            print(f"  Supplier: {supplier_id}", flush=True)
            print(f"  Sizes: {sizes}", flush=True)

            if not acquire_lock(supplier_id):
                print(f"  Could not acquire lock for {supplier_id}, returning to queue", flush=True)
                update_job(job_id, status="queued", started_at=None)
                time.sleep(1)
                continue

            try:
                print(f"  Lock acquired, running scraper...", flush=True)
                run_supplier_scrape(supplier_id, sizes, job_id)
                update_job(
                    job_id,
                    status="done",
                    finished_at=datetime.now(timezone.utc),
                    last_error=None,
                )
                print(f"  Job {job_id} completed successfully", flush=True)
            except Exception as e:
                print(f"  Job {job_id} failed: {e}", flush=True)
                update_job(
                    job_id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc),
                    last_error=str(e),
                )
            finally:
                release_lock(supplier_id)
                print(f"  Lock released for {supplier_id}", flush=True)

        except KeyboardInterrupt:
            print("\nWorker stopped by user", flush=True)
            break
        except Exception as e:
            print(f"Worker error: {e}", flush=True)
            # Backoff progressivo: 5s, 10s, 20s, 40s, máx 60s
            _worker_backoff = getattr(main, '_backoff', 5)
            print(f"  Retrying in {_worker_backoff}s...", flush=True)
            time.sleep(_worker_backoff)
            main._backoff = min(_worker_backoff * 2, 60)
        else:
            # Reset backoff após ciclo bem-sucedido
            main._backoff = 5


if __name__ == "__main__":
    main()
