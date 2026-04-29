#!/usr/bin/env python3
"""
Standalone scraper that runs independently and saves results to PostgreSQL.
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
                if 15 < price < 800:
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

        # Login form present if we're still on a login/default page (not yet authenticated)
        if 'login' in current_url.lower() or 'default' in current_url.lower():

            # ASP.NET Login control — try several known ID patterns
            user_selectors = [
                '#ContentPlaceHolder1_ctrlLogin_Login_UserName',
                '#ContentPlaceHolder1_Login1_UserName',
                '#ctl00_ContentPlaceHolder1_Login1_UserName',
                'input[id$="_UserName"]',
                'input[name$="UserName"]',
                'input[autocomplete="username"]',
            ]
            filled_user = False
            for sel in user_selectors:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.fill(username)
                    print(f"  [S. José] Filled username via: {sel}")
                    filled_user = True
                    break
            if not filled_user:
                await page.locator('input[type="text"]').first.fill(username)
                print("  [S. José] Used generic username selector")

            pass_selectors = [
                '#ContentPlaceHolder1_ctrlLogin_Login_Password',
                '#ContentPlaceHolder1_Login1_Password',
                '#ctl00_ContentPlaceHolder1_Login1_Password',
                'input[id$="_Password"]',
                'input[name$="Password"]',
                'input[autocomplete="current-password"]',
            ]
            filled_pass = False
            for sel in pass_selectors:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.fill(password)
                    print(f"  [S. José] Filled password via: {sel}")
                    filled_pass = True
                    break
            if not filled_pass:
                await page.locator('input[type="password"]').first.fill(password)
                print("  [S. José] Used generic password selector")

            # Login button — try specific ID first, then any submit
            btn_selectors = [
                '#ContentPlaceHolder1_ctrlLogin_Login_btnLogin',   # S. José real ID
                '#ContentPlaceHolder1_ctrlLogin_Login_LoginButton', # fallback variant
                '#ContentPlaceHolder1_Login1_LoginButton',
                '#ctl00_ContentPlaceHolder1_Login1_LoginButton',
                'input[id$="_btnLogin"]',
                'input[id$="_LoginButton"]',
                'input[type="submit"]',
                'button[type="submit"]',
            ]
            for btn_sel in btn_selectors:
                btn_loc = page.locator(btn_sel).first
                if await btn_loc.count() > 0:
                    print(f"  [S. José] Clicking login button via: {btn_sel}")
                    await btn_loc.click()
                    break

            await asyncio.sleep(5)
            await page.wait_for_load_state("networkidle")

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
                               url_login: str = "https://b2b.current.gruposoledad.com/login",
                               url_search: str = "https://b2b.current.gruposoledad.com/dashboard/main",
                               skip_login: bool = False) -> dict:
    """Scrape Grupo Soledad B2B portal (SPA at b2b.current.gruposoledad.com).
    skip_login=True reuses an already-authenticated page (session reuse for multiple medidas).
    """
    result = {
        "supplier": "Grupo Soledad",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

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

    url_origin = '/'.join(url_search.split('/')[:3])  # https://b2b.new.gruposoledad.com

    try:
        _scrape_t0 = datetime.now()
        if skip_login:
            print(f"  [Soledad] Skipping login — reusing existing session for {medida}")
        else:
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

            # Fill username — seletores específicos; evitar input[type="text"] genérico
            # que apanharia qualquer campo de texto na página.
            user_field = page.locator(
                'input[name="userId"], input[name="username"], input[name="email"], '
                'input[name="user"], input[type="email"], '
                'input[id*="userId" i], input[id*="user" i], input[id*="email" i], '
                'input[placeholder*="user" i], input[placeholder*="email" i], '
                'input[placeholder*="utilizador" i], input[placeholder*="usuario" i]'
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
                _url_now = page.url
                if await page.locator('input[type="password"]').count() == 0:
                    print(f"  [Soledad] Password field gone after ~{_i * 0.5:.0f}s — url={_url_now}")
                    break
                # Log URL changes during login (angular routing steps)
                if _i % 4 == 0:
                    print(f"  [Soledad] Login wait {_i * 0.5:.0f}s — url={_url_now}")
            else:
                print(f"  [Soledad] Warning: password field still present after 20s — url={page.url}")

            try:
                await page.wait_for_load_state("load", timeout=15000)
            except Exception:
                pass
            await asyncio.sleep(3)

            url_after = page.url
            _save_debug('/tmp/soledad_after_login.html', await page.content())
            print(f"  [Soledad] After login: {url_after}")

            # Log visible error messages on the page
            _login_errors = await page.evaluate('''() => {
                const selectors = ['.alert', '.error', '[class*="error"]', '[class*="invalid"]',
                                   '[class*="danger"]', '[role="alert"]', '.toast', '.notification',
                                   'p.text-danger', 'span.text-danger', '.mat-error'];
                return Array.from(new Set(
                    selectors.flatMap(s => Array.from(document.querySelectorAll(s)))
                )).map(el => el.textContent.trim()).filter(t => t.length > 2 && t.length < 300);
            }''')
            if _login_errors:
                print(f"  [Soledad] Login page errors: {_login_errors}")

            # Verificar sucesso: password ainda visível OU URL é exactamente a mesma da página de login.
            # NOTA: não usar 'login' in url_after — o redirect SSO pós-auth tem /login?params=... na URL
            # mas NÃO é a página de login (é um redirect para domínio diferente).
            login_form_still_visible = await page.locator('input[type="password"]').count() > 0
            still_on_login_page = url_after.rstrip('/') == url_login.rstrip('/')
            if login_form_still_visible or still_on_login_page:
                result["error"] = (
                    f"Login failed — password_visible={login_form_still_visible}, url={url_after}"
                )
                print(f"  [Soledad] {result['error']}")
                return result
            print(f"  [Soledad] Login succeeded")

            # ── SSO handoff: b2b.current → b2b.new ───────────────────────────
            # After login, b2b.current redirects to b2b.new.gruposoledad.com/login?params=TOKEN
            # This SSO token is processed by b2b.new and creates the session there.
            # We must wait for this redirect to complete before navigating anywhere.
            _post_login_url = page.url
            if 'params=' in _post_login_url and '/login' in _post_login_url:
                print(f"  [Soledad] SSO handoff in progress — waiting for dashboard redirect...")
                for _sso_i in range(30):
                    await asyncio.sleep(1)
                    _sso_url = page.url
                    if '/login' not in _sso_url:
                        print(f"  [Soledad] SSO complete after {_sso_i+1}s — {_sso_url}")
                        break
                    if _sso_i % 5 == 0:
                        print(f"  [Soledad] SSO wait {_sso_i}s — {_sso_url}")
                else:
                    print(f"  [Soledad] SSO timeout — still on {page.url}")
                # Session was established on b2b.new — update search URL accordingly
                url_search = 'https://b2b.new.gruposoledad.com/dashboard/main'
                url_origin = 'https://b2b.new.gruposoledad.com'
                print(f"  [Soledad] Search URL updated to b2b.new (SSO domain)")

        # ── Navigate to search page ───────────────────────────────────────────
        # Clear any API responses captured during login — we only want search responses
        api_responses.clear()

        # Navigate to the B2B search dashboard
        _t_nav = datetime.now()
        print(f"  [Soledad] Navigating to: {url_search} (login took {(_t_nav-_scrape_t0).total_seconds():.0f}s)")
        try:
            await page.goto(url_search, wait_until="domcontentloaded", timeout=20000)
        except Exception as nav_e:
            print(f"  [Soledad] Navigation warning: {nav_e}")
        try:
            await page.wait_for_load_state("load", timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(2)  # Angular render

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
        # Portal: b2b.new.gruposoledad.com/dashboard/main
        # Form fields: Medida (id=typeahead-basic-busqueda), Marca dropdown
        # Submit: click red "Pesquisar" button → navigates to dashboard/products/car
        _t_search = datetime.now()
        print(f"  [Soledad] Searching: {medida_norm} (nav took {(_t_search-_t_nav).total_seconds():.0f}s)")

        search_done = False

        # Always (re-)navigate to the search dashboard.
        # Previous code left the browser on a wrong page due to failed URL attempts.
        if page.url.rstrip('/') != url_search.rstrip('/'):
            print(f"  [Soledad] Navigating to search form: {url_search}")
            try:
                await page.goto(url_search, wait_until="domcontentloaded", timeout=15000)
                try:
                    await page.wait_for_load_state("load", timeout=6000)
                except Exception:
                    pass
                await asyncio.sleep(2)
            except Exception as nav_e:
                print(f"  [Soledad] Navigation warning: {nav_e}")

        # Guard: abort if we ended up on login page
        if await page.locator('input[type="password"]').count() > 0:
            print(f"  [Soledad] Login page detected, aborting")
            result["error"] = "Redirected to login before search — session issue"
            _save_debug('/tmp/soledad_results.html', await page.content())
            return result

        # Step 1: Fill Medida — focus via JS then type via keyboard (full Angular event pipeline)
        el_focused = await page.evaluate('''() => {
            const el = document.getElementById("typeahead-basic-busqueda")
                     || document.querySelector("input[placeholder*='Medida']")
                     || document.querySelector("input[placeholder*='2055516']");
            if (!el) return false;
            el.focus();
            el.select();
            return true;
        }''')
        filled = False
        if el_focused:
            try:
                await page.keyboard.type(medida_norm, delay=40)
                await asyncio.sleep(0.3)
                val_in_dom = await page.evaluate(
                    'document.getElementById("typeahead-basic-busqueda")?.value || ""')
                filled = medida_norm in (val_in_dom or '')
                print(f"  [Soledad] keyboard.type fill: dom_val={val_in_dom!r} ok={filled}")
            except Exception as ke:
                print(f"  [Soledad] keyboard.type error: {ke}")

        if not filled:
            # Fallback: native value setter + input/change events
            filled = await page.evaluate('''(term) => {
                const el = document.getElementById("typeahead-basic-busqueda")
                         || document.querySelector("input[placeholder*='Medida']");
                if (!el) return false;
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, "value").set;
                setter.call(el, term);
                el.dispatchEvent(new Event("input", {bubbles: true}));
                el.dispatchEvent(new Event("change", {bubbles: true}));
                return true;
            }''', medida_norm)
            print(f"  [Soledad] evaluate() fill fallback: {filled}")

        await asyncio.sleep(0.3)

        # Step 2: Click "Pesquisar" via evaluate() — also dispatches ngSubmit on the form
        pesquisar_clicked = await page.evaluate('''() => {
            for (const b of document.querySelectorAll("button")) {
                if (b.textContent.trim().toLowerCase().includes("pesquisar")) {
                    b.click();
                    const form = b.closest("form") || document.querySelector("form");
                    if (form) form.dispatchEvent(new Event("submit", {bubbles:true,cancelable:true}));
                    return true;
                }
            }
            const form = document.querySelector("form");
            if (form) { form.dispatchEvent(new Event("submit", {bubbles:true,cancelable:true})); return true; }
            return false;
        }''')
        print(f"  [Soledad] evaluate() button click: {pesquisar_clicked}")

        if not pesquisar_clicked:
            # Fallback: try locator with short timeout
            for btn_sel in ['button:has-text("Pesquisar")', 'button[type="submit"]']:
                try:
                    btn = page.locator(btn_sel).first
                    if await btn.count() == 0:
                        continue
                    await btn.click(timeout=3000, force=True)
                    print(f"  [Soledad] Clicked Pesquisar via locator: {btn_sel}")
                    pesquisar_clicked = True
                    break
                except Exception as be:
                    print(f"  [Soledad] Button error ({btn_sel}): {be}")
                    continue

        # Step 3: Wait for the products page (dashboard/products/car)
        if filled or pesquisar_clicked:
            await asyncio.sleep(2)
            try:
                await page.wait_for_url("**/products/car**", timeout=15000)
                print(f"  [Soledad] Navigated to products page: {page.url}")
            except Exception:
                try:
                    await page.wait_for_url("**/products**", timeout=5000)
                except Exception:
                    pass
            await asyncio.sleep(3)  # Angular needs extra time to render product list

            # Scroll down to trigger lazy-loaded product list (Angular virtual scroll)
            try:
                await page.evaluate("window.scrollTo(0, 600)")
                await asyncio.sleep(2)
                await page.evaluate("window.scrollTo(0, 1200)")
                await asyncio.sleep(2)
            except Exception:
                pass

            products_html = await page.content()
            has_s = medida_slashed.lower() in products_html.lower() or medida_norm in products_html
            has_p = bool(re.search(r'[€£$]\s*\d{2,3}|\d{2,3}[,\.]\d{2}\s*[€£$]', products_html))
            print(f"  [Soledad] Products page: url=.../{page.url.split('/')[-1]} has_size={has_s} has_price={has_p}")
            # Print snippet of products HTML for diagnosis
            _html_snip = products_html.replace('\n', ' ')[:1000]
            print(f"  [Soledad] Products HTML snippet: {_html_snip}")
            _save_debug('/tmp/soledad_results.html', products_html)
            search_done = True
        else:
            print(f"  [Soledad] Could not fill medida or click Pesquisar")

        # Save final page state for debugging
        final_html = await page.content()
        if not search_done:
            _save_debug('/tmp/soledad_results.html', final_html)
            print(f"  [Soledad] Search not completed")

        # ── Extract products ──────────────────────────────────────────────────
        # Brand/model abbreviation tables for Grupo Soledad's description format
        # e.g. "195/65X15 MICH.PCY4 91H" → brand=MICHELIN, model=PRIMACY 4
        _SOL_BRANDS = {
            'MICH': 'MICHELIN',    'CONT': 'CONTINENTAL',  'GY': 'GOODYEAR',
            'GOOD': 'GOODYEAR',    'PIREL': 'PIRELLI',     'PIRE': 'PIRELLI',
            'BS': 'BRIDGESTONE',   'BRID': 'BRIDGESTONE',  'DUN': 'DUNLOP',
            'DUNL': 'DUNLOP',      'HAN': 'HANKOOK',       'HANK': 'HANKOOK',
            'YOKO': 'YOKOHAMA',    'TOYO': 'TOYO',         'NEXEN': 'NEXEN',
            'KUMHO': 'KUMHO',      'FALK': 'FALKEN',       'FALKEN': 'FALKEN',
            'NOK': 'NOKIAN',       'NOKIAN': 'NOKIAN',     'VRED': 'VREDESTEIN',
            'MAXX': 'MAXXIS',      'UNIR': 'UNIROYAL',     'COOP': 'COOPER',
            'SEMP': 'SEMPERIT',    'SEMPERIT': 'SEMPERIT', 'BARUM': 'BARUM',
            'KLEB': 'KLEBER',      'KLEBER': 'KLEBER',     'FULDA': 'FULDA',
            'GISL': 'GISLAVED',    'LINGL': 'LINGLONG',    'GEN': 'GENERAL',
            'SAIL': 'SAILUN',      'WEST': 'WESTLAKE',     'NANK': 'NANKANG',
            'TRIAN': 'TRIANGLE',   'LASSA': 'LASSA',       'SAVA': 'SAVA',
        }
        _SOL_MODELS = {
            # MICHELIN
            'PCY4': 'PRIMACY 4',        'PCY5': 'PRIMACY 5',
            'PCY3': 'PRIMACY 3',        'PCY.ST': 'PRIMACY ST',
            'CROSSC.2': 'CROSSCLIMATE 2', 'CROSSC.+': 'CROSSCLIMATE+',
            'CROSSC+': 'CROSSCLIMATE+', 'CROSSCLIMATE.2': 'CROSSCLIMATE 2',
            'PILOT.SP.4': 'PILOT SPORT 4', 'PILOT.SP.5': 'PILOT SPORT 5',
            'PILOT.SP.4S': 'PILOT SPORT 4S', 'PILOT.SP.3': 'PILOT SPORT 3',
            'PILOT.SP.CUP2': 'PILOT SPORT CUP 2',
            'ALPIN.6': 'ALPIN 6',       'ALPIN.A4': 'ALPIN A4',
            'ALPIN.A3': 'ALPIN A3',
            'LAT.SP.3': 'LATITUDE SPORT 3', 'LAT.SPORT': 'LATITUDE SPORT',
            'LAT.XCLIM': 'LATITUDE X-ICE', 'LAT.ALPIN': 'LATITUDE ALPIN',
            'E.PRIM.4': 'E PRIMACY 4',
            'AGIL.+': 'AGILITY+',       'EN.SAV+': 'ENERGY SAVER+',
            # CONTINENTAL
            'PREMIUMCONTACT.7': 'PREMIUMCONTACT 7', 'PREMIUMCONTACT.6': 'PREMIUMCONTACT 6',
            'SPORTCONTACT.7': 'SPORTCONTACT 7', 'SPORTCONTACT.6': 'SPORTCONTACT 6',
            'ECOCONTACT.6': 'ECOCONTACT 6', 'ALLSEASONS.CONT.3': 'ALLSEASONCONTACT 3',
            'WINTERCONTACT.TS870': 'WINTERCONTACT TS 870',
            # BRIDGESTONE
            'TURANZA.T005': 'TURANZA T005', 'TURANZA.T006': 'TURANZA T006',
            'POTENZA.SPORT': 'POTENZA SPORT', 'BLIZZAK.LM005': 'BLIZZAK LM005',
            # GOODYEAR
            'EFF.GRIP.PERF.2': 'EFFICIENTGRIP PERF 2', 'EFF.GRIP.2': 'EFFICIENTGRIP 2',
            'EAGLE.F1.ASYMM.6': 'EAGLE F1 ASYMMETRIC 6',
            'ULTRA.GRIP.9+': 'ULTRAGRIP 9+',
        }
        # Description regex: optional medida + BRAND.MODEL_CODE + LI+SI
        _sol_desc_re = re.compile(
            r'^(?:\d{3}/\d{2}[Xx]\d{2}\s+)?'  # optional "195/65X15 "
            r'([A-Z]{2,8})\.'                   # brand code like MICH
            r'([A-Z0-9.+]+(?:\s+\w+)?)'         # model code like PCY4 or CROSSC.2
            r'(?:\s+\d{2,3}[A-Z]+(?:\s+XL)?)?$',  # optional LI+SI
            re.IGNORECASE
        )

        def _expand_soledad(brand: str, model: str):
            """Expand Grupo Soledad brand abbreviations and model codes."""
            b = brand.strip().upper()
            m = model.strip()
            # Try to expand known brand abbreviation
            expanded_b = _SOL_BRANDS.get(b, b)
            # If model looks like a description (BRAND.MODEL), parse it
            if not expanded_b or expanded_b == b:
                src = m.upper() if m else b
                hit = _sol_desc_re.match(src)
                if hit:
                    b_code = hit.group(1).upper()
                    m_code = hit.group(2).strip().upper()
                    expanded_b = _SOL_BRANDS.get(b_code, b_code)
                    expanded_m = _SOL_MODELS.get(m_code, m_code.replace('.', ' ').replace('_', ' '))
                    return expanded_b, expanded_m
            # Expand known model code
            expanded_m = _SOL_MODELS.get(m.upper(), m)
            return expanded_b, expanded_m

        # Primary: parse intercepted JSON API responses
        products = []

        # Price/brand/model field names — case-insensitive search covers Grupo Soledad
        # AR_ prefix pattern (AR_PRECIO, AR_MARCA, AR_DESCRIPCION) used in Spanish B2B systems.
        _PRICE_SUBSTRINGS = ('pvp', 'preco', 'precio', 'price', 'valor', 'coste',
                             'tarifa', 'importe', 'unitprice', 'saleprice', 'netprice')
        _BRAND_SUBSTRINGS = ('marca', 'brand', 'manufacturer', 'fabricante', 'marque')
        _MODEL_SUBSTRINGS = ('descripcion', 'descricao', 'description', 'modelo',
                             'model', 'nome', 'designation', 'denominacion', 'referencia')

        _logged_keys: set = set()  # avoid printing the same key set twice

        def _parse_api_json(data, depth=0):
            """Recursively search JSON for objects that look like tire products."""
            if depth > 6:
                return
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        # Case-insensitive price field search (covers AR_PRECIO, PRECIO, pvp, etc.)
                        item_lc = {k.lower(): (k, v) for k, v in item.items()}

                        # Log the key set once per unique response to aid diagnostics
                        keys_sig = frozenset(item_lc.keys())
                        if keys_sig not in _logged_keys and len(item_lc) > 3:
                            _logged_keys.add(keys_sig)
                            print(f"  [Soledad] API item keys (depth={depth}): "
                                  f"{sorted(item_lc.keys())[:20]}")

                        price_val = None
                        used_pk = None
                        for lk, (orig_k, v) in item_lc.items():
                            if not any(sub in lk for sub in _PRICE_SUBSTRINGS):
                                continue
                            if v is None:
                                continue
                            if isinstance(v, dict):
                                v = v.get('value') or v.get('formattedValue') or v.get('amount') or 0
                            try:
                                price_val = float(str(v).replace(',', '.').replace('€', '').strip())
                                if price_val < 10 or price_val > 2000:
                                    price_val = None
                                else:
                                    used_pk = orig_k
                            except Exception:
                                pass
                            if price_val:
                                break

                        if not price_val:
                            _parse_api_json(item, depth + 1)
                            continue

                        brand_val = ''
                        for lk, (orig_k, v) in item_lc.items():
                            if any(sub in lk for sub in _BRAND_SUBSTRINGS) and v:
                                brand_val = str(v).upper()
                                break

                        model_val = ''
                        for lk, (orig_k, v) in item_lc.items():
                            if any(sub in lk for sub in _MODEL_SUBSTRINGS) and v:
                                model_val = str(v)
                                break

                        print(f"  [Soledad] API product: brand={brand_val!r} "
                              f"model={model_val[:40]!r} price={price_val} (field={used_pk})")
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
        # Preview the 3 largest responses (most likely to contain product data)
        for _r in sorted(api_responses, key=lambda x: len(x['body']), reverse=True)[:3]:
            print(f"  [Soledad] API preview ({_r['url'].split('?')[0][-40:]}): {_r['body'][:300]}")

        for resp in api_responses:
            try:
                data = json.loads(resp['body'])
                before = len(products)
                _parse_api_json(data)
                if len(products) > before:
                    print(f"  [Soledad] +{len(products)-before} products from {resp['url'].split('?')[0][-50:]}")
            except Exception as _parse_err:
                print(f"  [Soledad] Warning: falha ao parsear resposta API "
                      f"{resp['url'].split('?')[0][-50:]}: {_parse_err}")

        if products:
            print(f"  [Soledad] {len(products)} products from API interception")
        else:
            # Secondary: DOM extraction
            print(f"  [Soledad] No API products — trying DOM extraction")
            products = await page.evaluate(r'''() => {
                const products = [];
                // Full names + Grupo Soledad abbreviations (MICH.PCY4, CONT.ECO6, etc.)
                const BRANDS = /MICHELIN|MICH(?=\.)|BRIDGESTONE|BS(?=\.)|CONTINENTAL|CONT(?=\.)|PIRELLI|PIREL(?=\.)|GOODYEAR|GY(?=\.)|DUNLOP|DUN(?=\.)|HANKOOK|HAN(?=\.)|YOKOHAMA|YOKO(?=\.)|FIRESTONE|KUMHO|TOYO|NEXEN|FALKEN|FALK(?=\.)|NOKIAN|NOK(?=\.)|VREDESTEIN|VRED(?=\.)|MAXXIS|MAXX(?=\.)|GENERAL|GEN(?=\.)|UNIROYAL|UNIR(?=\.)|SEMPERIT|SEMP(?=\.)|BARUM|LASSA|SAVA|KLEBER|KLEB(?=\.)|FULDA|GISLAVED|GISL(?=\.)|COOPER|COOP(?=\.)|NANKANG|NANK(?=\.)|LINGLONG|LINGL(?=\.)|TRIANGLE|TRIAN(?=\.)|SAILUN|SAIL(?=\.)|WESTLAKE|WEST(?=\.)/i;

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
                        // Accept abbreviated brand format (MICH.PCY4) even if BRANDS regex didn't match
                        if(brand || /[A-Z]{2,8}\.[A-Z0-9]/.test(model.toUpperCase())) products.push({brand,model,price});
                    }
                }

                // Deduplicate keeping lowest price — chave usa model completo para não fundir variantes
                const seen={};
                for(const p of products){
                    const k=(p.brand||"")+"|"+(p.model||"").trim();
                    if(!seen[k]||p.price<seen[k].price) seen[k]=p;
                }
                return Object.values(seen);
            }''')
            if products:
                print(f"  [Soledad] {len(products)} products from DOM")

        # Post-process: expand Grupo Soledad brand abbreviations and model codes
        # e.g. brand="MICH" → "MICHELIN", model="PCY4" → "PRIMACY 4"
        # Also handles full description in model field: "195/65X15 MICH.PCY4 91H"
        for p in products:
            b, m = _expand_soledad(p.get('brand', ''), p.get('model', ''))
            if b:
                p['brand'] = b
            if m:
                p['model'] = m

        if products:
            print(f"  [Soledad] {len(products)} products after brand expansion")
            for p in products[:5]:
                print(f"    brand={p.get('brand')!r} model={p.get('model','')[:40]!r} price={p.get('price')}")
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

async def scrape_inter_sprint(page, username: str, password: str, medida: str,
                               marca: str = '', modelo: str = '', indice: str = '') -> dict:
    """Scrape Inter-Sprint B2B portal (customers.inter-sprint.nl).

    O portal usa HTTP Basic Auth — o contexto Playwright DEVE ter http_credentials
    definidas antes de chamar esta função (ver run_scraper loop).

    Após Basic Auth, se existir form login HTML, preenche-o.

    Pesquisa progressiva:
      Nível 1: Codigo do Artigo (medida) + Marca (dropdown) + LI/SI (indice)
      Nível 2: Codigo do Artigo + Marca (sem indice)
      Nível 3: Código do Artigo only
    """
    result = {
        "supplier": "InterSprint",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    medida_norm = normalize_medida(medida)   # ex: 2055516
    # Formato alternativo: 205/55R16 (para portais que não aceitam dígitos só)
    _m = re.match(r'^(\d{3})(\d{2})(\d{2})$', medida_norm)
    medida_fmt = f"{_m.group(1)}/{_m.group(2)}R{_m.group(3)}" if _m else medida_norm
    marca_upper = (marca or '').strip().upper()

    try:
        _search_url = "https://customers.inter-sprint.nl/#ecommerce"
        print(f"  [InterSprint] Navegando para {_search_url} (Basic Auth via contexto)")
        await page.goto(_search_url, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(2)

        # Guardar HTML para debug independentemente do resultado
        try:
            with open('/tmp/intersprint_pre_login.html', 'w', encoding='utf-8') as _f:
                _f.write(await page.content())
        except Exception:
            pass

        # Verificar se Basic Auth falhou (401)
        _title = await page.title()
        if '401' in _title or 'unauthorized' in _title.lower():
            result["error"] = f"HTTP Basic Auth falhou — verificar credenciais (título: {_title})"
            return result

        print(f"  [InterSprint] Após Basic Auth: {page.url} (título: {_title})")

        # Caso o portal tenha também um formulário HTML de login (além de Basic Auth)
        if await page.locator('input[type="password"]').count() > 0:
            print(f"  [InterSprint] Form login HTML detectado — a preencher")
            user_input = page.locator(
                'input[name="username"], input[name="user"], input[name="login"], '
                'input[id*="user" i], input[id*="name" i], input[type="text"]'
            ).first
            pass_input = page.locator('input[type="password"]').first
            if await user_input.count() > 0:
                await user_input.clear()
                await user_input.type(username, delay=60)
            await pass_input.clear()
            await pass_input.type(password, delay=60)
            await asyncio.sleep(0.5)
            submit_btn = page.locator(
                'button[type="submit"], input[type="submit"], '
                'button:has-text("Login"), button:has-text("Inloggen"), '
                'button:has-text("Entrar"), button:has-text("OK")'
            ).first
            if await submit_btn.count() > 0:
                await submit_btn.click()
            else:
                await pass_input.press("Enter")
            await asyncio.sleep(5)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await asyncio.sleep(2)
            print(f"  [InterSprint] Após form login: {page.url}")

        _work_page = page

        # ── Detectar frame principal (portal usa <frameset>) ──────────────
        # Todo o conteúdo (pesquisa, resultados) está dentro do frame "mainFrame"
        # com src="/scripts/cgirpc32.dll/...". Usar o frame para locators.
        await asyncio.sleep(3)
        _ctx = page  # fallback: usar página se não houver frame
        _named_frame = page.frame(name="mainFrame")
        if _named_frame:
            _ctx = _named_frame
            print(f"  [InterSprint] Frame 'mainFrame' detectado: {_named_frame.url}")
        else:
            for _fr in page.frames:
                if _fr.url and ('cgirpc32' in _fr.url or _fr is not page.main_frame):
                    _ctx = _fr
                    print(f"  [InterSprint] Frame detectado: {_fr.url}")
                    break

        _all_frames = [(f.name, f.url) for f in page.frames]
        print(f"  [InterSprint] Todos os frames: {_all_frames}")
        print(f"  [InterSprint] _ctx tipo: {'Frame' if _ctx is not page else 'Page'}, URL: {_ctx.url}")

        # Guardar conteúdo do frame para debug (/api/scraper/debug-html?supplier=intersprint&file=frame)
        try:
            with open('/tmp/intersprint_frame.html', 'w', encoding='utf-8') as _f:
                _f.write(await _ctx.content())
        except Exception:
            pass

        # Registar todos os inputs do frame para diagnóstico
        try:
            _all_inputs = await _ctx.evaluate('''() =>
                Array.from(document.querySelectorAll("input,select,textarea")).map(el => ({
                    tag: el.tagName, type: el.type, name: el.name,
                    id: el.id, placeholder: el.placeholder,
                    value: el.value.substring(0, 40)
                }))
            ''')
            print(f"  [InterSprint] Inputs no frame ({len(_all_inputs)}): {_all_inputs[:15]}")
        except Exception as _e:
            print(f"  [InterSprint] Não foi possível listar inputs: {_e}")

        # Clicar 'Procura por pneus' se necessário
        procura_link = _ctx.locator(
            'a:has-text("Procura por pneus"), button:has-text("Procura por pneus"), '
            'a:has-text("procura por pneus"), span:has-text("Procura por pneus"), '
            'a:has-text("Tyre search"), a:has-text("Zoek band"), '
            'a:has-text("Banden zoeken"), a:has-text("Bandenzoeker"), '
            'a:has-text("Banden"), a:has-text("Tyres"), '
            'a[href*="pneus"], a[href*="tyres"], a[href*="band"]'
        ).first
        if await procura_link.count() > 0:
            await procura_link.click()
            await asyncio.sleep(3)
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            print(f"  [InterSprint] Clicado 'Procura por pneus'")
            # Guardar HTML após navegação para página de pesquisa
            try:
                with open('/tmp/intersprint_after_nav.html', 'w', encoding='utf-8') as _f:
                    _f.write(await _ctx.content())
            except Exception:
                pass
        else:
            print(f"  [InterSprint] Link 'Procura por pneus' não encontrado — usar snelzoek")

        # ── Helpers de pesquisa ────────────────────────────────────────────
        async def _limpar_campos():
            """Limpar campos de pesquisa (entre tentativas)."""
            for sel in [
                'form[name="f"] input[name="artkode"]',
                'input[name="lisi"]',
            ]:
                el = _ctx.locator(sel).first
                if await el.count() > 0:
                    await el.clear()
            # Reset Marca dropdown para primeira opção
            marca_select = _ctx.locator(
                'select[name="merk"], select[id*="marca" i], select[name*="marca" i], '
                'select[id*="brand" i], select[name*="brand" i]'
            ).first
            if await marca_select.count() > 0:
                try:
                    await marca_select.select_option(index=0)
                except Exception:
                    pass

        async def _has_results() -> bool:
            """Verificar se a pesquisa devolveu resultados.

            InterSprint não usa € nas células de preço — formato:
            &nbsp;   125,58 &nbsp;  (cabeçalho da coluna é "EUR", sem símbolo €).
            """
            content = await _ctx.content()
            return bool(re.search(
                r'€\s*\d+[,.]\d{2}|\d+[,.]\d{2}\s*€|&nbsp;\s*\d+,\d{2}\s*&nbsp;',
                content
            ))

        async def _do_search(use_marca: bool, use_indice: bool, medida_str: str = None) -> bool:
            """Executar pesquisa. Retorna True se há resultados."""
            _val = medida_str or medida_norm
            # Selector exclusivo para o formulário principal (form[name="f"]).
            # NÃO usar input[name="artkode"] genérico — há 2 inputs com esse
            # nome na página: um no snelzoek (canto sup-dir) e outro no form f.
            # Playwright .first selecciona por DOM order, apanhando o snelzoek
            # primeiro. Isso preenche o campo errado e o submit devolve a mesma
            # página (artkode vazio no form f).
            artigo_input = _ctx.locator('form[name="f"] input[name="artkode"]')
            if await artigo_input.count() == 0:
                # Fallback: input com class form2 (mesmo campo, sem contexto form)
                artigo_input = _ctx.locator('input[name="artkode"][class="form2"]')
            if await artigo_input.count() == 0:
                print(f"  [InterSprint] Campo artkode (form f) não encontrado")
                return False
            await artigo_input.first.clear()
            await artigo_input.first.fill(_val)
            artigo_input = artigo_input.first

            # Marca dropdown
            if use_marca and marca_upper:
                marca_select = _ctx.locator(
                    'select[name="merk"], select[id*="marca" i], select[name*="marca" i], '
                    'select[id*="brand" i], select[name*="brand" i]'
                ).first
                if await marca_select.count() > 0:
                    try:
                        options = await marca_select.evaluate(
                            'el => Array.from(el.options).map(o => ({value: o.value, text: o.text}))'
                        )
                        matched = next(
                            (o['value'] for o in options if marca_upper in o['text'].upper()),
                            None
                        )
                        if matched is not None:
                            await marca_select.select_option(value=str(matched))
                            print(f"  [InterSprint] Marca '{marca_upper}' seleccionada")
                        else:
                            print(f"  [InterSprint] Marca '{marca_upper}' não encontrada no dropdown")
                    except Exception as _e:
                        print(f"  [InterSprint] Erro dropdown: {_e}")

            # LI/SI
            if use_indice and indice:
                lisi_input = _ctx.locator(
                    'input[name="lisi"], input[placeholder*="LI" i], input[id*="lisi" i]'
                ).first
                if await lisi_input.count() > 0:
                    await lisi_input.clear()
                    await lisi_input.fill(indice)

            # Clicar "Procura"
            procura_btn = _ctx.locator(
                'button:has-text("Procura"), input[value*="Procura" i], '
                'button:has-text("Search"), input[value*="Search" i], '
                'button:has-text("Zoeken"), input[value*="Zoeken" i], '
                'button:has-text("Zoek"), input[value*="Zoek" i], '
                'button[type="submit"], input[type="submit"]'
            ).first
            if await procura_btn.count() > 0:
                await procura_btn.click()
            else:
                await artigo_input.press("Enter")

            await asyncio.sleep(5)
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            await asyncio.sleep(1)
            has = await _has_results()
            # Guardar HTML sempre (mesmo sem resultados) para diagnóstico
            try:
                _dbg = await _ctx.content()
                with open('/tmp/intersprint_search_page.html', 'w', encoding='utf-8') as _f:
                    _f.write(_dbg)
                print(f"  [InterSprint] _do_search: frame URL={_ctx.url} has_results={has} html_len={len(_dbg)}")
            except Exception as _e:
                print(f"  [InterSprint] _do_search debug save failed: {_e}")
            return has

        print(f"  [InterSprint] Pesquisa: medida_norm={medida_norm} medida_fmt={medida_fmt} marca={marca_upper} indice={indice}")

        found = False
        # Nível 1: medida + marca + indice
        if marca_upper and indice:
            if await _do_search(use_marca=True, use_indice=True):
                print(f"  [InterSprint] Nível 1 (medida+marca+indice) com resultados")
                found = True

        # Nível 2: medida + marca
        if not found and marca_upper:
            await _limpar_campos()
            if await _do_search(use_marca=True, use_indice=False):
                print(f"  [InterSprint] Nível 2 (medida+marca) com resultados")
                found = True

        # Nível 3: só medida (formato dígitos)
        if not found:
            await _limpar_campos()
            if await _do_search(use_marca=False, use_indice=False):
                print(f"  [InterSprint] Nível 3 (só medida dígitos) com resultados")
                found = True

        # Nível 4: só medida (formato 205/55R16) — portais que não aceitam só dígitos
        if not found and medida_fmt != medida_norm:
            await _limpar_campos()
            if await _do_search(use_marca=False, use_indice=False, medida_str=medida_fmt):
                print(f"  [InterSprint] Nível 4 (só medida formatada {medida_fmt}) com resultados")
                found = True

        if not found:
            result["error"] = "Sem resultados para esta medida"
            return result

        # ── Extrair produtos do HTML ──────────────────────────────────────
        content = await _ctx.content()

        try:
            # Compatível com /api/scraper/debug-html?supplier=intersprint&file=search_page
            with open('/tmp/intersprint_search_page.html', 'w', encoding='utf-8') as _f:
                _f.write(content)
        except Exception:
            pass

        products = _parse_intersprint_html(content, marca_upper)

        if products:
            result["products"] = products
            result["price"] = min(p['price'] for p in products)
            result["all_prices"] = sorted(p['price'] for p in products)[:10]
            print(f"  [InterSprint] {len(products)} produtos, melhor €{result['price']}")
            for p in products[:5]:
                print(f"    {p['brand']} {p['medida']} {p.get('indice','')} {p.get('model','')} → €{p['price']}")
        else:
            prices = extract_prices(content)
            if prices:
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
                print(f"  [InterSprint] Fallback: {len(prices)} preços, melhor €{result['price']}")
            else:
                result["error"] = "Produtos não encontrados"

    except Exception as e:
        result["error"] = str(e)
        print(f"  [InterSprint] Error: {e}")

    return result


def _parse_intersprint_html(html: str, search_brand: str = '') -> list:
    """Parse HTML da página de resultados InterSprint.

    Estrutura da tabela InterSprint (colunas):
      Marca | Descricao | Estacao | 3PMSF | LI/SI | Rotulo | Foto | E/EU | Stock | EUR | ...

    Descricao format: "{size} {[A-Z]?R}{rim} TL {LI/SI} {brand_abbr} {model}"
    Exemplo: "205/55 VR16 TL 94V SUNNY NP226 XL"

    FIXES v5:
    - Decode HTML entities (&nbsp; → space, &#47; → /) BEFORE running any regex,
      because InterSprint separates column content with &nbsp; inside <td>.
    - medida_re now allows optional spaces around the speed-letter and R.
    - Context tracking: when a row has size info but no price (rowspan header),
      the next row(s) with price inherit that context.
    - debug print for rows with price but no medida after decode.
    search_brand: fallback quando a célula da marca está vazia.
    """
    import re as _re

    products: list = []
    seen: set = set()
    _no_medida_dbg: list = []  # DEBUG: primeiras linhas com preço mas sem medida

    price_re = _re.compile(
        r'€\s*(\d+[,.]\d{2})|(\d+[,.]\d{2})\s*€|&nbsp;\s*(\d+[,.]\d{2})\s*&nbsp;',
        _re.IGNORECASE
    )
    # medida_re aceita espaços opcionais ao redor da letra de construção e entre R e jante
    # Suporta: "205/55 VR16", "205/55R16", "205/55 R16", "205/55 ZR18", "205/55 R 16"
    medida_re = _re.compile(r'(\d{3}/\d{2})\s*[A-Z]?\s*R\s*(\d{2})\b', _re.IGNORECASE)
    # indice_re aceita espaço opcional entre número e letra (ex: "94 V" ou "94V")
    indice_re = _re.compile(r'\b(\d{2,3}\s*[A-Z]{1,2}(?:\s*XL)?)\b')
    tag_re    = _re.compile(r'<[^>]+>')
    row_re    = _re.compile(r'<tr[^>]*>(.*?)</tr>', _re.IGNORECASE | _re.DOTALL)

    # Contexto do último row que tinha informação de medida/marca
    # (para tabelas com rowspan onde o preço fica em linhas separadas)
    _ctx_brand  = ''
    _ctx_medida = ''
    _ctx_indice = ''
    _ctx_model  = ''

    def _decode_entities(text: str) -> str:
        """Decodifica entidades HTML comuns antes do matching de regex."""
        text = text.replace('&#47;', '/').replace('&amp;', '&')
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>')
        text = _re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
        text = _re.sub(r'&\w+;', ' ', text)  # outras entidades → espaço
        return _re.sub(r'\s+', ' ', text).strip()

    def _extract_model(row_text: str, after_pos: int, brand: str) -> str:
        rem = row_text[after_pos:]
        rem = price_re.sub('', rem)
        # Após decode, preços ficam como "89.90" sem € — remover explicitamente
        rem = _re.sub(r'\b\d+[,.]\d{2}\b', ' ', rem)
        rem = _re.sub(r'\bTL\b|\bTW\b', ' ', rem, flags=_re.IGNORECASE)
        rem = _re.sub(r'\b\d{2,3}\s*[A-Z]{1,2}(?:\s*XL)?\b', ' ', rem)
        rem = _re.sub(r'\b\d+\b', ' ', rem)
        rem = _re.sub(r'\s+', ' ', rem).strip()
        parts = rem.upper().split()
        if parts:
            first = parts[0]
            if (first == brand
                    or brand.startswith(first)
                    or (len(first) <= 3 and first.isalpha())):
                parts = parts[1:]
        return ' '.join(parts)[:60].strip()

    for row_m in row_re.finditer(html):
        # 1. Strip tags → raw text
        raw = _re.sub(r'\s+', ' ', tag_re.sub(' ', row_m.group(1))).strip()
        if len(raw) < 5:
            continue

        # 2. Decode HTML entities (&nbsp; é separador de colunas no portal)
        # Nota: linhas de preço isoladas ficam com < 10 chars após decode (ex: "93,16")
        # por isso não filtrar pelo comprimento do decoded text — só rejeitar verdadeiramente vazias.
        row_text = _decode_entities(raw)
        if not row_text:
            continue

        # 3. Tentar extrair medida DESTA linha (atualiza contexto se encontrar)
        medida_m = medida_re.search(row_text)
        if medida_m:
            g1 = medida_m.group(1).replace(' ', '')   # normaliza "205 / 55" → "205/55"
            _ctx_medida = f"{g1}R{medida_m.group(2)}".upper()
            _ctx_brand  = row_text[:medida_m.start()].strip().upper()
            if not _ctx_brand:
                _ctx_brand = search_brand.upper() if search_brand else 'UNKNOWN'
            # Índice: procurar a partir do início da medida
            im = indice_re.search(row_text[medida_m.start():])
            _ctx_indice = im.group(1).upper().replace(' ', '') if im else ''
            _ctx_model  = _extract_model(row_text, medida_m.end(), _ctx_brand)
            if not _ctx_model and _ctx_indice:
                _ctx_model = _ctx_indice

        # 4. Verificar se esta linha tem preço (usar raw: &nbsp; ainda não foi decodificado)
        price_m = price_re.search(raw)
        if not price_m:
            continue
        try:
            price = float(
                (price_m.group(1) or price_m.group(2) or price_m.group(3)).replace(',', '.')
            )
        except ValueError:
            continue
        if not (15 < price < 800):
            continue

        # 5. Usar medida/marca do contexto (desta linha ou da última linha com medida)
        medida_val = _ctx_medida
        brand_val  = _ctx_brand if _ctx_brand else (search_brand.upper() or 'UNKNOWN')
        indice_val = _ctx_indice
        model_val  = _ctx_model

        # DEBUG: registar linhas com preço mas sem medida (máx 3)
        if not medida_val and len(_no_medida_dbg) < 3:
            _no_medida_dbg.append(row_text[:300])

        if not model_val and indice_val:
            model_val = indice_val

        key = f"{brand_val}|{medida_val}|{indice_val}|{price}"
        if key not in seen:
            seen.add(key)
            products.append({
                'brand':  brand_val,
                'medida': medida_val,
                'indice': indice_val,
                'model':  model_val,
                'price':  price,
            })

    print(f"  [InterSprint] _parse_intersprint_html: {len(products)} produtos")
    if _no_medida_dbg:
        print(f"  [InterSprint] DEBUG linhas-sem-medida: {_no_medida_dbg}")
    return products


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
                "url_search": d.get("url_search", ""),
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

async def run_scraper(medidas: list, supplier_filter: str = None, items_list: list = None):
    """Main scraper function"""
    print(f"Starting scraper at {datetime.now()}")
    print(f"Medidas to scrape: {medidas}")

    # Build per-medida brand list so brand-aware suppliers (TugaPneus) can do specific searches
    # items_list = [{"medida": "20555R16", "marca": "MICHELIN", "modelo": "primacy 5"}, ...]
    medida_items: dict = {}  # {medida: [{marca, modelo}, ...]}
    for item in (items_list or []):
        m = item.get('medida', '')
        if m:
            medida_items.setdefault(m, []).append({
                'marca': (item.get('marca') or '').strip().upper(),
                'modelo': (item.get('modelo') or '').strip(),
            })

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
        is_tuga = 'tugapneus' in supplier_name or 'tuga' in supplier_name
        is_brand_aware = is_tuga or 'inter-sprint' in supplier_name or 'intersprint' in supplier_name

        # For TugaPneus: build (medida, marca, modelo) targets for brand-specific searches
        # For all others: use generic (medida, '', '') targets
        if is_brand_aware and medida_items:
            targets: list = []
            seen_targets: set = set()
            for medida in medidas:
                brand_items = medida_items.get(medida, [])
                if brand_items:
                    for bi in brand_items:
                        key = (medida, bi['marca'], bi['modelo'])
                        if key not in seen_targets:
                            seen_targets.add(key)
                            targets.append(key)
                else:
                    key = (medida, '', '')
                    if key not in seen_targets:
                        seen_targets.add(key)
                        targets.append(key)
            print(f"  [{supplier['name']}] {len(targets)} pesquisas marca+medida: {targets[:5]}")
        else:
            targets = [(m, '', '') for m in medidas]

        # ── Grupo Soledad: sessão única para todas as medidas (evita login repetido) ──
        if 'soledad' in supplier_name:
            _sol_ctx_kwargs = dict(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='pt-PT',
            )
            async with async_playwright() as _p_sol:
                _sol_browser = await _p_sol.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                _sol_ctx = await _sol_browser.new_context(**_sol_ctx_kwargs)
                # Nota: cada medida usa uma página nova no mesmo contexto.
                # O contexto partilha cookies (sessão autenticada), mas a página é fresca.
                # Isto evita que um timeout/cancel numa medida corrompa o estado do browser.
                _sol_first = True
                for medida, marca, modelo in targets:
                    _sol_page = await _sol_ctx.new_page()
                    await _sol_page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
                    try:
                        _is_first = _sol_first
                        _sol_first = False  # set before await so exceptions don't leave it True
                        _t0 = datetime.now()
                        print(f"  [Soledad] Início medida {medida} às {_t0.strftime('%H:%M:%S')} (skip_login={not _is_first})")
                        # Login em b2b.current (credenciais funcionam aqui).
                        # b2b.current faz SSO para b2b.new/login?params=TOKEN após auth.
                        # A sessão é criada no b2b.new — pesquisa usa b2b.new.
                        _sol_url_login = 'https://b2b.current.gruposoledad.com/login'
                        _sol_url_search = 'https://b2b.new.gruposoledad.com/dashboard/main'
                        result = await asyncio.wait_for(
                            scrape_grupo_soledad(
                                _sol_page, supplier['username'], supplier['password'], medida,
                                _sol_url_login,
                                _sol_url_search,
                                skip_login=(not _is_first),
                            ),
                            timeout=150,  # 2.5 min max por medida → 5 medidas = 12.5 min max
                        )
                        _dt = (datetime.now() - _t0).total_seconds()
                        print(f"  [Soledad] Fim medida {medida}: {_dt:.0f}s, price={result.get('price')}, products={len(result.get('products',[]))}")
                        result["medida"] = medida
                        results.append(result)
                        # Save to PostgreSQL
                        products = result.get('products', [])
                        now = datetime.now(timezone.utc)
                        conn_save = await _pg_connect()
                        try:
                            if products:
                                marcas_encontradas = {prod.get('brand', '').upper() for prod in products}
                                for m_brand in marcas_encontradas:
                                    await conn_save.execute(
                                        "DELETE FROM scraped_prices WHERE supplier_name=$1 AND medida=$2 AND COALESCE(marca,'')=$3",
                                        supplier['name'], medida, m_brand,
                                    )
                                for prod in products:
                                    await conn_save.execute(
                                        "INSERT INTO scraped_prices (id,supplier_name,medida,marca,modelo,price,load_index,scraped_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                                        str(uuid.uuid4()), supplier['name'], medida,
                                        prod.get('brand', '').upper(), prod.get('model', ''),
                                        prod.get('price'), prod.get('indice') or '', datetime.now(timezone.utc),
                                    )
                                print(f"  {medida}: saved {len(products)} products")
                            else:
                                await conn_save.execute(
                                    "DELETE FROM scraped_prices WHERE supplier_name=$1 AND medida=$2 AND marca IS NULL",
                                    supplier['name'], medida,
                                )
                                if result.get('price') is not None:
                                    await conn_save.execute(
                                        "INSERT INTO scraped_prices (id,supplier_name,medida,price,scraped_at) VALUES ($1,$2,$3,$4,$5)",
                                        str(uuid.uuid4()), supplier['name'], medida, result['price'], datetime.now(timezone.utc),
                                    )
                                print(f"  {medida}: €{result.get('price')} (no brand data)")
                        finally:
                            await conn_save.close()
                        print(f"  {medida}: best price €{result.get('price')}" if result.get('price') else f"  {medida}: {result.get('error','No price found')}")
                    except asyncio.TimeoutError:
                        _dt = (datetime.now() - _t0).total_seconds()
                        print(f"  [Soledad] TIMEOUT medida {medida} após {_dt:.0f}s — a avançar para próxima medida")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": "Timeout 150s"})
                    except Exception as _e_sol:
                        print(f"  Error (Soledad {medida}): {_e_sol}")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": str(_e_sol)})
                    finally:
                        try:
                            await _sol_page.close()
                        except Exception:
                            pass
                await _sol_browser.close()
            continue  # Skip the generic per-medida loop below

        for medida, marca, modelo in targets:
            # Create completely fresh browser for each medida
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )

                # InterSprint usa HTTP Basic Auth — definir credenciais no contexto
                _ctx_kwargs = dict(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='pt-PT',
                )
                if 'inter-sprint' in supplier_name or 'intersprint' in supplier_name:
                    _ctx_kwargs['http_credentials'] = {
                        'username': supplier['username'],
                        'password': supplier['password'],
                    }
                context = await browser.new_context(**_ctx_kwargs)

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
                    elif 'aguesport' in supplier_name:
                        result = await scrape_aguesport(page, supplier['username'], supplier['password'], medida)
                    elif 'abt' in supplier_name:
                        result = await scrape_abt_tyres(page, supplier['username'], supplier['password'], medida)
                    elif is_tuga:
                        result = await scrape_tugapneus(page, supplier['username'], supplier['password'], medida, marca, modelo)
                    elif 'inter-sprint' in supplier_name or 'intersprint' in supplier_name:
                        result = await scrape_inter_sprint(page, supplier['username'], supplier['password'], medida, marca, modelo)
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
                            # Apagar TODOS os registos antigos deste fornecedor+medida+marca
                            # antes de inserir os novos — garante que modelos fora de stock
                            # não ficam no BD após um re-scrape.
                            marcas_encontradas = {prod.get('brand', '').upper() for prod in products}
                            for m_brand in marcas_encontradas:
                                await conn_save.execute(
                                    """
                                    DELETE FROM scraped_prices
                                    WHERE supplier_name = $1 AND medida = $2
                                      AND COALESCE(marca,'') = $3
                                    """,
                                    supplier['name'], medida, m_brand,
                                )
                            for prod in products:
                                prod_marca = prod.get('brand', '').upper()
                                prod_modelo = prod.get('model', '')
                                prod_indice = prod.get('indice') or ''
                                await conn_save.execute(
                                    """
                                    INSERT INTO scraped_prices
                                        (id, supplier_name, medida, marca, modelo, price, load_index, scraped_at)
                                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                                    """,
                                    str(uuid.uuid4()), supplier['name'], medida,
                                    prod_marca, prod_modelo, prod.get('price'), prod_indice, now,
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
    parser.add_argument('--items-json', type=str, default='[]',
                        help='JSON list of {medida, marca, modelo} for brand-specific searches')

    args = parser.parse_args()

    # Default medida for testing
    if args.medida:
        medidas = [args.medida]
    elif args.medidas:
        medidas = [m.strip() for m in args.medidas.split(',')]
    else:
        medidas = ['2055516']  # Default test size

    items_list = json.loads(args.items_json or '[]')
    await run_scraper(medidas, args.supplier, items_list=items_list)

if __name__ == "__main__":
    asyncio.run(main())
