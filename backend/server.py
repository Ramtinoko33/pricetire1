from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from typing import List, Optional, Dict
import uuid
from datetime import datetime, timezone
import asyncio
from io import BytesIO

from models import (
    Supplier, SupplierCreate, SupplierUpdate, SupplierStatus,
    Job, JobCreate, JobItem, JobStatus, ItemStatus,
    Price, Log, TestLoginResponse, JobProgress
)
from scraper_service import ScraperService
from excel_service import ExcelService
from passlib.context import CryptContext

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

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

@api_router.get("/suppliers", response_model=List[Supplier])
async def get_suppliers():
    suppliers = await db.suppliers.find({}, {"_id": 0}).to_list(1000)
    for supplier in suppliers:
        supplier['password'] = "********"
    return suppliers

@api_router.post("/suppliers", response_model=Supplier)
async def create_supplier(supplier_data: SupplierCreate):
    supplier_dict = supplier_data.model_dump()
    supplier_dict['password'] = pwd_context.hash(supplier_dict['password'])
    supplier_dict['id'] = str(uuid.uuid4())
    supplier_dict['is_active'] = True
    supplier_dict['status'] = SupplierStatus.ACTIVE.value
    supplier_dict['last_test'] = None
    supplier_dict['created_at'] = datetime.now(timezone.utc).isoformat()
    
    await db.suppliers.insert_one(supplier_dict)
    supplier_dict['password'] = "********"
    return Supplier(**supplier_dict)

@api_router.put("/suppliers/{supplier_id}", response_model=Supplier)
async def update_supplier(supplier_id: str, supplier_data: SupplierUpdate):
    update_dict = {k: v for k, v in supplier_data.model_dump().items() if v is not None}
    if 'password' in update_dict:
        update_dict['password'] = pwd_context.hash(update_dict['password'])
        # Also update password_raw for scraping
        update_dict['password_raw'] = supplier_data.password
    
    result = await db.suppliers.update_one({"id": supplier_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    supplier['password'] = "********"
    return Supplier(**supplier)

@api_router.get("/suppliers/{supplier_id}/selectors")
async def get_supplier_selectors(supplier_id: str):
    """Get CSS selectors for a supplier"""
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    # Default selectors structure
    default_selectors = {
        "login_username": "",
        "login_password": "",
        "login_button": "",
        "search_input": "",
        "search_button": "",
        "price_pattern": "",
        "notes": ""
    }
    
    current_selectors = supplier.get('selectors') or {}
    return {**default_selectors, **current_selectors}

@api_router.put("/suppliers/{supplier_id}/selectors")
async def update_supplier_selectors(supplier_id: str, selectors: Dict[str, str]):
    """Update CSS selectors for a supplier"""
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    result = await db.suppliers.update_one(
        {"id": supplier_id},
        {"$set": {"selectors": selectors}}
    )
    
    return {"message": "Selectors updated", "selectors": selectors}

@api_router.delete("/suppliers/{supplier_id}")
async def delete_supplier(supplier_id: str):
    result = await db.suppliers.delete_one({"id": supplier_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {"message": "Supplier deleted successfully"}

@api_router.post("/suppliers/{supplier_id}/test", response_model=TestLoginResponse)
async def test_supplier_login(supplier_id: str):
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    try:
        success, message, screenshot = await scraper_service.test_supplier_login(supplier)
        
        await db.suppliers.update_one(
            {"id": supplier_id},
            {"$set": {
                "last_test": datetime.now(timezone.utc).isoformat(),
                "status": SupplierStatus.ACTIVE.value if success else SupplierStatus.ERROR.value
            }}
        )
        
        log_doc = {
            "id": str(uuid.uuid4()),
            "supplier_id": supplier_id,
            "level": "INFO" if success else "ERROR",
            "message": f"Login test: {message}",
            "screenshot_path": screenshot,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.logs.insert_one(log_doc)
        
        return TestLoginResponse(success=success, message=message, screenshot_path=screenshot)
        
    except Exception as e:
        logger.error(f"Test login error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/jobs/upload", response_model=Job)
async def upload_excel(file: UploadFile = File(...), threshold_euro: float = 5.0, threshold_percent: float = 10.0):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="File must be Excel format (.xlsx or .xls)")
    
    try:
        content = await file.read()
        items = excel_service.parse_upload(content, file.filename)
        
        if not items:
            raise HTTPException(status_code=400, detail="No valid items found in Excel file")
        
        job_id = str(uuid.uuid4())
        job_dict = {
            "id": job_id,
            "filename": file.filename,
            "status": JobStatus.PENDING.value,
            "total_items": len(items),
            "processed_items": 0,
            "found_items": 0,
            "total_savings": 0.0,
            "threshold_euro": threshold_euro,
            "threshold_percent": threshold_percent,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "error_message": None
        }
        
        await db.jobs.insert_one(job_dict)
        
        for item in items:
            item_doc = {
                "id": str(uuid.uuid4()),
                "job_id": job_id,
                "ref_id": item['ref_id'],
                "medida": item['medida'],
                "marca": item['marca'],
                "modelo": item['modelo'],
                "indice": item['indice'],
                "meu_preco": item['meu_preco'],
                "melhor_preco": None,
                "melhor_fornecedor": None,
                "economia_euro": None,
                "economia_percent": None,
                "status": ItemStatus.PENDING.value,
                "supplier_prices": {},
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.job_items.insert_one(item_doc)
        
        logger.info(f"Created job {job_id} with {len(items)} items")
        return Job(**job_dict)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

@api_router.post("/jobs/{job_id}/run")
async def run_job(job_id: str, background_tasks: BackgroundTasks):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job['status'] == JobStatus.RUNNING.value:
        raise HTTPException(status_code=400, detail="Job is already running")
    
    await db.jobs.update_one(
        {"id": job_id},
        {"$set": {
            "status": JobStatus.RUNNING.value,
            "started_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    background_tasks.add_task(run_scraping_job, job_id)
    return {"message": "Job started", "job_id": job_id}

async def run_scraping_job(job_id: str):
    try:
        logger.info(f"Starting scraping job {job_id}")
        
        job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
        items = await db.job_items.find({"job_id": job_id}, {"_id": 0}).to_list(None)
        suppliers = await db.suppliers.find({"is_active": True}, {"_id": 0}).to_list(None)
        
        if not suppliers:
            await db.jobs.update_one(
                {"id": job_id},
                {"$set": {
                    "status": JobStatus.FAILED.value,
                    "error_message": "No active suppliers found",
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            return
        
        processed = 0
        found = 0
        total_savings = 0.0
        
        for item in items:
            logger.info(f"Processing item {item['ref_id']}: {item['medida']} {item['marca']} {item['modelo']}")
            
            await db.job_items.update_one(
                {"id": item['id']},
                {"$set": {"status": ItemStatus.PROCESSING.value}}
            )
            
            supplier_prices = {}
            best_price = None
            best_supplier = None
            
            for supplier in suppliers:
                try:
                    logger.info(f"Searching in {supplier['name']}...")
                    
                    price = await scraper_service.scrape_product(
                        supplier,
                        item['medida'],
                        item['marca'],
                        item['modelo'],
                        item['indice']
                    )
                    
                    if price is not None:
                        supplier_prices[supplier['name']] = price
                        
                        if best_price is None or price < best_price:
                            best_price = price
                            best_supplier = supplier['name']
                        
                        price_doc = {
                            "id": str(uuid.uuid4()),
                            "job_id": job_id,
                            "item_id": item['id'],
                            "supplier_id": supplier['id'],
                            "supplier_name": supplier['name'],
                            "price": price,
                            "status": ItemStatus.FOUND.value,
                            "found_at": datetime.now(timezone.utc).isoformat()
                        }
                        await db.prices.insert_one(price_doc)
                    else:
                        supplier_prices[supplier['name']] = "NAO_ENCONTRADO"
                        
                        price_doc = {
                            "id": str(uuid.uuid4()),
                            "job_id": job_id,
                            "item_id": item['id'],
                            "supplier_id": supplier['id'],
                            "supplier_name": supplier['name'],
                            "price": None,
                            "status": ItemStatus.NOT_FOUND.value,
                            "found_at": datetime.now(timezone.utc).isoformat()
                        }
                        await db.prices.insert_one(price_doc)
                    
                    await asyncio.sleep(0.7)
                    
                except Exception as e:
                    logger.error(f"Error searching {supplier['name']}: {str(e)}")
                    supplier_prices[supplier['name']] = "ERRO"
                    
                    log_doc = {
                        "id": str(uuid.uuid4()),
                        "job_id": job_id,
                        "supplier_id": supplier['id'],
                        "level": "ERROR",
                        "message": f"Error searching item {item['ref_id']}: {str(e)}",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db.logs.insert_one(log_doc)
            
            economia_euro = None
            economia_percent = None
            item_status = ItemStatus.NOT_FOUND.value
            
            if best_price is not None:
                economia_euro = item['meu_preco'] - best_price
                economia_percent = (economia_euro / item['meu_preco']) * 100
                
                if economia_euro >= job['threshold_euro'] or economia_percent >= job['threshold_percent']:
                    item_status = ItemStatus.FOUND.value
                    found += 1
                    total_savings += economia_euro
            
            await db.job_items.update_one(
                {"id": item['id']},
                {"$set": {
                    "melhor_preco": best_price,
                    "melhor_fornecedor": best_supplier,
                    "economia_euro": economia_euro,
                    "economia_percent": economia_percent,
                    "status": item_status,
                    "supplier_prices": supplier_prices
                }}
            )
            
            processed += 1
            
            await db.jobs.update_one(
                {"id": job_id},
                {"$set": {
                    "processed_items": processed,
                    "found_items": found,
                    "total_savings": total_savings
                }}
            )
        
        for supplier in suppliers:
            await scraper_service.cleanup_supplier(supplier['id'])
        
        await db.jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": JobStatus.COMPLETED.value,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"Job {job_id} completed. Processed: {processed}, Found: {found}, Savings: €{total_savings:.2f}")
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")
        await db.jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": JobStatus.FAILED.value,
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )

@api_router.get("/jobs", response_model=List[Job])
async def get_jobs():
    # Filter out scrape queue jobs (which have type field)
    jobs = await db.jobs.find({"type": {"$exists": False}}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [Job(**job) for job in jobs]

@api_router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return Job(**job)

@api_router.get("/jobs/{job_id}/progress", response_model=JobProgress)
async def get_job_progress(job_id: str):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    progress_percent = (job['processed_items'] / job['total_items'] * 100) if job['total_items'] > 0 else 0
    
    return JobProgress(
        job_id=job_id,
        status=JobStatus(job['status']),
        total_items=job['total_items'],
        processed_items=job['processed_items'],
        found_items=job['found_items'],
        progress_percent=round(progress_percent, 1)
    )

@api_router.get("/jobs/{job_id}/results")
async def get_job_results(job_id: str):
    items = await db.job_items.find({"job_id": job_id}, {"_id": 0}).to_list(None)
    return items

@api_router.post("/jobs/{job_id}/compare")
async def compare_job_with_scraped_prices(job_id: str):
    """Compare job items with existing scraped prices by MEDIDA + MARCA"""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    items = await db.job_items.find({"job_id": job_id}, {"_id": 0}).to_list(None)
    
    if not items:
        raise HTTPException(status_code=400, detail="No items found in job")
    
    updated_count = 0
    found_count = 0
    matched_count = 0
    total_savings = 0.0
    
    for item in items:
        # Normalize medida and marca for matching
        medida_norm = item['medida'].replace('/', '').replace('R', '').replace('r', '')
        marca_norm = (item.get('marca') or '').strip().upper()
        
        # First try: exact match by medida + marca
        scraped = await db.scraped_prices.find(
            {
                "medida": medida_norm, 
                "marca": marca_norm,
                "price": {"$ne": None}
            },
            {"_id": 0}
        ).sort("price", 1).to_list(100)
        
        match_type = "exact"
        
        # Second try: if no exact match, try partial brand match (for variations like "GOOD YEAR" vs "GOODYEAR")
        if not scraped and marca_norm:
            # Create regex pattern to match brand variations
            marca_pattern = marca_norm.replace(' ', '.*')
            scraped = await db.scraped_prices.find(
                {
                    "medida": medida_norm, 
                    "marca": {"$regex": marca_pattern, "$options": "i"},
                    "price": {"$ne": None}
                },
                {"_id": 0}
            ).sort("price", 1).to_list(100)
            match_type = "partial"
        
        # Third try: fallback to medida only if no brand match found
        if not scraped:
            scraped = await db.scraped_prices.find(
                {
                    "medida": medida_norm, 
                    "price": {"$ne": None}
                },
                {"_id": 0}
            ).sort("price", 1).to_list(100)
            match_type = "medida_only"
        
        if scraped:
            best = scraped[0]
            best_price = best['price']
            best_supplier = best['supplier_name']
            best_marca = best.get('marca', '')
            
            # Calculate savings
            meu_preco = item.get('meu_preco', 0)
            economia_euro = meu_preco - best_price if meu_preco else None
            economia_percent = (economia_euro / meu_preco * 100) if meu_preco and economia_euro else None
            
            # Build supplier_prices dict with brand info
            supplier_prices = {}
            for s in scraped:
                key = f"{s['supplier_name']} ({s.get('marca', 'N/A')})"
                supplier_prices[key] = s['price']
            
            # Update item
            await db.job_items.update_one(
                {"id": item['id']},
                {"$set": {
                    "melhor_preco": best_price,
                    "melhor_fornecedor": best_supplier,
                    "melhor_marca": best_marca,
                    "match_type": match_type,
                    "economia_euro": round(economia_euro, 2) if economia_euro else None,
                    "economia_percent": round(economia_percent, 2) if economia_percent else None,
                    "supplier_prices": supplier_prices,
                    "status": "found" if economia_euro and economia_euro > 0 else "processed"
                }}
            )
            
            updated_count += 1
            if match_type in ["exact", "partial"]:
                matched_count += 1
            if economia_euro and economia_euro > 0:
                found_count += 1
                total_savings += economia_euro
    
    # Update job stats
    await db.jobs.update_one(
        {"id": job_id},
        {"$set": {
            "processed_items": updated_count,
            "found_items": found_count,
            "matched_items": matched_count,
            "total_savings": round(total_savings, 2),
            "status": JobStatus.COMPLETED.value,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        "message": "Comparison completed",
        "items_processed": updated_count,
        "items_with_savings": found_count,
        "total_savings": round(total_savings, 2)
    }

@api_router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete job and all related data"""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Delete job items
    await db.job_items.delete_many({"job_id": job_id})
    
    # Delete prices
    await db.prices.delete_many({"job_id": job_id})
    
    # Delete logs related to this job
    await db.logs.delete_many({"job_id": job_id})
    
    # Delete job
    await db.jobs.delete_one({"id": job_id})
    
    logger.info(f"Deleted job {job_id} and all related data")
    return {"message": "Job deleted successfully"}

@api_router.get("/jobs/{job_id}/export")
async def export_job_results(job_id: str):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    items = await db.job_items.find({"job_id": job_id}, {"_id": 0}).to_list(None)
    suppliers = await db.suppliers.find({"is_active": True}, {"_id": 0}).to_list(None)
    supplier_names = [s['name'] for s in suppliers]
    
    try:
        excel_bytes = excel_service.generate_results(job, items, supplier_names)
        
        return StreamingResponse(
            BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=results_{job_id[:8]}.xlsx"}
        )
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/logs")
async def get_logs(job_id: Optional[str] = None, limit: int = 100):
    query = {}
    if job_id:
        query["job_id"] = job_id
    
    logs = await db.logs.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return logs

@api_router.get("/stats")
async def get_stats():
    total_jobs = await db.jobs.count_documents({})
    completed_jobs = await db.jobs.count_documents({"status": JobStatus.COMPLETED.value})
    active_suppliers = await db.suppliers.count_documents({"is_active": True})
    
    pipeline = [
        {"$match": {"status": JobStatus.COMPLETED.value}},
        {"$group": {"_id": None, "total": {"$sum": "$total_savings"}}}
    ]
    savings_result = await db.jobs.aggregate(pipeline).to_list(None)
    total_savings = savings_result[0]['total'] if savings_result else 0.0
    
    recent_jobs = await db.jobs.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    
    return {
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "active_suppliers": active_suppliers,
        "total_savings": round(total_savings, 2),
        "recent_jobs": recent_jobs
    }

# ==================== Manual Scraper Endpoints ====================

scraper_status = {
    "running": False,
    "started_at": None,
    "progress": "",
    "results": []
}

async def run_manual_scraper(medidas: list):
    """Background task to run the scraper"""
    import subprocess
    global scraper_status
    
    scraper_status["running"] = True
    scraper_status["started_at"] = datetime.now(timezone.utc).isoformat()
    scraper_status["progress"] = "Starting scraper..."
    scraper_status["results"] = []
    
    try:
        medidas_str = ','.join(medidas)
        
        env = os.environ.copy()
        env['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'
        
        process = subprocess.Popen(
            ['python3', '/app/backend/run_scraper.py', '--medidas', medidas_str],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd='/app/backend'
        )
        
        output_lines = []
        for line in iter(process.stdout.readline, ''):
            if line:
                output_lines.append(line.strip())
                scraper_status["progress"] = line.strip()
                logger.info(f"Scraper: {line.strip()}")
        
        process.wait()
        
        scraper_status["progress"] = "Completed"
        scraper_status["results"] = output_lines[-20:]  # Last 20 lines
        
    except Exception as e:
        scraper_status["progress"] = f"Error: {str(e)}"
        logger.error(f"Scraper error: {e}")
    finally:
        scraper_status["running"] = False

@api_router.post("/scraper/run")
async def start_manual_scraper(background_tasks: BackgroundTasks, medidas: list = None):
    """Start the manual scraper in background"""
    global scraper_status
    
    if scraper_status["running"]:
        raise HTTPException(status_code=409, detail="Scraper is already running")
    
    if not medidas:
        # Get medidas from pending jobs
        pending_jobs = await db.jobs.find({"status": {"$in": ["pending", "running"]}}).to_list(10)
        medidas = []
        for job in pending_jobs:
            items = await db.job_items.find({"job_id": job["id"]}).to_list(100)
            for item in items:
                medida = item.get("medida", "").replace("/", "").replace("R", "")
                if medida and medida not in medidas:
                    medidas.append(medida)
        
        if not medidas:
            medidas = ["2055516"]  # Default test
    
    background_tasks.add_task(run_manual_scraper, medidas)
    
    return {"message": "Scraper started", "medidas": medidas}

@api_router.get("/scraper/status")
async def get_scraper_status():
    """Get current scraper status"""
    return scraper_status

@api_router.get("/scraped-prices")
async def get_scraped_prices(medida: str = None):
    """Get scraped prices from database"""
    query = {}
    if medida:
        medida_norm = medida.replace("/", "").replace("R", "")
        query["medida"] = {"$regex": medida_norm, "$options": "i"}
    
    prices = await db.scraped_prices.find(query, {"_id": 0}).sort("scraped_at", -1).to_list(100)
    return prices

@api_router.get("/scraped-prices/best/{medida}")
async def get_best_price(medida: str):
    """Get best price for a specific tire size"""
    medida_norm = medida.replace("/", "").replace("R", "")
    
    prices = await db.scraped_prices.find(
        {"medida": {"$regex": medida_norm, "$options": "i"}, "price": {"$ne": None}},
        {"_id": 0}
    ).sort("price", 1).to_list(100)
    
    if prices:
        best = prices[0]
        return {
            "medida": medida,
            "best_price": best["price"],
            "best_supplier": best["supplier_name"],
            "scraped_at": best.get("scraped_at"),
            "all_prices": [{"supplier": p["supplier_name"], "price": p["price"]} for p in prices]
        }
    
    return {"medida": medida, "best_price": None, "message": "No prices found"}

# ==================== Worker Queue Endpoints ====================

from pydantic import BaseModel as PydanticBaseModel

class EnqueueReq(PydanticBaseModel):
    supplier_id: str
    sizes: List[str]
    meta: Optional[dict] = None

@api_router.post("/scrape/enqueue")
async def enqueue_scrape(req: EnqueueReq):
    """Enqueue a scraping job for the worker"""
    job = {
        "type": "scrape",
        "supplier_id": req.supplier_id,
        "payload": {"sizes": req.sizes, "meta": req.meta or {}},
        "status": "queued",
        "attempts": 0,
        "created_at": datetime.utcnow(),
        "started_at": None,
        "finished_at": None,
        "last_error": None,
    }
    res = await db.jobs.insert_one(job)
    return {"ok": True, "job_id": str(res.inserted_id)}

@api_router.get("/scrape/jobs")
async def get_scrape_jobs(status: str = None, limit: int = 20):
    """Get scraping jobs from queue"""
    query = {"type": "scrape"}
    if status:
        query["status"] = status
    
    jobs = await db.jobs.find(query).sort("created_at", -1).limit(limit).to_list(limit)
    
    # Convert ObjectId to string
    for job in jobs:
        job["_id"] = str(job["_id"])
    
    return jobs

@api_router.get("/scrape/jobs/{job_id}")
async def get_scrape_job(job_id: str):
    """Get a specific scraping job"""
    from bson import ObjectId
    try:
        job = await db.jobs.find_one({"_id": ObjectId(job_id)})
        if job:
            job["_id"] = str(job["_id"])
            return job
        raise HTTPException(status_code=404, detail="Job not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
