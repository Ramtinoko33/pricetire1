import sys
print("=== WORKER STARTING ===", flush=True)
sys.stdout.flush()

import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

print("=== IMPORTS OK ===", flush=True)

MONGO_URL = os.environ.get(
    'MONGO_URL',
    'mongodb://mongo:xaqYuAhAqswTyVYfYwkDrIlhTHBQVPxh@mongodb.railway.internal:27017'
)
DB_NAME = os.environ['DB_NAME']

print(f"=== MONGO_URL: {MONGO_URL[:50]}... ===", flush=True)
print(f"=== DB_NAME: {DB_NAME} ===", flush=True)

try:
    from pymongo import MongoClient, ReturnDocument
    from bson import ObjectId
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    client.admin.command('ping')
    db = client[DB_NAME]
    print("=== MONGODB CONNECTED OK ===", flush=True)
except Exception as e:
    print("=== FAILED TO CONNECT TO MONGODB ===", flush=True)
    print(f"=== MONGODB URL (masked): {MONGO_URL[:50]}... ===", flush=True)
    print(f"=== MONGODB ERROR: {e} ===", flush=True)
    sys.exit(1)

def claim_job():
    return db.jobs.find_one_and_update(
        {"status": "queued", "type": "scrape"},
        {"$set": {"status": "running", "started_at": datetime.utcnow()}},
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER
    )

def acquire_lock(supplier_id: str, ttl_minutes: int = 10) -> bool:
    now = datetime.utcnow()
    expires = now + timedelta(minutes=ttl_minutes)
    try:
        doc = db.locks.find_one_and_update(
            {"_id": supplier_id, "$or": [{"expires_at": {"$lte": now}}, {"expires_at": {"$exists": False}}, {"locked": {"$ne": True}}]},
            {"$set": {"locked": True, "expires_at": expires, "updated_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return doc and doc.get("expires_at") and doc["expires_at"] > now
    except Exception as e:
        print(f"Error acquiring lock: {e}", flush=True)
        return False

def release_lock(supplier_id: str):
    db.locks.update_one({"_id": supplier_id}, {"$set": {"locked": False, "updated_at": datetime.utcnow()}})

def run_supplier_scrape(supplier_id: str, sizes: list, job_id: str):
    from run_scraper import run_supplier
    run_supplier(supplier_id=supplier_id, sizes=sizes, job_id=job_id)

def main():
    print(f"Worker started at {datetime.now()}", flush=True)
    print(f"MongoDB: {MONGO_URL[:50]}...", flush=True)
    print(f"Database: {DB_NAME}", flush=True)
    print("-" * 50, flush=True)

    while True:
        try:
            job = claim_job()

            if not job:
                time.sleep(2)
                continue

            supplier_id = job["supplier_id"]
            job_id = str(job["_id"])
            sizes = job["payload"]["sizes"]

            print(f"\n[{datetime.now()}] Processing job {job_id}", flush=True)
            print(f"  Supplier: {supplier_id}", flush=True)
            print(f"  Sizes: {sizes}", flush=True)

            if not acquire_lock(supplier_id):
                print(f"  Could not acquire lock for {supplier_id}, returning to queue", flush=True)
                db.jobs.update_one({"_id": job["_id"]}, {"$set": {"status": "queued", "started_at": None}})
                time.sleep(1)
                continue

            try:
                print(f"  Lock acquired, running scraper...", flush=True)
                run_supplier_scrape(supplier_id, sizes, job_id)
                db.jobs.update_one(
                    {"_id": job["_id"]},
                    {"$set": {"status": "done", "finished_at": datetime.utcnow(), "last_error": None}}
                )
                print(f"  Job {job_id} completed successfully", flush=True)
            except Exception as e:
                print(f"  Job {job_id} failed: {e}", flush=True)
                db.jobs.update_one(
                    {"_id": job["_id"]},
                    {"$set": {"status": "failed", "finished_at": datetime.utcnow(), "last_error": str(e)}}
                )
            finally:
                release_lock(supplier_id)
                print(f"  Lock released for {supplier_id}", flush=True)

        except KeyboardInterrupt:
            print("\nWorker stopped by user", flush=True)
            break
        except Exception as e:
            print(f"Worker error: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()
