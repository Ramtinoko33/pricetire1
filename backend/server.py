from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Body
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from typing import List, Optional, Dict
import uuid
from datetime import datetime, timezone, timedelta
import asyncio
from io import BytesIO
import json

from models import (
    Supplier, SupplierCreate, SupplierUpdate, SupplierStatus,
    Job, JobCreate, JobItem, JobStatus, ItemStatus,
    Price, Log, TestLoginResponse, JobProgress
)
from scraper_service import ScraperService
from excel_service import ExcelService
from passlib.context import CryptContext
from db import get_db, init_schema, close_db, row, rows

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
scraper_service = ScraperService()
excel_service = ExcelService()

app = FastAPI(title="Pneu Price Scout API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup():
    await init_schema()
    logger.info("API pronta.")


@app.on_event("shutdown")
async def shutdown():
    await close_db()


@app.get("/health")
async def health():
    """Endpoint de diagnóstico — sem base de dados."""
    return {"status": "ok", "service": "pricetire-api"}


@app.get("/health/db")
async def health_db():
    """Endpoint de diagnóstico — testa ligação à base de dados."""
    try:
        pool = await get_db()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "postgresql", "result": val}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ==================== Suppliers ====================

@api_router.get("/suppliers", response_model=List[Supplier])
async def get_suppliers():
    pool = await get_db()
    async with pool.acquire() as conn:
        rs = await conn.fetch("SELECT * FROM suppliers ORDER BY created_at DESC")
    result = []
    for r in rs:
        d = dict(r)
        d['password'] = "********"
        result.append(Supplier(**d))
    return result


@api_router.post("/suppliers", response_model=Supplier)
async def create_supplier(supplier_data: SupplierCreate):
    d = supplier_data.model_dump()
    supplier_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO suppliers
                (id, name, url_login, url_search, username, password, password_raw,
                 selectors, is_active, status, last_test, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            """,
            supplier_id,
            d['name'],
            d['url_login'],
            d['url_search'],
            d['username'],
            pwd_context.hash(d['password']),
            d['password'],          # password_raw — texto simples para o scraper
            d.get('selectors') or {},
            True,
            SupplierStatus.ACTIVE.value,
            None,
            now,
        )

    return Supplier(
        id=supplier_id,
        name=d['name'],
        url_login=d['url_login'],
        url_search=d['url_search'],
        username=d['username'],
        password="********",
        selectors=d.get('selectors'),
        is_active=True,
        status=SupplierStatus.ACTIVE,
        last_test=None,
        created_at=now,
    )


@api_router.put("/suppliers/{supplier_id}", response_model=Supplier)
async def update_supplier(supplier_id: str, supplier_data: SupplierUpdate):
    pool = await get_db()
    async with pool.acquire() as conn:
        existing = row(await conn.fetchrow(
            "SELECT * FROM suppliers WHERE id = $1", supplier_id
        ))
        if not existing:
            raise HTTPException(status_code=404, detail="Supplier not found")

        updates = {k: v for k, v in supplier_data.model_dump().items() if v is not None}
        if 'password' in updates:
            updates['password_raw'] = updates['password']
            updates['password'] = pwd_context.hash(updates['password'])

        if updates:
            set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
            values = list(updates.values())
            await conn.execute(
                f"UPDATE suppliers SET {set_clause} WHERE id = $1",
                supplier_id, *values
            )

        updated = row(await conn.fetchrow(
            "SELECT * FROM suppliers WHERE id = $1", supplier_id
        ))

    updated['password'] = "********"
    return Supplier(**updated)


@api_router.get("/suppliers/{supplier_id}/selectors")
async def get_supplier_selectors(supplier_id: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        r = row(await conn.fetchrow(
            "SELECT selectors FROM suppliers WHERE id = $1", supplier_id
        ))
    if not r:
        raise HTTPException(status_code=404, detail="Supplier not found")

    defaults = {
        "login_username": "", "login_password": "", "login_button": "",
        "search_input": "", "search_button": "", "price_pattern": "", "notes": ""
    }
    current = r.get('selectors') or {}
    return {**defaults, **current}


@api_router.put("/suppliers/{supplier_id}/selectors")
async def update_supplier_selectors(supplier_id: str, selectors: Dict[str, str]):
    pool = await get_db()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE suppliers SET selectors = $2 WHERE id = $1",
            supplier_id, selectors
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {"message": "Selectors updated", "selectors": selectors}


@api_router.delete("/suppliers/{supplier_id}")
async def delete_supplier(supplier_id: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM suppliers WHERE id = $1", supplier_id
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {"message": "Supplier deleted successfully"}


@api_router.post("/suppliers/{supplier_id}/test", response_model=TestLoginResponse)
async def test_supplier_login(supplier_id: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        supplier = row(await conn.fetchrow(
            "SELECT * FROM suppliers WHERE id = $1", supplier_id
        ))
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    try:
        success, message, screenshot = await scraper_service.test_supplier_login(supplier)
        now = datetime.now(timezone.utc)

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE suppliers SET last_test = $2, status = $3 WHERE id = $1",
                supplier_id,
                now,
                SupplierStatus.ACTIVE.value if success else SupplierStatus.ERROR.value,
            )
            await conn.execute(
                """
                INSERT INTO logs (id, supplier_id, level, message, screenshot_path, created_at)
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                str(uuid.uuid4()), supplier_id,
                "INFO" if success else "ERROR",
                f"Login test: {message}", screenshot, now,
            )

        return TestLoginResponse(success=success, message=message, screenshot_path=screenshot)
    except Exception as e:
        logger.error(f"Test login error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Jobs ====================

@api_router.post("/jobs/upload", response_model=Job)
async def upload_excel(
    file: UploadFile = File(...),
    threshold_euro: float = 5.0,
    threshold_percent: float = 10.0,
):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="File must be Excel format (.xlsx or .xls)")

    try:
        content = await file.read()
        items = excel_service.parse_upload(content, file.filename)
        if not items:
            raise HTTPException(status_code=400, detail="No valid items found in Excel file")

        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        pool = await get_db()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO jobs
                        (id, filename, status, total_items, processed_items, found_items,
                         total_savings, threshold_euro, threshold_percent, created_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                    """,
                    job_id, file.filename, JobStatus.PENDING.value,
                    len(items), 0, 0, 0.0,
                    threshold_euro, threshold_percent, now,
                )
                for item in items:
                    await conn.execute(
                        """
                        INSERT INTO job_items
                            (id, job_id, ref_id, medida, marca, modelo, indice,
                             meu_preco, status, supplier_prices, created_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                        """,
                        str(uuid.uuid4()), job_id,
                        item['ref_id'], item['medida'], item['marca'],
                        item['modelo'], item['indice'], item['meu_preco'],
                        ItemStatus.PENDING.value, {}, now,
                    )

        logger.info(f"Job {job_id} criado com {len(items)} itens")
        return Job(
            id=job_id, filename=file.filename, status=JobStatus.PENDING,
            total_items=len(items), processed_items=0, found_items=0,
            total_savings=0.0, threshold_euro=threshold_euro,
            threshold_percent=threshold_percent, created_at=now,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")


@api_router.post("/jobs/{job_id}/run")
async def run_job(job_id: str, background_tasks: BackgroundTasks):
    pool = await get_db()
    async with pool.acquire() as conn:
        job = row(await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job['status'] == JobStatus.RUNNING.value:
        raise HTTPException(status_code=400, detail="Job is already running")

    pool2 = await get_db()
    async with pool2.acquire() as conn:
        await conn.execute(
            "UPDATE jobs SET status = $2, started_at = $3 WHERE id = $1",
            job_id, JobStatus.RUNNING.value, datetime.now(timezone.utc),
        )

    background_tasks.add_task(run_scraping_job, job_id)
    return {"message": "Job started", "job_id": job_id}


async def run_scraping_job(job_id: str):
    pool = await get_db()
    try:
        logger.info(f"A iniciar job de scraping {job_id}")

        async with pool.acquire() as conn:
            job = row(await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id))
            items = rows(await conn.fetch(
                "SELECT * FROM job_items WHERE job_id = $1", job_id
            ))
            suppliers = rows(await conn.fetch(
                "SELECT * FROM suppliers WHERE is_active = TRUE"
            ))

        if not suppliers:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE jobs SET status=$2, error_message=$3, completed_at=$4 WHERE id=$1",
                    job_id, JobStatus.FAILED.value, "No active suppliers found",
                    datetime.now(timezone.utc),
                )
            return

        processed = found = 0
        total_savings = 0.0

        for item in items:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE job_items SET status=$2 WHERE id=$1",
                    item['id'], ItemStatus.PROCESSING.value,
                )

            supplier_prices = {}
            best_price = best_supplier = None

            for supplier in suppliers:
                try:
                    price = await scraper_service.scrape_product(
                        supplier, item['medida'], item['marca'],
                        item['modelo'], item['indice'],
                    )
                    now = datetime.now(timezone.utc)
                    async with pool.acquire() as conn:
                        if price is not None:
                            supplier_prices[supplier['name']] = price
                            if best_price is None or price < best_price:
                                best_price = price
                                best_supplier = supplier['name']
                            await conn.execute(
                                """
                                INSERT INTO prices
                                    (id, job_id, item_id, supplier_id, supplier_name,
                                     price, status, found_at)
                                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                                """,
                                str(uuid.uuid4()), job_id, item['id'],
                                supplier['id'], supplier['name'],
                                price, ItemStatus.FOUND.value, now,
                            )
                        else:
                            supplier_prices[supplier['name']] = "NAO_ENCONTRADO"
                            await conn.execute(
                                """
                                INSERT INTO prices
                                    (id, job_id, item_id, supplier_id, supplier_name,
                                     price, status, found_at)
                                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                                """,
                                str(uuid.uuid4()), job_id, item['id'],
                                supplier['id'], supplier['name'],
                                None, ItemStatus.NOT_FOUND.value, now,
                            )
                    await asyncio.sleep(0.7)

                except Exception as e:
                    logger.error(f"Erro a pesquisar {supplier['name']}: {str(e)}")
                    supplier_prices[supplier['name']] = "ERRO"
                    async with pool.acquire() as conn:
                        await conn.execute(
                            """
                            INSERT INTO logs
                                (id, job_id, supplier_id, level, message, created_at)
                            VALUES ($1,$2,$3,$4,$5,$6)
                            """,
                            str(uuid.uuid4()), job_id, supplier['id'],
                            "ERROR", f"Error searching item {item['ref_id']}: {str(e)}",
                            datetime.now(timezone.utc),
                        )

            economia_euro = economia_percent = None
            item_status = ItemStatus.NOT_FOUND.value
            if best_price is not None:
                economia_euro = item['meu_preco'] - best_price
                economia_percent = (economia_euro / item['meu_preco']) * 100 if item['meu_preco'] else None
                if economia_euro >= job['threshold_euro'] or (economia_percent is not None and economia_percent >= job['threshold_percent']):
                    item_status = ItemStatus.FOUND.value
                    found += 1
                    total_savings += economia_euro

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE job_items SET
                        melhor_preco=$2, melhor_fornecedor=$3,
                        economia_euro=$4, economia_percent=$5,
                        status=$6, supplier_prices=$7
                    WHERE id=$1
                    """,
                    item['id'], best_price, best_supplier,
                    economia_euro, economia_percent,
                    item_status, supplier_prices,
                )

            processed += 1
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE jobs SET processed_items=$2, found_items=$3, total_savings=$4 WHERE id=$1",
                    job_id, processed, found, total_savings,
                )

        for supplier in suppliers:
            await scraper_service.cleanup_supplier(supplier['id'])

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE jobs SET status=$2, completed_at=$3 WHERE id=$1",
                job_id, JobStatus.COMPLETED.value, datetime.now(timezone.utc),
            )
        logger.info(f"Job {job_id} concluído. Processados: {processed}, Encontrados: {found}")

    except Exception as e:
        logger.error(f"Job {job_id} falhou: {str(e)}")
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE jobs SET status=$2, error_message=$3, completed_at=$4 WHERE id=$1",
                job_id, JobStatus.FAILED.value, str(e), datetime.now(timezone.utc),
            )


@api_router.get("/jobs", response_model=List[Job])
async def get_jobs():
    pool = await get_db()
    async with pool.acquire() as conn:
        rs = rows(await conn.fetch(
            "SELECT * FROM jobs WHERE type IS NULL ORDER BY created_at DESC LIMIT 100"
        ))
    return [Job(**r) for r in rs]


@api_router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        r = row(await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id))
    if not r:
        raise HTTPException(status_code=404, detail="Job not found")
    return Job(**r)


@api_router.get("/jobs/{job_id}/progress", response_model=JobProgress)
async def get_job_progress(job_id: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        r = row(await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id))
    if not r:
        raise HTTPException(status_code=404, detail="Job not found")
    pct = (r['processed_items'] / r['total_items'] * 100) if r['total_items'] > 0 else 0
    return JobProgress(
        job_id=job_id,
        status=JobStatus(r['status']),
        total_items=r['total_items'],
        processed_items=r['processed_items'],
        found_items=r['found_items'],
        progress_percent=round(pct, 1),
    )


@api_router.get("/jobs/{job_id}/results")
async def get_job_results(job_id: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        rs = rows(await conn.fetch(
            "SELECT * FROM job_items WHERE job_id = $1", job_id
        ))
    return rs


@api_router.post("/jobs/{job_id}/compare")
async def compare_job_with_scraped_prices(job_id: str, force: bool = False):
    """
    Compara itens do job com preços raspados — matching hierárquico 3 níveis:
    Nível 1: medida + marca + modelo
    Nível 2: medida + marca
    Nível 3: medida apenas

    force=true → apaga cache e re-scrape todas as medidas (verifica stock/preço actual)
    """
    import re

    pool = await get_db()
    async with pool.acquire() as conn:
        job = row(await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id))
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        items = rows(await conn.fetch(
            "SELECT * FROM job_items WHERE job_id = $1", job_id
        ))
        if not items:
            raise HTTPException(status_code=400, detail="No items found in job")

        def _norm_medida(m: str) -> str:
            return m.replace('/', '').replace('R', '').replace('r', '')

        unique_medidas = list({_norm_medida(item['medida']) for item in items})

        # Triplos únicos (medida, marca, modelo) para cache check granular
        unique_triples = list({
            (
                _norm_medida(item['medida']),
                (item.get('marca')  or '').strip().upper(),
                (item.get('modelo') or '').strip().upper(),
            )
            for item in items
        })
        unique_pairs = list({(m, b) for m, b, _ in unique_triples})

        if force:
            # Apaga todo o cache para estas medidas — força re-scrape completo
            await conn.execute(
                "DELETE FROM scraped_prices WHERE medida = ANY($1)",
                unique_medidas,
            )
            pairs_sem_dados = unique_pairs
        else:
            # ── Nova política de cache ──────────────────────────────────────
            # Um par (medida, marca) só usa o cache se:
            #   1. O item não tem modelo especificado (qualquer dado recente serve), OU
            #   2. Existe um match exato de modelo nos últimos 12h em TODOS os fornecedores
            #      activos.
            # Em qualquer outro caso → re-scrape para verificar stock actual.
            CACHE_TTL_H = 12
            cache_cutoff = datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_H)

            active_supplier_names = {
                r['name'] for r in
                await conn.fetch("SELECT name FROM suppliers WHERE is_active = TRUE")
            }

            # Obter dados recentes (< 12h) com marca E modelo preenchidos
            rows_cache = await conn.fetch(
                """SELECT sp.supplier_name, sp.medida,
                          UPPER(COALESCE(sp.marca,''))  AS marca_up,
                          UPPER(COALESCE(sp.modelo,'')) AS modelo_up
                   FROM scraped_prices sp
                   JOIN suppliers s ON s.name = sp.supplier_name
                   WHERE sp.medida = ANY($1)
                     AND sp.price IS NOT NULL
                     AND sp.marca IS NOT NULL AND sp.marca != ''
                     AND sp.scraped_at > $2
                     AND s.is_active = TRUE""",
                unique_medidas, cache_cutoff,
            )

            # (supplier, medida, marca) → conjunto de modelos em cache recente
            cache_modelos: dict = {}
            for r in rows_cache:
                key = (r['supplier_name'], r['medida'], r['marca_up'])
                cache_modelos.setdefault(key, set()).add(r['modelo_up'])

            pairs_sem_dados_set: set = set()
            for m, b, mod in unique_triples:
                for s in active_supplier_names:
                    key = (s, m, b)
                    cached = cache_modelos.get(key, set())

                    if not mod:
                        # Sem modelo especificado: basta ter qualquer dado recente
                        if not cached:
                            pairs_sem_dados_set.add((m, b))
                        break

                    # Com modelo: exigir match exato no cache recente
                    # (modelo guardado começa com ou contém o modelo pesquisado)
                    has_exact = any(
                        mod == stored or stored.startswith(mod + ' ') or stored.startswith(mod)
                        for stored in cached
                        if stored
                    )
                    if not has_exact:
                        pairs_sem_dados_set.add((m, b))
                    break  # basta verificar um fornecedor (todos recebem o mesmo scrape)

            pairs_sem_dados = list(pairs_sem_dados_set)

    scraper_timed_out = False
    # Scrape pares (medida, marca) em falta (ou todos se force=true)
    if pairs_sem_dados:
        medidas_sem_dados = list({p[0] for p in pairs_sem_dados})
        marcas_sem_dados  = list({b for _, b in pairs_sem_dados if b})
        # Limpa registos sem marca E registos antigos (> 12h) das marcas a re-scrape
        # para não servir modelos fora de stock após a pesquisa
        pool2 = await get_db()
        async with pool2.acquire() as conn:
            await conn.execute(
                "DELETE FROM scraped_prices WHERE medida = ANY($1) AND marca IS NULL",
                medidas_sem_dados,
            )
            if marcas_sem_dados:
                stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
                await conn.execute(
                    """DELETE FROM scraped_prices
                       WHERE medida = ANY($1)
                         AND UPPER(COALESCE(marca,'')) = ANY($2)
                         AND scraped_at < $3""",
                    medidas_sem_dados,
                    [b.upper() for b in marcas_sem_dados],
                    stale_cutoff,
                )
        items_json = json.dumps([{"medida": m, "marca": b} for m, b in pairs_sem_dados])
        logger.info(f"A correr scraper para {len(pairs_sem_dados)} pares medida+marca...")
        env = os.environ.copy()
        env['PLAYWRIGHT_BROWSERS_PATH'] = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/pw-browsers')
        medidas_str = ','.join(medidas_sem_dados)
        proc = await asyncio.create_subprocess_exec(
            'python3', '/app/backend/run_scraper.py',
            '--medidas', medidas_str,
            '--items-json', items_json,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            cwd='/app/backend',
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=1200)
            logger.info(f"Scraper concluído. Output final: {stdout.decode()[-500:]}")
        except asyncio.TimeoutError:
            proc.kill()
            logger.warning("Scraper timeout após 20 minutos")
            scraper_timed_out = True

    pool = await get_db()
    async with pool.acquire() as conn:
        all_scraped = rows(await conn.fetch(
            """
            SELECT sp.* FROM scraped_prices sp
            JOIN suppliers s ON s.name = sp.supplier_name
            WHERE sp.medida = ANY($1)
              AND sp.price IS NOT NULL
              AND s.is_active = TRUE
            """,
            unique_medidas,
        ))

    # Indexar por medida
    prices_by_medida: Dict[str, list] = {}
    for sp in all_scraped:
        m = sp.get('medida', '')
        prices_by_medida.setdefault(m, []).append(sp)

    updated_count = found_count = matched_count = 0
    total_savings = 0.0
    bulk_updates = []

    for item in items:
        medida_norm = item['medida'].replace('/', '').replace('R', '').replace('r', '')
        marca_norm  = (item.get('marca')  or '').strip().upper()
        modelo_norm = (item.get('modelo') or '').strip().upper()

        scraped = []
        match_type = None
        medida_prices = prices_by_medida.get(medida_norm, [])

        if medida_prices:
            if marca_norm and modelo_norm:
                marca_prices = [p for p in medida_prices if (p.get('marca') or '').upper() == marca_norm]
                if marca_prices:
                    # Level 1: exact match
                    pat_exact = re.compile(f"^{re.escape(modelo_norm)}$", re.IGNORECASE)
                    scraped = [p for p in marca_prices if pat_exact.match(p.get('modelo') or '')]
                    if scraped:
                        match_type = "modelo_exato"
                    else:
                        # Level 2: scraped description ends with the user's model name
                        # e.g. user="crossclimate 2", scraped="MICHELIN 205/55R16 91W CROSSCLIMATE 2"
                        # Also handles "CROSSCLIMATE 2 XL" (model + suffix like XL/SUV/etc)
                        pat_end = re.compile(
                            r'(?:^|\s)' + re.escape(modelo_norm) + r'(\s+\w+)?$',
                            re.IGNORECASE
                        )
                        scraped = [p for p in marca_prices if pat_end.search(p.get('modelo') or '')]
                        if scraped:
                            match_type = "modelo_exato"
                        else:
                            # Level 3: model name at start of description
                            pat_start = re.compile(f"^{re.escape(modelo_norm)}(\\s|$)", re.IGNORECASE)
                            scraped = [p for p in marca_prices if pat_start.match(p.get('modelo') or '')]
                            if scraped:
                                match_type = "modelo_parcial"
                            else:
                                # Level 4: model name anywhere in description
                                pat_contains = re.compile(re.escape(modelo_norm), re.IGNORECASE)
                                scraped = [p for p in marca_prices if pat_contains.search(p.get('modelo') or '')]
                                if scraped:
                                    match_type = "modelo_parcial"

            if not scraped and marca_norm:
                marca_prices = [p for p in medida_prices if (p.get('marca') or '').upper() == marca_norm]
                if marca_prices:
                    scraped = marca_prices
                    match_type = "marca"
                else:
                    pat_marca = re.compile(f"^{marca_norm.replace(' ', '.*')}$", re.IGNORECASE)
                    scraped = [p for p in medida_prices if pat_marca.match(p.get('marca') or '')]
                    if scraped:
                        match_type = "marca_parcial"

            if not scraped:
                scraped = medida_prices
                match_type = "medida"

        if scraped:
            scraped = sorted(scraped, key=lambda x: x.get('price', 999999))
            best = scraped[0]
            best_price    = best['price']
            best_supplier = best['supplier_name']
            best_marca    = best.get('marca', '')
            best_modelo   = best.get('modelo', '')
            meu_preco     = item.get('meu_preco', 0)
            sup_prices = {}
            for s in scraped:
                k = s['supplier_name']
                if k not in sup_prices or s['price'] < sup_prices[k]:
                    sup_prices[k] = s['price']

            # Só conta poupança real se houver match de marca/modelo
            # "só medida" = outra marca diferente → preço informativo, não é poupança
            brand_matched = match_type in ("modelo_exato", "modelo_parcial", "marca", "marca_parcial")
            if brand_matched and meu_preco:
                economia_euro    = meu_preco - best_price
                economia_percent = economia_euro / meu_preco * 100
            else:
                economia_euro    = None
                economia_percent = None

            if match_type == "medida":
                item_status = "no_brand_match"
            elif economia_euro and economia_euro > 0:
                item_status = "found"
            else:
                item_status = "processed"

            bulk_updates.append((
                item['id'], best_price, best_supplier, best_marca, best_modelo,
                match_type,
                round(economia_euro, 2) if economia_euro is not None else None,
                round(economia_percent, 2) if economia_percent is not None else None,
                sup_prices,
                item_status,
            ))
            updated_count += 1
            matched_count += 1
            if economia_euro and economia_euro > 0:
                found_count += 1
                total_savings += economia_euro
        else:
            bulk_updates.append((
                item['id'], None, None, None, None, "sem_dados",
                None, None, {}, "no_data",
            ))
            updated_count += 1

    async with pool.acquire() as conn:
        async with conn.transaction():
            for u in bulk_updates:
                await conn.execute(
                    """
                    UPDATE job_items SET
                        melhor_preco=$2, melhor_fornecedor=$3, melhor_marca=$4,
                        modelo_encontrado=$5, match_type=$6,
                        economia_euro=$7, economia_percent=$8,
                        supplier_prices=$9, status=$10
                    WHERE id=$1
                    """,
                    *u,
                )
            await conn.execute(
                """
                UPDATE jobs SET
                    processed_items=$2, found_items=$3, matched_items=$4,
                    total_savings=$5, status=$6, completed_at=$7
                WHERE id=$1
                """,
                job_id, updated_count, found_count, matched_count,
                round(total_savings, 2), JobStatus.COMPLETED.value,
                datetime.now(timezone.utc),
            )

    return {
        "message": "Comparison completed",
        "items_processed": updated_count,
        "items_matched": matched_count,
        "items_with_savings": found_count,
        "total_savings": round(total_savings, 2),
        "scraper_timeout": scraper_timed_out,
    }


@api_router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        r = row(await conn.fetchrow("SELECT id FROM jobs WHERE id = $1", job_id))
        if not r:
            raise HTTPException(status_code=404, detail="Job not found")
        async with conn.transaction():
            await conn.execute("DELETE FROM job_items WHERE job_id = $1", job_id)
            await conn.execute("DELETE FROM prices    WHERE job_id = $1", job_id)
            await conn.execute("DELETE FROM logs      WHERE job_id = $1", job_id)
            await conn.execute("DELETE FROM jobs      WHERE id     = $1", job_id)
    logger.info(f"Job {job_id} e dados relacionados eliminados")
    return {"message": "Job deleted successfully"}


@api_router.get("/jobs/{job_id}/export")
async def export_job_results(job_id: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        job = row(await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id))
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        items = rows(await conn.fetch("SELECT * FROM job_items WHERE job_id = $1", job_id))
        suppliers = rows(await conn.fetch("SELECT name FROM suppliers WHERE is_active = TRUE"))

    supplier_names = [s['name'] for s in suppliers]
    try:
        excel_bytes = excel_service.generate_results(job, items, supplier_names)
        return StreamingResponse(
            BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=results_{job_id[:8]}.xlsx"},
        )
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Logs ====================

@api_router.get("/logs")
async def get_logs(job_id: Optional[str] = None, limit: int = 100):
    pool = await get_db()
    async with pool.acquire() as conn:
        if job_id:
            rs = rows(await conn.fetch(
                "SELECT * FROM logs WHERE job_id = $1 ORDER BY created_at DESC LIMIT $2",
                job_id, limit,
            ))
        else:
            rs = rows(await conn.fetch(
                "SELECT * FROM logs ORDER BY created_at DESC LIMIT $1", limit
            ))
    return rs


# ==================== Stats ====================

@api_router.get("/stats")
async def get_stats():
    pool = await get_db()
    async with pool.acquire() as conn:
        total_jobs     = await conn.fetchval("SELECT COUNT(*) FROM jobs WHERE type IS NULL")
        completed_jobs = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE type IS NULL AND status = $1",
            JobStatus.COMPLETED.value,
        )
        active_suppliers = await conn.fetchval(
            "SELECT COUNT(*) FROM suppliers WHERE is_active = TRUE"
        )
        total_savings = await conn.fetchval(
            "SELECT COALESCE(SUM(total_savings), 0) FROM jobs WHERE status = $1",
            JobStatus.COMPLETED.value,
        ) or 0.0
        recent_jobs = rows(await conn.fetch(
            "SELECT * FROM jobs WHERE type IS NULL ORDER BY created_at DESC LIMIT 5"
        ))

    return {
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "active_suppliers": active_suppliers,
        "total_savings": round(float(total_savings), 2),
        "recent_jobs": recent_jobs,
    }


# ==================== Manual Scraper ====================

scraper_status = {"running": False, "started_at": None, "progress": "", "results": []}


async def run_manual_scraper(medidas: list):
    global scraper_status
    scraper_status.update(running=True, started_at=datetime.now(timezone.utc).isoformat(),
                          progress="Starting scraper...", results=[])
    try:
        medidas_str = ','.join(medidas)
        env = os.environ.copy()
        env['PLAYWRIGHT_BROWSERS_PATH'] = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/pw-browsers')
        proc = await asyncio.create_subprocess_exec(
            'python3', '/app/backend/run_scraper.py', '--medidas', medidas_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            cwd='/app/backend',
        )
        output_lines = []
        # Read output line-by-line without blocking the event loop
        async for raw_line in proc.stdout:
            line = raw_line.decode(errors='replace').rstrip()
            if line:
                output_lines.append(line)
                scraper_status["progress"] = line
        await proc.wait()
        scraper_status["progress"] = "Completed"
        scraper_status["results"] = output_lines[-100:]
    except Exception as e:
        scraper_status["progress"] = f"Error: {str(e)}"
        logger.error(f"Scraper error: {e}")
    finally:
        scraper_status["running"] = False


from pydantic import BaseModel as PydanticBaseModel  # noqa: F811 (re-import for local use)


class ScrapeRunReq(PydanticBaseModel):
    medidas: Optional[List[str]] = None


@api_router.post("/scraper/run")
async def start_manual_scraper(
    background_tasks: BackgroundTasks,
    req: Optional[ScrapeRunReq] = Body(default=None),
):
    medidas = req.medidas if req else None
    global scraper_status
    if scraper_status["running"]:
        raise HTTPException(status_code=409, detail="Scraper is already running")

    if not medidas:
        pool = await get_db()
        async with pool.acquire() as conn:
            pending_jobs = rows(await conn.fetch(
                "SELECT id FROM jobs WHERE status = ANY($1) AND type IS NULL",
                ['pending', 'running'],
            ))
        medidas = []
        for job in pending_jobs:
            pool2 = await get_db()
            async with pool2.acquire() as conn:
                job_items_list = rows(await conn.fetch(
                    "SELECT medida FROM job_items WHERE job_id = $1", job['id']
                ))
            for it in job_items_list:
                m = it.get("medida", "").replace("/", "").replace("R", "")
                if m and m not in medidas:
                    medidas.append(m)
        if not medidas:
            medidas = ["2055516"]

    background_tasks.add_task(run_manual_scraper, medidas)
    return {"message": "Scraper started", "medidas": medidas}


@api_router.get("/scraper/status")
async def get_scraper_status():
    return scraper_status


@api_router.get("/scraper/debug-html")
async def get_scraper_debug_html(file: str = "results", supplier: str = "sjose"):
    """Return content of /tmp/{supplier}_{file}.html debug files.
    ?supplier=sjose|soledad  &file=pre_login|after_login|search_page|results
    """
    allowed_files = {"pre_login", "after_login", "search_page", "results", "inputs", "api", "frame", "after_nav"}
    allowed_suppliers = {"sjose", "soledad", "tugapneus", "intersprint"}
    if file not in allowed_files:
        raise HTTPException(status_code=400, detail=f"file must be one of {allowed_files}")
    if supplier not in allowed_suppliers:
        raise HTTPException(status_code=400, detail=f"supplier must be one of {allowed_suppliers}")
    path = f"/tmp/{supplier}_{file}.html"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read(30000)
        return {"file": path, "size": len(content), "content": content}
    except FileNotFoundError:
        return {"file": path, "size": 0, "content": None,
                "note": f"File not found — run a scrape for that supplier first"}


@api_router.get("/scraper/debug-forms")
async def get_scraper_debug_forms(file: str = "after_login"):
    """Parse /tmp/sjose_*.html and return all form inputs (id, name, type, value).
    Useful for finding the correct CSS selectors for the login/search forms.
    """
    from html.parser import HTMLParser

    allowed = {"pre_login", "after_login", "search_page", "results"}
    if file not in allowed:
        raise HTTPException(status_code=400, detail=f"file must be one of {allowed}")
    path = f"/tmp/sjose_{file}.html"

    class InputParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.inputs = []
            self.forms = []

        def handle_starttag(self, tag, attrs):
            d = dict(attrs)
            if tag == "input":
                self.inputs.append({
                    "id":    d.get("id", ""),
                    "name":  d.get("name", ""),
                    "type":  d.get("type", "text"),
                    "value": d.get("value", "")[:60],
                })
            elif tag == "form":
                self.forms.append({
                    "id":     d.get("id", ""),
                    "action": d.get("action", ""),
                    "method": d.get("method", ""),
                })
            elif tag == "button":
                self.inputs.append({
                    "id":    d.get("id", ""),
                    "name":  d.get("name", ""),
                    "type":  f"button/{d.get('type', '')}",
                    "value": d.get("value", "")[:60],
                })
            elif tag == "a":
                href = d.get("href", "")
                if "javascript" in href.lower() or d.get("id"):
                    self.inputs.append({
                        "id":    d.get("id", ""),
                        "name":  "",
                        "type":  "link",
                        "value": href[:80],
                    })

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            html = fh.read()
        parser = InputParser()
        parser.feed(html)
        return {
            "file": path,
            "forms": parser.forms,
            "inputs": [i for i in parser.inputs if i["type"] not in ("hidden",)],
            "hidden_count": sum(1 for i in parser.inputs if i["type"] == "hidden"),
        }
    except FileNotFoundError:
        return {"file": path, "forms": [], "inputs": [],
                "note": "File not found — run a scrape for S. José Pneus first"}


@api_router.get("/scraper/availability")
async def check_scraper_availability():
    pw_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/pw-browsers')
    chromium_dirs = list(Path(pw_path).glob('chromium_headless_shell-*'))
    available = len(chromium_dirs) > 0
    return {
        "available": available,
        "playwright_path": pw_path,
        "message": "Scraping is available" if available else "Playwright browsers not installed.",
    }


# ==================== Scraped Prices ====================

@api_router.get("/scraped-prices")
async def get_scraped_prices(
    medida: str = None, marca: str = None,
    modelo: str = None, load_index: str = None,
):
    conditions = ["TRUE"]
    params: list = []

    if medida:
        mn = medida.replace("/", "").replace("R", "")
        params.append(f"%{mn}%")
        conditions.append(f"medida ILIKE ${len(params)}")
    if marca:
        params.append(f"%{marca.strip()}%")
        conditions.append(f"marca ILIKE ${len(params)}")
    if modelo:
        params.append(f"%{modelo.strip()}%")
        conditions.append(f"modelo ILIKE ${len(params)}")
    if load_index:
        params.append(f"%{load_index.strip()}%")
        conditions.append(f"load_index ILIKE ${len(params)}")

    where = " AND ".join(conditions)
    pool = await get_db()
    async with pool.acquire() as conn:
        rs = rows(await conn.fetch(
            f"""
            SELECT sp.* FROM scraped_prices sp
            INNER JOIN suppliers s ON LOWER(s.name) = LOWER(sp.supplier_name) AND s.is_active = TRUE
            WHERE {where}
            ORDER BY sp.scraped_at DESC LIMIT 500
            """,
            *params,
        ))
    return rs


@api_router.get("/scraped-prices/best/{medida}")
async def get_best_price(medida: str):
    mn = medida.replace("/", "").replace("R", "")
    pool = await get_db()
    async with pool.acquire() as conn:
        rs = rows(await conn.fetch(
            """
            SELECT sp.* FROM scraped_prices sp
            INNER JOIN suppliers s ON LOWER(s.name) = LOWER(sp.supplier_name) AND s.is_active = TRUE
            WHERE sp.medida ILIKE $1 AND sp.price IS NOT NULL
            ORDER BY sp.price ASC LIMIT 100
            """,
            f"%{mn}%",
        ))
    if rs:
        best = rs[0]
        return {
            "medida": medida,
            "best_price": best["price"],
            "best_supplier": best["supplier_name"],
            "scraped_at": best.get("scraped_at"),
            "all_prices": [{"supplier": p["supplier_name"], "price": p["price"]} for p in rs],
        }
    return {"medida": medida, "best_price": None, "message": "No prices found"}


# ==================== Worker Queue ====================


class EnqueueReq(PydanticBaseModel):
    supplier_id: str
    sizes: List[str]
    meta: Optional[dict] = None


@api_router.post("/scrape/enqueue")
async def enqueue_scrape(req: EnqueueReq):
    job_id = str(uuid.uuid4())
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO jobs
                (id, type, supplier_id, payload, status, attempts, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            job_id, "scrape", req.supplier_id,
            {"sizes": req.sizes, "meta": req.meta or {}},
            "queued", 0, datetime.now(timezone.utc),
        )
    return {"ok": True, "job_id": job_id}


@api_router.get("/scrape/jobs")
async def get_scrape_jobs(status: str = None, limit: int = 20):
    pool = await get_db()
    async with pool.acquire() as conn:
        if status:
            rs = rows(await conn.fetch(
                "SELECT * FROM jobs WHERE type='scrape' AND status=$1 ORDER BY created_at DESC LIMIT $2",
                status, limit,
            ))
        else:
            rs = rows(await conn.fetch(
                "SELECT * FROM jobs WHERE type='scrape' ORDER BY created_at DESC LIMIT $1", limit
            ))
    return rs


@api_router.get("/scrape/jobs/{job_id}")
async def get_scrape_job(job_id: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        r = row(await conn.fetchrow(
            "SELECT * FROM jobs WHERE id = $1 AND type = 'scrape'", job_id
        ))
    if not r:
        raise HTTPException(status_code=404, detail="Job not found")
    return r


# ==================== Worker Management ====================

@api_router.get("/worker/status")
async def get_worker_status():
    import subprocess
    try:
        result = subprocess.run(
            ["pgrep", "-f", "worker.py"],
            capture_output=True, text=True, timeout=5,
        )
        is_running = result.returncode == 0
        pids = result.stdout.strip().split('\n') if is_running else []
        pool = await get_db()
        async with pool.acquire() as conn:
            queued_count  = await conn.fetchval(
                "SELECT COUNT(*) FROM jobs WHERE type='scrape' AND status='queued'"
            )
            running_count = await conn.fetchval(
                "SELECT COUNT(*) FROM jobs WHERE type='scrape' AND status='running'"
            )
        return {"running": is_running, "pids": pids,
                "queued_jobs": queued_count, "running_jobs": running_count}
    except Exception as e:
        return {"running": False, "error": str(e)}


@api_router.post("/worker/start")
async def start_worker():
    import subprocess
    check = subprocess.run(["pgrep", "-f", "worker.py"], capture_output=True, text=True)
    if check.returncode == 0:
        return {"ok": True, "message": "Worker already running", "pid": check.stdout.strip()}
    try:
        python_path = "/root/.venv/bin/python3"
        cmd = f"cd /app/backend && nohup {python_path} worker.py >> /tmp/worker.log 2>&1 &"
        proc = await asyncio.create_subprocess_shell(cmd)
        await proc.wait()
        await asyncio.sleep(3)
        check = subprocess.run(["pgrep", "-f", "worker.py"], capture_output=True, text=True)
        if check.returncode == 0:
            return {"ok": True, "message": "Worker started successfully", "pid": check.stdout.strip()}
        try:
            with open("/tmp/worker.log") as f:
                last_lines = f.read().split('\n')[-10:]
            return {"ok": False, "message": "Worker failed to start", "log": last_lines}
        except Exception:
            return {"ok": False, "message": "Worker failed to start"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class EnqueueBatchReq(PydanticBaseModel):
    sizes: List[str]
    supplier_ids: Optional[List[str]] = None


@api_router.post("/scrape/enqueue-batch")
async def enqueue_batch_scrape(req: EnqueueBatchReq):
    pool = await get_db()
    async with pool.acquire() as conn:
        if req.supplier_ids:
            suppliers = []
            for sid in req.supplier_ids:
                r = row(await conn.fetchrow(
                    "SELECT * FROM suppliers WHERE (id=$1 OR name ILIKE $2) AND is_active=TRUE",
                    sid, f"%{sid}%",
                ))
                if r:
                    suppliers.append(r)
        else:
            suppliers = rows(await conn.fetch(
                "SELECT * FROM suppliers WHERE is_active = TRUE"
            ))

    if not suppliers:
        raise HTTPException(status_code=400, detail="No active suppliers found")

    normalized = [s.strip().replace('/', '').replace('R', '').replace('r', '')
                  for s in req.sizes if s.strip()]
    if not normalized:
        raise HTTPException(status_code=400, detail="No valid sizes provided")

    job_ids = []
    now = datetime.now(timezone.utc)
    pool2 = await get_db()
    async with pool2.acquire() as conn:
        for supplier in suppliers:
            job_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO jobs
                    (id, type, supplier_id, supplier_name, payload, status,
                     attempts, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                job_id, "scrape", supplier['id'], supplier['name'],
                {"sizes": normalized}, "queued", 0, now,
            )
            job_ids.append(job_id)

    return {
        "ok": True,
        "jobs_created": len(job_ids),
        "job_ids": job_ids,
        "suppliers": [s['name'] for s in suppliers],
        "sizes": normalized,
    }


# ==================== App setup ====================

app.include_router(api_router)

_cors_origins = os.environ.get('CORS_ORIGINS', '*').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_credentials=_cors_origins != ['*'],
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
