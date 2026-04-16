#!/usr/bin/env python3
"""
Standalone scraper that runs independently and saves results to MongoDB.
Can be triggered manually or via cron.

Usage:
  python3 run_scraper.py                    # Scrape all active suppliers
  python3 run_scraper.py --supplier MP24    # Scrape specific supplier
  python3 run_scraper.py --medidas 2055516  # Scrape specific tire size
"""
import asyncio
import json
import os
import sys
import argparse
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Setup environment
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '/pw-browsers')
sys.path.insert(0, '/app/backend')

import asyncpg
from playwright.async_api import async_playwright
import re

# PostgreSQL connection
DATABASE_URL = os.environ['DATABASE_URL']


async def _pg_connect():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    return conn

# Results directory
RESULTS_DIR = Path('/app/tmp/scraper_results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def extract_prices(content: str) -> list:
    """Extract prices from HTML content"""
    price_patterns = [
        r'€\s*(\d+[,\.]\d{2})',
        r'(\d+[,\.]\d{2})\s*€',
        r'"price"\s*:\s*"?(\d+[,\.]\d{2})"?',
        r'"preco"\s*:\s*"?(\d+[,\.]\d{2})"?',
        r'"purchasePrice"\s*:\s*"?(\d+\.?\d*)"?',
    ]
    
    found_prices = []
    for pattern in price_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches:
            try:
                price_str = match.replace(',', '.')
                price = float(price_str)
                if 15 < price < 500:
                    found_prices.append(price)
            except ValueError:
                continue
    
    return list(set(found_prices))

def normalize_medida(medida: str) -> str:
    return medida.replace('/', '').replace('R', '').replace('r', '')

def normalize_brand(brand: str) -> str:
    """Normalize brand name for comparison"""
    if not brand:
        return ""
    brand = brand.strip().upper()
    # Common variations
    brand = brand.replace('GOODYEAR', 'GOODYEAR')
    brand = brand.replace('GOOD YEAR', 'GOODYEAR')
    return brand

async def extract_products_from_page(page) -> list:
    """Extract all products with brand, model and price from current page"""
    products = []
    
    # Try to get products via JavaScript evaluation
    try:
        # Common product container selectors
        product_data = await page.evaluate('''() => {
            const products = [];
            
            // Try different selectors for product rows/cards
            const selectors = [
                '.product-row', '.article-row', '.product-item', 
                'tr[data-article]', '.tyre-item', '[class*="product"]',
                '.article', '.item-row'
            ];
            
            for (const selector of selectors) {
                const items = document.querySelectorAll(selector);
                if (items.length > 0) {
                    items.forEach(item => {
                        const text = item.textContent || '';
                        
                        // Extract brand - usually in bold or specific class
                        let brand = '';
                        const brandEl = item.querySelector('.brand, .manufacturer, [class*="brand"], strong, b');
                        if (brandEl) brand = brandEl.textContent.trim();
                        
                        // Extract model/profile
                        let model = '';
                        const modelEl = item.querySelector('.model, .profile, .description, [class*="model"]');
                        if (modelEl) model = modelEl.textContent.trim();
                        
                        // Extract price
                        let price = null;
                        const priceMatch = text.match(/€?\s*(\d+[,\.]\d{2})\s*€?/);
                        if (priceMatch) {
                            price = parseFloat(priceMatch[1].replace(',', '.'));
                        }
                        
                        if (price && price > 15 && price < 500) {
                            products.push({ brand, model, price, text: text.substring(0, 200) });
                        }
                    });
                    break;
                }
            }
            
            return products;
        }''')
        
        if product_data:
            products = product_data
    except Exception as e:
        print(f"  Error extracting products via JS: {e}")
    
    return products

async def scrape_mp24(page, username: str, password: str, medida: str) -> dict:
    """Scrape MP24 (always does full login)"""
    return await scrape_mp24_with_session(page, username, password, medida, already_logged_in=False)

async def scrape_mp24_with_session(page, username: str, password: str, medida: str, already_logged_in: bool = False) -> dict:
    """Scrape MP24 with session reuse support - extracts ALL products with brand/model via API interception"""
    result = {
        "supplier": "MP24", 
        "price": None, 
        "error": None, 
        "products": [],  # List of all products found
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    captured_tyres = []
    
    # Set up response handler to capture API data
    async def handle_response(response):
        try:
            if '/api/frontend/v1/tyres?' in response.url and 'json' in response.headers.get('content-type', ''):
                data = await response.json()
                if isinstance(data, list):
                    captured_tyres.extend(data)
        except:
            pass
    
    page.on('response', handle_response)
    
    try:
        if not already_logged_in:
            # Login
            print("  [MP24] Logging in...")
            await page.goto("https://pt.mp24.online/pt_PT", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            
            await page.locator('input[name="_username"]').fill(username)
            await page.locator('input[name="_password"]').fill(password)
            await page.locator('a:has-text("Início de sessão")').click()
            await asyncio.sleep(5)
        
        # Navigate to tyres page (always needed for new search)
        print("  [MP24] Navigating to tyres page...")
        await page.goto("https://pt.mp24.online/pt_PT/tyres/", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)
        
        medida_norm = normalize_medida(medida)
        
        # Find matchcode field
        print("  [MP24] Looking for matchcode field...")
        matchcode_input = page.locator('#matchcodeField')
        count = await matchcode_input.count()
        
        if count > 0:
            # Scroll to element and fill
            await matchcode_input.scroll_into_view_if_needed()
            await asyncio.sleep(1)
            await matchcode_input.fill(medida_norm)
            print(f"  [MP24] Searching for: {medida_norm}")
            await asyncio.sleep(1)
            
            # Find and click the submit button
            form = page.locator('#matchcode')
            submit_btn = form.locator('button[type="submit"]')
            
            if await submit_btn.count() > 0:
                await submit_btn.click()
            else:
                await matchcode_input.press('Enter')
            
            # Wait for API response
            await asyncio.sleep(8)
            await page.wait_for_load_state("networkidle")
            
            # Process captured API data
            print(f"  [MP24] Captured {len(captured_tyres)} tyres from API")
            
            if captured_tyres:
                # Group products by brand+model and keep minimum price
                product_map = {}  # key: "BRAND|MODEL" -> min price
                
                for tyre in captured_tyres:
                    brand = tyre.get('manufacturer', '').upper()
                    model = tyre.get('profile', '')
                    
                    # Get minimum price from all sources
                    best_prices = tyre.get('bestPricesBySource', {})
                    price = None
                    
                    # Try all price sources and get the minimum
                    for source in ['supplier', 'loadAll', 'central_warehouse', 'my_stock']:
                        source_data = best_prices.get(source, {})
                        best_price = source_data.get('bestPrice', {})
                        if best_price and best_price.get('purchasePrice'):
                            source_price = best_price['purchasePrice']
                            if price is None or source_price < price:
                                price = source_price
                    
                    if brand and model and price and price > 15 and price < 500:
                        key = f"{brand}|{model}"
                        if key not in product_map or price < product_map[key]:
                            product_map[key] = price
                
                # Convert map back to list
                products = []
                for key, price in product_map.items():
                    brand, model = key.split('|', 1)
                    products.append({
                        'brand': brand,
                        'model': model,
                        'price': price
                    })
                
                if products:
                    result["products"] = products
                    prices = [p['price'] for p in products]
                    result["price"] = min(prices)
                    result["all_prices"] = sorted(prices)[:10]
                    print(f"  [MP24] Extracted {len(products)} unique products with brand/model")
                    
                    # Show sample products
                    for p in sorted(products, key=lambda x: x['price'])[:5]:
                        print(f"    - {p['brand']} {p['model']}: €{p['price']}")
                else:
                    result["error"] = "No valid products found in API response"
            else:
                # Fallback to simple price extraction
                content = await page.content()
                prices = extract_prices(content)
                if prices:
                    result["price"] = min(prices)
                    result["all_prices"] = sorted(prices)[:10]
                    print(f"  [MP24] Fallback: Found {len(prices)} prices, best: €{result['price']}")
                else:
                    result["error"] = "No products found"
        else:
            result["error"] = "matchcodeField not found"
            
    except Exception as e:
        result["error"] = str(e)
        print(f"  [MP24] Error: {e}")
    finally:
        # Remove the response handler
        page.remove_listener('response', handle_response)
    
    return result

async def scrape_prismanil(page, username: str, password: str, medida: str) -> dict:
    """Scrape Prismanil - extracts ALL products with brand/model"""
    result = {
        "supplier": "Prismanil", 
        "price": None, 
        "error": None, 
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        print("  [Prismanil] Navigating...")
        await page.goto("https://www.prismanil.pt/b2b/pesquisa", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        content = await page.content()
        if "txtPesquisa" not in content:
            print("  [Prismanil] Logging in...")
            username_input = page.locator('input[type="text"]').first
            if await username_input.count() > 0:
                await username_input.fill(username)
            
            password_input = page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(password)
            
            submit_btn = page.locator('button:has-text("Entrar")').first
            if await submit_btn.count() > 0:
                await submit_btn.click()
            await asyncio.sleep(5)
        
        medida_norm = normalize_medida(medida)
        
        search_input = page.locator('#txtPesquisa')
        if await search_input.count() > 0:
            print(f"  [Prismanil] Searching for: {medida_norm}")
            await search_input.fill(medida_norm)
            await asyncio.sleep(1)
            
            search_btn = page.locator('#btnPesquisar')
            if await search_btn.count() > 0:
                await search_btn.click()
            await asyncio.sleep(5)
            
            # Extract products from data-* attributes
            print("  [Prismanil] Extracting products...")
            products = await page.evaluate('''() => {
                const products = [];
                const items = document.querySelectorAll('[data-produto][data-preco]');
                
                items.forEach(item => {
                    const produtoStr = item.getAttribute('data-produto') || '';
                    const precoStr = item.getAttribute('data-preco') || '';
                    
                    if (produtoStr && precoStr) {
                        // Parse produto string: "BRIDGESTONE 205/55R16 EP150 91V"
                        const parts = produtoStr.trim().split(' ');
                        const brand = parts[0] || '';
                        const model = parts.slice(2).join(' ') || '';
                        
                        const price = parseFloat(precoStr.replace(',', '.'));
                        
                        if (brand && price > 15 && price < 500) {
                            products.push({
                                brand: brand.toUpperCase(),
                                model: model,
                                price: price
                            });
                        }
                    }
                });
                
                return products;
            }''')
            
            if products and len(products) > 0:
                result["products"] = products
                prices = [p['price'] for p in products]
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
                print(f"  [Prismanil] Found {len(products)} products with brand/model")
                for p in products[:3]:
                    print(f"    - {p['brand']} {p['model']}: €{p['price']}")
            else:
                # Fallback to simple price extraction
                content = await page.content()
                prices = extract_prices(content)
                if prices:
                    result["price"] = min(prices)
                    result["all_prices"] = sorted(prices)[:10]
                else:
                    result["error"] = "No products found"
        else:
            result["error"] = "Search field not found"
    except Exception as e:
        result["error"] = str(e)
        print(f"  [Prismanil] Error: {e}")
    
    return result

async def scrape_dispnal(page, username: str, password: str, medida: str) -> dict:
    """Scrape Dispnal - extracts ALL products with brand/model"""
    result = {
        "supplier": "Dispnal", 
        "price": None, 
        "error": None, 
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        print("  [Dispnal] Navigating...")
        await page.goto("https://dispnal.pt/home/homepage", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)
        
        content = await page.content()
        if 'Entrar' in content or 'Login' in content:
            print("  [Dispnal] Logging in...")
            login_link = page.locator('a:has-text("Entrar"), a:has-text("Login")')
            if await login_link.count() > 0:
                await login_link.first.click()
                await asyncio.sleep(2)
            
            email_input = page.locator('input[type="email"], input[name*="email"]').first
            if await email_input.count() > 0:
                await email_input.fill(username)
            
            password_input = page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(password)
            
            submit_btn = page.locator('button[type="submit"]').first
            if await submit_btn.count() > 0:
                await submit_btn.click()
            await asyncio.sleep(5)
        
        medida_norm = normalize_medida(medida)
        
        medida_input = page.locator('#medida-normal')
        if await medida_input.count() > 0:
            print(f"  [Dispnal] Searching for: {medida_norm}")
            await medida_input.fill(medida_norm)
            await asyncio.sleep(1)
            
            search_btn = page.locator('button[type="submit"], .btn-search').first
            if await search_btn.count() > 0:
                await search_btn.click()
            await asyncio.sleep(5)
            
            # Extract products
            print("  [Dispnal] Extracting products...")
            products = await page.evaluate('''() => {
                const products = [];
                const rows = document.querySelectorAll('.prod-list-row[data-price]');
                
                rows.forEach(row => {
                    const priceStr = row.getAttribute('data-price') || '';
                    const price = parseFloat(priceStr);
                    
                    // Get brand from image alt attribute
                    const brandImg = row.querySelector('.prod-list-brand-wrapper img');
                    const brand = brandImg ? (brandImg.getAttribute('alt') || '') : '';
                    
                    // Get model from description
                    const nameCell = row.querySelector('.cell-name');
                    let model = '';
                    if (nameCell) {
                        // Look for model text after brand
                        const descText = nameCell.textContent || '';
                        const lines = descText.split('\\n').map(l => l.trim()).filter(l => l);
                        // Model is usually the second non-empty line or contains pattern like "PRIMACY"
                        for (const line of lines) {
                            if (line.length > 3 && !line.includes(brand) && !line.includes('€')) {
                                model = line;
                                break;
                            }
                        }
                    }
                    
                    if (brand && price > 15 && price < 500) {
                        products.push({
                            brand: brand.toUpperCase(),
                            model: model,
                            price: price
                        });
                    }
                });
                
                return products;
            }''')
            
            if products and len(products) > 0:
                result["products"] = products
                prices = [p['price'] for p in products]
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
                print(f"  [Dispnal] Found {len(products)} products with brand/model")
                for p in products[:3]:
                    print(f"    - {p['brand']} {p['model']}: €{p['price']}")
            else:
                # Fallback to simple price extraction
                content = await page.content()
                prices = extract_prices(content)
                if prices:
                    result["price"] = min(prices)
                    result["all_prices"] = sorted(prices)[:10]
                else:
                    result["error"] = "No products found"
        else:
            result["error"] = "Search field not found"
    except Exception as e:
        result["error"] = str(e)
        print(f"  [Dispnal] Error: {e}")
    
    return result

async def scrape_sjose(page, username: str, password: str, medida: str,
                       url_login: str = "https://b2b.sjosepneus.com/default.aspx",
                       url_search: str = "https://b2b.sjosepneus.com/articles/articles.aspx") -> dict:
    """Scrape S. José Pneus (ASP.NET B2B portal).

    url_login  — login page URL (stored in suppliers.url_login)
    url_search — product search URL (stored in suppliers.url_search)

    On first run the page HTML is saved to /tmp/sjose_after_login.html and
    /tmp/sjose_results.html so selectors can be verified if anything goes wrong.
    """
    result = {
        "supplier": "S. José Pneus",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Use sensible defaults if empty strings were passed
    if not url_login:
        url_login = "https://b2b.sjosepneus.com/default.aspx"
    if not url_search:
        url_search = "https://b2b.sjosepneus.com/articles/articles.aspx"

    def _save_debug(path: str, content: str):
        try:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(content)
        except Exception:
            pass

    try:
        # ── Login ────────────────────────────────────────────────────────────
        print(f"  [S. José] Navigating to login: {url_login}")
        await page.goto(url_login, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)

        current_url = page.url
        print(f"  [S. José] URL after navigation: {current_url}")

        # Save the page BEFORE login attempt so we can inspect the form structure
        _save_debug('/tmp/sjose_pre_login.html', await page.content())

        # Log ALL input IDs (visible and hidden) to diagnose selector issues
        input_ids = await page.evaluate(
            "() => Array.from(document.querySelectorAll('input')).map(i => "
            "({id: i.id, name: i.name, type: i.type, visible: i.offsetParent !== null}))"
        )
        visible_inputs = [x for x in input_ids if x.get('type') not in ('hidden',)]
        print(f"  [S. José] ALL visible inputs on page: {visible_inputs}")

        # Login form present if we're still on login.aspx (not yet authenticated)
        # NOTE: after SUCCESSFUL login, S. José redirects to default.aspx (home page)
        # so 'default' in URL does NOT mean login failed — only 'login' means we haven't logged in yet
        login_form_present = 'login' in current_url.lower()
        if login_form_present:
            # Use type() instead of fill() to simulate real keystrokes (avoids bot detection)
            user_field = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_UserName').first
            if await user_field.count() == 0:
                user_field = page.locator('input[id$="_UserName"], input[name$="UserName"]').first
            if await user_field.count() == 0:
                user_field = page.locator('input[type="text"]').first
            await user_field.click()
            await user_field.type(username, delay=80)
            print(f"  [S. José] Typed username")

            await asyncio.sleep(0.5)

            pass_field = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_Password').first
            if await pass_field.count() == 0:
                pass_field = page.locator('input[id$="_Password"], input[name$="Password"]').first
            if await pass_field.count() == 0:
                pass_field = page.locator('input[type="password"]').first
            await pass_field.click()
            await pass_field.type(password, delay=80)
            print(f"  [S. José] Typed password")

            await asyncio.sleep(0.5)

            # Click the login button (confirmed ID from debug-forms)
            btn_loc = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_btnLogin').first
            if await btn_loc.count() == 0:
                btn_loc = page.locator('input[id$="_btnLogin"], input[id$="_LoginButton"]').first
            if await btn_loc.count() == 0:
                btn_loc = page.locator('input[type="submit"]').first
            print(f"  [S. José] Clicking login button")
            await btn_loc.click()

            # Wait for navigation to complete
            try:
                await page.wait_for_url(lambda url: 'login' not in url.lower(), timeout=15000)
            except Exception:
                pass  # may already be redirected or slow
            await page.wait_for_load_state("networkidle", timeout=30000)

        url_after_login = page.url
        print(f"  [S. José] URL after login: {url_after_login}")
        after_login_html = await page.content()
        _save_debug('/tmp/sjose_after_login.html', after_login_html)

        # Check if login succeeded:
        # - Success: URL is default.aspx (home) or any other non-login page
        # - Failure: still on login.aspx, OR login form still visible in DOM
        still_on_login = 'login' in url_after_login.lower()
        login_form_still_visible = await page.locator(
            '#ContentPlaceHolder1_ctrlLogin_Login_UserName'
        ).count() > 0

        if still_on_login or login_form_still_visible:
            result["error"] = (
                f"Login failed — still on login page ({url_after_login}). "
                "Check credentials or use /scraper/debug-html?file=after_login"
            )
            print(f"  [S. José] Login FAILED: {result['error']}")
            return result

        print(f"  [S. José] Login successful — now on: {url_after_login}")

        # ── Navigate to search page ───────────────────────────────────────────
        medida_norm = normalize_medida(medida)
        medida_orig = medida.strip()

        # Reconstruct the slashed format from a normalized medida
        # e.g. "1956515" → "195/65R15"  (3-digit width + 2-digit ratio + 2-digit rim)
        import re as _re
        _m = _re.match(r'^(\d{3})(\d{2})(\d{2})$', medida_norm)
        medida_slashed = f"{_m.group(1)}/{_m.group(2)}R{_m.group(3)}" if _m else medida_orig

        # All formats to try for form filling (deduplicated, slashed first)
        all_search_terms = list(dict.fromkeys([medida_slashed, medida_orig, medida_norm]))

        def _size_in_content(content: str, mnorm: str, mslashed: str) -> bool:
            """Check that the page actually contains the searched tire size."""
            cl = content.lower()
            # Check normalized form (e.g. "1956515")
            if mnorm.lower() in cl:
                return True
            # Check slashed form (e.g. "195/65r15")
            if mslashed.lower() in cl:
                return True
            # Check without R (e.g. "195/65/15")
            if mslashed.lower().replace('r', '/') in cl:
                return True
            # Check with space (e.g. "195 65 15")
            if mslashed.lower().replace('/', ' ').replace('r', ' ') in cl:
                return True
            return False

        print(f"  [S. José] Navigating to search page: {url_search}")
        print(f"  [S. José] Searching for: {medida_norm} → slashed: {medida_slashed}")

        # Strategy 1: try URL query parameters with BOTH normalized and original format
        # Only accept the page if the searched medida actually appears in the response
        search_url_tried = False
        for param in ['q', 'pesquisa', 'search', 'medida', 'codigo', 'ref']:
            for search_term in all_search_terms:
                try_url = f"{url_search}?{param}={search_term}"
                await page.goto(try_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)
                content_check = await page.content()
                # Accept only if the page has prices AND references the searched size
                has_prices = any(c in content_check for c in ['€', 'preco', 'Preco', 'PVP', 'pvp'])
                has_size   = _size_in_content(content_check, medida_norm, medida_slashed)
                if has_prices and has_size:
                    print(f"  [S. José] URL param '{param}'={search_term!r} has matching results")
                    search_url_tried = True
                    break
                elif has_prices:
                    print(f"  [S. José] Param '{param}'={search_term!r} has prices but NOT the searched size — ignoring")
                else:
                    print(f"  [S. José] Param '{param}'={search_term!r} — no prices")
            if search_url_tried:
                break

        # Strategy 2: navigate to search page and fill form
        if not search_url_tried:
            await page.goto(url_search, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            search_page_url = page.url
            print(f"  [S. José] Search page actual URL: {search_page_url}")
            _save_debug('/tmp/sjose_search_page.html', await page.content())
            # Guard: if navigating to the search page redirected back to LOGIN page,
            # don't fill the search box (we'd be filling into the username field)
            # Note: default.aspx is the HOME page after login, NOT a login page
            if 'login' in search_page_url.lower():
                result["error"] = (
                    f"Navigating to {url_search} redirected to login page ({search_page_url}). "
                    "Session may have expired — check /tmp/sjose_after_login.html"
                )
                return result

        # Ordered list of selectors seen in ASP.NET B2B tire portals
        search_selectors = [
            '#ContentPlaceHolder1_txtPesquisa',
            '#ContentPlaceHolder1_txtMedida',
            '#ContentPlaceHolder1_txtSearch',
            '#ContentPlaceHolder1_TextBox1',
            'input[id*="Pesquisa"]',
            'input[id*="Medida"]',
            'input[id*="txtP"]',
            'input[id*="Search"]',
            'input[id*="search"]',
            'input[name*="pesq"]',
            'input[name*="Pesq"]',
            'input[type="text"]',   # last-resort generic (EXCLUDE if on login page)
        ]

        submit_selectors = [
            '#ContentPlaceHolder1_btnPesquisar',
            '#ContentPlaceHolder1_btnSearch',
            '#ContentPlaceHolder1_ImageButton1',  # ASP.NET ImageButton
            'input[type="submit"]',
            'input[type="image"]',
            'button[type="submit"]',
        ]

        search_found = search_url_tried  # already searched via URL params
        if not search_found:
            # Try slashed format first (e.g. "195/65R15"), then original, then normalized
            search_terms_to_try = all_search_terms
            for sel in search_selectors:
                el = page.locator(sel).first
                if await el.count() > 0:
                    for term in search_terms_to_try:
                        await el.fill(term)
                        print(f"  [S. José] Filled search field via {sel!r} with {term!r}")
                        submitted = False
                        for btn_sel in submit_selectors:
                            btn = page.locator(btn_sel).first
                            if await btn.count() > 0:
                                await btn.click()
                                submitted = True
                                print(f"  [S. José] Clicked submit via: {btn_sel}")
                                break
                        if not submitted:
                            await el.press('Enter')
                            print("  [S. José] Submitted via Enter key")
                        await asyncio.sleep(5)
                        await page.wait_for_load_state("networkidle")
                        # Check if results page references the searched size
                        after_submit = await page.content()
                        if _size_in_content(after_submit, medida_norm, medida_slashed):
                            print(f"  [S. José] Search with term {term!r} returned relevant content")
                            search_found = True
                            break
                        print(f"  [S. José] Search with {term!r} didn't return size-specific content, trying next term")
                        # Navigate back to search page for next attempt
                        if term != search_terms_to_try[-1]:
                            await page.goto(url_search, wait_until="networkidle", timeout=30000)
                            await asyncio.sleep(2)
                            el = page.locator(sel).first  # re-find after navigation
                    if search_found:
                        break
                    # If no term produced relevant results, still mark as searched (best effort)
                    if not search_found:
                        print(f"  [S. José] No search term produced size-specific results, using last attempt")
                        search_found = True
                    break

        content = await page.content()
        _save_debug('/tmp/sjose_results.html', content)

        if not search_found:
            result["error"] = "Search field not found — HTML saved to /tmp/sjose_search_page.html"
            return result

        # ── Extract products from ASP.NET GridView table ─────────────────────
        products = await page.evaluate('''() => {
            const products = [];

            for (const table of document.querySelectorAll("table")) {
                const rows = table.querySelectorAll("tr");
                if (rows.length < 2) continue;

                // Detect column positions from header row
                let brandCol = -1, modelCol = -1, priceCol = -1;
                const headerCells = rows[0].querySelectorAll("th, td");
                headerCells.forEach((h, i) => {
                    const t = h.textContent.trim().toLowerCase();
                    if (/marca|brand|fabricante/.test(t))         brandCol = i;
                    else if (/modelo|descri|perfil|artigo|denom/.test(t)) modelCol = i;
                    else if (/pre[çc]o|valor|pvp|unit/.test(t))   priceCol = i;
                });

                for (let i = 1; i < rows.length; i++) {
                    const cells = rows[i].querySelectorAll("td");
                    if (cells.length < 2) continue;

                    let brand = "", model = "", price = null;

                    if (brandCol >= 0 && brandCol < cells.length)
                        brand = cells[brandCol].textContent.trim().toUpperCase();
                    if (modelCol >= 0 && modelCol < cells.length)
                        model = cells[modelCol].textContent.trim();

                    // Price from detected column
                    if (priceCol >= 0 && priceCol < cells.length) {
                        const m = cells[priceCol].textContent.match(/(\d+[,\\.]\d{2})/);
                        if (m) price = parseFloat(m[1].replace(",", "."));
                    }

                    // Price fallback: scan each cell for standalone currency value
                    if (!price) {
                        for (const cell of cells) {
                            const m = cell.textContent.trim().match(/^€?\\s*(\d+[,\\.]\d{2})\\s*€?$/);
                            if (m) {
                                const p = parseFloat(m[1].replace(",", "."));
                                if (p > 15 && p < 500) { price = p; break; }
                            }
                        }
                    }

                    // Brand fallback: scan full row text for known brand names
                    if (!brand) {
                        const rowText = Array.from(cells).map(c => c.textContent).join(" ").toUpperCase();
                        const bm = rowText.match(
                            /(MICHELIN|BRIDGESTONE|CONTINENTAL|PIRELLI|GOODYEAR|DUNLOP|HANKOOK|YOKOHAMA|FIRESTONE|KUMHO|TOYO|NEXEN|FALKEN|NOKIAN|VREDESTEIN|MAXXIS|GENERAL|UNIROYAL|SEMPERIT|BARUM|LASSA|SAVA|KLEBER|FULDA|GISLAVED|MATADOR|DEBICA|KELLY)/
                        );
                        if (bm) brand = bm[1];
                    }

                    if (price && price > 15 && price < 500)
                        products.push({ brand, model, price });
                }

                if (products.length > 0) break; // stop at first table with results
            }
            return products;
        }''')

        if products:
            # Deduplicate by brand+model keeping lowest price
            seen = {}
            for p in products:
                key = f"{p.get('brand','')}|{p.get('model','')}"
                if key not in seen or p['price'] < seen[key]['price']:
                    seen[key] = p
            products = list(seen.values())

            result["products"] = products
            prices_list = [p['price'] for p in products]
            result["price"] = min(prices_list)
            result["all_prices"] = sorted(prices_list)[:10]
            print(f"  [S. José] {len(products)} products found. Best: €{result['price']}")
            for p in sorted(products, key=lambda x: x['price'])[:3]:
                print(f"    - {p.get('brand','-')} {p.get('model','-')}: €{p['price']}")
        else:
            # Final fallback: regex price extraction from raw HTML
            prices_list = extract_prices(content)
            if prices_list:
                result["price"] = min(prices_list)
                result["all_prices"] = sorted(prices_list)[:10]
                print(f"  [S. José] Fallback regex: {len(prices_list)} prices, best: €{result['price']}")
            else:
                result["error"] = "No products found — check /tmp/sjose_results.html"

    except Exception as e:
        result["error"] = str(e)
        print(f"  [S. José] Error: {e}")

    return result

async def scrape_euromais(page, username: str, password: str, medida: str) -> dict:
    """Scrape Euromais/Eurotyre"""
    result = {"supplier": "euromais", "price": None, "error": None, "timestamp": datetime.now(timezone.utc).isoformat()}
    
    try:
        print("  [Euromais] Logging in...")
        await page.goto("https://www.eurotyre.pt/", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        # Look for login link/button
        login_link = page.locator('a:has-text("Entrar"), a:has-text("Login"), button:has-text("Login")')
        if await login_link.count() > 0:
            await login_link.first.click()
            await asyncio.sleep(2)
        
        # Fill login form
        username_input = page.locator('input[type="text"], input[type="email"]').first
        if await username_input.count() > 0:
            await username_input.fill(username)
        
        password_input = page.locator('input[type="password"]').first
        if await password_input.count() > 0:
            await password_input.fill(password)
        
        # Submit login
        submit_btn = page.locator('button[type="submit"], input[type="submit"]').first
        if await submit_btn.count() > 0:
            await submit_btn.click()
        await asyncio.sleep(5)
        
        print("  [Euromais] Searching for products...")
        medida_norm = normalize_medida(medida)
        
        # Try to find search field
        search_input = page.locator('input[type="search"], input[placeholder*="pesq"], input[name*="search"]').first
        if await search_input.count() > 0:
            await search_input.fill(medida_norm)
            await search_input.press('Enter')
            await asyncio.sleep(5)
            
            content = await page.content()
            prices = extract_prices(content)
            if prices:
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
                print(f"  [Euromais] Found {len(prices)} prices, best: €{result['price']}")
            else:
                result["error"] = "No prices found"
        else:
            content = await page.content()
            with open('/app/tmp/euromais_after_login.html', 'w') as f:
                f.write(content)
            result["error"] = "Search interface not found"
            
    except Exception as e:
        result["error"] = str(e)
        print(f"  [Euromais] Error: {e}")
    
    return result

# ============================================================
# NEW SCRAPERS - 6 Fornecedores Adicionais
# ============================================================

async def scrape_grupo_soledad(page, username: str, password: str, medida: str,
                               url_login: str = "https://www.gruposoledad.com/b2b/current/login",
                               url_search: str = "https://b2b.new.gruposoledad.com/dashboard/main") -> dict:
    """Scrape Grupo Soledad B2B portal (modern SPA at b2b.new.gruposoledad.com)."""
    result = {
        "supplier": "Grupo Soledad",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if not url_login:
        url_login = "https://www.gruposoledad.com/b2b/current/login"
    if not url_search:
        url_search = "https://b2b.new.gruposoledad.com/dashboard/main"

    def _save_debug(path: str, content: str):
        try:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(content)
        except Exception:
            pass

    # Reconstruct slashed medida for search (e.g. "1956515" → "195/65R15")
    medida_norm = normalize_medida(medida)
    import re as _re2
    _m2 = _re2.match(r'^(\d{3})(\d{2})(\d{2})$', medida_norm)
    medida_slashed = f"{_m2.group(1)}/{_m2.group(2)}R{_m2.group(3)}" if _m2 else medida

    # ── Intercept JSON API responses (primary method for Angular SPAs) ────────
    api_responses = []

    async def _capture_api_response(response):
        try:
            if response.status != 200:
                return
            ct = response.headers.get('content-type') or ''
            if 'json' not in ct:
                return
            body = await response.text()
            if len(body) > 80:
                api_responses.append({'url': response.url, 'body': body})
                print(f"  [Soledad] API: {response.url.split('?')[0][-60:]} ({len(body)}b)")
        except Exception:
            pass

    page.on('response', _capture_api_response)

    try:
        # ── Login ────────────────────────────────────────────────────────────
        print(f"  [Soledad] Navigating to: {url_login}")
        try:
            await page.goto(url_login, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            await page.goto(url_login, wait_until="commit", timeout=60000)
        try:
            await page.wait_for_load_state("load", timeout=20000)
        except Exception:
            pass
        await asyncio.sleep(2)
        _save_debug('/tmp/soledad_pre_login.html', await page.content())
        print(f"  [Soledad] Login page URL: {page.url}")

        # Fill username (try multiple field name patterns)
        user_field = page.locator(
            'input[name="userId"], input[name="username"], input[name="email"], '
            'input[name="user"], input[type="email"], '
            'input[id*="userId" i], input[id*="user" i], input[id*="email" i], '
            'input[placeholder*="user" i], input[placeholder*="email" i], '
            'input[placeholder*="utilizador" i], input[placeholder*="usuario" i], '
            'input[type="text"]'
        ).first
        if await user_field.count() > 0:
            await user_field.click()
            await user_field.type(username, delay=80)
            print(f"  [Soledad] Username entered")
        else:
            result["error"] = "Username field not found"
            return result

        await asyncio.sleep(0.4)

        pass_field = page.locator('input[type="password"]').first
        if await pass_field.count() > 0:
            await pass_field.click()
            await pass_field.type(password, delay=80)
            print(f"  [Soledad] Password entered")
        else:
            result["error"] = "Password field not found"
            return result

        await asyncio.sleep(0.5)

        # Click submit button
        submit = page.locator(
            'button[type="submit"], input[type="submit"], '
            'button:has-text("Entrar"), button:has-text("Login"), '
            'button:has-text("Iniciar"), button:has-text("Acceder"), '
            'button:has-text("Sign In"), button:has-text("Iniciar sesión")'
        ).first
        if await submit.count() > 0:
            await submit.click()
            print(f"  [Soledad] Submit clicked")
        else:
            await pass_field.press('Enter')
            print(f"  [Soledad] Submit via Enter")

        # Wait for login: poll until password field disappears (works for any SPA/MPA)
        print(f"  [Soledad] Waiting for login to complete...")
        for _i in range(40):  # Up to 20 seconds
            await asyncio.sleep(0.5)
            if await page.locator('input[type="password"]').count() == 0:
                print(f"  [Soledad] Password field gone after ~{_i * 0.5:.0f}s")
                break
        else:
            print(f"  [Soledad] Warning: password field still present after 20s")

        try:
            await page.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(3)

        url_after = page.url
        _save_debug('/tmp/soledad_after_login.html', await page.content())
        print(f"  [Soledad] After login: {url_after}")

        # Verify login success
        login_form_still_visible = await page.locator('input[type="password"]').count() > 0
        if login_form_still_visible:
            result["error"] = f"Login failed — password form still visible at {url_after}"
            print(f"  [Soledad] {result['error']}")
            return result
        print(f"  [Soledad] Login succeeded")

        # ── Navigate to search page ───────────────────────────────────────────
        url_origin = '/'.join(url_search.split('/')[:3])  # https://b2b.new.gruposoledad.com

        # Clear any API responses captured during login — we only want search responses
        api_responses.clear()

        # Navigate to the B2B search dashboard
        print(f"  [Soledad] Navigating to: {url_search}")
        try:
            await page.goto(url_search, wait_until="domcontentloaded", timeout=60000)
        except Exception as nav_e:
            print(f"  [Soledad] Navigation warning: {nav_e}")
        try:
            await page.wait_for_load_state("load", timeout=20000)
        except Exception:
            pass
        await asyncio.sleep(4)  # Extra wait for Angular to render

        _save_debug('/tmp/soledad_search_page.html', await page.content())
        search_page_url = page.url
        print(f"  [Soledad] Search page URL: {search_page_url}")

        # Diagnostic: dump all visible inputs on the search page
        page_inputs = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll("input, textarea, select, button"))
                .slice(0, 30)
                .map(el => ({
                    tag: el.tagName, type: el.type || "",
                    id: el.id || "", name: el.name || "",
                    placeholder: (el.placeholder || "").substring(0, 60),
                    classes: (el.className || "").toString().substring(0, 80),
                    text: el.textContent.trim().substring(0, 40),
                    visible: el.offsetWidth > 0 && el.offsetHeight > 0
                }));
        }''')
        inputs_summary = [f"{e['tag']}[{e['type']}] id={e['id']} name={e['name']} ph={e['placeholder']!r}" for e in page_inputs]
        print(f"  [Soledad] Dashboard inputs: {inputs_summary}")
        _save_debug('/tmp/soledad_inputs.html', json.dumps(page_inputs, indent=2, ensure_ascii=False))

        # Check if we were bounced back to login
        if 'login' in search_page_url.lower() and url_origin.lower() not in search_page_url.lower().replace('/login', ''):
            pw_count = await page.locator('input[type="password"]').count()
            if pw_count > 0:
                result["error"] = f"Session not valid for {url_origin} — redirected to login"
                return result

        # ── Search ────────────────────────────────────────────────────────────
        print(f"  [Soledad] Searching: {medida_slashed}")

        # Strategy A: URL-based search (Spartacus / SAP Commerce patterns)
        search_url_candidates = [
            f"{url_origin}/search?query={medida_slashed}",
            f"{url_origin}/search?q={medida_slashed}",
            f"{url_origin}/products?search={medida_slashed}",
            f"{url_origin}/catalog?q={medida_slashed}",
            f"{url_origin}/b2b/current/search?text={medida_slashed}",
            f"{url_origin}/b2b/current/search?q={medida_slashed}",
        ]

        search_done = False
        for surl in search_url_candidates:
            try:
                print(f"  [Soledad] URL search: {surl}")
                await page.goto(surl, wait_until="domcontentloaded", timeout=25000)
                try:
                    await page.wait_for_load_state("load", timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(5)  # Angular needs time to render after route change

                cur = page.url
                if await page.locator('input[type="password"]').count() > 0:
                    print(f"  [Soledad] URL search redirected to login, trying UI search")
                    await page.goto(url_search, wait_until="domcontentloaded", timeout=30000)
                    try:
                        await page.wait_for_load_state("load", timeout=15000)
                    except Exception:
                        pass
                    await asyncio.sleep(4)
                    break

                html = await page.content()
                has_size = medida_slashed.lower() in html.lower() or medida_norm in html
                has_price = bool(re.search(r'[€£$]\s*\d{2,3}|\d{2,3}[,\.]\d{2}\s*[€£$]', html))
                if has_size and has_price:
                    print(f"  [Soledad] URL search found results at: {cur}")
                    search_done = True
                    _save_debug('/tmp/soledad_results.html', html)
                    break
                print(f"  [Soledad] {surl.split('?')[0]} — no size+price in HTML")
            except Exception as ue:
                print(f"  [Soledad] URL search error: {ue}")
                continue

        # Strategy B: UI search (type in search box)
        if not search_done:
            print(f"  [Soledad] Trying UI search...")
            # Make sure we're on the dashboard, not login
            if await page.locator('input[type="password"]').count() > 0:
                print(f"  [Soledad] Login page detected, can't search")
                result["error"] = "Redirected to login before search — session issue"
                _save_debug('/tmp/soledad_results.html', await page.content())
                return result

            ui_selectors = [
                'cx-searchbox input',                     # Spartacus searchbox
                'input[placeholder*="medida" i]',
                'input[placeholder*="pesqui" i]',
                'input[placeholder*="buscar" i]',
                'input[placeholder*="search" i]',
                'input[placeholder*="referência" i]',
                'input[placeholder*="dimensão" i]',
                'input[placeholder*="referencia" i]',
                'input[name*="search" i]',
                'input[name*="pesqui" i]',
                'input[name*="medida" i]',
                'input[name*="query" i]',
                'input[name*="texto" i]',
                '[class*="search"] input',
                '[role="search"] input',
                'input[type="search"]',
                'input[type="text"]:not([name*="user" i]):not([name*="email" i]):not([autocomplete*="email" i])',
            ]

            for sel in ui_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.count() == 0:
                        continue
                    print(f"  [Soledad] Found input: {sel}")

                    for term in [medida_slashed, medida_norm]:
                        await el.click()
                        await el.triple_click()
                        await el.fill("")
                        await el.type(term, delay=60)
                        print(f"  [Soledad] Typed '{term}'")
                        await asyncio.sleep(0.5)
                        await el.press('Enter')
                        await asyncio.sleep(6)  # Generous wait for SPA render
                        try:
                            await page.wait_for_load_state("load", timeout=15000)
                        except Exception:
                            pass
                        await asyncio.sleep(2)

                        html_after = await page.content()
                        has_s = medida_slashed.lower() in html_after.lower() or medida_norm in html_after
                        has_p = bool(re.search(r'[€£$]\s*\d{2,3}|\d{2,3}[,\.]\d{2}\s*[€£$]', html_after))
                        if has_s:
                            print(f"  [Soledad] UI search ok for '{term}' (has_price={has_p})")
                            search_done = True
                            _save_debug('/tmp/soledad_results.html', html_after)
                            break
                        print(f"  [Soledad] '{term}' not in results HTML")
                        try:
                            await el.triple_click()
                        except Exception:
                            pass

                    if not search_done:
                        # Still accept whatever state we're in — save for debug
                        _save_debug('/tmp/soledad_results.html', await page.content())
                        search_done = True
                    break

                except Exception as se:
                    print(f"  [Soledad] Input error ({sel}): {se}")
                    continue

        # Save final page state regardless
        final_html = await page.content()
        if not search_done:
            _save_debug('/tmp/soledad_results.html', final_html)
            print(f"  [Soledad] No search input found")

        # ── Extract products ──────────────────────────────────────────────────
        # Primary: parse intercepted JSON API responses
        products = []

        def _parse_api_json(data, depth=0):
            """Recursively search JSON for objects that look like tire products."""
            if depth > 6:
                return
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        # Try to find price
                        price_val = None
                        for pk in ['price', 'preco', 'pvp', 'valor', 'netPrice',
                                   'purchasePrice', 'salePrice', 'unitPrice']:
                            v = item.get(pk)
                            if v is None:
                                continue
                            if isinstance(v, dict):
                                v = v.get('value') or v.get('formattedValue') or v.get('amount') or 0
                            try:
                                price_val = float(str(v).replace(',', '.').replace('€', '').strip())
                                if price_val < 10 or price_val > 2000:
                                    price_val = None
                            except Exception:
                                pass
                            if price_val:
                                break

                        if not price_val:
                            _parse_api_json(item, depth + 1)
                            continue

                        brand_val = ''
                        for bk in ['marca', 'brand', 'manufacturer', 'fabricante', 'brandName']:
                            v = item.get(bk)
                            if v:
                                brand_val = str(v).upper()
                                break

                        model_val = ''
                        for mk in ['modelo', 'model', 'description', 'descricao',
                                   'name', 'nome', 'designation', 'title']:
                            v = item.get(mk)
                            if v:
                                model_val = str(v)
                                break

                        products.append({'brand': brand_val, 'model': model_val, 'price': price_val})
                    else:
                        _parse_api_json(item, depth + 1)
            elif isinstance(data, dict):
                for v in data.values():
                    _parse_api_json(v, depth + 1)

        # Save API debug info (first 500 chars of each response body + URL)
        api_debug_info = [
            {'url': r['url'], 'len': len(r['body']), 'preview': r['body'][:500]}
            for r in api_responses
        ]
        _save_debug('/tmp/soledad_api.html', json.dumps(api_debug_info, indent=2, ensure_ascii=False))
        print(f"  [Soledad] {len(api_responses)} JSON API responses captured: "
              f"{[r['url'].split('?')[0][-40:] for r in api_responses]}")

        for resp in api_responses:
            try:
                data = json.loads(resp['body'])
                before = len(products)
                _parse_api_json(data)
                if len(products) > before:
                    print(f"  [Soledad] +{len(products)-before} products from {resp['url'].split('?')[0][-50:]}")
            except Exception:
                pass

        if products:
            print(f"  [Soledad] {len(products)} products from API interception")
        else:
            # Secondary: DOM extraction
            print(f"  [Soledad] No API products — trying DOM extraction")
            products = await page.evaluate(r'''() => {
                const products = [];
                const BRANDS = /MICHELIN|BRIDGESTONE|CONTINENTAL|PIRELLI|GOODYEAR|DUNLOP|HANKOOK|YOKOHAMA|FIRESTONE|KUMHO|TOYO|NEXEN|FALKEN|NOKIAN|VREDESTEIN|MAXXIS|GENERAL|UNIROYAL|SEMPERIT|BARUM|LASSA|SAVA|KLEBER|FULDA|GISLAVED|COOPER|NANKANG|LINGLONG|TRIANGLE|SAILUN|WESTLAKE/i;

                // Strategy 1: tables
                for (const tbl of document.querySelectorAll("table")) {
                    const rows = Array.from(tbl.querySelectorAll("tr"));
                    if (rows.length < 2) continue;
                    const hdr = Array.from(rows[0].querySelectorAll("th,td")).map(h=>h.textContent.trim().toLowerCase());
                    let bC=-1,mC=-1,pC=-1;
                    hdr.forEach((t,i)=>{
                        if(/marca|brand|fab/.test(t)) bC=i;
                        else if(/model|descri|artig|ref|denom/.test(t)) mC=i;
                        else if(/pre[cç]o|pvp|valor|unit|price/.test(t)) pC=i;
                    });
                    for (let i=1;i<rows.length;i++){
                        const cells=Array.from(rows[i].querySelectorAll("td"));
                        if(cells.length<2) continue;
                        let brand=bC>=0?cells[bC]?.textContent.trim().toUpperCase():"";
                        let model=mC>=0?cells[mC]?.textContent.trim():"";
                        let price=null;
                        if(pC>=0){const m=cells[pC]?.textContent.match(/(\d+[,.]?\d*)/);if(m)price=parseFloat(m[1].replace(",","."));}
                        if(!price){for(const c of cells){const m=c.textContent.trim().match(/^[€$]?\s*(\d{2,3}[,.]\d{2})\s*[€$]?$/);if(m){const p=parseFloat(m[1].replace(",","."));if(p>15&&p<2000){price=p;break;}}}}
                        if(!brand){const t=cells.map(c=>c.textContent).join(" ").toUpperCase();const bm=t.match(BRANDS);if(bm)brand=bm[0];}
                        if(price&&price>15&&price<2000) products.push({brand,model,price});
                    }
                    if(products.length>0) break;
                }

                // Strategy 2: any element containing a price near a brand name
                if(products.length===0){
                    const allEls = Array.from(document.querySelectorAll("*"));
                    for(const el of allEls){
                        const t = el.childNodes.length===1&&el.childNodes[0].nodeType===3 ? el.textContent.trim() : "";
                        if(!t) continue;
                        const pm=t.match(/^[€$]?\s*(\d{2,3}[,.]\d{2})\s*[€$]?$/);
                        if(!pm) continue;
                        const price=parseFloat(pm[1].replace(",","."));
                        if(price<15||price>2000) continue;
                        // Find nearby brand in ancestor text
                        let brand="",model="";
                        let ancestor=el.parentElement;
                        for(let d=0;d<5&&ancestor;d++,ancestor=ancestor.parentElement){
                            const at=ancestor.textContent.toUpperCase();
                            const bm=at.match(BRANDS);
                            if(bm){brand=bm[0];model=ancestor.textContent.trim().substring(0,120);break;}
                        }
                        if(brand) products.push({brand,model,price});
                    }
                }

                // Deduplicate keeping lowest price
                const seen={};
                for(const p of products){
                    const k=(p.brand||"")+(p.model||"").substring(0,30);
                    if(!seen[k]||p.price<seen[k].price) seen[k]=p;
                }
                return Object.values(seen);
            }''')
            if products:
                print(f"  [Soledad] {len(products)} products from DOM")

        if products:
            result["products"] = products
            prices = [p['price'] for p in products]
            result["price"] = min(prices)
            result["all_prices"] = sorted(prices)[:10]
            print(f"  [Soledad] Best price: €{result['price']}")
        else:
            # Last resort: regex price scan on final HTML
            prices_list = extract_prices(final_html)
            if prices_list:
                result["price"] = min(prices_list)
                result["all_prices"] = sorted(prices_list)[:10]
                print(f"  [Soledad] Regex fallback: {len(prices_list)} prices, best €{result['price']}")
            else:
                result["error"] = (
                    f"No products found — "
                    f"API responses: {len(api_responses)}, "
                    f"search_done: {search_done}. "
                    f"Check /tmp/soledad_results.html and /api/scraper/debug-html?supplier=soledad&file=results"
                )
                print(f"  [Soledad] {result['error']}")

    except Exception as e:
        result["error"] = str(e)
        print(f"  [Soledad] Exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            page.remove_listener('response', _capture_api_response)
        except Exception:
            pass

    return result

async def scrape_aguesport(page, username: str, password: str, medida: str) -> dict:
    """Scrape Aguesport"""
    result = {
        "supplier": "Aguesport",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        print("  [Aguesport] Logging in...")
        await page.goto("https://encomendas.aguesport.com/login", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        # Fill login form
        email_input = page.locator('input[type="email"], input[name="email"], input[name="username"]').first
        if await email_input.count() > 0:
            await email_input.fill(username)
        
        password_input = page.locator('input[type="password"]').first
        if await password_input.count() > 0:
            await password_input.fill(password)
        
        # Submit login
        submit_btn = page.locator('button[type="submit"], input[type="submit"]').first
        if await submit_btn.count() > 0:
            await submit_btn.click()
        await asyncio.sleep(5)
        
        # Search for tires
        medida_norm = normalize_medida(medida)
        print(f"  [Aguesport] Searching for: {medida_norm}")
        
        search_input = page.locator('input[type="search"], input[placeholder*="pesq"], input[name*="search"], #search').first
        if await search_input.count() > 0:
            await search_input.fill(medida_norm)
            await search_input.press('Enter')
            await asyncio.sleep(5)
        
        # Extract products
        products = await page.evaluate('''() => {
            const products = [];
            const items = document.querySelectorAll('.product, .item, [class*="product"], [class*="item"], table tr');
            
            items.forEach(item => {
                const text = item.textContent || '';
                const priceMatch = text.match(/(\d+[,\.]\d{2})\s*€|€\s*(\d+[,\.]\d{2})/);
                
                if (priceMatch) {
                    const priceStr = priceMatch[1] || priceMatch[2];
                    const price = parseFloat(priceStr.replace(',', '.'));
                    
                    // Try to extract brand and model
                    const brandMatch = text.match(/(MICHELIN|BRIDGESTONE|CONTINENTAL|PIRELLI|GOODYEAR|DUNLOP|HANKOOK|YOKOHAMA|FIRESTONE|BF GOODRICH|KUMHO|TOYO|NEXEN|FALKEN|COOPER|NOKIAN|VREDESTEIN|MAXXIS|GENERAL|UNIROYAL|SEMPERIT|BARUM|LASSA|SAVA|KLEBER|FULDA|GISLAVED|MATADOR|DEBICA|KELLY|DAYTON|ROADSTONE|NANKANG|FEDERAL|ACHILLES|LINGLONG|TRIANGLE|WESTLAKE|GOODRIDE|SAILUN|LANDSAIL|RADAR|ZEETEX|APLUS|COMPASAL|WINDFORCE|SUNFULL|ROADCLAW|HIFLY|SUNWIDE|POWERTRAC|THREE-A|GREMAX|ANTARES|BOTO|JINYU|DELINTE|MASSIMO|INSA TURBO)/i);
                    
                    if (price > 15 && price < 500) {
                        products.push({
                            brand: brandMatch ? brandMatch[1].toUpperCase() : 'UNKNOWN',
                            model: '',
                            price: price
                        });
                    }
                }
            });
            
            return products;
        }''')
        
        if products and len(products) > 0:
            result["products"] = products
            prices = [p['price'] for p in products]
            result["price"] = min(prices)
            result["all_prices"] = sorted(prices)[:10]
            print(f"  [Aguesport] Found {len(products)} products")
        else:
            content = await page.content()
            prices = extract_prices(content)
            if prices:
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
            else:
                result["error"] = "No products found"
                
    except Exception as e:
        result["error"] = str(e)
        print(f"  [Aguesport] Error: {e}")
    
    return result

async def scrape_abt_tyres(page, username: str, password: str, medida: str) -> dict:
    """Scrape ABT Tyres B2B"""
    result = {
        "supplier": "ABT Tyres",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        print("  [ABT Tyres] Logging in...")
        await page.goto("https://b2b.abtyres.pt/", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        # Fill login form
        username_input = page.locator('input[name="username"], input[name="user"], input[type="text"]').first
        if await username_input.count() > 0:
            await username_input.fill(username)
        
        password_input = page.locator('input[type="password"]').first
        if await password_input.count() > 0:
            await password_input.fill(password)
        
        # Submit login
        submit_btn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Entrar")').first
        if await submit_btn.count() > 0:
            await submit_btn.click()
        await asyncio.sleep(5)
        
        # Search for tires
        medida_norm = normalize_medida(medida)
        print(f"  [ABT Tyres] Searching for: {medida_norm}")
        
        # Try search box
        search_input = page.locator('input[type="search"], input[placeholder*="pesq"], input[name*="search"], #searchInput, .search-box input').first
        if await search_input.count() > 0:
            await search_input.fill(medida_norm)
            await search_input.press('Enter')
            await asyncio.sleep(5)
        
        # Extract products
        products = await page.evaluate('''() => {
            const products = [];
            const items = document.querySelectorAll('.product, .item, .tire, [class*="product"], [class*="tire"], table tbody tr');
            
            items.forEach(item => {
                const text = item.textContent || '';
                const priceMatch = text.match(/(\d+[,\.]\d{2})\s*€|€\s*(\d+[,\.]\d{2})/);
                
                if (priceMatch) {
                    const priceStr = priceMatch[1] || priceMatch[2];
                    const price = parseFloat(priceStr.replace(',', '.'));
                    
                    const brandMatch = text.match(/(MICHELIN|BRIDGESTONE|CONTINENTAL|PIRELLI|GOODYEAR|DUNLOP|HANKOOK|YOKOHAMA|FIRESTONE|BF GOODRICH|KUMHO|TOYO|NEXEN|FALKEN|COOPER|NOKIAN|VREDESTEIN|MAXXIS|GENERAL|UNIROYAL|SEMPERIT|BARUM|LASSA|SAVA|KLEBER|FULDA|GISLAVED|MATADOR)/i);
                    
                    if (price > 15 && price < 500) {
                        products.push({
                            brand: brandMatch ? brandMatch[1].toUpperCase() : 'UNKNOWN',
                            model: '',
                            price: price
                        });
                    }
                }
            });
            
            return products;
        }''')
        
        if products and len(products) > 0:
            result["products"] = products
            prices = [p['price'] for p in products]
            result["price"] = min(prices)
            result["all_prices"] = sorted(prices)[:10]
            print(f"  [ABT Tyres] Found {len(products)} products")
        else:
            content = await page.content()
            prices = extract_prices(content)
            if prices:
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
            else:
                result["error"] = "No products found"
                
    except Exception as e:
        result["error"] = str(e)
        print(f"  [ABT Tyres] Error: {e}")
    
    return result

async def scrape_tugapneus(page, username: str, password: str, medida: str,
                           marca: str = '', modelo: str = '') -> dict:
    """Scrape TugaPneus (tugapneus.pt)"""
    result = {
        "supplier": "TugaPneus",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    medida_norm = normalize_medida(medida)
    # Reconstruct slashed format for search (e.g. 1956515 → 195/65R15)
    _m = re.match(r'^(\d{3})(\d{2})(\d{2})$', medida_norm)
    medida_slashed = f"{_m.group(1)}/{_m.group(2)}R{_m.group(3)}" if _m else medida_norm

    try:
        print(f"  [TugaPneus] Logging in as {username}...")
        await page.goto("https://www.tugapneus.pt/login", wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        await asyncio.sleep(2)

        current_url = page.url
        if '/produtos' in current_url or 'login' not in current_url.lower():
            print(f"  [TugaPneus] Already logged in, on: {current_url}")
        else:
            # Fill email — use type() for human-like input (avoids bot detection)
            email_input = page.locator(
                'input[type="email"], input[name="email"], input[name*="mail"], '
                'input[name="username"], input[type="text"]'
            ).first
            if await email_input.count() > 0:
                await email_input.click()
                await email_input.type(username, delay=80)
                await asyncio.sleep(0.4)
            else:
                result["error"] = "Email field not found on TugaPneus login page"
                return result

            password_input = page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.click()
                await password_input.type(password, delay=80)
                await asyncio.sleep(0.4)
            else:
                result["error"] = "Password field not found on TugaPneus login page"
                return result

            # Submit — o botão chama-se "EFETUAR LOGIN"
            submit_btn = page.locator(
                'button:has-text("EFETUAR LOGIN"), '
                'button:has-text("Efetuar Login"), '
                'button[type="submit"], input[type="submit"], '
                'button:has-text("Login"), button:has-text("Entrar"), '
                'a:has-text("EFETUAR LOGIN")'
            ).first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                print(f"  [TugaPneus] Botão de login clicado")
            else:
                await password_input.press("Enter")
                print(f"  [TugaPneus] Submit via Enter")

            # Aguardar até o campo password desaparecer (login AJAX — URL pode manter-se em /login)
            for _i in range(40):  # até 20 segundos
                await asyncio.sleep(0.5)
                if await page.locator('input[type="password"]').count() == 0:
                    print(f"  [TugaPneus] Campo password desapareceu ao fim de ~{_i*0.5:.0f}s")
                    break
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            await asyncio.sleep(2)

            # Tratar popup obrigatório "TOMEI CONHECIMENTO" que aparece após login
            try:
                popup_btn = page.locator(
                    'button:has-text("TOMEI CONHECIMENTO"), '
                    'button:has-text("Tomei Conhecimento"), '
                    'a:has-text("TOMEI CONHECIMENTO"), '
                    '[class*="modal"] button, [class*="popup"] button, '
                    '[role="dialog"] button'
                ).first
                if await popup_btn.count() > 0:
                    await popup_btn.click()
                    print(f"  [TugaPneus] Popup dispensado ('TOMEI CONHECIMENTO')")
                    await asyncio.sleep(2)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                else:
                    # Esperar um pouco mais e tentar novamente
                    await asyncio.sleep(3)
                    if await popup_btn.count() > 0:
                        await popup_btn.click()
                        print(f"  [TugaPneus] Popup dispensado (2ª tentativa)")
                        await asyncio.sleep(2)
            except Exception as pe:
                print(f"  [TugaPneus] Aviso popup: {pe}")

            url_after = page.url
            content_after = await page.content()
            print(f"  [TugaPneus] URL após login: {url_after}")

            # Verificar sucesso: URL mudou para /produtos OU campo password desapareceu
            pw_still_visible = await page.locator('input[type="password"]').count() > 0
            url_ok = 'produtos' in url_after.lower() or 'conhecimento' in url_after.lower()
            content_ok = any(t in content_after.lower() for t in [
                'sair', 'logout', 'minha conta', 'bem-vindo', 'olá,', 'carrinho'
            ])
            if pw_still_visible and not url_ok and not content_ok:
                result["error"] = f"Login falhou — credenciais rejeitadas ({url_after})"
                return result
            print(f"  [TugaPneus] Login efectuado com sucesso (URL: {url_after})")

        # Navegar sempre para /produtos com estado limpo (mesmo que já estejamos em /produtos?conhecimento=1)
        print(f"  [TugaPneus] A navegar para /produtos (URL actual: {page.url})...")
        await page.goto("https://www.tugapneus.pt/produtos", wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(2)

        # Se o popup aparecer de novo, dispensar
        try:
            popup2 = page.locator(
                'button:has-text("TOMEI CONHECIMENTO"), button:has-text("Tomei Conhecimento"), '
                '[role="dialog"] button, [class*="modal"] button'
            ).first
            if await popup2.count() > 0:
                await popup2.click()
                print(f"  [TugaPneus] Popup dispensado ao navegar para /produtos")
                await asyncio.sleep(2)
        except Exception:
            pass

        if 'login' in page.url.lower():
            result["error"] = "Redireccionado para login ao navegar para produtos — sessão inválida"
            return result

        print(f"  [TugaPneus] Pronto para pesquisar. URL: {page.url}")

        # Pesquisa progressiva TugaPneus
        # Nível 1: "pneu [marca] [medida] [modelo]"  (se marca e modelo disponíveis)
        # Nível 2: "pneu [marca] [medida]"            (se marca disponível)
        # Nível 3: "[medida]"                          (formato com / e R, ex: 205/60R16)
        _terms: list[str] = []
        if marca and modelo:
            _terms.append(f"pneu {marca} {medida_slashed} {modelo}".lower())
        if marca:
            _terms.append(f"pneu {marca} {medida_slashed}".lower())
        _terms.append(medida_slashed)

        # Localiza o campo de pesquisa
        _search_input = None
        for _sel in [
            'input[type="search"]',
            'input[name*="search" i]',
            'input[name*="pesq" i]',
            'input[placeholder*="pesq" i]',
            'input[placeholder*="medida" i]',
            '#search',
            '.search-input input',
            'input[type="text"]',
        ]:
            _el = page.locator(_sel).first
            if await _el.count() > 0:
                _search_input = _el
                break

        async def _limpar_pesquisa():
            btn = page.locator('button:has-text("LIMPAR"), button:has-text("Limpar")').first
            if await btn.count() > 0:
                await btn.click()
                await asyncio.sleep(0.4)
            elif _search_input:
                await _search_input.clear()

        print(f"  [TugaPneus] Pesquisa progressiva: {_terms}")
        _found = False
        for i, _term in enumerate(_terms):
            print(f"  [TugaPneus] Tentativa {i+1}/{len(_terms)}: '{_term}'")

            if i > 0:
                await _limpar_pesquisa()

            if _search_input:
                await _search_input.clear()
                await _search_input.fill(_term)
                await asyncio.sleep(0.4)
                _btn = page.locator(
                    'button:has-text("PESQUISAR"), button:has-text("Pesquisar"), '
                    'button:has-text("Buscar"), button[type="submit"], .search-btn'
                ).first
                if await _btn.count() > 0:
                    await _btn.click()
                else:
                    await _search_input.press("Enter")
            else:
                await page.goto(
                    f"https://www.tugapneus.pt/produtos?search={_term.replace(' ', '+')}",
                    wait_until="domcontentloaded", timeout=30000
                )

                # Aguarda que a página carregue (sem depender do DOM renderizado)
            await asyncio.sleep(5)
            _html = await page.content()
            _url_now = page.url
            print(f"  [TugaPneus] URL após pesquisa: {_url_now}")

            # Verifica se há descrições "PNEU ..." no HTML bruto
            if re.search(r'PNEU\s+\w', _html, re.IGNORECASE):
                print(f"  [TugaPneus] Dados encontrados no HTML com '{_term}'")
                _found = True
                break
            print(f"  [TugaPneus] Sem 'PNEU...' no HTML para '{_term}', próximo nível...")

        content = await page.content()
        _has_pneu = bool(re.search(r'PNEU\s+\w', content, re.IGNORECASE))
        print(f"  [TugaPneus] HTML size: {len(content)} chars, PNEU encontrado: {_has_pneu}")
        # Guardar HTML para debug via /api/scraper/debug-html?supplier=tugapneus&file=search_page
        try:
            with open('/tmp/tugapneus_search_page.html', 'w', encoding='utf-8') as _f:
                _f.write(content)
        except Exception:
            pass
        # Debug: contexto à volta do primeiro "PNEU"
        _pneu_m = re.search(r'PNEU\s+\w', content, re.IGNORECASE)
        if _pneu_m:
            _start = max(0, _pneu_m.start() - 30)
            _snippet = content[_start:_pneu_m.start()+200].replace('\n', ' ')
            print(f"  [TugaPneus] CONTEXTO: {repr(_snippet)}")

        if not _found:
            print(f"  [TugaPneus] Nenhuma tentativa retornou resultados, extraindo o que houver...")

        # ── Extracção via Python regex sobre HTML bruto ───────────────────
        # Estrutura TugaPneus confirmada pelo debug:
        #   id="linha_tit_XXXX"   → <strong>PNEU MASSIMO 235/45R18 98W OTTIMA PLUS XL</strong>
        #   id="linha_precv_XXXX" → 47.00€
        # Fazemos pair por ID numérico — muito mais robusto do que posição.
        def _parse_tuga_html(html: str) -> list:
            # 1. Extrair descrições: id="linha_tit_NNN" → texto do <strong>
            tit_re = re.compile(
                r'id=["\']linha_tit_(\d+)["\'][^>]*>.*?<strong[^>]*>\s*(.*?)\s*</strong>',
                re.IGNORECASE | re.DOTALL
            )
            # 2. Extrair preços: id="linha_precv_NNN" → número€
            prec_re = re.compile(
                r'id=["\']linha_precv_(\d+)["\'][^>]*>[\s\S]{0,300}?(\d+[,.]\d{2})\s*\u20ac',
                re.IGNORECASE
            )
            # 3. Parse da descrição "PNEU MARCA MEDIDA ÍNDICE MODELO"
            desc_re = re.compile(
                r'PNEU\s+([\w\-]+(?:\s+[\w\-]+)?)\s+(\d{3}/\d{2}R\d{2})\s+(\d{2,3}[A-Z]{1,2}(?:\s+XL)?)\s*(.*)',
                re.IGNORECASE
            )

            titles = {m.group(1): m.group(2).strip() for m in tit_re.finditer(html)}
            prices: dict = {}
            for m in prec_re.finditer(html):
                try:
                    v = float(m.group(2).replace(',', '.'))
                    if 15 < v < 800:
                        prices[m.group(1)] = v
                except ValueError:
                    pass

            print(f"  [TugaPneus] _parse_tuga_html: {len(titles)} títulos, {len(prices)} preços")

            products = []
            for pid, desc in titles.items():
                if pid not in prices:
                    continue
                dm = desc_re.match(desc)
                if not dm:
                    continue
                products.append({
                    'brand':  dm.group(1).strip().upper(),
                    'medida': dm.group(2).strip().upper(),
                    'indice': dm.group(3).strip().upper(),
                    'model':  dm.group(4).strip().upper(),
                    'price':  prices[pid]
                })

            # Dedup: mesma chave → fica o mais barato
            seen: dict = {}
            for p in products:
                k = f"{p['brand']}|{p['medida']}|{p['indice']}|{p['model']}"
                if k not in seen or p['price'] < seen[k]['price']:
                    seen[k] = p
            result_list = list(seen.values())
            print(f"  [TugaPneus] _parse_tuga_html: {len(result_list)} produtos extraídos")
            return result_list

        products = _parse_tuga_html(content)

        if products:
            result["products"] = products
            result["price"] = min(p['price'] for p in products)
            result["all_prices"] = sorted(p['price'] for p in products)[:10]
            print(f"  [TugaPneus] {len(products)} produtos extraídos do HTML, melhor: €{result['price']}")
            for p in products[:5]:
                print(f"    {p['brand']} {p['medida']} {p['indice']} {p['model']} → €{p['price']}")
        else:
            # Fallback: apenas preços sem estrutura (garante que não fica sem dados)
            prices = extract_prices(content)
            if prices:
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
                print(f"  [TugaPneus] Fallback preços: {len(prices)} preços, melhor: €{result['price']}")
            else:
                result["error"] = "No products found"
                print(f"  [TugaPneus] Sem produtos")

    except Exception as e:
        result["error"] = str(e)
        print(f"  [TugaPneus] Error: {e}")

    return result

async def scrape_inter_sprint(page, username: str, password: str, medida: str) -> dict:
    """Scrape Inter-Sprint (Netherlands)"""
    result = {
        "supplier": "Inter-Sprint",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        print("  [Inter-Sprint] Logging in...")
        await page.goto("https://customers.inter-sprint.nl/", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        # Fill login form
        username_input = page.locator('input[name="username"], input[name="user"], input[type="text"]').first
        if await username_input.count() > 0:
            await username_input.fill(username)
        
        password_input = page.locator('input[type="password"]').first
        if await password_input.count() > 0:
            await password_input.fill(password)
        
        # Submit login
        submit_btn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Sign in")').first
        if await submit_btn.count() > 0:
            await submit_btn.click()
        await asyncio.sleep(5)
        
        # Search for tires
        medida_norm = normalize_medida(medida)
        print(f"  [Inter-Sprint] Searching for: {medida_norm}")
        
        # Try to navigate to tyres section
        tyres_link = page.locator('a:has-text("Tyres"), a:has-text("Banden"), a:has-text("Tires")').first
        if await tyres_link.count() > 0:
            await tyres_link.click()
            await asyncio.sleep(3)
        
        search_input = page.locator('input[type="search"], input[placeholder*="search"], input[name*="search"], #search').first
        if await search_input.count() > 0:
            await search_input.fill(medida_norm)
            await search_input.press('Enter')
            await asyncio.sleep(5)
        
        # Extract products
        products = await page.evaluate('''() => {
            const products = [];
            const items = document.querySelectorAll('.product, .item, .tire, [class*="product"], table tbody tr');
            
            items.forEach(item => {
                const text = item.textContent || '';
                const priceMatch = text.match(/€\s*(\d+[,\.]\d{2})|(\d+[,\.]\d{2})\s*€/);
                
                if (priceMatch) {
                    const priceStr = priceMatch[1] || priceMatch[2];
                    const price = parseFloat(priceStr.replace(',', '.'));
                    
                    const brandMatch = text.match(/(MICHELIN|BRIDGESTONE|CONTINENTAL|PIRELLI|GOODYEAR|DUNLOP|HANKOOK|YOKOHAMA|FIRESTONE|KUMHO|TOYO|NEXEN|FALKEN|NOKIAN|VREDESTEIN|MAXXIS|GENERAL|UNIROYAL)/i);
                    
                    if (price > 15 && price < 500) {
                        products.push({
                            brand: brandMatch ? brandMatch[1].toUpperCase() : 'UNKNOWN',
                            model: '',
                            price: price
                        });
                    }
                }
            });
            
            return products;
        }''')
        
        if products and len(products) > 0:
            result["products"] = products
            prices = [p['price'] for p in products]
            result["price"] = min(prices)
            result["all_prices"] = sorted(prices)[:10]
            print(f"  [Inter-Sprint] Found {len(products)} products")
        else:
            content = await page.content()
            prices = extract_prices(content)
            if prices:
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
            else:
                result["error"] = "No products found"
                
    except Exception as e:
        result["error"] = str(e)
        print(f"  [Inter-Sprint] Error: {e}")
    
    return result

async def scrape_pneus_cruzeiro(page, username: str, password: str, medida: str) -> dict:
    """Scrape Pneus Cruzeiro"""
    result = {
        "supplier": "Pneus Cruzeiro",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        print("  [Pneus Cruzeiro] Logging in...")
        await page.goto("https://www.pneuscruzeiro.pt/", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        # Look for login button/link
        login_link = page.locator('a:has-text("Login"), a:has-text("Entrar"), button:has-text("Login"), .login-link').first
        if await login_link.count() > 0:
            await login_link.click()
            await asyncio.sleep(2)
        
        # Fill login form
        email_input = page.locator('input[type="email"], input[name="email"], input[name="username"]').first
        if await email_input.count() > 0:
            await email_input.fill(username)
        
        password_input = page.locator('input[type="password"]').first
        if await password_input.count() > 0:
            await password_input.fill(password)
        
        # Submit login
        submit_btn = page.locator('button[type="submit"], input[type="submit"]').first
        if await submit_btn.count() > 0:
            await submit_btn.click()
        await asyncio.sleep(5)
        
        # Search for tires
        medida_norm = normalize_medida(medida)
        print(f"  [Pneus Cruzeiro] Searching for: {medida_norm}")
        
        # Navigate to tires section
        tyres_link = page.locator('a:has-text("Pneus"), a:has-text("Catálogo")').first
        if await tyres_link.count() > 0:
            await tyres_link.click()
            await asyncio.sleep(3)
        
        search_input = page.locator('input[type="search"], input[placeholder*="pesq"], input[name*="search"], #search').first
        if await search_input.count() > 0:
            await search_input.fill(medida_norm)
            await search_input.press('Enter')
            await asyncio.sleep(5)
        
        # Extract products
        products = await page.evaluate('''() => {
            const products = [];
            const items = document.querySelectorAll('.product, .item, [class*="product"], [class*="item"]');
            
            items.forEach(item => {
                const text = item.textContent || '';
                const priceMatch = text.match(/(\d+[,\.]\d{2})\s*€|€\s*(\d+[,\.]\d{2})/);
                
                if (priceMatch) {
                    const priceStr = priceMatch[1] || priceMatch[2];
                    const price = parseFloat(priceStr.replace(',', '.'));
                    
                    const brandMatch = text.match(/(MICHELIN|BRIDGESTONE|CONTINENTAL|PIRELLI|GOODYEAR|DUNLOP|HANKOOK|YOKOHAMA|FIRESTONE|KUMHO|TOYO|NEXEN|FALKEN|NOKIAN|VREDESTEIN|MAXXIS)/i);
                    
                    if (price > 15 && price < 500) {
                        products.push({
                            brand: brandMatch ? brandMatch[1].toUpperCase() : 'UNKNOWN',
                            model: '',
                            price: price
                        });
                    }
                }
            });
            
            return products;
        }''')
        
        if products and len(products) > 0:
            result["products"] = products
            prices = [p['price'] for p in products]
            result["price"] = min(prices)
            result["all_prices"] = sorted(prices)[:10]
            print(f"  [Pneus Cruzeiro] Found {len(products)} products")
        else:
            content = await page.content()
            prices = extract_prices(content)
            if prices:
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
            else:
                result["error"] = "No products found"
                
    except Exception as e:
        result["error"] = str(e)
        print(f"  [Pneus Cruzeiro] Error: {e}")
    
    return result

# ============================================================
# END NEW SCRAPERS
# ============================================================

async def get_suppliers_from_db():
    """Get active suppliers from PostgreSQL"""
    conn = await _pg_connect()
    try:
        rows = await conn.fetch("SELECT * FROM suppliers WHERE is_active = TRUE")
        suppliers = []
        for row in rows:
            d = dict(row)
            password = d.get("password_raw") or d.get("password", "")
            suppliers.append({
                "id": d["id"],
                "name": d["name"],
                "username": d["username"],
                "password": password,
                "url_login": d.get("url_login", ""),
            })
        return suppliers
    finally:
        await conn.close()

async def save_price_to_db(supplier_name: str, medida: str, price: float, error: str = None):
    """Save scraping result to PostgreSQL (upsert by supplier+medida, no brand)"""
    conn = await _pg_connect()
    try:
        # Delete existing record for this supplier+medida with no brand, then insert fresh
        await conn.execute(
            "DELETE FROM scraped_prices WHERE supplier_name = $1 AND medida = $2 AND marca IS NULL",
            supplier_name, medida,
        )
        if price is not None:
            await conn.execute(
                """
                INSERT INTO scraped_prices (id, supplier_name, medida, price, scraped_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                str(uuid.uuid4()), supplier_name, medida, price, datetime.now(timezone.utc),
            )
    finally:
        await conn.close()

async def run_scraper(medidas: list, supplier_filter: str = None):
    """Main scraper function"""
    print(f"Starting scraper at {datetime.now()}")
    print(f"Medidas to scrape: {medidas}")
    
    suppliers = await get_suppliers_from_db()
    print(f"Found {len(suppliers)} suppliers")
    
    if supplier_filter:
        suppliers = [s for s in suppliers if supplier_filter.lower() in s['name'].lower()]
        print(f"Filtered to {len(suppliers)} suppliers matching '{supplier_filter}'")
    
    results = []
    
    # Process each supplier with its own browser instance (like test script)
    for supplier in suppliers:
        supplier_name = supplier['name'].lower()
        print(f"\n--- Scraping {supplier['name']} ---")
        
        for medida in medidas:
            # Create completely fresh browser for each supplier (like test script does)
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='pt-PT',
                )
                
                page = await context.new_page()
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
                
                try:
                    if 'mp24' in supplier_name:
                        result = await scrape_mp24(page, supplier['username'], supplier['password'], medida)
                    elif 'prismanil' in supplier_name:
                        result = await scrape_prismanil(page, supplier['username'], supplier['password'], medida)
                    elif 'dispnal' in supplier_name:
                        result = await scrape_dispnal(page, supplier['username'], supplier['password'], medida)
                    elif 'josé' in supplier_name or 'jose' in supplier_name:
                        result = await scrape_sjose(page, supplier['username'], supplier['password'], medida,
                                                    supplier.get('url_login', ''), supplier.get('url_search', ''))
                    elif 'euromais' in supplier_name or 'eurotyre' in supplier_name:
                        result = await scrape_euromais(page, supplier['username'], supplier['password'], medida)
                    elif 'soledad' in supplier_name:
                        result = await scrape_grupo_soledad(page, supplier['username'], supplier['password'], medida,
                                                            supplier.get('url_login', ''), supplier.get('url_search', ''))
                    elif 'aguesport' in supplier_name:
                        result = await scrape_aguesport(page, supplier['username'], supplier['password'], medida)
                    elif 'abt' in supplier_name:
                        result = await scrape_abt_tyres(page, supplier['username'], supplier['password'], medida)
                    elif 'tugapneus' in supplier_name or 'tuga' in supplier_name:
                        result = await scrape_tugapneus(page, supplier['username'], supplier['password'], medida)
                    elif 'inter-sprint' in supplier_name or 'intersprint' in supplier_name:
                        result = await scrape_inter_sprint(page, supplier['username'], supplier['password'], medida)
                    elif 'cruzeiro' in supplier_name:
                        result = await scrape_pneus_cruzeiro(page, supplier['username'], supplier['password'], medida)
                    else:
                        result = {"supplier": supplier['name'], "price": None, "error": "Adapter not implemented"}
                    
                    result["medida"] = medida
                    results.append(result)

                    # Save to PostgreSQL with full brand/model data
                    products = result.get('products', [])
                    now = datetime.now(timezone.utc)
                    conn_save = await _pg_connect()
                    try:
                        if products:
                            for prod in products:
                                marca = prod.get('brand', '').upper()
                                modelo = prod.get('model', '')
                                await conn_save.execute(
                                    """
                                    DELETE FROM scraped_prices
                                    WHERE supplier_name = $1 AND medida = $2
                                      AND COALESCE(marca,'') = $3 AND COALESCE(modelo,'') = $4
                                    """,
                                    supplier['name'], medida, marca, modelo,
                                )
                                await conn_save.execute(
                                    """
                                    INSERT INTO scraped_prices
                                        (id, supplier_name, medida, marca, modelo, price, scraped_at)
                                    VALUES ($1,$2,$3,$4,$5,$6,$7)
                                    """,
                                    str(uuid.uuid4()), supplier['name'], medida,
                                    marca, modelo, prod.get('price'), now,
                                )
                            print(f"  {medida}: saved {len(products)} products with brand/model")
                        else:
                            # Fallback: save single price without brand
                            await conn_save.execute(
                                "DELETE FROM scraped_prices WHERE supplier_name=$1 AND medida=$2 AND marca IS NULL",
                                supplier['name'], medida,
                            )
                            if result.get('price') is not None:
                                await conn_save.execute(
                                    """
                                    INSERT INTO scraped_prices (id, supplier_name, medida, price, scraped_at)
                                    VALUES ($1,$2,$3,$4,$5)
                                    """,
                                    str(uuid.uuid4()), supplier['name'], medida,
                                    result['price'], now,
                                )
                            print(f"  {medida}: €{result.get('price')} (no brand data)")
                    finally:
                        await conn_save.close()

                    if result.get('price'):
                        print(f"  {medida}: best price €{result['price']}")
                    else:
                        print(f"  {medida}: {result.get('error', 'No price found')}")
                        
                except Exception as e:
                    print(f"  Error: {e}")
                    results.append({"supplier": supplier['name'], "medida": medida, "error": str(e)})
                finally:
                    await browser.close()
    
    # Save results to file
    result_file = RESULTS_DIR / f"scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to {result_file}")
    print(f"Scraper finished at {datetime.now()}")
    
    return results

def run_supplier(supplier_id: str, sizes: list, job_id: str = None):
    """
    Synchronous function called by worker.py
    Runs scraping for a single supplier
    """
    print(f"run_supplier called: supplier_id={supplier_id}, sizes={sizes}, job_id={job_id}")
    
    # Run async scraper in sync context
    asyncio.run(_run_supplier_async(supplier_id, sizes, job_id))

async def _run_supplier_async(supplier_id: str, sizes: list, job_id: str = None):
    """Async implementation of run_supplier"""
    print(f"Starting scraper for supplier {supplier_id}")

    # Get supplier from PostgreSQL
    conn = await _pg_connect()
    row = await conn.fetchrow("SELECT * FROM suppliers WHERE id = $1", supplier_id)
    if not row:
        row = await conn.fetchrow(
            "SELECT * FROM suppliers WHERE LOWER(name) LIKE $1",
            f"%{supplier_id.lower()}%",
        )

    if not row:
        print(f"Supplier not found: {supplier_id}")
        await conn.close()
        return

    supplier = dict(row)
    
    supplier_name = supplier['name'].lower()
    username = supplier['username']
    # Use password_raw (plain text) for scraping, fallback to password if not hashed
    password = supplier.get('password_raw') or supplier.get('password', '')
    
    # Check if password is hashed (bcrypt hashes start with $2)
    if password.startswith('$2'):
        print(f"WARNING: Password appears to be hashed for {supplier['name']}. Scraping may fail.")
    
    print(f"Found supplier: {supplier['name']}")
    print(f"Sizes to scrape: {sizes}")
    
    results = []
    
    # Run scraping with ONE browser for all sizes (reuse session)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
        )
        
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        
        # Do login once for the supplier
        logged_in = False
        
        for medida in sizes:
            try:
                print(f"Scraping {supplier['name']} for size {medida}...")
                
                if 'mp24' in supplier_name:
                    result = await scrape_mp24_with_session(page, username, password, medida, logged_in)
                    logged_in = True  # After first scrape, we're logged in
                elif 'prismanil' in supplier_name:
                    result = await scrape_prismanil(page, username, password, medida)
                elif 'dispnal' in supplier_name:
                    result = await scrape_dispnal(page, username, password, medida)
                elif 'josé' in supplier_name or 'jose' in supplier_name:
                    result = await scrape_sjose(page, username, password, medida,
                                                supplier.get('url_login', ''), supplier.get('url_search', ''))
                elif 'euromais' in supplier_name or 'eurotyre' in supplier_name:
                    result = await scrape_euromais(page, username, password, medida)
                elif 'soledad' in supplier_name:
                    result = await scrape_grupo_soledad(page, username, password, medida)
                elif 'aguesport' in supplier_name:
                    result = await scrape_aguesport(page, username, password, medida)
                elif 'abt' in supplier_name:
                    result = await scrape_abt_tyres(page, username, password, medida)
                elif 'tugapneus' in supplier_name or 'tuga' in supplier_name:
                    result = await scrape_tugapneus(page, username, password, medida)
                elif 'inter-sprint' in supplier_name or 'intersprint' in supplier_name:
                    result = await scrape_inter_sprint(page, username, password, medida)
                elif 'cruzeiro' in supplier_name:
                    result = await scrape_pneus_cruzeiro(page, username, password, medida)
                else:
                    result = {"supplier": supplier['name'], "price": None, "error": "Adapter not implemented"}
                
                result["medida"] = medida
                result["job_id"] = job_id
                results.append(result)
                
                # Save to PostgreSQL - save ALL products with brand/model
                products = result.get('products', [])
                now = datetime.now(timezone.utc)

                if products:
                    # Delete old records for this supplier+medida+brand+model, then insert fresh
                    for prod in products:
                        marca = prod.get('brand', '').upper()
                        modelo = prod.get('model', '')
                        await conn.execute(
                            """
                            DELETE FROM scraped_prices
                            WHERE supplier_name = $1 AND medida = $2
                              AND COALESCE(marca,'') = $3 AND COALESCE(modelo,'') = $4
                            """,
                            supplier['name'], medida, marca, modelo,
                        )
                        await conn.execute(
                            """
                            INSERT INTO scraped_prices
                                (id, supplier_name, supplier_id, medida, marca, modelo, price, scraped_at)
                            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                            """,
                            str(uuid.uuid4()), supplier['name'], supplier_id,
                            medida, marca, modelo, prod.get('price'), now,
                        )
                    print(f"  Saved {len(products)} products with brand/model")
                else:
                    # Fallback: save single price without brand
                    await conn.execute(
                        "DELETE FROM scraped_prices WHERE supplier_name = $1 AND medida = $2 AND marca IS NULL",
                        supplier['name'], medida,
                    )
                    if result.get('price') is not None:
                        await conn.execute(
                            """
                            INSERT INTO scraped_prices
                                (id, supplier_name, supplier_id, medida, price, scraped_at)
                            VALUES ($1,$2,$3,$4,$5,$6)
                            """,
                            str(uuid.uuid4()), supplier['name'], supplier_id,
                            medida, result.get('price'), now,
                        )
                
                if result.get('price'):
                    print(f"  Result: €{result['price']}")
                else:
                    print(f"  Result: {result.get('error', 'No price found')}")
                    
            except Exception as e:
                print(f"  Error scraping {medida}: {e}")
                results.append({"supplier": supplier['name'], "medida": medida, "error": str(e)})
        
        await browser.close()

    await conn.close()
    print(f"Finished scraping {supplier['name']}")
    return results

async def main():
    parser = argparse.ArgumentParser(description='Run tire price scraper')
    parser.add_argument('--supplier', type=str, help='Filter by supplier name')
    parser.add_argument('--medida', type=str, help='Specific tire size (e.g., 2055516)')
    parser.add_argument('--medidas', type=str, help='Comma-separated list of tire sizes')
    
    args = parser.parse_args()
    
    # Default medida for testing
    if args.medida:
        medidas = [args.medida]
    elif args.medidas:
        medidas = [m.strip() for m in args.medidas.split(',')]
    else:
        medidas = ['2055516']  # Default test size
    
    await run_scraper(medidas, args.supplier)

if __name__ == "__main__":
    asyncio.run(main())
