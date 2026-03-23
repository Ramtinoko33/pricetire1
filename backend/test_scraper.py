#!/usr/bin/env python3
"""
Test script for debugging ScrapingBee scraping
Run: python3 test_scraper.py
"""
import requests
import re
import hashlib
import logging
import json
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ScrapingBee config
API_KEY = "O39DKUCEBZMYH87283H6GI2JE84RI5WRRZ9190ARLV7MX5AROAKDTU8DD9RURWDERRV82VO4O1OAN9UW"
API_URL = "https://app.scrapingbee.com/api/v1/"

# Test credentials
SUPPLIERS = {
    "mp24": {
        "url_login": "https://pt.mp24.online/pt_PT",
        "url_search": "https://pt.mp24.online/pt_PT",
        "username": "PTO02101",
        "password": "Sl6dBhGf"
    },
    "euromais": {
        "url_login": "https://www.eurotyre.pt/",
        "url_search": "https://www.eurotyre.pt/home/inicio",
        "username": "5010600251",
        "password": "5010600251"
    },
    "prismanil": {
        "url_login": "https://www.prismanil.pt/b2b/pesquisa",
        "url_search": "https://www.prismanil.pt/b2b/pesquisa",
        "username": "dpedrov287",
        "password": "dompedro4785"
    },
    "sjose": {
        "url_login": "https://b2b.sjosepneus.com/default.aspx",
        "url_search": "https://b2b.sjosepneus.com/default.aspx",
        "username": "5010600251",
        "password": "5010600251"
    }
}

def test_simple_fetch(supplier_name: str, url: str):
    """Just fetch page without JS rendering to see what we get"""
    print(f"\n=== SIMPLE FETCH: {supplier_name} ===")
    print(f"URL: {url}")
    
    params = {
        'api_key': API_KEY,
        'url': url,
        'render_js': 'false',  # No JS
    }
    
    response = requests.get(API_URL, params=params, timeout=30)
    print(f"Status: {response.status_code}")
    print(f"Content length: {len(response.text)} bytes")
    
    # Save HTML for inspection
    Path("/app/tmp/scraper_debug").mkdir(parents=True, exist_ok=True)
    filepath = f"/app/tmp/scraper_debug/{supplier_name}_simple.html"
    with open(filepath, 'w') as f:
        f.write(response.text)
    print(f"Saved to: {filepath}")
    
    # Check for login indicators
    content_lower = response.text.lower()
    has_login = any(kw in content_lower for kw in ['login', 'password', 'utilizador', 'entrar', 'iniciar sessão'])
    print(f"Has login form: {has_login}")
    
    return response.text

def test_js_render(supplier_name: str, url: str, stealth: bool = True):
    """Fetch page with JS rendering"""
    print(f"\n=== JS RENDER: {supplier_name} (stealth={stealth}) ===")
    print(f"URL: {url}")
    
    params = {
        'api_key': API_KEY,
        'url': url,
        'render_js': 'true',
        'wait': '3000',  # Wait 3 seconds for page load
        'country_code': 'pt',
    }
    
    if stealth:
        params['stealth_proxy'] = 'true'
    
    response = requests.get(API_URL, params=params, timeout=60)
    print(f"Status: {response.status_code}")
    print(f"Content length: {len(response.text)} bytes")
    
    # Save HTML
    filepath = f"/app/tmp/scraper_debug/{supplier_name}_jsrender.html"
    with open(filepath, 'w') as f:
        f.write(response.text)
    print(f"Saved to: {filepath}")
    
    # Check for login indicators
    content_lower = response.text.lower()
    has_login = any(kw in content_lower for kw in ['login', 'password', 'utilizador', 'entrar'])
    print(f"Has login form: {has_login}")
    
    # Extract any prices
    prices = extract_prices(response.text)
    print(f"Found prices: {prices}")
    
    return response.text

def test_login_with_scenario(supplier_name: str, supplier: dict):
    """Test login using JS scenario"""
    print(f"\n=== LOGIN TEST: {supplier_name} ===")
    
    # Generate session ID
    session_id = hashlib.md5(f"{supplier_name}_{supplier['username']}".encode()).hexdigest()
    print(f"Session ID: {session_id}")
    
    # Build login scenario based on supplier
    if 'mp24' in supplier_name.lower():
        # MP24 has a specific login flow
        js_scenario = json.dumps({
            "instructions": [
                {"wait": 2000},
                {"click": "button:contains('Login'), a:contains('Login'), .login-btn"},
                {"wait": 2000},
                {"fill": [{"selector": "input[type='text'], input[name*='user'], input[name*='email']", "text": supplier['username']}]},
                {"fill": [{"selector": "input[type='password']", "text": supplier['password']}]},
                {"wait": 500},
                {"click": "button[type='submit'], input[type='submit'], .login-submit"},
                {"wait": 5000}
            ]
        })
    elif 'prismanil' in supplier_name.lower():
        js_scenario = json.dumps({
            "instructions": [
                {"wait": 2000},
                {"fill": [{"selector": "input[type='text'], input[name*='user']", "text": supplier['username']}]},
                {"fill": [{"selector": "input[type='password']", "text": supplier['password']}]},
                {"wait": 500},
                {"click": "button[type='submit'], input[type='submit']"},
                {"wait": 5000}
            ]
        })
    else:
        # Generic login
        js_scenario = json.dumps({
            "instructions": [
                {"wait": 2000},
                {"fill": [{"selector": "input[type='text']", "text": supplier['username']}]},
                {"fill": [{"selector": "input[type='password']", "text": supplier['password']}]},
                {"wait": 500},
                {"click": "button[type='submit'], input[type='submit']"},
                {"wait": 5000}
            ]
        })
    
    params = {
        'api_key': API_KEY,
        'url': supplier['url_login'],
        'render_js': 'true',
        'stealth_proxy': 'true',
        'session_id': session_id,
        'js_scenario': js_scenario,
        'country_code': 'pt',
    }
    
    print(f"Making login request...")
    response = requests.get(API_URL, params=params, timeout=60)
    print(f"Status: {response.status_code}")
    print(f"Content length: {len(response.text)} bytes")
    
    # Save HTML
    filepath = f"/app/tmp/scraper_debug/{supplier_name}_login.html"
    with open(filepath, 'w') as f:
        f.write(response.text)
    print(f"Saved to: {filepath}")
    
    # Check result
    content_lower = response.text.lower()
    still_login = any(kw in content_lower for kw in ['login', 'password', 'entrar', 'iniciar sessão'])
    logged_in = any(kw in content_lower for kw in ['sair', 'logout', 'carrinho', 'cart', 'bem-vindo', 'welcome', 'minha conta'])
    
    print(f"Still on login page: {still_login}")
    print(f"Logged in indicators: {logged_in}")
    
    return session_id, response.text

def test_search_with_session(supplier_name: str, supplier: dict, session_id: str, medida: str = "2055516"):
    """Test product search with authenticated session"""
    print(f"\n=== SEARCH TEST: {supplier_name} - {medida} ===")
    
    # Build search URL based on supplier
    if 'mp24' in supplier_name.lower():
        search_url = f"https://pt.mp24.online/pt_PT/search?q={medida}"
    elif 'prismanil' in supplier_name.lower():
        search_url = f"https://www.prismanil.pt/b2b/pesquisa?medida={medida}"
    elif 'eurotyre' in supplier_name.lower() or 'euromais' in supplier_name.lower():
        search_url = f"https://www.eurotyre.pt/pt/pesquisa?q={medida}"
    elif 'sjose' in supplier_name.lower():
        search_url = f"https://b2b.sjosepneus.com/articles.aspx?search={medida}"
    else:
        search_url = f"{supplier['url_search']}?search={medida}"
    
    print(f"Search URL: {search_url}")
    
    params = {
        'api_key': API_KEY,
        'url': search_url,
        'render_js': 'true',
        'stealth_proxy': 'true',
        'session_id': session_id,  # Use logged-in session
        'wait': '5000',
        'country_code': 'pt',
    }
    
    print(f"Making search request with session {session_id}...")
    response = requests.get(API_URL, params=params, timeout=60)
    print(f"Status: {response.status_code}")
    print(f"Content length: {len(response.text)} bytes")
    
    # Save HTML
    filepath = f"/app/tmp/scraper_debug/{supplier_name}_search_{medida}.html"
    with open(filepath, 'w') as f:
        f.write(response.text)
    print(f"Saved to: {filepath}")
    
    # Check if still on login page
    content_lower = response.text.lower()
    still_login = 'login' in content_lower and 'password' in content_lower
    print(f"Still on login page: {still_login}")
    
    # Extract prices
    prices = extract_prices(response.text)
    print(f"Found prices: {prices}")
    
    if prices:
        print(f"✅ Best price: €{min(prices)}")
    else:
        print("❌ No prices found")
    
    return prices

def extract_prices(content: str) -> list:
    """Extract prices from HTML content"""
    price_patterns = [
        r'€\s*(\d+[,\.]\d{2})',
        r'(\d+[,\.]\d{2})\s*€',
        r'"price"\s*:\s*"?(\d+[,\.]\d{2})"?',
        r'preco["\']?\s*:\s*["\']?(\d+[,\.]\d{2})',
        r'(\d+\.\d{2})\s*EUR',
    ]
    
    found_prices = []
    for pattern in price_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches:
            try:
                price_str = match.replace(',', '.')
                price = float(price_str)
                if 15 < price < 500:  # Reasonable tire price range
                    found_prices.append(price)
            except ValueError:
                continue
    
    return list(set(found_prices))

def main():
    print("=" * 60)
    print("SCRAPINGBEE SCRAPER DEBUG")
    print("=" * 60)
    
    # Test one supplier at a time
    test_supplier = "mp24"  # Change this to test others
    supplier = SUPPLIERS[test_supplier]
    
    # Step 1: Simple fetch (no JS)
    print("\n" + "=" * 60)
    print("STEP 1: SIMPLE FETCH (No JS)")
    print("=" * 60)
    test_simple_fetch(test_supplier, supplier['url_login'])
    
    # Step 2: JS render without login
    print("\n" + "=" * 60)
    print("STEP 2: JS RENDER (No login)")
    print("=" * 60)
    test_js_render(test_supplier, supplier['url_login'])
    
    # Step 3: Login with JS scenario
    print("\n" + "=" * 60)
    print("STEP 3: LOGIN TEST")
    print("=" * 60)
    session_id, _ = test_login_with_scenario(test_supplier, supplier)
    
    # Step 4: Search with authenticated session
    print("\n" + "=" * 60)
    print("STEP 4: SEARCH TEST (with session)")
    print("=" * 60)
    prices = test_search_with_session(test_supplier, supplier, session_id, "2055516")
    
    print("\n" + "=" * 60)
    print("DEBUG COMPLETE")
    print("=" * 60)
    print(f"HTML files saved to: /app/tmp/scraper_debug/")
    print(f"Final result: {'SUCCESS' if prices else 'NO PRICES FOUND'}")

if __name__ == "__main__":
    main()
