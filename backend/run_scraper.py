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
import aiohttp

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
                    # Extract load/speed index
                    _li = str(tyre.get('loadIndex') or tyre.get('li') or '').strip()
                    _si = str(tyre.get('speedIndex') or tyre.get('si') or '').strip().upper()
                    if _li.isdigit() and _si and len(_si) == 1 and _si.isalpha():
                        load_index = f"{_li}{_si}"
                    elif _si and len(_si) == 1 and _si.isalpha():
                        load_index = _si
                    else:
                        load_index = ''

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
                        key = f"{brand}|{model}|{load_index}"
                        if key not in product_map or price < product_map[key][0]:
                            product_map[key] = (price, load_index)

                # Convert map back to list
                products = []
                for key, (price, load_index) in product_map.items():
                    parts = key.split('|', 2)
                    products.append({
                        'brand': parts[0],
                        'model': parts[1],
                        'price': price,
                        'load_index': parts[2] if len(parts) > 2 else load_index,
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
                        const remaining = parts.slice(2).join(' ');

                        const idxMatch = remaining.match(/\b(\d{2,3}[A-Z]{1,2}(?:\/\d{2,3}[A-Z]{1,2})?(?:\s+XL)?)\b/i);
                        const loadIndex = idxMatch ? idxMatch[1].trim().toUpperCase() : '';
                        let model = (idxMatch ? remaining.slice(0, idxMatch.index) : remaining).trim();
                        model = model.replace(/\b(DOT\d*|TL|TT|RFT|MO|AO|VOL|BMW|ROF|SSR|FP)\b/gi, '').trim();

                        const price = parseFloat(precoStr.replace(',', '.'));

                        if (brand && price > 15 && price < 500) {
                            products.push({
                                brand: brand.toUpperCase(),
                                model: model,
                                load_index: loadIndex,
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
                    for p in products[:3]:
                      print(f"    - {p['brand']} {p.get('model','')} [{p.get('load_index','VAZIO')}]: €{p['price']}")
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
        await page.goto("https://dispnal.pt/home/homepage", wait_until="domcontentloaded", timeout=60000)
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

    Selectores confirmados via HTML real (2026-05):
      - Campo medida : #ContentPlaceHolder1_txtSize  (formato "1955015" sem barras)
      - Botão pesquisa: #lkbtnSearch  (<a> com __doPostBack — NÃO é input[type=submit])
      - Resultados    : #ContentPlaceHolder1_UpdatePanelResults  (UpdatePanel AJAX)
      - Campo descrição: #ContentPlaceHolder1_txtDescription  (filtro extra opcional)
    """
    result = {
        "supplier": "S. José Pneus",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

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
        await page.goto(url_login, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)
        _save_debug('/tmp/sjose_pre_login.html', await page.content())

        # Detectar se o formulário de login está presente (utilizador não autenticado)
        # O campo de username confirmado via HTML real: #ContentPlaceHolder1_ctrlLogin_Login_UserName
        login_field = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_UserName').first
        if await login_field.count() > 0:
            print(f"  [S. José] Login form found — filling credentials")
            await login_field.fill(username)

            pwd_field = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_Password').first
            if await pwd_field.count() > 0:
                await pwd_field.fill(password)
            else:
                await page.locator('input[type="password"]').first.fill(password)

            # Botão de login confirmado: #ContentPlaceHolder1_ctrlLogin_Login_btnLogin
            btn = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_btnLogin').first
            if await btn.count() > 0:
                await btn.click()
            else:
                # Fallback para outros padrões ASP.NET
                for sel in ['input[id$="_LoginButton"]', 'input[type="submit"]', 'button[type="submit"]']:
                    b = page.locator(sel).first
                    if await b.count() > 0:
                        await b.click()
                        break

            await asyncio.sleep(5)
            await page.wait_for_load_state("networkidle")
        else:
            print(f"  [S. José] No login form found — assuming already authenticated")

        url_after = page.url
        print(f"  [S. José] URL after login step: {url_after}")
        _save_debug('/tmp/sjose_after_login.html', await page.content())

        # Verificar falha de login: formulário ainda visível
        if await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_UserName').count() > 0:
            result["error"] = f"Login failed — credentials rejected ({url_after})"
            print(f"  [S. José] {result['error']}")
            return result

        # ── Pesquisa ─────────────────────────────────────────────────────────
        # O campo aceita formato normalizado: "1956515" (sem barras, sem R)
        medida_norm = normalize_medida(medida)
        print(f"  [S. José] Navigating to search: {url_search}")
        try:
            await page.goto(url_search, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            await page.goto(url_search, wait_until="commit", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(2)

        search_page_url = page.url
        print(f"  [S. José] Search page URL: {search_page_url}")

        if 'login' in search_page_url.lower():
            result["error"] = f"Session expired — redirected to login from articles page"
            return result

        # Campo medida confirmado: #ContentPlaceHolder1_txtSize
        size_field = page.locator('#ContentPlaceHolder1_txtSize').first
        if await size_field.count() == 0:
            result["error"] = "Campo #ContentPlaceHolder1_txtSize não encontrado na página de pesquisa"
            _save_debug('/tmp/sjose_search_page.html', await page.content())
            return result

        await size_field.fill(medida_norm)
        print(f"  [S. José] Filled size field with: {medida_norm!r}")

        # Botão pesquisar confirmado: #lkbtnSearch (âncora com __doPostBack — NÃO é input[submit])
        search_btn = page.locator('#lkbtnSearch').first
        if await search_btn.count() > 0:
            await search_btn.click()
            print(f"  [S. José] Clicked #lkbtnSearch")
        else:
            # Fallback: pressionar Enter no campo
            await size_field.press('Enter')
            print(f"  [S. José] Submitted via Enter (lkbtnSearch not found)")

        # Aguardar o UpdatePanel AJAX atualizar
        await asyncio.sleep(4)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        content = await page.content()
        _save_debug('/tmp/sjose_results.html', content)
        print(f"  [S. José] Results page loaded (content length: {len(content)})")

        # ── Extracção de produtos da tabela GridView ──────────────────────────
        # O S. José tem UMA coluna "Descrição" com formato:
        #   "BRIDGESTONE 215/55R18 95H TURANZA T005A"
        #   "YOKOHAMA 215/55R18 99V GEOLANDAR CV G058 XL"
        # Estrutura: MARCA  MEDIDA  ÍNDICE  MODELO  [sufixos]
        # "desm" = desmontado — removido do modelo
        # A coluna de preço chama-se "PR. COMPRA" (contém "compra")
        _SJOSE_EXTRACT_JS = '''() => {
            const products = [];

            const panel = document.getElementById('ContentPlaceHolder1_UpdatePanelResults');
            const root = panel || document;

            function parseDesc(txt) {
                // Remove "desm" (desmontado) e normaliza espaços
                txt = txt.replace(/\\bdesm\\b/gi, '').replace(/\\s+/g, ' ').trim();
                if (!txt) return { brand: '', model: '' };

                // A célula Descrição pode conter texto duplicado:
                //   "P7 CINTURATO (P7C2) XL PIRELLI 215/55R18 99V P7 CINTURATO (P7C2) XL"
                // (parte visível + tooltip/hidden com a descrição completa)
                // Fix: usar a medida como âncora posicional.
                //   - MARCA  = última palavra ANTES da medida
                //   - MODELO = tudo DEPOIS do índice de carga (99V, 95H, ...)
                const medidaRe = /\\d{3}\\/\\d{2}[RrBb]\\d{2}/;
                const medidaMatch = txt.match(medidaRe);
                if (!medidaMatch) {
                    // Sem medida: primeiro token = marca, resto = modelo
                    const parts = txt.split(/\\s+/);
                    return { brand: parts[0].toUpperCase(), model: parts.slice(1).join(' ').trim(), loadIndex: '' };
                }

                // Última palavra antes da medida = marca
                const beforeMedida = txt.slice(0, medidaMatch.index).trim();
                const beforeParts  = beforeMedida.split(/\\s+/).filter(p => p);
                const brand = (beforeParts[beforeParts.length - 1] || '').toUpperCase();

                // Após a medida: extrair índice de carga (ex: 99V, 95H, 91T, 94W XL), resto = modelo
                const afterMedida = txt.slice(medidaMatch.index + medidaMatch[0].length).trim();
                const afterParts  = afterMedida.split(/\\s+/).filter(p => p);
                let loadIndex = '';
                const idxStart = (afterParts.length > 0 && /^\\d{2,3}[A-Za-z]{1,3}$/.test(afterParts[0])) ? 1 : 0;
                if (idxStart === 1) loadIndex = afterParts[0];
                const model = afterParts.slice(idxStart).join(' ').trim();

                return { brand, model, loadIndex };
            }

            for (const table of root.querySelectorAll("table")) {
                const rows = table.querySelectorAll("tr");
                if (rows.length < 2) continue;

                // Detectar colunas pelo cabeçalho
                let descCol = -1, priceCol = -1;
                const headerCells = rows[0].querySelectorAll("th, td");
                headerCells.forEach((h, i) => {
                    const t = h.textContent.trim().toLowerCase();
                    if (/descri/.test(t))                              descCol = i;
                    else if (/compra|pre[çc]o|valor|pvp|unit/.test(t)) priceCol = i;
                });

                // Marcas conhecidas para fallback quando cabeçalho não é encontrado
                const KNOWN_BRANDS = /^(MICHELIN|CONTINENTAL|PIRELLI|BRIDGESTONE|GOODYEAR|DUNLOP|HANKOOK|YOKOHAMA|FALKEN|TOYO|KUMHO|NOKIAN|UNIROYAL|KLEBER|SAVA|BARUM|MAXXIS|NEXEN|COOPER|NANKANG|SEMPERIT|FIRESTONE|BFGOODRICH|LAUFENN|ATLAS|ARIVO|IMPERIAL|SUNWIDE|LANVIGATOR|ROTALLA|INFINITY|SAILUN|WINDFORCE|GOODRIDE|DOUBLESTAR|WANLI|HIFLY|COMFORSER|TRIANGLE|SPORTIVA|RIKEN|RADAR|EVENT|AMTEL|AUTOGREEN)$/i;

                for (let i = 1; i < rows.length; i++) {
                    const cells = rows[i].querySelectorAll("td");
                    if (cells.length < 2) continue;

                    let brand = "", model = "", loadIndex = "", price = null;

                    if (descCol >= 0 && descCol < cells.length) {
                        // Estrutura confirmada: <a style="visibility:hidden;display:none;">TEXT</a>
                        //                      <span id="...lblDescription_N" style="visibility:visible;">TEXT</span>
                        // textContent concatena ambos → texto duplicado. Usar só o span.
                        const spanEl = cells[descCol].querySelector('span[id*="lblDescription"]');
                        const rawTxt = spanEl ? spanEl.textContent.trim()
                                              : cells[descCol].textContent.trim();
                        const parsed = parseDesc(rawTxt);
                        brand = parsed.brand;
                        model = parsed.model;
                        loadIndex = parsed.loadIndex || '';
                    } else {
                        // Fallback: varrer células à procura de marca conhecida
                        for (const cell of cells) {
                            const spanEl = cell.querySelector('span[id*="lblDescription"]');
                            const txt = spanEl ? spanEl.textContent.trim()
                                               : cell.textContent.trim();
                            if (txt.split(/\\s+/).length >= 2 && KNOWN_BRANDS.test(txt.split(/\\s+/)[0])) {
                                const parsed = parseDesc(txt);
                                brand = parsed.brand;
                                model = parsed.model;
                                loadIndex = parsed.loadIndex || '';
                                break;
                            }
                        }
                    }

                    // Preço da coluna PR. COMPRA
                    if (priceCol >= 0 && priceCol < cells.length) {
                        const m = cells[priceCol].textContent.match(/(\\d+[,\\.]\\d{2})/);
                        if (m) price = parseFloat(m[1].replace(",", "."));
                    }

                    // Fallback preço: varrer todas as células
                    if (!price) {
                        for (const cell of cells) {
                            const m = cell.textContent.replace(/\\s/g,'').match(/^€?(\\d+[,\\.]\\d{2})€?$/);
                            if (m) {
                                const p = parseFloat(m[1].replace(",", "."));
                                if (p > 15 && p < 500) { price = p; break; }
                            }
                        }
                    }

                    if (brand && price && price > 15 && price < 500)
                        products.push({ brand, model, load_index: loadIndex, price });
                }

                if (products.length > 0) break;
            }
            return products;
        }'''

        products = await page.evaluate(_SJOSE_EXTRACT_JS)
        print(f"  [S. José] Página 1: {len(products)} produtos")

        # ── Paginação: loop por todas as páginas via btn_Next ─────────────────
        import re as _re_sj
        _pager_loc = page.locator('#ContentPlaceHolder1_lblPager')
        _pager_text = (await _pager_loc.text_content()) if await _pager_loc.count() > 0 else ''
        _pm = _re_sj.search(r'(\d+)\s+de\s+(\d+)', _pager_text or '')
        _current_page = int(_pm.group(1)) if _pm else 1
        _total_pages  = int(_pm.group(2)) if _pm else 1
        print(f"  [S. José] Paginador: {_pager_text!r} → página {_current_page} de {_total_pages}")

        _MAX_PAGES_SJ = 15
        while _current_page < _total_pages and _current_page < _MAX_PAGES_SJ:
            _next_btn = page.locator('#ContentPlaceHolder1_btn_Next')
            if await _next_btn.count() == 0:
                print(f"  [S. José] Botão próxima página não encontrado — parando")
                break
            await _next_btn.click()
            try:
                await page.wait_for_load_state('networkidle', timeout=15000)
            except Exception:
                await asyncio.sleep(2)
            await asyncio.sleep(1)

            _page_prods = await page.evaluate(_SJOSE_EXTRACT_JS)
            products.extend(_page_prods)

            _pager_text = (await _pager_loc.text_content()) if await _pager_loc.count() > 0 else ''
            _pm = _re_sj.search(r'(\d+)\s+de\s+(\d+)', _pager_text or '')
            _current_page = int(_pm.group(1)) if _pm else (_current_page + 1)
            print(f"  [S. José] Página {_current_page}/{_total_pages}: {len(_page_prods)} produtos")

        print(f"  [S. José] Total: {len(products)} produtos ({_current_page} páginas)")

        if products:
            # Deduplicar por marca+modelo+índice de carga mantendo preço mais baixo.
            # O índice (ex: 95H vs 99V) distingue produtos com preços diferentes.
            discarded = []
            seen = {}
            for p in products:
                load_idx = p.get('load_index', '') or ''
                key = f"{p.get('brand','')}|{p.get('model','')}|{load_idx}"
                if key not in seen or p['price'] < seen[key]['price']:
                    seen[key] = p
                else:
                    discarded.append(p)

            for d in discarded[:10]:
                print(f"  [SJ-DESCARTADO] brand={d.get('brand')!r} "
                      f"model={d.get('model')!r} price={d.get('price')} "
                      f"load_index={d.get('load_index')!r}")

            products = list(seen.values())

            result["products"] = products
            prices_list = [p['price'] for p in products]
            result["price"] = min(prices_list)
            result["all_prices"] = sorted(prices_list)[:10]
            print(f"  [S. José] {len(products)} produtos únicos. Melhor: €{result['price']}")
            for p in sorted(products, key=lambda x: x['price'])[:5]:
                print(f"    - {p.get('brand','-')} {p.get('model','-')}: €{p['price']}")
        else:
            # Fallback: regex de preços no HTML bruto
            prices_list = extract_prices(content)
            if prices_list:
                result["price"] = min(prices_list)
                result["all_prices"] = sorted(prices_list)[:10]
                print(f"  [S. José] Fallback regex: {len(prices_list)} preços, melhor: €{result['price']}")
            else:
                result["error"] = "Nenhum produto encontrado — ver /tmp/sjose_results.html"
                print(f"  [S. José] {result['error']}")

    except Exception as e:
        result["error"] = str(e)
        print(f"  [S. José] Error: {e}")

    return result

async def scrape_euromais(page, username: str, password: str, medida: str) -> dict:
    """Scrape Euromais/Eurotyre"""
    result = {"supplier": "euromais", "price": None, "error": None, "timestamp": datetime.now(timezone.utc).isoformat()}
    
    try:
        print("  [Euromais] Logging in...")
        await page.goto("https://www.eurotyre.pt/", wait_until="domcontentloaded", timeout=60000)
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

    # ── Intercept API responses (primary method for Angular SPAs) ────────────
    # Captures ALL restBusinessDelegate.aspx responses regardless of content-type,
    # plus any other JSON response. This avoids missing product data that may be
    # returned with a non-standard content-type from the ASP.NET backend.
    api_responses = []

    async def _capture_api_response(response):
        try:
            if response.status != 200:
                return
            url = response.url
            ct = response.headers.get('content-type') or ''
            is_delegate = 'restBusinessDelegate' in url
            is_json = 'json' in ct
            if not is_delegate and not is_json:
                return
            body = await response.text()
            if len(body) > 80:
                api_responses.append({'url': url, 'body': body})
                print(f"  [Soledad] API: {url.split('?')[0][-60:]} ({len(body)}b) ct={ct[:25]!r}")
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
            #
            # Three observed cases after login:
            #  A) URL is b2b.new/login?params=TOKEN — SSO in progress (wait for it)
            #  B) URL is b2b.new/dashboard/* — SSO already completed during sleep(3)
            #  C) URL is b2b.current/* — SSO hasn't triggered yet (wait for it)
            _post_login_url = page.url
            if 'params=' in _post_login_url and '/login' in _post_login_url:
                # Case A: SSO token in URL — wait for b2b.new to process it
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
                url_search = 'https://b2b.new.gruposoledad.com/dashboard/main'
                url_origin = 'https://b2b.new.gruposoledad.com'
                print(f"  [Soledad] Search URL updated to b2b.new (SSO domain)")
            elif 'b2b.new' in _post_login_url and '/login' not in _post_login_url:
                # Case B: already on b2b.new dashboard — SSO completed during sleep
                url_search = 'https://b2b.new.gruposoledad.com/dashboard/main'
                url_origin = 'https://b2b.new.gruposoledad.com'
                print(f"  [Soledad] Already on b2b.new after login — SSO complete: {_post_login_url}")
            else:
                # Case C: still on b2b.current — SSO hasn't triggered yet.
                # Wait up to 25s for the page to navigate to b2b.new.
                print(f"  [Soledad] Waiting for SSO redirect from {_post_login_url}...")
                try:
                    await page.wait_for_url('**/b2b.new/**', timeout=25000)
                    _url_now = page.url
                    url_search = 'https://b2b.new.gruposoledad.com/dashboard/main'
                    url_origin = 'https://b2b.new.gruposoledad.com'
                    print(f"  [Soledad] SSO redirect detected: {_url_now}")
                    if 'params=' in _url_now and '/login' in _url_now:
                        for _sso_proc in range(20):
                            await asyncio.sleep(1)
                            if '/login' not in page.url:
                                print(f"  [Soledad] SSO token processed after {_sso_proc+1}s")
                                break
                except Exception:
                    # SSO never happened — proceed anyway, session may still work
                    url_search = 'https://b2b.new.gruposoledad.com/dashboard/main'
                    url_origin = 'https://b2b.new.gruposoledad.com'
                    print(f"  [Soledad] No SSO redirect after 25s — proceeding to b2b.new")

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
        # Aguardar que o Angular renderize o formulário de pesquisa (typeahead input).
        # Para medidas com skip_login=True a página é nova e o Angular precisa de mais tempo
        # do que o simples wait_for_load_state("load").
        _ta_sel = '#typeahead-basic-busqueda, input[placeholder*="Medida" i], input[id*="busqueda" i]'
        try:
            await page.wait_for_selector(_ta_sel, state='visible', timeout=12000)
            print(f"  [Soledad] Typeahead input visible")
        except Exception:
            # Não encontrou em 12s — esperar mais 3s e continuar na mesma
            await asyncio.sleep(3)
            print(f"  [Soledad] Typeahead input timeout — continuing anyway")

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

        # Limpar respostas stale capturadas durante inicialização Angular (localStorage auto-load).
        # O Angular SPA pode disparar automaticamente a pesquisa anterior ao navegar para url_search.
        # Só queremos respostas da pesquisa actual, não da pesquisa anterior.
        api_responses.clear()

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
            await asyncio.sleep(2)  # Angular needs extra time to render product list

            # Scroll to trigger lazy-loaded product list.
            # Angular CDK virtual scroll uses a specific container — scroll it directly,
            # not just window, otherwise virtual scroll items may never render.
            try:
                await page.evaluate("""() => {
                    // Try Angular CDK virtual scroll viewport first, then generic containers
                    const sel = [
                        '.cdk-virtual-scroll-viewport',
                        'app-car-products', 'app-product-list', 'app-products',
                        '[class*="product-list"]', '[class*="products-container"]',
                        'main', 'app-layout-main-search'
                    ];
                    let scroller = null;
                    for (const s of sel) {
                        const el = document.querySelector(s);
                        if (el && el.scrollHeight > el.clientHeight) { scroller = el; break; }
                    }
                    if (scroller) { scroller.scrollTop = 600; }
                    window.scrollTo(0, 600);
                }""")
                await asyncio.sleep(1)
                await page.evaluate("""() => {
                    const sel = ['.cdk-virtual-scroll-viewport','app-car-products','app-product-list','main'];
                    for (const s of sel) {
                        const el = document.querySelector(s);
                        if (el && el.scrollHeight > el.clientHeight) { el.scrollTop = 1200; break; }
                    }
                    window.scrollTo(0, 1200);
                }""")
                await asyncio.sleep(1)
                await page.evaluate("window.scrollTo(0, 2000)")
                await asyncio.sleep(1)
            except Exception:
                pass

            # Wait up to 10s for a 'restBusinessDelegate' response that looks like products
            # (larger than 1KB and contains 'PRECIO' or 'price' in the body, indicating real data)
            print(f"  [Soledad] Waiting for product data API response...")
            for _pw in range(10):
                await asyncio.sleep(0.5)
                _found_products_api = any(
                    len(r['body']) > 1000
                    and ('PRECIO' in r['body'].upper() or '"price"' in r['body'].lower()
                         or '"valor"' in r['body'].lower())
                    and 'restBusinessDelegate' in r['url']
                    for r in api_responses
                )
                if _found_products_api:
                    print(f"  [Soledad] Product API response detected after {_pw*0.5:.1f}s extra wait")
                    break
            else:
                print(f"  [Soledad] No product price API response found after 10s — using DOM")

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
        # NOTE: 'valor' and 'importe' intentionally excluded — too generic:
        #   VALOR appears in filter dropdowns, IMPORTE_SIGUIENTE/CONSEGUIDO in promotions.
        # Soledad API price fields — ordered by priority (most specific first).
        # PRECIOMOSTRARBUSQUEDA = preço de venda ao cliente na pesquisa (campo confirmado).
        # PRECIOMOSTRARPEDIDO   = preço de venda ao cliente no pedido.
        # PRECIOCONDESCUENTO    = preço com desconto aplicado.
        # PRECIOSINDESCUENTO    = preço sem desconto (bruto).
        # AR_PVR = Precio de Venta al Público — NÃO usar (é o PVP, não o preço de custo).
        # Campos ordenados por prioridade: PRECIOMOSTRARBUSQUEDA é o preço de custo confirmado.
        _PRICE_SUBSTRINGS = ('preciomostrarbusqueda', 'preciomostrarpedido',
                             'preciocondescuento', 'preciosindescuento', 'prepre',
                             'pvp', 'preco', 'precio', 'price', 'coste',
                             'tarifa', 'unitprice', 'saleprice', 'netprice', 'preciouni',
                             'precouni', 'pvpfinal', 'pvpnet')
        # Soledad API uses AR_MARCA for brand and AR_MODELO for model
        _BRAND_SUBSTRINGS = ('ar_marca', 'marca', 'brand', 'manufacturer', 'fabricante', 'marque')
        _MODEL_SUBSTRINGS = ('ar_modelo', 'descripcion', 'descricao', 'description', 'modelo',
                             'model', 'nome', 'designation', 'denominacion', 'referencia')
        # Soledad API uses AR_CARGA (load number e.g. 91) and AR_VELOCIDAD (speed letter e.g. H)
        # Use endswith matching to avoid false positives from field names containing 'ic' etc.
        _IC_FIELD_SUFFIXES = ('_carga', '_ic', '_li', '_loadindex', '_load_index',
                              '_indcarga', '_indicecarga')
        _CV_FIELD_SUFFIXES = ('_velocidad', '_cv', '_si', '_velocidade', '_speedindex',
                              '_speed_index', '_indvel')

        _logged_keys: set = set()  # avoid printing the same key set twice
        import re as _re_idx

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
                                if price_val < 15 or price_val > 2000:
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
                                brand_val = str(v).strip().upper()  # strip fixed-width padding
                                break

                        if not brand_val:
                            # No brand field → not a tire product (promotions, filters, etc.)
                            _parse_api_json(item, depth + 1)
                            continue

                        model_val = ''
                        for lk, (orig_k, v) in item_lc.items():
                            if any(sub in lk for sub in _MODEL_SUBSTRINGS) and v:
                                model_val = str(v).strip()  # strip fixed-width padding
                                break

                        # Extract load/speed index using suffix matching only (avoids false positives
                        # from field names like 'clasificacion_orden' that contain 'ic' as substring)
                        # AR_CARGA='91' + AR_VELOCIDAD='V' → indice='91V'
                        ic_val = cv_val = ''
                        for lk, (orig_k, v) in item_lc.items():
                            if any(lk == suf.lstrip('_') or lk.endswith(suf)
                                   for suf in _IC_FIELD_SUFFIXES) and v is not None:
                                _s = str(v).strip()
                                if _s.isdigit():
                                    ic_val = _s
                                    break  # only break on success
                        for lk, (orig_k, v) in item_lc.items():
                            if any(lk == suf.lstrip('_') or lk.endswith(suf)
                                   for suf in _CV_FIELD_SUFFIXES) and v is not None:
                                _s = str(v).strip().upper()
                                if len(_s) == 1 and _s.isalpha():
                                    cv_val = _s
                                    break  # only break on success
                        indice_val = (ic_val + cv_val).strip()
                        # Second load/speed pair (109T/107T) — e.g. AR_CARGA2 + AR_VELOCIDAD2
                        ic2_val = cv2_val = ''
                        _IC2_SUFFIXES = ('_carga2', '_ic2', '_li2', '_loadindex2', '_indcarga2')
                        _CV2_SUFFIXES = ('_velocidad2', '_cv2', '_si2', '_speedindex2', '_indvel2')
                        for lk, (orig_k, v) in item_lc.items():
                            if any(lk == s.lstrip('_') or lk.endswith(s)
                                   for s in _IC2_SUFFIXES) and v is not None:
                                _s = str(v).strip()
                                if _s.isdigit():
                                    ic2_val = _s
                                    break
                        for lk, (orig_k, v) in item_lc.items():
                            if any(lk == s.lstrip('_') or lk.endswith(s)
                                   for s in _CV2_SUFFIXES) and v is not None:
                                _s = str(v).strip().upper()
                                if len(_s) == 1 and _s.isalpha():
                                    cv2_val = _s
                                    break
                        indice2 = (ic2_val + cv2_val).strip()
                        if indice2 and indice2 != indice_val:
                            indice_val = f"{indice_val}/{indice2}"
                        # Detect run-together dual index in AR_NOMBRE (e.g. "109T107T")
                        if indice_val and '/' not in indice_val:
                            _nombre_val = str(item_lc.get('ar_nombre', ('', ''))[1] or '')
                            _md = _re_idx.search(
                                r'\b(\d{2,3}[A-Z]{1,2})(\d{2,3}[A-Z]{1,2})\b',
                                _nombre_val.upper()
                            )
                            if _md:
                                indice_val = f"{_md.group(1)}/{_md.group(2)}"
                        # Fallback: regex on model text e.g. "PRIMACY 4 91H XL" or "109T107T"
                        if not indice_val and model_val:
                            _m = _re_idx.search(
                                r'\b(\d{2,3}[A-Z]{1,2}(?:[/ ]\d{2,3}[A-Z]{1,2})?(?:\s+XL)?)\b',
                                model_val.upper()
                            )
                            if _m:
                                indice_val = _m.group(1).strip()

                        print(f"  [Soledad] API product: brand={brand_val!r} "
                              f"model={model_val[:40]!r} price={price_val} "
                              f"ic={ic_val!r} cv={cv_val!r} indice={indice_val!r} "
                              f"(field={used_pk})")
                        products.append({'brand': brand_val, 'model': model_val,
                                         'price': price_val, 'indice': indice_val,
                                         'load_index': indice_val})
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

        # Filtrar respostas para usar apenas as que contêm produtos da medida pesquisada.
        # O campo AR_NOMBRE tem formato "215/55X18 ..." — o scraper pode capturar respostas
        # de stock geral (outras medidas) que chegam antes/depois da pesquisa actual.
        def _response_has_medida(body: str) -> bool:
            if len(medida_norm) < 7:
                return True  # medida fora do padrão — não filtrar
            ancho  = medida_norm[:3]          # "215"
            perfil = medida_norm[3:5]         # "55"
            llanta = medida_norm[5:7]         # "18"
            # Soledad usa "X" em vez de "R" no campo AR_NOMBRE: "215/55X18"
            medida_x = f"{ancho}/{perfil}X{llanta}"   # "215/55X18"
            medida_r = f"{ancho}/{perfil}R{llanta}"   # "215/55R18" (fallback)
            body_lower = body.lower()
            return medida_x.lower() in body_lower or medida_r.lower() in body_lower

        _relevant = [r for r in api_responses if _response_has_medida(r['body'])]
        _responses_to_parse = _relevant if _relevant else api_responses
        if not _relevant:
            print(f"  [Soledad] Aviso: nenhuma resposta contém medida {medida_norm} — usando todas ({len(api_responses)})")
        else:
            print(f"  [Soledad] Filtro medida: {len(_relevant)}/{len(api_responses)} respostas relevantes para {medida_norm}")

        for resp in _responses_to_parse:
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
            # Print first 3 products with all fields so we can verify index extraction
            for _p in products[:3]:
                print(f"  [Soledad] DIAG product: {_p}")

        # Print first raw item from the largest response — shows ALL field names+values
        # Placed AFTER products so it appears at the end of the log (visible in Railway)
        _diag_printed = False
        for _r in sorted(api_responses, key=lambda x: len(x['body']), reverse=True)[:3]:
            try:
                _d = json.loads(_r['body'])
                def _first_list_item(obj, d=0):
                    if d > 4: return None
                    if isinstance(obj, list):
                        for _x in obj:
                            if isinstance(_x, dict) and len(_x) > 3:
                                return _x
                    if isinstance(obj, dict):
                        for _v in obj.values():
                            _r2 = _first_list_item(_v, d+1)
                            if _r2: return _r2
                    return None
                _sample = _first_list_item(_d)
                if _sample and not _diag_printed:
                    print(f"  [Soledad] DIAG first item from {_r['url'].split('?')[0][-50:]}:")
                    for _k, _v in list(_sample.items())[:30]:
                        print(f"    {_k}={_v!r}")
                    _diag_printed = True
            except Exception:
                pass

        if not products:
            # Secondary: DOM extraction (only when API interception found nothing)
            print(f"  [Soledad] No API products — trying DOM extraction")
            products = await page.evaluate(r'''() => {
                const products = [];
                // Full names + Grupo Soledad abbreviations (MICH.PCY4, CONT.ECO6, etc.)
                const BRANDS = /MICHELIN|MICH(?=\.)|BRIDGESTONE|BS(?=\.)|CONTINENTAL|CONT(?=\.)|PIRELLI|PIREL(?=\.)|GOODYEAR|GY(?=\.)|DUNLOP|DUN(?=\.)|HANKOOK|HAN(?=\.)|YOKOHAMA|YOKO(?=\.)|FIRESTONE|KUMHO|TOYO|NEXEN|FALKEN|FALK(?=\.)|NOKIAN|NOK(?=\.)|VREDESTEIN|VRED(?=\.)|MAXXIS|MAXX(?=\.)|GENERAL|GEN(?=\.)|UNIROYAL|UNIR(?=\.)|SEMPERIT|SEMP(?=\.)|BARUM|LASSA|SAVA|KLEBER|KLEB(?=\.)|FULDA|GISLAVED|GISL(?=\.)|COOPER|COOP(?=\.)|NANKANG|NANK(?=\.)|LINGLONG|LINGL(?=\.)|TRIANGLE|TRIAN(?=\.)|SAILUN|SAIL(?=\.)|WESTLAKE|WEST(?=\.)/i;

                // Elements to exclude — navigation bar, promotions sidebar, saldo/SOL€S widget
                // These contain brand names + numbers that are NOT products
                const EXCLUDE_SELECTORS = [
                    'nav', 'header', 'app-top-menu', 'app-saldo-btn', 'app-user-menu',
                    'app-client-info', 'app-promotions', '[class*="promo"]', '[class*="saldo"]',
                    'footer'
                ];
                function isExcluded(el) {
                    return EXCLUDE_SELECTORS.some(sel => {
                        try { return el.closest(sel) !== null; } catch(e) { return false; }
                    });
                }

                // Strategy 1: tables (skip excluded sections)
                for (const tbl of document.querySelectorAll("table")) {
                    if (isExcluded(tbl)) continue;
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
                        if(price&&price>15&&price<2000){
                            const idxM=model.match(/\b(\d{2,3}[A-Z]{1,2}(?:[/ ]\d{2,3}[A-Z]{1,2})?(?:\s+XL)?)\b/i);
                            const loadIndex=idxM?idxM[0]:'';
                            if(idxM) model=model.slice(0,idxM.index).trim();
                            products.push({brand,model,load_index:loadIndex,price});
                        }
                    }
                    if(products.length>0) break;
                }

                // Strategy 2: any element containing a price near a brand name (skip excluded sections)
                if(products.length===0){
                    const allEls = Array.from(document.querySelectorAll("*"));
                    for(const el of allEls){
                        if (isExcluded(el)) continue;
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
                            if (isExcluded(ancestor)) { brand=""; break; }
                            const at=ancestor.textContent.toUpperCase();
                            const bm=at.match(BRANDS);
                            if(bm){brand=bm[0];model=ancestor.textContent.trim().substring(0,120);break;}
                        }
                        // Accept abbreviated brand format (MICH.PCY4) even if BRANDS regex didn't match
                        if(brand || /[A-Z]{2,8}\.[A-Z0-9]/.test(model.toUpperCase())){
                            const idxM=model.match(/\b(\d{2,3}[A-Z]{1,2}(?:[/ ]\d{2,3}[A-Z]{1,2})?(?:\s+XL)?)\b/i);
                            const loadIndex=idxM?idxM[0]:'';
                            if(idxM) model=model.slice(0,idxM.index).trim();
                            products.push({brand,model,load_index:loadIndex,price});
                        }
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

        # Discard products with empty model — DOM sometimes picks up brand near a stock/promo number
        before_filter = len(products)
        products = [p for p in products if p.get('model', '').strip()]
        if len(products) < before_filter:
            print(f"  [Soledad] Dropped {before_filter - len(products)} no-model products")

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

def _parse_andres_html(html: str) -> list:
    """Parse product list from Grupo Andres buscador page HTML.

    Each card is separated by result-thumbnail-tooltip="".
    Brand in <img title="Michelin"> (mixed case — regex deve ser case-insensitive).
    Description in data-ajax-description="205/55 R16 91V TURANZA 6" (no brand).
    P. Compre in class="campaign-price"><span> (fallback: class="campaign-base-price").
    """
    import html as htmllib

    desc_re       = re.compile(r'data-ajax-description="([^"]+)"')
    # BUG1 FIX: aceitar mixed case (ex: "Michelin", "BF Goodrich") — .upper() na extracção
    brand_re      = re.compile(r'<img[^>]*\btitle="([A-Za-z][A-Za-z0-9 \-/]+)"')
    camp_price_re = re.compile(r'class="campaign-price"><span[^>]*>\s*([\d,.]+)')
    base_price_re = re.compile(r'class="campaign-base-price">\s*([\d,.]+)')
    title_re      = re.compile(
        r'\d{3}/\d{2}\s+R\d{2}\s+(\d{2,3}[A-Z]{1,2}(?:\s+XL)?)\s+(.*)',
        re.IGNORECASE,
    )

    products = []
    for card in re.split(r'(?=result-thumbnail-tooltip="")', html)[1:]:
        d = desc_re.search(card)
        b = brand_re.search(card)
        if not d or not b:
            continue

        p = camp_price_re.search(card) or base_price_re.search(card)
        if not p:
            continue

        try:
            price = float(p.group(1).replace(',', '.'))
        except ValueError:
            continue
        if price <= 0:
            continue

        desc = htmllib.unescape(d.group(1)).strip()
        m = title_re.match(desc)
        if not m:
            continue

        products.append({
            'brand':      b.group(1).strip().upper(),
            'model':      m.group(2).strip().upper(),
            'load_index': m.group(1).strip().upper(),
            'price':      price,
        })
    return products


async def scrape_grupo_andres(page, username: str, password: str, medida: str,
                               skip_login: bool = False) -> dict:
    """Scrape Grupo Andres B2B via JSON API (online.grupoandres.com).

    Login: Playwright em online.grupoandres.com/login — cria sessão autenticada.
    Pesquisa: aiohttp GET /search/tyres?page=N com cookies Playwright.
    Campos confirmados via Network tab:
      data['search_results'][i]['brand']['name']
      data['search_results'][i]['model']['name']
      data['search_results'][i]['load'] + ['speed'] → load_index
      data['search_results'][i]['price']['distributor_price']['campaign_price' | 'base_price']
    """
    result = {
        "supplier": "Grupo Andres",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if not skip_login:
            print("  [Andres] Login em online.grupoandres.com/login ...")
            await page.goto("https://online.grupoandres.com/login",
                            wait_until="domcontentloaded", timeout=60000)
            await page.locator('input[name="data[Usuario][user]"]').fill(username)
            await page.locator('input[name="data[Usuario][pass]"]').fill(password)
            await page.locator('form#login_form').evaluate("f => f.submit()")
            await asyncio.sleep(4)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            print(f"  [Andres] URL após login: {page.url}")

        # Extrair cookies da sessão autenticada do Playwright
        cookies = await page.context.cookies()
        cookie_str = '; '.join(f"{c['name']}={c['value']}" for c in cookies)
        medida_norm = normalize_medida(medida)

        all_products: list = []
        page_num = 0
        async with aiohttp.ClientSession() as session:
            while True:
                url = (
                    f"https://online.grupoandres.com/search/tyres"
                    f"?page={page_num}&step=1&filterWithStock=true&isNewSearch=true"
                    f"&sortBy=null&sortOrder=null&sortLoadSpeed=null"
                    f"&category=cubiertas&searchText={medida_norm}"
                )
                async with session.get(url, headers={
                    'Cookie': cookie_str,
                    'Accept': 'application/json',
                    'Referer': 'https://online.grupoandres.com/',
                    'X-Requested-With': 'XMLHttpRequest',
                }, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        print(f"  [Andres] page={page_num} status={resp.status} — stop")
                        break
                    try:
                        data = await resp.json(content_type=None)
                    except Exception as json_err:
                        raw = await resp.text()
                        print(f"  [Andres] page={page_num} JSON error: {json_err} raw={raw[:80]!r}")
                        break

                items = data.get('search_results', []) if isinstance(data, dict) else []
                if not items or data.get('empty_result', False):
                    print(f"  [Andres] page={page_num} fim ({len(items)} items, empty_result={data.get('empty_result') if isinstance(data, dict) else '?'})")
                    break

                print(f"  [Andres] page={page_num}: {len(items)} items")
                for item in items:
                    brand = (item.get('brand') or {}).get('name', '').strip().upper()
                    model = (item.get('model') or {}).get('name', '').strip().upper()
                    load  = str(item.get('load', '')).strip()
                    speed = str(item.get('speed', '')).strip()
                    load_index = (load + speed).upper()
                    dist = (item.get('price') or {}).get('distributor_price') or {}
                    price_val = dist.get('campaign_price') or dist.get('base_price')
                    if not price_val or not brand or not model:
                        continue
                    try:
                        price = float(price_val)
                    except (TypeError, ValueError):
                        continue
                    if price <= 0:
                        continue
                    all_products.append({
                        'brand':      brand,
                        'model':      model,
                        'load_index': load_index,
                        'price':      price,
                    })

                page_num += 1
                if page_num > 50:
                    print("  [Andres] Limite 50 páginas atingido")
                    break

        print(f"  [Andres] {medida}: {len(all_products)} produtos em {page_num} páginas")

        if all_products:
            result["products"] = all_products
            result["price"] = min(p["price"] for p in all_products)
            print(f"  [Andres] {medida}: mín €{result['price']:.2f}")
        else:
            result["error"] = "Nenhum produto encontrado"
            print(f"  [Andres] {medida}: sem produtos")

    except Exception as e:
        result["error"] = str(e)
        print(f"  [Andres] Erro: {e}")

    return result


def _parse_aguesport_html(html: str) -> list:
    """Parse product list from Aguesport results page HTML.

    Title format in class="ma-bold14": "205/55 R16 91V KUMHO Ecowing ES31"
    Price format in class="price ma-semibold14": "42,95€"
    """
    card_re = re.compile(
        r'class="info-text"><span[^>]*class="ma-bold14">(.*?)</span>.*?'
        r'class="price ma-semibold14">([\d,.]+)',
        re.DOTALL,
    )
    title_re = re.compile(
        r'\d{3}/\d{2}\s+R\d{2}\s+(\d{2,3}[A-Z]{1,2}(?:\s+XL)?)\s+(\S+)\s+(.*)',
        re.IGNORECASE,
    )
    products = []
    for title, price_str in card_re.findall(html):
        title = title.strip()
        try:
            price = float(price_str.replace(',', '.'))
        except ValueError:
            continue
        if price <= 0:
            continue
        m = title_re.match(title)
        if not m:
            continue
        products.append({
            'brand':      m.group(2).strip().upper(),
            'model':      m.group(3).strip().upper(),
            'load_index': m.group(1).strip().upper(),
            'price':      price,
        })
    return products


async def scrape_aguesport(page, username: str, password: str, medida: str,
                            skip_login: bool = False) -> dict:
    """Scrape Aguesport B2B portal (encomendas.aguesport.com).

    Login: input[type="email"] + input[type="password"] → button[type="submit"]
    Pesquisa: input[placeholder*="Medida"] com medida normalizada (ex: 2055516)
    Resultados: class="info-text" / class="price ma-semibold14"
    """
    result = {
        "supplier": "Aguesport",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    try:
        if not skip_login:
            print("  [Aguesport] Login...")
            await page.goto("https://encomendas.aguesport.com/login",
                            wait_until="domcontentloaded", timeout=60000)
            await page.locator('input[type="email"]').first.fill(username)
            await page.locator('input[type="password"]').first.fill(password)
            await page.locator('button[type="submit"]').first.click()
            await asyncio.sleep(2)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            print(f"  [Aguesport] URL após login: {page.url}")

        medida_norm = normalize_medida(medida)
        print(f"  [Aguesport] Pesquisa: {medida_norm}")
        if skip_login:
            await page.goto("https://encomendas.aguesport.com/",
                            wait_until="domcontentloaded", timeout=30000)
        medida_field = page.locator('input[placeholder*="Medida"]').first
        await medida_field.fill(medida_norm)
        await asyncio.sleep(0.3)
        await medida_field.press("Enter")
        try:
            await page.wait_for_selector('.ma-bold14', state='visible', timeout=12000)
        except Exception:
            await asyncio.sleep(3)

        html = await page.content()
        products = _parse_aguesport_html(html)

        if products:
            result["products"] = products
            result["price"] = min(p["price"] for p in products)
            print(f"  [Aguesport] {medida}: {len(products)} produtos, mín €{result['price']}")
        else:
            result["error"] = "Nenhum produto encontrado"
            print(f"  [Aguesport] {medida}: sem produtos")

    except Exception as e:
        result["error"] = str(e)
        print(f"  [Aguesport] Erro: {e}")

    return result

def _parse_abtyres_html(html: str) -> list:
    """Parse product rows from ABTyres results page HTML.

    Each row is a <tr role="row"> (skipping DEMO rows with yellow bg #FFF63D).
    Data lives in hidden form inputs: marca, nome, preco.
    nome format: "205/55 R 16 - 91V - TQ021" → load_index=91V, model=TQ021.
    """
    nome_re = re.compile(
        r'[\d/\s]+R\s*\d+\s*-\s*(\d{2,3}[A-Z]{1,2}(?:\s+XL)?)\s*-\s*(.*)',
        re.IGNORECASE,
    )
    row_re   = re.compile(r'<tr\b[^>]*role=["\']row["\'][^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    input_re = re.compile(r'<input\b[^>]*name=["\'](\w+)["\'][^>]*value=["\']([^"\']*)["\']', re.IGNORECASE)

    products = []
    for row_m in row_re.finditer(html):
        row_html = row_m.group(0)
        # BUG2 FIX (a): fundo amarelo → linha DEMO
        if 'FFF63D' in row_html or 'fff63d' in row_html:
            continue
        fields = {m.group(1): m.group(2) for m in input_re.finditer(row_html)}
        marca  = fields.get('marca', '').strip().upper()
        nome   = fields.get('nome', '').strip()
        preco  = fields.get('preco', '').strip()
        if not nome or not preco:
            continue
        # BUG2 FIX (b): marca com sufixo DEMO (ex: 'NEXEN DEMO', 'KUMHO DEMO')
        if 'DEMO' in marca:
            continue
        try:
            price = float(preco.replace(',', '.'))
        except ValueError:
            continue
        if price <= 0:
            continue
        m = nome_re.match(nome)
        if not m:
            continue
        products.append({
            'brand':      marca,
            'model':      m.group(2).strip().upper(),
            'load_index': m.group(1).strip().upper(),
            'price':      price,
        })
    return products


async def scrape_abtyres(page, username: str, password: str, medida: str,
                         skip_login: bool = False) -> dict:
    """Scrape ABTyres B2B portal (b2b.abtyres.pt).

    Login: input[name="user"] + input[type="password"] + button:has-text("Entrar").
    Search: input[name="pesq"] + button:has-text("PESQUISA") on /pneus.
    Results: <tr role="row"> with hidden inputs marca/nome/preco; skip DEMO (#FFF63D).
    """
    result = {
        "supplier": "ABTyres",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if not skip_login:
            print("  [ABTyres] Login...")
            # BUG1 FIX: domcontentloaded em vez de networkidle (loading azul mantém rede activa)
            await page.goto("https://b2b.abtyres.pt/menu", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(1)
            current = page.url
            if 'menu' not in current and 'pneus' not in current:
                # Need to login
                await page.goto("https://b2b.abtyres.pt/", wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(1)
                await page.locator('input[name="user"]').first.fill(username)
                await page.locator('input[type="password"]').first.fill(password)
                await page.locator('button:has-text("Entrar")').first.click()
                await asyncio.sleep(4)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=20000)
                except Exception:
                    pass
                print(f"  [ABTyres] URL após login: {page.url}")
        else:
            await page.goto("https://b2b.abtyres.pt/pneus", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(1)

        medida_norm = normalize_medida(medida)
        print(f"  [ABTyres] Pesquisa: {medida_norm}")
        await page.goto("https://b2b.abtyres.pt/pneus", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(1)

        pesq = page.locator('input[name="pesq"]').first
        await pesq.fill(medida_norm)
        await asyncio.sleep(0.3)
        await page.locator('button:has-text("PESQUISA")').first.click()

        # Aguarda spinner desaparecer, depois aguarda primeira linha de resultado
        try:
            await page.wait_for_selector('#loading', state='hidden', timeout=20000)
        except Exception:
            pass
        try:
            await page.wait_for_selector('tr[role="row"]', state='visible', timeout=20000)
        except Exception:
            await asyncio.sleep(5)

        html = await page.content()
        products = _parse_abtyres_html(html)

        result["products"] = products
        if products:
            result["price"] = min(p["price"] for p in products)
            print(f"  [ABTyres] {medida}: {len(products)} produtos, mín €{result['price']}")
        else:
            result["error"] = "Nenhum produto encontrado"
            print(f"  [ABTyres] {medida}: sem produtos")

    except Exception as e:
        result["error"] = str(e)
        print(f"  [ABTyres] Erro: {e}")

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

            # Verifica se há linhas de produto no HTML (id="linha_tit_NNN")
            _tit_count = len(re.findall(r'id=["\']linha_tit_\d+["\']', _html, re.IGNORECASE))
            print(f"  [TugaPneus] linha_tit encontrados={_tit_count} para '{_term}'")
            if _tit_count > 0:
                print(f"  [TugaPneus] Dados encontrados no HTML com '{_term}'")
                _found = True
                break
            print(f"  [TugaPneus] Sem produtos no HTML para '{_term}', próximo nível...")

        content = await page.content()
        print(f"  [TugaPneus] HTML size: {len(content)} chars")
        try:
            with open('/tmp/tugapneus_search_page.html', 'w', encoding='utf-8') as _f:
                _f.write(content)
        except Exception:
            pass

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
            # 3. Parse da descrição "PNEU MARCA MEDIDA <resto>"
            # O <resto> pode ser "MODELO ÍNDICE" (ex: "PRIMACY 5 91V")
            # ou "ÍNDICE MODELO" (ex: "98W OTTIMA PLUS XL") — extraímos o índice
            # pelo padrão e o restante torna-se o modelo.
            desc_re = re.compile(
                r'PNEU\s+([\w\-]+(?:\s+[\w\-]+)?)\s+(\d{3}/\d{2}R\d{2})\s+(.*)',
                re.IGNORECASE
            )
            idx_re = re.compile(r'\b(\d{2,3}[A-Z]{1,2}(?:\s+XL)?)\b', re.IGNORECASE)

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
                rest = dm.group(3).strip()
                idx_m = idx_re.search(rest)
                if idx_m:
                    indice = idx_m.group(1).strip().upper()
                    model = (rest[:idx_m.start()] + ' ' + rest[idx_m.end():]).strip().upper()
                else:
                    indice = ''
                    model = rest.upper()
                products.append({
                    'brand':  dm.group(1).strip().upper(),
                    'medida': dm.group(2).strip().upper(),
                    'indice': indice,
                    'model':  model,
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

        # ── Ordenar por preço (clicar cabeçalho EUR/Preco se disponível) ──
        try:
            _sort_loc = _ctx.locator(
                'th:has-text("EUR"), th:has-text("Preco"), th:has-text("Preço"), '
                'a:has-text("EUR"), a:has-text("Preco"), a:has-text("Preço")'
            ).first
            if await _sort_loc.count() > 0:
                await _sort_loc.click()
                await asyncio.sleep(3)
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                print(f"  [InterSprint] Ordenado por preço")
        except Exception:
            pass

        # ── Extrair produtos de TODAS as páginas ─────────────────────────
        _MAX_PAGES = 10
        _all_products: list = []
        _seen_all: set = set()
        _total_pages = 1
        _content = ''

        for _pg_num in range(1, _MAX_PAGES + 1):
            try:
                _content = await _ctx.content()
            except Exception as _e_ct:
                print(f"  [InterSprint] Erro ao obter HTML da página {_pg_num}: {_e_ct}")
                break

            # Guardar HTML da página 1 para debug
            if _pg_num == 1:
                try:
                    with open('/tmp/intersprint_search_page.html', 'w', encoding='utf-8') as _f:
                        _f.write(_content)
                except Exception:
                    pass
                # Extrair número total de páginas
                _tp_m = re.search(
                    r'[Tt]otal\s+de\s+p[aá]ginas?\s*[:\(]?\s*(\d+)',
                    _content
                )
                if _tp_m:
                    _total_pages = min(int(_tp_m.group(1)), _MAX_PAGES)
                    print(f"  [InterSprint] Total de páginas detectado: {_total_pages}")
                else:
                    print(f"  [InterSprint] 'Total de paginas' não encontrado — assume 1 página")

            _page_prods = _parse_intersprint_html(_content, marca_upper)

            # Deduplicar entre páginas
            _new_prods = []
            for _p in _page_prods:
                _k = f"{_p['brand']}|{_p['medida']}|{_p['indice']}|{_p['price']}"
                if _k not in _seen_all:
                    _seen_all.add(_k)
                    _new_prods.append(_p)
            _all_products.extend(_new_prods)
            print(f"  [InterSprint] Página {_pg_num}: {len(_page_prods)} produtos ({len(_new_prods)} novos)")

            if _pg_num >= _total_pages:
                break

            # Navegar para a próxima página
            _next_pg = _pg_num + 1
            _navigated = False
            for _nav_sel in [
                f'a:has-text("{_next_pg}")',
                f'input[value="{_next_pg}"]',
                'a:has-text("Proxima"), a:has-text("Próxima"), '
                'a:has-text(">>"), a:has-text("Siguiente"), a:has-text("Next")',
            ]:
                try:
                    _nav_lnk = _ctx.locator(_nav_sel).first
                    if await _nav_lnk.count() > 0:
                        await _nav_lnk.click()
                        await asyncio.sleep(4)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=15000)
                        except Exception:
                            pass
                        _navigated = True
                        break
                except Exception:
                    continue

            if not _navigated:
                print(f"  [InterSprint] Sem link para página {_next_pg} — a parar paginação")
                break

        print(f"  [InterSprint] Total acumulado: {len(_all_products)} produtos")
        products = _all_products

        if products:
            result["products"] = products
            result["price"] = min(p['price'] for p in products)
            result["all_prices"] = sorted(p['price'] for p in products)[:10]
            print(f"  [InterSprint] {len(products)} produtos, melhor €{result['price']}")
            for p in products[:5]:
                print(f"    {p['brand']} {p['medida']} {p.get('indice','')} {p.get('model','')} → €{p['price']}")
        else:
            # Fallback: extrair preços brutos do HTML da última página lida
            prices = extract_prices(_content)
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

    Estrutura da tabela (colunas):
      Marca | Descricao | Estacao | 3PMSF | LI/SI | Rotulo | Foto | E/EU | Stock | EUR

    Descricao format: "215/55 VR18 TL 99V MI PRIMACY 5 XL [M&S,Todas as estacoes]"
    Campos posicionais após medida regex match:
      TL → load_index → brand_abbr → modelo...

    ABORDAGEM: parsing por célula <td> individual.
    Extrai a célula Descricao (a que contém o padrão de medida) e
    passa-a isolada para _parse_after_medida — evita contaminação
    das colunas adjacentes (LI/SI duplicado, E/EU, Estacao, Stock…).

    search_brand: fallback quando a célula Marca está vazia.
    """
    import re as _re

    products: list = []
    seen: set = set()
    _no_medida_dbg: list = []

    price_re  = _re.compile(
        r'€\s*(\d+[,.]\d{2})|(\d+[,.]\d{2})\s*€|&nbsp;\s*(\d+[,.]\d{2})\s*&nbsp;',
        _re.IGNORECASE
    )
    medida_re = _re.compile(r'(\d{3}/\d{2})\s*[A-Z]?\s*R\s*(\d{2})\b', _re.IGNORECASE)
    tag_re    = _re.compile(r'<[^>]+>')
    row_re    = _re.compile(r'<tr\b[^>]*>(.*?)</tr>', _re.IGNORECASE | _re.DOTALL)
    td_re     = _re.compile(r'<td\b[^>]*>(.*?)</td>', _re.IGNORECASE | _re.DOTALL)

    # Contexto da última linha com Descricao (para rowspan: preço em linha separada)
    _ctx_brand  = ''
    _ctx_medida = ''
    _ctx_indice = ''
    _ctx_model  = ''

    def _decode_entities(text: str) -> str:
        text = text.replace('&#47;', '/').replace('&amp;', '&')
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>')
        text = _re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
        text = _re.sub(r'&\w+;', ' ', text)
        return _re.sub(r'\s+', ' ', text).strip()

    def _parse_after_medida(after_text: str, ctx_brand: str) -> tuple:
        """Parse da Descricao APENAS após o match da medida (texto isolado da célula).

        after_text: texto da célula Descricao desde o fim da medida regex.
        Exemplo: " TL 99V MI PRIMACY 5 XL [M&S,Todas as estacoes]"

        Campos posicionais:
          [skip TL/TW]  [load_index: 99V]  [brand_abbr: MI]  [model: PRIMACY 5 XL]

        Retorna (brand, model, load_index).
        """
        _BMAP = {
            'MI': 'MICHELIN',    'BR': 'BRIDGESTONE', 'GY': 'GOODYEAR',
            'CO': 'CONTINENTAL', 'PI': 'PIRELLI',     'HA': 'HANKOOK',
            'DU': 'DUNLOP',      'KL': 'KLEBER',      'UN': 'UNIROYAL',
            'VR': 'VREDESTEIN',  'GE': 'GENERAL',     'VI': 'VIKING',
            'DC': 'DOUBLE COIN', 'DE': 'DELINTE',     'LA': 'LANDSAIL',
            'SE': 'SENTURY',     'MS': 'MASTERSTEEL', 'RH': 'ROADHOG',
            'NK': 'NANKANG',     'FU': 'FULDA',       'TR': 'TRIANGLE',
            'AT': 'ATLAS',       'CA': 'CEAT',        'HI': 'HIFLY',
            'SU': 'SUNNY',       'AP': 'APOLLO',      'TO': 'TOYO',
            'YO': 'YOKOHAMA',    'SA': 'SAILUN',      'BA': 'BARUM',
            'MA': 'MAXXIS',      'LI': 'LINGLONG',    'WA': 'WANLI',
            'KU': 'KUMHO',       'FA': 'FALKEN',      'RI': 'RIKEN',
            'BF': 'BF GOODRICH', 'BI': 'BF GOODRICH', 'NO': 'NOKIAN',
            'LE': 'LENDA',       'EV': 'EVENT',       'NE': 'NEXEN',
            'FO': 'FORTUNA',     'LF': 'LANDFORSAIL', 'ZE': 'ZEETEX',
            'SC': 'SECURITY',    'CI': 'CIMOS',       'GT': 'GT RADIAL',
        }
        # 1. Remover conteúdo entre [...] (M&S, Todas as estacoes, etc.)
        clean = _re.sub(r'\[.*?\]', '', after_text).strip()
        tokens = clean.split()

        i = 0
        # Saltar TL / TW
        while i < len(tokens) and tokens[i].upper() in ('TL', 'TW'):
            i += 1

        # Load index: \d{2,3}[A-Z]{1,2}  ex: "99V", "95H", "121S"
        load_index = ''
        if i < len(tokens) and _re.match(r'^\d{2,3}[A-Z]{1,2}$', tokens[i], _re.I):
            load_index = tokens[i].upper()
            i += 1

        # Abreviatura de marca: exatamente 2 letras maiúsculas  ex: "MI", "DC"
        parsed_brand = ctx_brand
        if i < len(tokens) and _re.match(r'^[A-Z]{2}$', tokens[i]):
            parsed_brand = _BMAP.get(tokens[i].upper(), ctx_brand or tokens[i].upper())
            i += 1

        # Modelo: tokens restantes (Descricao já está isolada — sem colunas extra)
        model = ' '.join(t.upper() for t in tokens[i:])

        return parsed_brand, model, load_index

    for row_m in row_re.finditer(html):
        row_inner = row_m.group(1)

        # ── Extrair células <td> individuais ─────────────────────────────
        _cells_txt = [
            _decode_entities(_re.sub(r'\s+', ' ', tag_re.sub(' ', c.group(1))).strip())
            for c in td_re.finditer(row_inner)
        ]

        # ── Célula Descricao: a que contém o padrão de medida ────────────
        _desc_cell = ''
        _desc_idx  = -1
        for _ci, _ct in enumerate(_cells_txt):
            if medida_re.search(_ct):
                _desc_cell = _ct
                _desc_idx  = _ci
                break

        # ── Preço: pesquisa no HTML raw da linha (preserva &nbsp; formato) ──
        _raw_row = _re.sub(r'\s+', ' ', tag_re.sub(' ', row_inner))
        price_m  = price_re.search(_raw_row)

        # ── Actualizar contexto se esta linha tem Descricao ──────────────
        if _desc_cell:
            _dm = medida_re.search(_desc_cell)
            _g1 = _dm.group(1).replace(' ', '')
            _ctx_medida = f"{_g1}R{_dm.group(2)}".upper()
            # Célula Marca: imediatamente antes da Descricao (normalmente índice 0)
            _mk = _cells_txt[_desc_idx - 1].upper() if _desc_idx > 0 else ''
            # Filtrar alt-text de imagens (contém espaços ou dígitos → ignorar)
            if len(_mk) > 25 or any(c.isdigit() for c in _mk):
                _mk = ''
            _parsed_brand, _ctx_model, _ctx_indice = _parse_after_medida(
                _desc_cell[_dm.end():], _mk
            )
            _ctx_brand = _mk or _parsed_brand or search_brand.upper() or 'UNKNOWN'

        # ── Sem preço → não é linha de produto ───────────────────────────
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

        # ── Construir produto com contexto acumulado ──────────────────────
        medida_val = _ctx_medida
        brand_val  = _ctx_brand or search_brand.upper() or 'UNKNOWN'
        indice_val = _ctx_indice
        model_val  = _ctx_model

        if not medida_val and len(_no_medida_dbg) < 3:
            _no_medida_dbg.append(str(_cells_txt[:6])[:300])

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


def _parse_cruzeiro_html(html: str) -> list:
    """Parse <tr> rows from Cruzeiro HTMX AJAX response HTML.

    Colunas: 0=Imagem 1=Fabricante 2=Produto 3=DOT 4=Stock 5=Etq 6=Qtd 7=Preço 8=PVP
    Formato Produto: "PNEU MARCA MEDIDA MODELO ÍNDICE"
      ex.: "PNEU MICHELIN 205/55R16 PRIMACY 5 91V"
    """
    tag_re = re.compile(r'<[^>]+>', re.DOTALL)
    td_re  = re.compile(r'<td\b[^>]*>(.*?)</td>', re.DOTALL | re.IGNORECASE)
    tr_re  = re.compile(r'<tr\b[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    products = []

    for tr_m in tr_re.finditer(html):
        cells = [tag_re.sub('', td.group(1)).strip() for td in td_re.finditer(tr_m.group(1))]
        if len(cells) < 8:
            continue

        # Coluna 2 (Produto) é a fonte fiável — coluna 1 (Fabricante) pode
        # conter "PNEU", texto de imagem ou estar vazia.
        # Formato: "PNEU MARCA MEDIDA MODELO ÍNDICE"
        #   ex: "PNEU MICHELIN 215/55R16 PRIMACY 5 91V"
        #   ex: "NEXEN 215/55R18 N'FERA RU1 99V XL"  (sem prefixo PNEU)
        prod  = ' '.join(cells[2].split())
        txt   = re.sub(r'^PNEU\s+', '', prod, flags=re.IGNORECASE)
        parts = [p for p in txt.split() if p]

        if not parts:
            continue

        # 1. Primeiro token = MARCA (sempre da coluna Produto)
        brand = parts.pop(0).upper()

        # 2. Ignorar token de medida ("205/55R16")
        if parts and re.match(r'\d{3}/\d{2}[Rr]\d{2}', parts[0]):
            parts.pop(0)

        # 3. Modelo = tudo antes do primeiro índice de carga+velocidade
        remaining = ' '.join(parts)
        idx_m = re.search(r'\b(\d{2,3}[A-Z]{1,2}(?:\s+XL)?)\b', remaining, re.IGNORECASE)
        model = remaining[:idx_m.start()].strip() if idx_m else remaining.strip()
        load_index = idx_m.group(1).strip().upper() if idx_m else ''

        # Preço (coluna 7)
        m_price = re.search(r'(\d+[,.]\d{2})', cells[7])
        if not m_price:
            continue
        try:
            price = float(m_price.group(1).replace(',', '.'))
        except ValueError:
            continue
        if price <= 5:
            continue

        products.append({'brand': brand, 'model': model, 'load_index': load_index, 'price': price})

    return products


async def scrape_pneus_cruzeiro(page, username: str, password: str, medida: str,
                               url_login: str = "https://www.pneuscruzeiro.pt/pt/login",
                               url_search: str = "https://www.pneuscruzeiro.pt/pt/privatearea",
                               skip_login: bool = False,
                               marca: str = '') -> dict:
    """Scrape Pneus Cruzeiro B2B portal (pneuscruzeiro.pt).

    Login: POST https://www.pneuscruzeiro.pt/pt/login
      - input[name="username"] (email), input[name="password"]
      - reCAPTCHA invisible v2: o JS interceta o submit, resolve o captcha
        e chama form.submit(). Basta clicar o botão e aguardar navegação.
    Pesquisa: HTMX GET https://www.pneuscruzeiro.pt/pt/produtos-tabela-ajax
      - campo: #campo_de_texto_para_pesquisar_os_produtos (name=prodssrchtxt)
      - botão: #botao_iniciador_pesquisa_produtos
      - resultados: tbody#contentor_linhas_tabela_produtos
    Colunas da tabela:
      0=Imagem  1=Fabricante  2=Produto  3=DOT  4=Stock  5=Etq  6=Qtd  7=Preço  8=PVP
    Formato da coluna Produto: "PNEU MARCA MEDIDA MODELO ÍNDICE"
      ex.: "PNEU MICHELIN 205/55R16 PRIMACY 5 91V"
           → marca=MICHELIN, modelo=PRIMACY 5, índice=91V
    """
    result = {
        "supplier": "Pneus Cruzeiro",
        "price": None,
        "error": None,
        "products": [],
        "medida": medida,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if not url_login:
        url_login = "https://www.pneuscruzeiro.pt/pt/login"
    if not url_search:
        url_search = "https://www.pneuscruzeiro.pt/pt/privatearea"

    medida_norm = normalize_medida(medida)  # ex: "2055516"
    # Cruzeiro pesquisa por texto nas descrições ("PNEU MICHELIN 205/55R16 ..."),
    # por isso precisa do formato "205/55R16" e não "2055516"
    import re as _re_med
    _m_fmt = _re_med.match(r'^(\d{3})(\d{2})(\d{2})$', medida_norm)
    medida_search = f"{_m_fmt.group(1)}/{_m_fmt.group(2)}R{_m_fmt.group(3)}" if _m_fmt else medida

    def _save_debug(path: str, content: str):
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            pass

    try:
        # ── LOGIN ────────────────────────────────────────────────────────────
        if not skip_login:
            print(f"  [Cruzeiro] A fazer login: {url_login}")
            await page.goto(url_login, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)
            _save_debug('/tmp/cruzeiro_pre_login.html', await page.content())

            # Verificar se já autenticado (sessão activa)
            if 'privatearea' not in page.url:
                # Preencher email e password com digitação lenta (ajuda reCAPTCHA)
                await page.focus('input[name="username"]')
                await asyncio.sleep(0.5)
                await page.type('input[name="username"]', username, delay=80)
                await asyncio.sleep(0.3)
                await page.focus('input[name="password"]')
                await asyncio.sleep(0.3)
                await page.type('input[name="password"]', password, delay=80)
                await asyncio.sleep(0.5)

                # ATENÇÃO: A página tem 2 botões button[type="submit"]:
                #   1. "Área Reservada" no cabeçalho (GET form → /pt/privatearea)
                #   2. "Login" no formulário #ew_form_logincliente (POST → /pt/login)
                # Selector específico para o botão correcto — dentro do formulário de login.
                login_btn = page.locator('#ew_form_logincliente button[type="submit"]').first
                await login_btn.click()
                print(f"  [Cruzeiro] Botão de login clicado; aguardar reCAPTCHA + navegação...")

                # Aguardar até 45s para o reCAPTCHA invisible resolver e a navegação ocorrer
                # O reCAPTCHA invisible v2 pode demorar até ~10s em headless
                try:
                    await page.wait_for_url(
                        lambda url: 'privatearea' in url,
                        timeout=45000,
                    )
                except Exception:
                    # Pode ter navegado mas não para privatearea — verificar abaixo
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass

                await asyncio.sleep(2)
                current_url = page.url
                print(f"  [Cruzeiro] URL após login: {current_url}")
                _save_debug('/tmp/cruzeiro_after_login.html', await page.content())

                if 'privatearea' not in current_url.lower():
                    result["error"] = (
                        f"Login falhou — URL após submit: {current_url}. "
                        "Possível bloqueio de reCAPTCHA em modo headless."
                    )
                    return result
            else:
                print(f"  [Cruzeiro] Já autenticado, a ignorar login.")

        # ── PESQUISA ─────────────────────────────────────────────────────────
        search_tab_url = url_search.rstrip('?&') + '?tab=produtos'
        print(f"  [Cruzeiro] Navegando para pesquisa: {search_tab_url}")
        await page.goto(search_tab_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)

        # Verificar redireccção para login (sessão expirada)
        if 'login' in page.url.lower():
            result["error"] = "Sessão expirada — redireccionado para login"
            return result

        # Verificar campo de pesquisa
        search_field = page.locator('#campo_de_texto_para_pesquisar_os_produtos')
        if await search_field.count() == 0:
            result["error"] = "Campo de pesquisa não encontrado (#campo_de_texto_para_pesquisar_os_produtos)"
            _save_debug('/tmp/cruzeiro_search_page.html', await page.content())
            return result

        await search_field.fill(medida_search)
        print(f"  [Cruzeiro] Pesquisar: {medida_search!r} (norm={medida_norm})")

        # Selecionar fabricante no dropdown FABRICANTE (se especificado)
        if marca:
            try:
                # O dropdown FABRICANTE está junto ao campo de pesquisa
                selected = await page.evaluate(f'''() => {{
                    const selects = document.querySelectorAll('select');
                    for (const sel of selects) {{
                        for (const opt of sel.options) {{
                            if (opt.text.trim().toUpperCase() === {marca.upper()!r}) {{
                                sel.value = opt.value;
                                sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                                return opt.text.trim();
                            }}
                        }}
                    }}
                    return null;
                }}''')
                if selected:
                    print(f"  [Cruzeiro] Fabricante seleccionado: {selected!r}")
                else:
                    print(f"  [Cruzeiro] Fabricante {marca!r} não encontrado no dropdown")
            except Exception as _e_fab:
                print(f"  [Cruzeiro] Erro ao seleccionar fabricante: {_e_fab}")

        # Clicar no botão de pesquisa → dispara HTMX para produtos-tabela-ajax
        search_btn = page.locator('#botao_iniciador_pesquisa_produtos')
        if await search_btn.count() > 0:
            try:
                async with page.expect_response(
                    lambda r: 'produtos-tabela-ajax' in r.url,
                    timeout=20000,
                ) as resp_info:
                    await search_btn.click()
                await resp_info.value  # garantir que a resposta foi totalmente recebida
                await asyncio.sleep(2)
            except Exception as e_htmx:
                print(f"  [Cruzeiro] HTMX wait falhou ({e_htmx}); aguardar networkidle...")
                await page.wait_for_load_state("networkidle", timeout=15000)
                await asyncio.sleep(2)
        else:
            await search_field.press('Enter')
            await page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(2)

        content = await page.content()
        _save_debug('/tmp/cruzeiro_results.html', content)
        print(f"  [Cruzeiro] Resultados carregados (content length: {len(content)})")

        # ── EXTRACÇÃO DE PRODUTOS (com paginação) ────────────────────────────
        # Tabela com colunas:
        #   0=Imagem  1=Fabricante  2=Produto  3=DOT  4=Stock  5=Etq  6=Qtd  7=Preço  8=PVP
        # Formato Produto: "PNEU MICHELIN 205/55R16 PRIMACY 5 91V"
        _EXTRACT_JS = r'''() => {
            const rows = document.querySelectorAll('#contentor_linhas_tabela_produtos tr');
            const products = [];

            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length < 8) continue;

                let brand = '', model = '', price = null;

                // ── Coluna Produto (índice 2) — fonte fiável de marca e modelo ──
                // Coluna Fabricante (índice 1) pode conter "PNEU", alt de imagem
                // incorrecta ou texto de fallback — NÃO usar como fonte primária.
                // Formato: "PNEU MARCA MEDIDA MODELO ÍNDICE"
                //   ex: "PNEU MICHELIN 205/55R16 PRIMACY 5 91V"
                //   ex: "NEXEN 215/55R18 N'FERA RU1 99V XL"  (sem prefixo PNEU)
                const produtoTxt = cells[2].textContent.trim().replace(/\s+/g, ' ');
                let txt = produtoTxt.replace(/^PNEU\s+/i, '');
                const parts = txt.split(' ').filter(p => p.length > 0);

                // 1. Primeiro token = MARCA (sempre)
                if (parts.length >= 1) {
                    brand = parts.shift().toUpperCase();
                }

                // Se a coluna Fabricante tinha texto, o produto repete a marca em parts[0]
                // ex: fab="YOKOHAMA", produto="YOKOHAMA 215/55R18 GEOLANDAR CV G058 91V"
                // → saltar o token duplicado antes de checar medida
                if (brand && parts.length > 0 && parts[0].toUpperCase() === brand) {
                    parts.shift();
                }

                // Saltar token que parece medida (ex: "205/55R16", "215/55R18")
                if (parts.length > 0 && /\d{3}[\/]\d{2}[Rr]\d{2}/.test(parts[0])) {
                    parts.shift();
                }

                // 3. Modelo = tudo antes do primeiro índice de carga+velocidade
                // ex: "PRIMACY 5 91V" → "PRIMACY 5"
                // ex: "EFFICIENTGRIP PERFORMANCE 2 99V XL" → "EFFICIENTGRIP PERFORMANCE 2"
                const remainingStr = parts.join(' ');
                const idxMatch = remainingStr.match(/\b(\d{2,3}[A-Z]{1,2}(?:\s+XL)?)\b/i);
                const loadIndex = idxMatch ? idxMatch[1].trim().toUpperCase() : '';
                model = (idxMatch ? remainingStr.slice(0, idxMatch.index) : remainingStr).trim();

                // ── Coluna Preço (índice 7) ───────────────────────────────
                const precoTxt = cells[7].textContent.trim();
                const m = precoTxt.match(/(\d+[,.]\d{2})/);
                if (m) price = parseFloat(m[1].replace(',', '.'));

                // DEBUG: emitir para diagnóstico
                const fabTxt = cells[1].textContent.trim().replace(/\s+/g, ' ').toUpperCase();
                products.push({
                    brand, model, load_index: loadIndex, price,
                    _raw_fabricante: fabTxt,
                    _raw_produto: produtoTxt,
                    _raw_preco: precoTxt,
                });
            }
            return products;
        }'''

        # JS reutilizável para parsear rows de HTML bruto (AJAX ou DOM).
        # Injecta o HTML num elemento temporário → usa textContent do browser
        # → comentários e entidades tratados correctamente, igual ao _EXTRACT_JS.
        _PARSE_HTML_JS = r'''(html) => {
            const temp = document.createElement('table');
            temp.innerHTML = html;
            const rows = temp.querySelectorAll('tr');
            const products = [];

            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length < 8) continue;

                let brand = '', model = '', price = null;

                const produtoTxt = cells[2].textContent.trim().replace(/\s+/g, ' ');
                let txt = produtoTxt.replace(/^PNEU\s+/i, '');
                const parts = txt.split(' ').filter(p => p.length > 0);

                if (parts.length >= 1) {
                    brand = parts.shift().toUpperCase();
                }

                if (parts.length > 0 && /\d{3}\/\d{2}[Rr]\d{2}/.test(parts[0])) {
                    parts.shift();
                }

                const remainingStr = parts.join(' ');
                const idxMatch = remainingStr.match(/\b(\d{2,3}[A-Z]{1,2}(?:\s+XL)?)\b/i);
                const loadIndex = idxMatch ? idxMatch[1].trim().toUpperCase() : '';
                model = (idxMatch ? remainingStr.slice(0, idxMatch.index) : remainingStr).trim();

                const precoTxt = cells[7].textContent.trim();
                const m = precoTxt.match(/(\d+[,.]\d{2})/);
                if (m) price = parseFloat(m[1].replace(',', '.'));

                if (brand && price) {
                    products.push({brand, model, load_index: loadIndex, price,
                        _raw_produto: produtoTxt, _raw_preco: precoTxt});
                }
            }
            return products;
        }'''

        products = await page.evaluate(_EXTRACT_JS)
        print(f"  [Cruzeiro] Página 1: {len(products)} linhas extraídas")
        for _dbg in products[:20]:
            print(f"  [Cruzeiro DEBUG] fab={_dbg.get('_raw_fabricante','?')!r:20} | produto={_dbg.get('_raw_produto','?')!r:60} | brand={_dbg.get('brand','?')!r:15} | model={_dbg.get('model','?')!r:30} | price={_dbg.get('price')}")

        # ── Paginação HTMX AJAX: offset=16, 32, 48... ───────────────────────
        # O site usa hx-trigger="intersect once" — não há botão de página.
        # Chama o endpoint AJAX directamente com os cookies de sessão.
        print(f"  [Cruzeiro] Página 1 (DOM): {len(products)} produtos; a paginar via AJAX...")
        _ajax_base = "https://www.pneuscruzeiro.pt/pt/produtos-tabela-ajax"
        _cookies = await page.context.cookies()
        _cookie_str = '; '.join(f"{c['name']}={c['value']}" for c in _cookies)
        _offset = 16
        async with aiohttp.ClientSession() as _http:
            while _offset <= 320:
                _ajax_url = (
                    f"{_ajax_base}?offset={_offset}&fabricante=&runflat=0"
                    f"&prodssrchtxt={medida_search}"
                    f"&medidas=&orderby=preco_do_artigo"
                    f"&orderdirection=ASC&tipoListaProdutos=1"
                )
                try:
                    async with _http.get(_ajax_url, headers={
                        'Cookie': _cookie_str,
                        'Accept': 'text/html,*/*',
                        'HX-Request': 'true',
                        'Referer': search_tab_url,
                    }, timeout=aiohttp.ClientTimeout(total=20)) as _resp:
                        if _resp.status != 200:
                            print(f"  [Cruzeiro] AJAX offset={_offset} status={_resp.status} — stop")
                            break
                        _ajax_html = await _resp.text()
                except Exception as _e_ajax:
                    print(f"  [Cruzeiro] AJAX offset={_offset} erro: {_e_ajax}")
                    break

                if '<tr' not in _ajax_html:
                    print(f"  [CRZ-AJAX] offset={_offset} sem <tr> — fim")
                    break
                # Mesmo parser que o DOM: injecta HTML no browser e usa textContent
                # (resolve comentários HTML, entidades, etc. que quebram o parser Python)
                _new_prods = await page.evaluate(_PARSE_HTML_JS, _ajax_html)
                print(f"  [CRZ-AJAX] offset={_offset} → {len(_new_prods)} produtos")
                products.extend(_new_prods)
                _offset += 16

        print(f"  [Cruzeiro] Total após paginação AJAX: {len(products)} produtos")

        # Limpar campos _raw_* usados apenas para debug
        for p in products:
            for k in list(p.keys()):
                if k.startswith('_raw'):
                    del p[k]

        if products:
            # Filtrar linhas sem preço válido e marcas com artefactos HTML (ex: "-->PNEU")
            # Log de descartados para diagnóstico
            valid_products = []
            for _p in products:
                _motivo = None
                if not _p.get('price') or _p['price'] <= 5:
                    _motivo = 'sem preço válido'
                elif not _p.get('brand'):
                    _motivo = 'sem marca'
                elif _p['brand'].startswith('-->') or _p['brand'] in ('', '-->', '-->PNEU'):
                    _motivo = f"marca artefacto HTML: {_p['brand']!r}"
                if _motivo:
                    print(f"  [CRZ-DESCARTADO] brand={_p.get('brand','')!r} model={_p.get('model','')!r} "
                          f"price={_p.get('price')!r} motivo={_motivo!r}")
                else:
                    valid_products.append(_p)
            products = valid_products
            # Deduplicar por marca+modelo, manter preço mais baixo
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
            print(f"  [Cruzeiro] {len(products)} produtos únicos. Melhor: €{result['price']}")
            for p in sorted(products, key=lambda x: x['price'])[:5]:
                print(f"    - {p.get('brand','-')} {p.get('model','-')}: €{p['price']}")
        else:
            # Fallback: regex de preços no HTML bruto
            prices_list = extract_prices(content)
            if prices_list:
                result["price"] = min(prices_list)
                result["all_prices"] = sorted(prices_list)[:10]
                print(f"  [Cruzeiro] Fallback regex: {len(prices_list)} preços, melhor: €{result['price']}")
            else:
                result["error"] = "Nenhum produto encontrado — ver /tmp/cruzeiro_results.html"
                print(f"  [Cruzeiro] {result['error']}")

    except Exception as e:
        result["error"] = str(e)
        print(f"  [Cruzeiro] ERRO: {e}")
        import traceback; traceback.print_exc()

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
                _sol_relogin = False  # set True when session expires mid-scrape
                _sol_medida_count = 0  # contador para re-login preventivo

                # Limpar medidas obsoletas: apagar registos do Soledad que NÃO estão
                # nas medidas actuais. Evita que medidas antigas (já removidas da lista)
                # continuem a aparecer nos resultados indefinidamente.
                _sol_current_medidas = [m for m, _, _ in targets]
                if _sol_current_medidas:
                    _conn_cleanup = await _pg_connect()
                    try:
                        _placeholders = ','.join(f'${i + 2}' for i in range(len(_sol_current_medidas)))
                        _deleted_obs = await _conn_cleanup.fetchval(
                            f"WITH d AS (DELETE FROM scraped_prices WHERE supplier_name=$1 AND medida NOT IN ({_placeholders}) RETURNING id) SELECT COUNT(*) FROM d",
                            supplier['name'], *_sol_current_medidas,
                        )
                        if _deleted_obs:
                            print(f"  [Soledad] Limpeza: {_deleted_obs} registos de medidas obsoletas apagados")
                    finally:
                        await _conn_cleanup.close()

                for medida, marca, modelo in targets:
                    _sol_page = await _sol_ctx.new_page()
                    await _sol_page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
                    try:
                        _sol_medida_count += 1
                        # Re-login preventivo a cada 3 medidas para evitar expiração de sessão
                        _preventive_relogin = (_sol_medida_count % 3 == 0) and not _sol_first
                        _is_first = _sol_first or _sol_relogin or _preventive_relogin
                        if _preventive_relogin:
                            print(f"  [Soledad] Re-login preventivo (medida #{_sol_medida_count})")
                        _sol_first = False
                        _sol_relogin = False
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
                            timeout=90,   # 1.5 min max por medida (fornecedores correm em paralelo)
                        )
                        _dt = (datetime.now() - _t0).total_seconds()
                        print(f"  [Soledad] Fim medida {medida}: {_dt:.0f}s, price={result.get('price')}, products={len(result.get('products',[]))}")

                        # Detect session expiry — retry CURRENT medida immediately with re-login
                        if 'session issue' in (result.get('error') or ''):
                            print(f"  [Soledad] Sessão expirou em {medida} — retentando imediatamente com re-login")
                            _sol_retry_page = await _sol_ctx.new_page()
                            await _sol_retry_page.add_init_script(
                                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
                            try:
                                result = await asyncio.wait_for(
                                    scrape_grupo_soledad(
                                        _sol_retry_page,
                                        supplier['username'], supplier['password'], medida,
                                        _sol_url_login, _sol_url_search,
                                        skip_login=False,  # forçar re-login
                                    ),
                                    timeout=120,  # mais tempo para login + pesquisa no retry
                                )
                                _dt2 = (datetime.now() - _t0).total_seconds()
                                print(f"  [Soledad] Retry medida {medida}: {_dt2:.0f}s, products={len(result.get('products',[]))}")
                            except Exception as _retry_e:
                                print(f"  [Soledad] Retry falhou ({medida}): {_retry_e}")
                            finally:
                                try:
                                    await _sol_retry_page.close()
                                except Exception:
                                    pass
                            # Próxima medida também deve re-autenticar (sessão pode ainda estar inválida)
                            _sol_relogin = True

                        result["medida"] = medida
                        results.append(result)
                        # Save to PostgreSQL
                        products = result.get('products', [])
                        _is_session_err = 'session issue' in (result.get('error') or '')
                        conn_save = await _pg_connect()
                        try:
                            if not _is_session_err:
                                # Clear ALL old entries for this medida — prevents stale prices
                                # from past (incorrect) runs from polluting future comparisons.
                                await conn_save.execute(
                                    "DELETE FROM scraped_prices WHERE supplier_name=$1 AND medida=$2",
                                    supplier['name'], medida,
                                )
                            if products:
                                for prod in products:
                                    await conn_save.execute(
                                        "INSERT INTO scraped_prices (id,supplier_name,medida,marca,modelo,price,load_index,scraped_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                                        str(uuid.uuid4()), supplier['name'], medida,
                                        prod.get('brand', '').upper(), prod.get('model', ''),
                                        prod.get('price'), prod.get('load_index') or prod.get('indice') or '', datetime.now(timezone.utc),
                                    )
                                print(f"  {medida}: saved {len(products)} products")
                            elif not _is_session_err:
                                if result.get('price') is not None:
                                    await conn_save.execute(
                                        "INSERT INTO scraped_prices (id,supplier_name,medida,price,scraped_at) VALUES ($1,$2,$3,$4,$5)",
                                        str(uuid.uuid4()), supplier['name'], medida, result['price'], datetime.now(timezone.utc),
                                    )
                                    print(f"  {medida}: €{result['price']} (no brand data)")
                                else:
                                    print(f"  {medida}: no products found — old data cleared")
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
            # Sumário compacto de todos os resultados Soledad (visível no fim dos logs)
            _sol_summary = []
            for _r in results:
                if _r.get('supplier', '').lower().startswith('grupo'):
                    _m = _r.get('medida', '?')
                    _np = len(_r.get('products', []))
                    _err = _r.get('error') or ''
                    _sol_summary.append(f"{_m}:{_np}p{'(ERR)' if _err else ''}")
            print(f"  [Soledad] RESUMO: {' | '.join(_sol_summary)}")
            continue  # Skip the generic per-medida loop below

        # ── Aguesport: sessão única para todas as medidas ──────────────────
        # Login uma vez; cada medida usa página nova no mesmo contexto.
        if 'aguesport' in supplier_name:
            _agu_ctx_kwargs = dict(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='pt-PT',
            )
            async with async_playwright() as _p_agu:
                _agu_browser = await _p_agu.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox',
                          '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                _agu_ctx = await _agu_browser.new_context(**_agu_ctx_kwargs)
                _agu_first = True
                _agu_summary = []

                for medida in medidas:
                    _agu_page = await _agu_ctx.new_page()
                    await _agu_page.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
                    )
                    try:
                        result = await asyncio.wait_for(
                            scrape_aguesport(
                                _agu_page,
                                supplier['username'], supplier['password'],
                                medida,
                                skip_login=(not _agu_first),
                            ),
                            timeout=60,
                        )
                        _agu_first = False
                        result["medida"] = medida
                        results.append(result)

                        products = result.get('products', [])
                        now = datetime.now(timezone.utc)
                        conn_save = await _pg_connect()
                        try:
                            await conn_save.execute(
                                "DELETE FROM scraped_prices WHERE supplier_name=$1 AND medida=$2",
                                supplier['name'], medida,
                            )
                            if products:
                                for prod in products:
                                    await conn_save.execute(
                                        """INSERT INTO scraped_prices
                                               (id, supplier_name, medida, marca, modelo, price, load_index, scraped_at)
                                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                                        str(uuid.uuid4()), supplier['name'], medida,
                                        prod.get('brand', '').upper(),
                                        prod.get('model', ''),
                                        prod.get('price'),
                                        prod.get('load_index', ''),
                                        now,
                                    )
                                print(f"  [Aguesport] {medida}: guardados {len(products)} produtos")
                            elif result.get('price') is not None:
                                await conn_save.execute(
                                    """INSERT INTO scraped_prices
                                           (id, supplier_name, medida, price, scraped_at)
                                       VALUES ($1,$2,$3,$4,$5)""",
                                    str(uuid.uuid4()), supplier['name'], medida,
                                    result['price'], now,
                                )
                                print(f"  [Aguesport] {medida}: €{result['price']} (sem dados marca)")
                            else:
                                print(f"  [Aguesport] {medida}: sem produtos — registos antigos apagados")
                        finally:
                            await conn_save.close()

                        _err = result.get('error') or ''
                        _np  = len(result.get('products', []))
                        _agu_summary.append(f"{medida}:{_np}p{'(ERR)' if _err else ''}")

                    except asyncio.TimeoutError:
                        print(f"  [Aguesport] Timeout em {medida}")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": "timeout"})
                        _agu_summary.append(f"{medida}:TIMEOUT")
                    except Exception as _e_agu:
                        print(f"  [Aguesport] Erro em {medida}: {_e_agu}")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": str(_e_agu)})
                        _agu_summary.append(f"{medida}:ERR")
                    finally:
                        await _agu_page.close()

                print(f"  [Aguesport] RESUMO: {' | '.join(_agu_summary)}")
                await _agu_browser.close()
            continue  # Skip the generic per-medida loop below

        # ── Grupo Andres: sessão única para todas as medidas ───────────────
        # Login uma vez via JS form submit; pesquisa por URL directa.
        if 'andres' in supplier_name:
            _and_ctx_kwargs = dict(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='pt-PT',
            )
            async with async_playwright() as _p_and:
                _and_browser = await _p_and.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox',
                          '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                _and_ctx = await _and_browser.new_context(**_and_ctx_kwargs)
                _and_first = True
                _and_summary = []

                for medida in medidas:
                    _and_page = await _and_ctx.new_page()
                    await _and_page.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
                    )
                    try:
                        result = await asyncio.wait_for(
                            scrape_grupo_andres(
                                _and_page,
                                supplier['username'], supplier['password'],
                                medida,
                                skip_login=(not _and_first),
                            ),
                            timeout=60,
                        )
                        _and_first = False
                        result["medida"] = medida
                        results.append(result)

                        products = result.get('products', [])
                        now = datetime.now(timezone.utc)
                        conn_save = await _pg_connect()
                        try:
                            await conn_save.execute(
                                "DELETE FROM scraped_prices WHERE supplier_name=$1 AND medida=$2",
                                supplier['name'], medida,
                            )
                            if products:
                                for prod in products:
                                    await conn_save.execute(
                                        """INSERT INTO scraped_prices
                                               (id, supplier_name, medida, marca, modelo, price, load_index, scraped_at)
                                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                                        str(uuid.uuid4()), supplier['name'], medida,
                                        prod.get('brand', '').upper(),
                                        prod.get('model', ''),
                                        prod.get('price'),
                                        prod.get('load_index', ''),
                                        now,
                                    )
                                print(f"  [Andres] {medida}: guardados {len(products)} produtos")
                            elif result.get('price') is not None:
                                await conn_save.execute(
                                    """INSERT INTO scraped_prices
                                           (id, supplier_name, medida, price, scraped_at)
                                       VALUES ($1,$2,$3,$4,$5)""",
                                    str(uuid.uuid4()), supplier['name'], medida,
                                    result['price'], now,
                                )
                                print(f"  [Andres] {medida}: €{result['price']} (sem dados marca)")
                            else:
                                print(f"  [Andres] {medida}: sem produtos — registos antigos apagados")
                        finally:
                            await conn_save.close()

                        _err = result.get('error') or ''
                        _np  = len(result.get('products', []))
                        _and_summary.append(f"{medida}:{_np}p{'(ERR)' if _err else ''}")

                    except asyncio.TimeoutError:
                        print(f"  [Andres] Timeout em {medida}")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": "timeout"})
                        _and_summary.append(f"{medida}:TIMEOUT")
                    except Exception as _e_and:
                        print(f"  [Andres] Erro em {medida}: {_e_and}")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": str(_e_and)})
                        _and_summary.append(f"{medida}:ERR")
                    finally:
                        await _and_page.close()

                print(f"  [Andres] RESUMO: {' | '.join(_and_summary)}")
                await _and_browser.close()
            continue  # Skip the generic per-medida loop below

        # ── ABTyres: sessão única para todas as medidas ─────────────────────
        # Login uma vez; cada medida navega directamente para /pneus e pesquisa.
        if 'abtyres' in supplier_name:
            _abt_ctx_kwargs = dict(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='pt-PT',
            )
            async with async_playwright() as _p_abt:
                _abt_browser = await _p_abt.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox',
                          '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                _abt_ctx = await _abt_browser.new_context(**_abt_ctx_kwargs)
                _abt_first = True
                _abt_summary = []

                for medida in medidas:
                    _abt_page = await _abt_ctx.new_page()
                    await _abt_page.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
                    )
                    try:
                        result = await asyncio.wait_for(
                            scrape_abtyres(
                                _abt_page,
                                supplier['username'], supplier['password'],
                                medida,
                                skip_login=(not _abt_first),
                            ),
                            timeout=180,
                        )
                        _abt_first = False
                        result["medida"] = medida
                        results.append(result)

                        products = result.get('products', [])
                        now = datetime.now(timezone.utc)
                        conn_save = await _pg_connect()
                        try:
                            await conn_save.execute(
                                "DELETE FROM scraped_prices WHERE supplier_name=$1 AND medida=$2",
                                supplier['name'], medida,
                            )
                            if products:
                                for prod in products:
                                    await conn_save.execute(
                                        """INSERT INTO scraped_prices
                                               (id, supplier_name, medida, marca, modelo, price, load_index, scraped_at)
                                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                                        str(uuid.uuid4()), supplier['name'], medida,
                                        prod.get('brand', '').upper(),
                                        prod.get('model', ''),
                                        prod.get('price'),
                                        prod.get('load_index', ''),
                                        now,
                                    )
                                print(f"  [ABTyres] {medida}: guardados {len(products)} produtos")
                            elif result.get('price') is not None:
                                await conn_save.execute(
                                    """INSERT INTO scraped_prices
                                           (id, supplier_name, medida, price, scraped_at)
                                       VALUES ($1,$2,$3,$4,$5)""",
                                    str(uuid.uuid4()), supplier['name'], medida,
                                    result['price'], now,
                                )
                                print(f"  [ABTyres] {medida}: €{result['price']} (sem dados marca)")
                            else:
                                print(f"  [ABTyres] {medida}: sem produtos — registos antigos apagados")
                        finally:
                            await conn_save.close()

                        _err = result.get('error') or ''
                        _np  = len(result.get('products', []))
                        _abt_summary.append(f"{medida}:{_np}p{'(ERR)' if _err else ''}")

                    except asyncio.TimeoutError:
                        print(f"  [ABTyres] Timeout em {medida}")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": "timeout"})
                        _abt_summary.append(f"{medida}:TIMEOUT")
                    except Exception as _e_abt:
                        print(f"  [ABTyres] Erro em {medida}: {_e_abt}")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": str(_e_abt)})
                        _abt_summary.append(f"{medida}:ERR")
                    finally:
                        await _abt_page.close()

                print(f"  [ABTyres] RESUMO: {' | '.join(_abt_summary)}")
                await _abt_browser.close()
            continue  # Skip the generic per-medida loop below

        # ── Pneus Cruzeiro: sessão única para todas as medidas ──────────────
        # Login só uma vez (reCAPTCHA invisible resolve automaticamente);
        # cada medida usa uma página nova no mesmo contexto autenticado.
        if 'cruzeiro' in supplier_name:
            _crz_ctx_kwargs = dict(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='pt-PT',
            )
            _crz_url_login  = supplier.get('url_login')  or 'https://www.pneuscruzeiro.pt/pt/login'
            _crz_url_search = supplier.get('url_search') or 'https://www.pneuscruzeiro.pt/pt/privatearea'

            # Targets Cruzeiro: um por (medida, marca) — dedupados
            # O site tem dropdown FABRICANTE, por isso pesquisamos por marca separadamente
            _crz_pairs: list = []
            _crz_seen_pairs: set = set()
            for _m in medidas:
                _brands = {bi['marca'].upper() for bi in medida_items.get(_m, []) if bi.get('marca')}
                if _brands:
                    for _b in sorted(_brands):
                        if (_m, _b) not in _crz_seen_pairs:
                            _crz_seen_pairs.add((_m, _b))
                            _crz_pairs.append((_m, _b))
                else:
                    if (_m, '') not in _crz_seen_pairs:
                        _crz_seen_pairs.add((_m, ''))
                        _crz_pairs.append((_m, ''))
            print(f"  [Cruzeiro] {len(_crz_pairs)} pesquisas (medida+fabricante): {_crz_pairs[:8]}")

            async with async_playwright() as _p_crz:
                _crz_browser = await _p_crz.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox',
                          '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                _crz_ctx   = await _crz_browser.new_context(**_crz_ctx_kwargs)
                _crz_first = True
                _crz_summary = []
                _crz_deleted_medidas: set = set()  # medidas já limpas na BD nesta sessão

                for medida, marca in _crz_pairs:
                    _crz_page = await _crz_ctx.new_page()
                    await _crz_page.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
                    )
                    try:
                        result = await asyncio.wait_for(
                            scrape_pneus_cruzeiro(
                                _crz_page,
                                supplier['username'], supplier['password'],
                                medida,
                                _crz_url_login, _crz_url_search,
                                skip_login=(not _crz_first),
                                marca=marca,
                            ),
                            timeout=90,
                        )
                        _crz_first = False
                        result["medida"] = medida
                        results.append(result)

                        # ── Guardar na BD ──────────────────────────────────
                        products = result.get('products', [])
                        now = datetime.now(timezone.utc)
                        conn_save = await _pg_connect()
                        try:
                            if products:
                                # Apagar TODOS os registos antigos desta medida na primeira
                                # pesquisa bem-sucedida — evita mistura de datas/marcas antigas.
                                # Cada medida tem múltiplas pesquisas (uma por marca), por isso
                                # rastreamos quais medidas já foram limpas nesta sessão.
                                if medida not in _crz_deleted_medidas:
                                    await conn_save.execute(
                                        "DELETE FROM scraped_prices WHERE supplier_name=$1 AND medida=$2",
                                        supplier['name'], medida,
                                    )
                                    _crz_deleted_medidas.add(medida)
                                for prod in products:
                                    await conn_save.execute(
                                        """INSERT INTO scraped_prices
                                               (id, supplier_name, medida, marca, modelo, price, load_index, scraped_at)
                                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                                        str(uuid.uuid4()), supplier['name'], medida,
                                        prod.get('brand', '').upper(),
                                        prod.get('model', ''),
                                        prod.get('price'), prod.get('load_index', ''), now,
                                    )
                                print(f"  [Cruzeiro] {medida}: guardados {len(products)} produtos")
                            else:
                                await conn_save.execute(
                                    "DELETE FROM scraped_prices WHERE supplier_name=$1 AND medida=$2 AND marca IS NULL",
                                    supplier['name'], medida,
                                )
                                if result.get('price') is not None:
                                    await conn_save.execute(
                                        """INSERT INTO scraped_prices
                                               (id, supplier_name, medida, price, scraped_at)
                                           VALUES ($1,$2,$3,$4,$5)""",
                                        str(uuid.uuid4()), supplier['name'], medida,
                                        result['price'], now,
                                    )
                                print(f"  [Cruzeiro] {medida}: €{result.get('price')} (sem dados marca)")
                        finally:
                            await conn_save.close()

                        _err = result.get('error') or ''
                        _np  = len(result.get('products', []))
                        _crz_summary.append(f"{medida}:{_np}p{'(ERR)' if _err else ''}")

                    except asyncio.TimeoutError:
                        print(f"  [Cruzeiro] Timeout em {medida}")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": "timeout"})
                        _crz_summary.append(f"{medida}:TIMEOUT")
                    except Exception as e:
                        print(f"  [Cruzeiro] Erro em {medida}: {e}")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": str(e)})
                        _crz_summary.append(f"{medida}:ERR")
                    finally:
                        await _crz_page.close()

                print(f"  [Cruzeiro] RESUMO: {' | '.join(_crz_summary)}")
            continue  # Skip the generic per-medida loop below

        # ── MP24: sessão única para todas as medidas ──────────────────────────
        if 'mp24' in supplier_name:
            _mp24_ctx_kwargs = dict(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='pt-PT',
            )
            async with async_playwright() as _p_mp24:
                _mp24_browser = await _p_mp24.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox',
                          '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                _mp24_ctx = await _mp24_browser.new_context(**_mp24_ctx_kwargs)
                _mp24_first = True
                _mp24_summary = []

                for medida, _, _ in targets:
                    _mp24_page = await _mp24_ctx.new_page()
                    await _mp24_page.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
                    )
                    try:
                        result = await asyncio.wait_for(
                            scrape_mp24_with_session(
                                _mp24_page,
                                supplier['username'], supplier['password'],
                                medida,
                                already_logged_in=(not _mp24_first),
                            ),
                            timeout=120,
                        )
                        _mp24_first = False
                        result["medida"] = medida
                        results.append(result)

                        products = result.get('products', [])
                        now = datetime.now(timezone.utc)
                        conn_save = await _pg_connect()
                        try:
                            await conn_save.execute(
                                "DELETE FROM scraped_prices WHERE supplier_name=$1 AND medida=$2",
                                supplier['name'], medida,
                            )
                            if products:
                                for prod in products:
                                    await conn_save.execute(
                                        """INSERT INTO scraped_prices
                                               (id, supplier_name, medida, marca, modelo, price, load_index, scraped_at)
                                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                                        str(uuid.uuid4()), supplier['name'], medida,
                                        prod.get('brand', '').upper(),
                                        prod.get('model', ''),
                                        prod.get('price'),
                                        prod.get('load_index', ''),
                                        now,
                                    )
                                print(f"  [MP24] {medida}: guardados {len(products)} produtos")
                            elif result.get('price') is not None:
                                await conn_save.execute(
                                    """INSERT INTO scraped_prices
                                           (id, supplier_name, medida, price, scraped_at)
                                       VALUES ($1,$2,$3,$4,$5)""",
                                    str(uuid.uuid4()), supplier['name'], medida,
                                    result['price'], now,
                                )
                                print(f"  [MP24] {medida}: €{result['price']} (sem dados marca)")
                            else:
                                print(f"  [MP24] {medida}: sem produtos")
                        finally:
                            await conn_save.close()

                        _err = result.get('error') or ''
                        _np = len(result.get('products', []))
                        _mp24_summary.append(f"{medida}:{_np}p{'(ERR)' if _err else ''}")

                    except asyncio.TimeoutError:
                        print(f"  [MP24] Timeout em {medida}")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": "timeout"})
                        _mp24_summary.append(f"{medida}:TIMEOUT")
                        _mp24_first = True  # forçar re-login na próxima medida
                    except Exception as _e_mp24:
                        print(f"  [MP24] Erro em {medida}: {_e_mp24}")
                        results.append({"supplier": supplier['name'], "medida": medida, "error": str(_e_mp24)})
                        _mp24_summary.append(f"{medida}:ERR")
                    finally:
                        try:
                            await _mp24_page.close()
                        except Exception:
                            pass

                print(f"  [MP24] RESUMO: {' | '.join(_mp24_summary)}")
                await _mp24_browser.close()
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
                        result = await scrape_abtyres(page, supplier['username'], supplier['password'], medida)
                    elif is_tuga:
                        result = await scrape_tugapneus(page, supplier['username'], supplier['password'], medida, marca, modelo)
                    elif 'inter-sprint' in supplier_name or 'intersprint' in supplier_name:
                        result = await scrape_inter_sprint(page, supplier['username'], supplier['password'], medida, marca, modelo)
                    elif 'cruzeiro' in supplier_name:
                        result = await scrape_pneus_cruzeiro(
                            page, supplier['username'], supplier['password'], medida,
                            supplier.get('url_login', ''), supplier.get('url_search', ''),
                        )
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
                                prod_indice = prod.get('load_index', '') or prod.get('indice') or ''
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
                    result = await scrape_abtyres(page, username, password, medida)
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
