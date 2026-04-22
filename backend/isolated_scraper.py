#!/usr/bin/env python3
"""
Isolated scraper runner - executes scraping in a separate process
This bypasses anti-bot detection that affects the FastAPI server context
"""
import asyncio
import json
import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

from playwright.async_api import async_playwright

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
    """Normalize tire size"""
    return medida.replace('/', '').replace('R', '').replace('r', '')

async def scrape_mp24(username: str, password: str, medida: str) -> dict:
    """Scrape MP24 in isolated context"""
    result = {"supplier": "MP24", "price": None, "error": None}
    
    debug_log = open('/app/tmp/mp24_subprocess_debug.log', 'w')  # Overwrite each time
    debug_log.write(f"=== MP24 scrape: {medida} ===\n")
    
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
            # Login
            await page.goto("https://pt.mp24.online/pt_PT", wait_until="networkidle", timeout=60000)
            debug_log.write(f"On login page: {page.url}\n")
            
            # Fill credentials
            await page.fill('input[name="_username"]', username)
            await page.fill('input[name="_password"]', password)
            debug_log.write("Credentials filled\n")
            
            # Try multiple submission methods
            # Method 1: Click the login link
            try:
                await page.click('a:has-text("Início de sessão")')
                debug_log.write("Clicked login link\n")
            except:
                debug_log.write("Click failed, trying JS submit\n")
                # Method 2: Submit form via JavaScript
                await page.evaluate("document.getElementById('login_form').submit()")
            
            # Wait for navigation
            await asyncio.sleep(4)
            
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass
            
            debug_log.write(f"After login: {page.url}\n")
            
            # Navigate directly to tyres page
            await page.goto("https://pt.mp24.online/pt_PT/tyres/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            
            current_url = page.url
            debug_log.write(f"On tyres: {current_url}\n")
            
            content = await page.content()
            has_matchcode = 'matchcodeField' in content
            debug_log.write(f"has_matchcode: {has_matchcode}\n")
            
            # Save debug page
            with open('/app/tmp/mp24_page.html', 'w') as f:
                f.write(content)
            
            if has_matchcode:
                medida_normalized = normalize_medida(medida)
                await page.fill('#matchcodeField', medida_normalized)
                await asyncio.sleep(1)
                
                # Submit search
                try:
                    await page.click('button[type="submit"]')
                except:
                    await page.press('#matchcodeField', 'Enter')
                
                await asyncio.sleep(5)
                await page.wait_for_load_state("networkidle")
                
                content = await page.content()
                prices = extract_prices(content)
                debug_log.write(f"Prices: {prices[:5] if prices else 'none'}\n")
                
                if prices:
                    result["price"] = min(prices)
            else:
                # Check if we're on login page
                if 'login' in current_url.lower() or 'conecte-se' in content.lower():
                    result["error"] = "Login failed - session expired"
                else:
                    result["error"] = "matchcodeField not found"
                debug_log.write(f"ERROR: {result['error']}\n")
                
        except Exception as e:
            result["error"] = str(e)
            debug_log.write(f"EXCEPTION: {e}\n")
        finally:
            await browser.close()
            debug_log.write("Done\n")
            debug_log.close()
    
    return result

async def scrape_prismanil(username: str, password: str, medida: str) -> dict:
    """Scrape Prismanil in isolated context"""
    result = {"supplier": "Prismanil", "price": None, "error": None}
    
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
            # Login
            await page.goto("https://www.prismanil.pt/b2b/pesquisa", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            
            # Check if need to login
            content = await page.content()
            if "txtPesquisa" not in content:
                # Need to login
                username_input = page.locator('input[type="text"]').first
                if await username_input.count() > 0:
                    await username_input.fill(username)
                
                password_input = page.locator('input[type="password"]').first
                if await password_input.count() > 0:
                    await password_input.fill(password)
                
                submit_btn = page.locator('button:has-text("Entrar")').first
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                else:
                    await password_input.press("Enter")
                
                await asyncio.sleep(5)
                await page.wait_for_load_state("networkidle")
            
            medida_normalized = normalize_medida(medida)
            
            # Search
            search_input = page.locator('#txtPesquisa')
            if await search_input.count() > 0:
                await search_input.fill(medida_normalized)
                await asyncio.sleep(1)
                
                search_btn = page.locator('#btnPesquisar')
                if await search_btn.count() > 0:
                    await search_btn.click()
                else:
                    await search_input.press("Enter")
                
                await asyncio.sleep(5)
                await page.wait_for_load_state("networkidle")
                
                content = await page.content()
                prices = extract_prices(content)
                
                if prices:
                    result["price"] = min(prices)
            else:
                result["error"] = "txtPesquisa not found"
                
        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()
    
    return result

async def scrape_dispnal(username: str, password: str, medida: str) -> dict:
    """Scrape Dispnal in isolated context"""
    result = {"supplier": "Dispnal", "price": None, "error": None}
    
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
            # Go to homepage
            await page.goto("https://dispnal.pt/home/homepage", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            
            content = await page.content()
            
            # Check if we need to login first
            if 'Entrar' in content or 'Login' in content:
                # Look for login link/button
                login_link = page.locator('a:has-text("Entrar"), a:has-text("Login")')
                if await login_link.count() > 0:
                    await login_link.first.click()
                    await asyncio.sleep(2)
                
                # Fill email
                email_input = page.locator('input[type="email"], input[name*="email"]').first
                if await email_input.count() > 0:
                    await email_input.fill(username)
                else:
                    # Try text input
                    text_input = page.locator('input[type="text"]').first
                    if await text_input.count() > 0:
                        await text_input.fill(username)
                
                # Fill password
                password_input = page.locator('input[type="password"]').first
                if await password_input.count() > 0:
                    await password_input.fill(password)
                
                await asyncio.sleep(1)
                
                # Submit
                submit_btn = page.locator('button[type="submit"], input[type="submit"]').first
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                else:
                    await password_input.press("Enter")
                
                await asyncio.sleep(5)
                await page.wait_for_load_state("networkidle")
            
            # Now on homepage - use the medida search field
            medida_normalized = normalize_medida(medida)
            
            # The search field is #medida-normal with placeholder "Ex: 2245417"
            medida_input = page.locator('#medida-normal')
            if await medida_input.count() > 0:
                await medida_input.fill(medida_normalized)
                await asyncio.sleep(1)
                
                # Submit the search form
                search_btn = page.locator('button[type="submit"], .btn-search, button:has-text("Pesquisar")')
                if await search_btn.count() > 0:
                    await search_btn.first.click()
                else:
                    await medida_input.press("Enter")
                
                await asyncio.sleep(5)
                await page.wait_for_load_state("networkidle")
                
                content = await page.content()
                
                # Save for debugging
                with open("/app/tmp/dispnal_results.html", 'w') as f:
                    f.write(content)
                
                prices = extract_prices(content)
                
                if prices:
                    result["price"] = min(prices)
                else:
                    # Check current URL for debugging
                    result["error"] = f"No prices found. URL: {page.url}"
            else:
                result["error"] = "medida-normal input not found"
                
        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()
    
    return result

async def scrape_sjose(username: str, password: str, medida: str) -> dict:
    """Scrape S. José in isolated context"""
    result = {"supplier": "S. José Pneus", "price": None, "error": None}
    
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
            await page.goto("https://b2b.sjosepneus.com/default.aspx", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            
            # Fill login
            username_input = page.locator('input[type="text"]').first
            if await username_input.count() > 0:
                await username_input.fill(username)
            
            password_input = page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(password)
                await password_input.press("Enter")
            
            await asyncio.sleep(5)
            
            medida_normalized = normalize_medida(medida)
            
            # Search
            search_input = page.locator('input[type="text"]').first
            if await search_input.count() > 0:
                await search_input.fill(medida_normalized)
                await search_input.press("Enter")
                
                await asyncio.sleep(5)
                
                content = await page.content()
                prices = extract_prices(content)
                
                if prices:
                    result["price"] = min(prices)
                    
        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()
    
    return result

async def scrape_euromais(username: str, password: str, medida: str) -> dict:
    """Scrape Euromais in isolated context"""
    result = {"supplier": "euromais", "price": None, "error": None}
    
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
            await page.goto("https://www.eurotyre.pt/", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            
            # Login - Euromais uses specific form
            username_input = page.locator('input[type="text"], input[type="email"]').first
            if await username_input.count() > 0:
                await username_input.fill(username)
            
            password_input = page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(password)
                await password_input.press("Enter")
            
            await asyncio.sleep(5)
            
            # Check for search
            medida_normalized = normalize_medida(medida)
            
            search_input = page.locator('input[type="search"], input[name*="search"]').first
            if await search_input.count() > 0:
                await search_input.fill(medida_normalized)
                await search_input.press("Enter")
                
                await asyncio.sleep(5)
                
                content = await page.content()
                prices = extract_prices(content)
                
                if prices:
                    result["price"] = min(prices)
            else:
                result["error"] = "Search not found"
                    
        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()
    
    return result

async def scrape_tugapneus(username: str, password: str, medida: str,
                           marca: str = '', modelo: str = '') -> dict:
    """Scrape TugaPneus — isolated process version"""
    result = {
        "supplier": "TugaPneus",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    medida_norm = normalize_medida(medida)
    _m = re.match(r'^(\d{3})(\d{2})(\d{2})$', medida_norm)
    medida_slashed = f"{_m.group(1)}/{_m.group(2)}R{_m.group(3)}" if _m else medida_norm

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                  '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")

        try:
            # Login
            await page.goto("https://www.tugapneus.pt/login", wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            await asyncio.sleep(3)

            if 'login' in page.url.lower():
                email_input = page.locator(
                    'input[type="email"], input[name="email"], input[name*="mail"], '
                    'input[name="username"], input[type="text"]'
                ).first
                if await email_input.count() > 0:
                    await email_input.click()
                    await email_input.type(username, delay=80)
                password_input = page.locator('input[type="password"]').first
                if await password_input.count() > 0:
                    await password_input.click()
                    await password_input.type(password, delay=80)
                await asyncio.sleep(0.5)
                # O botão chama-se "EFETUAR LOGIN"
                submit_btn = page.locator(
                    'button:has-text("EFETUAR LOGIN"), '
                    'button:has-text("Efetuar Login"), '
                    'button[type="submit"], input[type="submit"], '
                    'button:has-text("Login"), button:has-text("Entrar"), '
                    'a:has-text("EFETUAR LOGIN")'
                ).first
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                else:
                    await page.keyboard.press("Enter")

                # Aguardar até o campo password desaparecer (login AJAX)
                for _i in range(40):  # até 20 segundos
                    await asyncio.sleep(0.5)
                    if await page.locator('input[type="password"]').count() == 0:
                        break
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                await asyncio.sleep(2)

                # Tratar popup obrigatório "TOMEI CONHECIMENTO"
                try:
                    popup_btn = page.locator(
                        'button:has-text("TOMEI CONHECIMENTO"), '
                        'button:has-text("Tomei Conhecimento"), '
                        'a:has-text("TOMEI CONHECIMENTO"), '
                        '[class*="modal"] button, [role="dialog"] button'
                    ).first
                    if await popup_btn.count() > 0:
                        await popup_btn.click()
                        await asyncio.sleep(2)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            pass
                    else:
                        await asyncio.sleep(3)
                        if await popup_btn.count() > 0:
                            await popup_btn.click()
                            await asyncio.sleep(2)
                except Exception:
                    pass

                url_after = page.url
                pw_visible = await page.locator('input[type="password"]').count() > 0
                url_ok = 'produtos' in url_after.lower() or 'conhecimento' in url_after.lower()
                if pw_visible and not url_ok:
                    result["error"] = f"Login falhou (URL: {url_after})"
                    return result

            # Se já redireccionou para /produtos após o popup, não navegar de novo
            if 'produtos' not in page.url.lower():
                await page.goto("https://www.tugapneus.pt/produtos", wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                await asyncio.sleep(3)

            if 'login' in page.url.lower():
                result["error"] = "Redireccionado para login na página de produtos"
                return result

            # Pesquisa progressiva TugaPneus
            # Nível 1: "pneu [marca] [medida] [modelo]"  (se disponíveis)
            # Nível 2: "pneu [marca] [medida]"
            # Nível 3: "[medida]"  (formato 205/60R16)
            _terms: list = []
            if marca and modelo:
                _terms.append(f"pneu {marca} {medida_slashed} {modelo}".lower())
            if marca:
                _terms.append(f"pneu {marca} {medida_slashed}".lower())
            _terms.append(medida_slashed)

            _search_input = None
            for _sel in [
                'input[type="search"]', 'input[name*="search" i]',
                'input[name*="pesq" i]', 'input[placeholder*="pesq" i]',
                '#search', 'input[type="text"]',
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
                        'button[type="submit"], .search-btn'
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

                # Aguarda que a página carregue e verifica no HTML bruto
                await asyncio.sleep(5)
                _html = await page.content()
                if re.search(r'PNEU\s+\w', _html, re.IGNORECASE):
                    print(f"  [TugaPneus] Dados encontrados no HTML com '{_term}'")
                    _found = True
                    break
                print(f"  [TugaPneus] Sem 'PNEU...' no HTML para '{_term}', próximo nível...")

            content = await page.content()

            # ── Extracção via Python regex sobre HTML bruto ───────────────
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
                print(f"  [TugaPneus] {len(products)} produtos extraídos do HTML, melhor €{result['price']}")
                for p in products[:5]:
                    print(f"    {p['brand']} {p['medida']} {p['indice']} {p['model']} → €{p['price']}")
            else:
                prices = extract_prices(content)
                if prices:
                    result["price"] = min(prices)
                    result["all_prices"] = sorted(prices)[:10]
                    print(f"  [TugaPneus] Fallback preços: {len(prices)}, melhor €{result['price']}")
                else:
                    result["error"] = "No products found"

        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()

    return result


async def scrape_intersprint(username: str, password: str, medida: str,
                              marca: str = '', modelo: str = '', indice: str = '') -> dict:
    """Scrape Inter-Sprint B2B portal — versão isolated process.

    O portal customers.inter-sprint.nl usa HTTP Basic Auth.
    O contexto Playwright é criado com http_credentials para responder
    automaticamente ao challenge 401.
    """
    result = {
        "supplier": "InterSprint",
        "price": None,
        "error": None,
        "products": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    medida_norm = normalize_medida(medida)
    _m = re.match(r'^(\d{3})(\d{2})(\d{2})$', medida_norm)
    medida_fmt = f"{_m.group(1)}/{_m.group(2)}R{_m.group(3)}" if _m else medida_norm
    marca_upper = (marca or '').strip().upper()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox',
                  '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
        )
        # http_credentials: Playwright responde automaticamente ao HTTP Basic Auth 401
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
            http_credentials={'username': username, 'password': password},
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")

        try:
            _search_url = "https://customers.inter-sprint.nl/#ecommerce"
            print(f"  [InterSprint] Navegando para {_search_url} (Basic Auth via contexto)")
            await page.goto(_search_url, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await asyncio.sleep(2)

            # Guardar HTML para debug
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

            # Caso o portal tenha também formulário HTML de login (além de Basic Auth)
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

            # ── Detectar frame principal (portal usa <frameset>) ──────────
            await asyncio.sleep(3)
            _ctx = page  # fallback
            _named_frame = page.frame(name="mainFrame")
            if _named_frame:
                _ctx = _named_frame
                print(f"  [InterSprint] Frame 'mainFrame' detectado: {_named_frame.url}")
            else:
                for _fr in page.frames:
                    if _fr.url and 'cgirpc32' in _fr.url:
                        _ctx = _fr
                        print(f"  [InterSprint] Frame detectado: {_fr.url}")
                        break

            _all_frames = [(f.name, f.url) for f in page.frames]
            print(f"  [InterSprint] Todos os frames: {_all_frames}")
            print(f"  [InterSprint] _ctx tipo: {'Frame' if _ctx is not page else 'Page'}, URL: {_ctx.url}")

            # Guardar conteúdo do frame para debug
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

            # Helpers
            async def _limpar():
                for sel in [
                    'form[name="f"] input[name="artkode"]',
                    'input[name="lisi"]',
                ]:
                    el = _ctx.locator(sel).first
                    if await el.count() > 0:
                        await el.clear()
                msel = _ctx.locator(
                    'select[name="merk"], select[id*="marca" i], select[name*="marca" i], '
                    'select[id*="brand" i], select[name*="brand" i]'
                ).first
                if await msel.count() > 0:
                    try:
                        await msel.select_option(index=0)
                    except Exception:
                        pass

            async def _tem_resultados() -> bool:
                content = await _ctx.content()
                return bool(re.search(
                    r'€\s*\d+[,.]\d{2}|\d+[,.]\d{2}\s*€|&nbsp;\s*\d+,\d{2}\s*&nbsp;',
                    content
                ))

            async def _pesquisar(use_marca: bool, use_indice: bool, medida_str: str = None) -> bool:
                _val = medida_str or medida_norm
                artigo = _ctx.locator('form[name="f"] input[name="artkode"]')
                if await artigo.count() == 0:
                    artigo = _ctx.locator('input[name="artkode"][class="form2"]')
                if await artigo.count() == 0:
                    print(f"  [InterSprint] Campo artkode (form f) não encontrado")
                    return False
                await artigo.first.clear()
                await artigo.first.fill(_val)
                artigo = artigo.first

                if use_marca and marca_upper:
                    msel = _ctx.locator(
                        'select[name="merk"], select[id*="marca" i], select[name*="marca" i], '
                        'select[id*="brand" i], select[name*="brand" i]'
                    ).first
                    if await msel.count() > 0:
                        try:
                            opts = await msel.evaluate(
                                'el => Array.from(el.options).map(o => ({value: o.value, text: o.text}))'
                            )
                            matched = next(
                                (o['value'] for o in opts if marca_upper in o['text'].upper()), None
                            )
                            if matched is not None:
                                await msel.select_option(value=str(matched))
                        except Exception:
                            pass

                if use_indice and indice:
                    lisi = _ctx.locator(
                        'input[name="lisi"], input[placeholder*="LI" i], input[id*="lisi" i]'
                    ).first
                    if await lisi.count() > 0:
                        await lisi.clear()
                        await lisi.fill(indice)

                btn = _ctx.locator(
                    'button:has-text("Procura"), input[value*="Procura" i], '
                    'button:has-text("Search"), input[value*="Search" i], '
                    'button:has-text("Zoeken"), input[value*="Zoeken" i], '
                    'button:has-text("Zoek"), input[value*="Zoek" i], '
                    'button[type="submit"], input[type="submit"]'
                ).first
                if await btn.count() > 0:
                    await btn.click()
                else:
                    await artigo.press("Enter")

                await asyncio.sleep(5)
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                await asyncio.sleep(1)
                return await _tem_resultados()

            print(f"  [InterSprint] Pesquisa: medida_norm={medida_norm} medida_fmt={medida_fmt} marca={marca_upper} indice={indice}")
            found = False
            if marca_upper and indice:
                if await _pesquisar(True, True):
                    found = True
            if not found and marca_upper:
                await _limpar()
                if await _pesquisar(True, False):
                    found = True
            if not found:
                await _limpar()
                if await _pesquisar(False, False):
                    found = True
            # Nível 4: formato 205/55R16 se dígitos não funcionaram
            if not found and medida_fmt != medida_norm:
                await _limpar()
                if await _pesquisar(False, False, medida_str=medida_fmt):
                    found = True

            if not found:
                result["error"] = "Sem resultados"
                return result

            content = await _ctx.content()
            products = _parse_intersprint_isolated(content, marca_upper)

            if products:
                result["products"] = products
                result["price"] = min(p['price'] for p in products)
                result["all_prices"] = sorted(p['price'] for p in products)[:10]
                print(f"  [InterSprint] {len(products)} produtos, melhor €{result['price']}")
            else:
                prices = extract_prices(content)
                if prices:
                    result["price"] = min(prices)
                    result["all_prices"] = sorted(prices)[:10]
                else:
                    result["error"] = "Produtos não encontrados"

        except Exception as e:
            result["error"] = str(e)
            print(f"  [InterSprint] Error: {e}")
        finally:
            await browser.close()

    return result


def _parse_intersprint_isolated(html: str, search_brand: str = '') -> list:
    """Parse HTML resultados InterSprint (versão isolated).

    Estrutura da tabela: Marca | Descricao | ... | LI/SI | ... | EUR
    Descricao format: "{size} {[A-Z]?R}{rim} TL {LI/SI} {brand_abbr} {model}"
    Exemplo: "205/55 VR16 TL 94V SUNNY NP226 XL"

    FIXES v5 (em sync com run_scraper._parse_intersprint_html):
    - Decode &nbsp; e outras entidades HTML antes dos regexes.
    - medida_re e indice_re mais flexíveis (espaços opcionais).
    - Context tracking para tabelas com rowspan.
    search_brand: fallback quando a célula da marca está vazia.
    """
    products: list = []
    seen: set = set()
    _no_medida_dbg: list = []

    price_re = re.compile(
        r'€\s*(\d+[,.]\d{2})|(\d+[,.]\d{2})\s*€|&nbsp;\s*(\d+[,.]\d{2})\s*&nbsp;',
        re.IGNORECASE
    )
    medida_re = re.compile(r'(\d{3}/\d{2})\s*[A-Z]?\s*R\s*(\d{2})\b', re.IGNORECASE)
    indice_re = re.compile(r'\b(\d{2,3}\s*[A-Z]{1,2}(?:\s*XL)?)\b')
    tag_re    = re.compile(r'<[^>]+>')
    row_re    = re.compile(r'<tr[^>]*>(.*?)</tr>', re.IGNORECASE | re.DOTALL)

    _ctx_brand  = ''
    _ctx_medida = ''
    _ctx_indice = ''
    _ctx_model  = ''

    def _decode_entities(text: str) -> str:
        text = text.replace('&#47;', '/').replace('&amp;', '&')
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>')
        text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
        text = re.sub(r'&\w+;', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()

    def _extract_model(row_text: str, after_pos: int, brand: str) -> str:
        rem = row_text[after_pos:]
        rem = price_re.sub('', rem)
        rem = re.sub(r'\bTL\b|\bTW\b', ' ', rem, flags=re.IGNORECASE)
        rem = re.sub(r'\b\d{2,3}\s*[A-Z]{1,2}(?:\s*XL)?\b', ' ', rem)
        rem = re.sub(r'\b\d+\b', ' ', rem)
        rem = re.sub(r'\s+', ' ', rem).strip()
        parts = rem.upper().split()
        if parts:
            first = parts[0]
            if (first == brand
                    or brand.startswith(first)
                    or (len(first) <= 3 and first.isalpha())):
                parts = parts[1:]
        return ' '.join(parts)[:60].strip()

    for row_m in row_re.finditer(html):
        raw = re.sub(r'\s+', ' ', tag_re.sub(' ', row_m.group(1))).strip()
        if len(raw) < 5:
            continue

        row_text = _decode_entities(raw)
        if len(row_text) < 10:
            continue

        medida_m = medida_re.search(row_text)
        if medida_m:
            g1 = medida_m.group(1).replace(' ', '')
            _ctx_medida = f"{g1}R{medida_m.group(2)}".upper()
            _ctx_brand  = row_text[:medida_m.start()].strip().upper()
            if not _ctx_brand:
                _ctx_brand = search_brand.upper() if search_brand else 'UNKNOWN'
            im = indice_re.search(row_text[medida_m.start():])
            _ctx_indice = im.group(1).upper().replace(' ', '') if im else ''
            _ctx_model  = _extract_model(row_text, medida_m.end(), _ctx_brand)
            if not _ctx_model and _ctx_indice:
                _ctx_model = _ctx_indice

        price_m = price_re.search(row_text)
        if not price_m:
            continue
        try:
            price = float((price_m.group(1) or price_m.group(2) or price_m.group(3)).replace(',', '.'))
        except ValueError:
            continue
        if not (15 < price < 800):
            continue

        medida_val = _ctx_medida
        brand_val  = _ctx_brand if _ctx_brand else (search_brand.upper() or 'UNKNOWN')
        indice_val = _ctx_indice
        model_val  = _ctx_model

        if not medida_val and len(_no_medida_dbg) < 3:
            _no_medida_dbg.append(row_text[:300])

        if not model_val and indice_val:
            model_val = indice_val

        key = f"{brand_val}|{medida_val}|{indice_val}|{price}"
        if key not in seen:
            seen.add(key)
            products.append({'brand': brand_val, 'medida': medida_val,
                             'indice': indice_val, 'model': model_val, 'price': price})

    print(f"  [InterSprint] _parse: {len(products)} produtos")
    if _no_medida_dbg:
        print(f"  [InterSprint] DEBUG linhas-sem-medida: {_no_medida_dbg}")
    return products


async def main():
    """Main entry point - expects JSON config from stdin"""
    # Read config from stdin
    config = json.loads(sys.stdin.read())
    
    supplier = config.get('supplier', '').lower()
    username = config.get('username', '')
    password = config.get('password', '')
    medida = config.get('medida', '')
    marca  = config.get('marca', '')
    modelo = config.get('modelo', '')

    if 'mp24' in supplier:
        result = await scrape_mp24(username, password, medida)
    elif 'prismanil' in supplier:
        result = await scrape_prismanil(username, password, medida)
    elif 'dispnal' in supplier:
        result = await scrape_dispnal(username, password, medida)
    elif 'sjose' in supplier or 'josé' in supplier:
        result = await scrape_sjose(username, password, medida)
    elif 'euromais' in supplier or 'eurotyre' in supplier:
        result = await scrape_euromais(username, password, medida)
    elif 'tugapneus' in supplier or 'tuga' in supplier:
        result = await scrape_tugapneus(username, password, medida, marca, modelo)
    elif 'intersprint' in supplier or 'inter-sprint' in supplier:
        result = await scrape_intersprint(username, password, medida, marca, modelo)
    else:
        result = {"supplier": supplier, "price": None, "error": f"Unknown supplier: {supplier}"}
    
    # Output result as JSON
    print(json.dumps(result))

if __name__ == "__main__":
    asyncio.run(main())
