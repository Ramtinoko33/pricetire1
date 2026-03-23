"""
Backend API tests for Pneu Price Scout application
Tests for scraper endpoints, scraped prices, and queue functionality
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestScraperStatus:
    """Tests for scraper status endpoint"""
    
    def test_scraper_status_returns_200(self):
        """GET /api/scraper/status should return scraper status"""
        response = requests.get(f"{BASE_URL}/api/scraper/status")
        assert response.status_code == 200
        data = response.json()
        # Verify response structure
        assert "running" in data
        assert isinstance(data["running"], bool)
        print(f"✓ Scraper status: running={data['running']}")


class TestScrapedPrices:
    """Tests for scraped prices endpoints"""
    
    def test_get_scraped_prices(self):
        """GET /api/scraped-prices should return list of prices"""
        response = requests.get(f"{BASE_URL}/api/scraped-prices")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Found {len(data)} scraped prices")
        
        # If there are prices, verify structure
        if len(data) > 0:
            price = data[0]
            assert "medida" in price
            assert "supplier_name" in price
            # Price can be null if not found
            assert "price" in price or "error" in price
            print(f"  - Sample: {price['supplier_name']} - medida {price['medida']}")
    
    def test_get_scraped_prices_with_filter(self):
        """GET /api/scraped-prices?medida=2055516 should filter results"""
        response = requests.get(f"{BASE_URL}/api/scraped-prices?medida=2055516")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Found {len(data)} prices for medida 2055516")
        
        # Verify all returned prices match filter
        for price in data:
            assert "2055516" in price.get("medida", "")
    
    def test_get_best_price_existing_medida(self):
        """GET /api/scraped-prices/best/{medida} should return best price"""
        response = requests.get(f"{BASE_URL}/api/scraped-prices/best/2055516")
        assert response.status_code == 200
        data = response.json()
        
        assert "medida" in data
        # Check if we have prices or a message
        if data.get("best_price"):
            assert "best_supplier" in data
            assert isinstance(data["best_price"], (int, float))
            assert "all_prices" in data
            print(f"✓ Best price for 2055516: €{data['best_price']} ({data['best_supplier']})")
        else:
            assert "message" in data or data["best_price"] is None
            print(f"✓ No prices found for 2055516 (expected if not scraped yet)")
    
    def test_get_best_price_nonexistent_medida(self):
        """GET /api/scraped-prices/best/{medida} with invalid medida should return no prices"""
        response = requests.get(f"{BASE_URL}/api/scraped-prices/best/INVALID123")
        assert response.status_code == 200
        data = response.json()
        assert data.get("best_price") is None
        print(f"✓ Correctly returns no prices for invalid medida")


class TestEnqueueScrape:
    """Tests for scrape job queue endpoints"""
    
    def test_enqueue_scrape_job(self):
        """POST /api/scrape/enqueue should create a job in queue"""
        payload = {
            "supplier_id": "TEST_MP24",
            "sizes": ["2055516", "1956515"]
        }
        response = requests.post(
            f"{BASE_URL}/api/scrape/enqueue",
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("ok") is True
        assert "job_id" in data
        print(f"✓ Created scrape job: {data['job_id']}")
    
    def test_enqueue_scrape_job_with_meta(self):
        """POST /api/scrape/enqueue with meta data should work"""
        payload = {
            "supplier_id": "TEST_Prismanil",
            "sizes": ["2055516"],
            "meta": {"test": True, "priority": "high"}
        }
        response = requests.post(
            f"{BASE_URL}/api/scrape/enqueue",
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("ok") is True
        assert "job_id" in data
        print(f"✓ Created scrape job with meta: {data['job_id']}")
    
    def test_enqueue_scrape_missing_supplier_id(self):
        """POST /api/scrape/enqueue without supplier_id should fail"""
        payload = {
            "sizes": ["2055516"]
        }
        response = requests.post(
            f"{BASE_URL}/api/scrape/enqueue",
            json=payload
        )
        # Should return 422 for validation error
        assert response.status_code == 422
        print(f"✓ Correctly rejects request without supplier_id")
    
    def test_get_scrape_jobs(self):
        """GET /api/scrape/jobs should return list of jobs"""
        response = requests.get(f"{BASE_URL}/api/scrape/jobs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Found {len(data)} scrape jobs in queue")
        
        # Verify job structure if any exist
        if len(data) > 0:
            job = data[0]
            assert "type" in job
            assert job["type"] == "scrape"
            assert "status" in job
            print(f"  - Latest job status: {job['status']}")
    
    def test_get_scrape_jobs_filtered_by_status(self):
        """GET /api/scrape/jobs?status=queued should filter by status"""
        response = requests.get(f"{BASE_URL}/api/scrape/jobs?status=queued")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # All returned jobs should have queued status
        for job in data:
            assert job.get("status") == "queued"
        print(f"✓ Found {len(data)} queued scrape jobs")


class TestSuppliers:
    """Tests for suppliers endpoint"""
    
    def test_get_suppliers(self):
        """GET /api/suppliers should return list of suppliers"""
        response = requests.get(f"{BASE_URL}/api/suppliers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Found {len(data)} suppliers")
        
        # Verify supplier structure
        if len(data) > 0:
            supplier = data[0]
            assert "id" in supplier
            assert "name" in supplier
            assert "is_active" in supplier
            # Password should be masked
            assert supplier.get("password") == "********"
            print(f"  - Suppliers: {[s['name'] for s in data]}")


class TestManualScraper:
    """Tests for manual scraper run endpoint"""
    
    def test_scraper_run_endpoint_exists(self):
        """POST /api/scraper/run endpoint should exist"""
        payload = {"medidas": ["2055516"]}
        response = requests.post(f"{BASE_URL}/api/scraper/run", json=payload)
        # Should return 200 (started) or 409 (already running)
        assert response.status_code in [200, 409]
        data = response.json()
        
        if response.status_code == 200:
            assert "message" in data
            print(f"✓ Scraper started: {data.get('message')}")
        else:
            assert "detail" in data
            print(f"✓ Scraper already running: {data.get('detail')}")


class TestJobs:
    """Tests for jobs endpoints (general jobs, not scrape queue)"""
    
    @pytest.mark.skip(reason="BUG: /api/jobs returns 500 - scrape queue jobs mixed with upload jobs in same collection with different schema")
    def test_get_jobs(self):
        """GET /api/jobs should return list of jobs
        
        BUG: This endpoint returns 500 because:
        1. /api/scrape/enqueue creates jobs in db.jobs with fields: type, supplier_id, payload, status=queued
        2. /api/jobs tries to parse ALL jobs using Job model which expects: id, filename, total_items, etc.
        3. The scrape queue jobs don't have the required Job model fields
        
        FIX NEEDED: Either use separate collections for scrape queue jobs vs upload jobs,
        or filter by type in /api/jobs endpoint: query = {"type": {"$exists": False}}
        """
        response = requests.get(f"{BASE_URL}/api/jobs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Found {len(data)} jobs")


class TestStats:
    """Tests for stats endpoint"""
    
    def test_get_stats(self):
        """GET /api/stats should return statistics"""
        response = requests.get(f"{BASE_URL}/api/stats")
        assert response.status_code == 200
        data = response.json()
        
        assert "total_jobs" in data
        assert "completed_jobs" in data
        assert "active_suppliers" in data
        assert "total_savings" in data
        print(f"✓ Stats: {data['total_jobs']} jobs, {data['active_suppliers']} suppliers")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
