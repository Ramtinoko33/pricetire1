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

        # Check if login succeeded (URL should have changed away from default/login)
        login_failed = (
            'login' in url_after_login.lower() or 'default' in url_after_login.lower()
        )
        if login_failed:
            # Could be a login error message on the page
            error_texts = ['inválido', 'invalido', 'incorrect', 'wrong', 'failed',
                           'erro', 'error', 'senha', 'password']
            page_lower = after_login_html.lower()
            login_error_msg = next((t for t in error_texts if t in page_lower), None)
            print(f"  [S. José] WARNING: still on login/default page after login attempt. "
                  f"Possible error hint: {login_error_msg}")
            # Try to detect if there's actually a login error vs just a slow redirect
            # Wait a bit more and check again
            await asyncio.sleep(3)
            url_after_login = page.url
            if 'login' in url_after_login.lower() or 'default' in url_after_login.lower():
                result["error"] = (
                    f"Login may have failed — still on {url_after_login} after submit. "
                    f"Check credentials or HTML at /tmp/sjose_after_login.html"
                )
                # Still try to continue in case it's an unusual redirect flow
                print(f"  [S. José] Continuing despite possible login failure...")

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
            # Guard: if navigating to the search page redirected back to login,
            # don't fill the search box (we'd be filling into the username field)
            if 'login' in search_page_url.lower() or 'default' in search_page_url.lower():
                result["error"] = (
                    f"Navigating to {url_search} redirected to login page ({search_page_url}). "
                    "Login appears to have failed — check credentials and HTML at /tmp/sjose_after_login.html"
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

async def scrape_grupo_soledad(page, username: str, password: str, medida: str) -> dict:
    """Scrape Grupo Soledad B2B"""
    result = {
        "supplier": "Grupo Soledad",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        print("  [Grupo Soledad] Logging in...")
        await page.goto("https://www.gruposoledad.com/b2b/current/login", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        # Fill login form
        username_input = page.locator('input[name="username"], input[name="email"], input[type="text"]').first
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
        print(f"  [Grupo Soledad] Searching for: {medida_norm}")
        
        # Try common search patterns
        search_input = page.locator('input[type="search"], input[placeholder*="buscar"], input[placeholder*="pesq"], input[name*="search"], #search, .search-input').first
        if await search_input.count() > 0:
            await search_input.fill(medida_norm)
            await search_input.press('Enter')
            await asyncio.sleep(5)
        else:
            # Navigate to catalog/products page
            catalog_link = page.locator('a:has-text("Catálogo"), a:has-text("Productos"), a:has-text("Pneus"), a:has-text("Neumáticos")').first
            if await catalog_link.count() > 0:
                await catalog_link.click()
                await asyncio.sleep(3)
        
        # Extract products
        products = await page.evaluate('''() => {
            const products = [];
            // Try common product container selectors
            const items = document.querySelectorAll('.product, .item, .producto, [class*="product"], [class*="item"], tr[data-id]');
            
            items.forEach(item => {
                const brandEl = item.querySelector('.brand, .marca, [class*="brand"], [class*="marca"]');
                const modelEl = item.querySelector('.model, .modelo, .name, .nombre, [class*="model"], [class*="name"]');
                const priceEl = item.querySelector('.price, .precio, .preco, [class*="price"], [class*="precio"]');
                
                let brand = brandEl ? brandEl.textContent.trim() : '';
                let model = modelEl ? modelEl.textContent.trim() : '';
                let priceText = priceEl ? priceEl.textContent.trim() : '';
                
                // Extract price
                const priceMatch = priceText.match(/(\d+[,\.]\d{2})/);
                if (priceMatch) {
                    const price = parseFloat(priceMatch[1].replace(',', '.'));
                    if (price > 15 && price < 500) {
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
            print(f"  [Grupo Soledad] Found {len(products)} products")
        else:
            content = await page.content()
            prices = extract_prices(content)
            if prices:
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
                print(f"  [Grupo Soledad] Fallback: Found {len(prices)} prices")
            else:
                result["error"] = "No products found"
                
    except Exception as e:
        result["error"] = str(e)
        print(f"  [Grupo Soledad] Error: {e}")
    
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

async def scrape_tugapneus(page, username: str, password: str, medida: str) -> dict:
    """Scrape TugaPneus"""
    result = {
        "supplier": "TugaPneus",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        print("  [TugaPneus] Logging in...")
        await page.goto("http://tugapneus.pt/login", wait_until="networkidle", timeout=60000)
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
        print(f"  [TugaPneus] Searching for: {medida_norm}")
        
        search_input = page.locator('input[type="search"], input[placeholder*="pesq"], input[name*="search"], #search').first
        if await search_input.count() > 0:
            await search_input.fill(medida_norm)
            await search_input.press('Enter')
            await asyncio.sleep(5)
        
        # Extract products
        content = await page.content()
        prices = extract_prices(content)
        
        if prices:
            result["price"] = min(prices)
            result["all_prices"] = sorted(prices)[:10]
            print(f"  [TugaPneus] Found {len(prices)} prices, best: €{result['price']}")
        else:
            result["error"] = "No products found"
                
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
                        result = await scrape_grupo_soledad(page, supplier['username'], supplier['password'], medida)
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
