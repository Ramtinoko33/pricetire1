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
        "timestamp": __import__('datetime').datetime.utcnow().isoformat()
    }

    medida_norm = normalize_medida(medida)
    _m = __import__('re').match(r'^(\d{3})(\d{2})(\d{2})$', medida_norm)
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

            async def _has_results() -> bool:
                # Detecção por "PNEU X..." em tr — não depende do símbolo € no textContent
                # (TugaPneus pode renderizar € via CSS ::after, invisible no textContent)
                return await page.evaluate(r'''() => {
                    const rows = [...document.querySelectorAll('tr')];
                    return rows.some(tr => /PNEU\s+\w/i.test(tr.textContent));
                }''')

            print(f"  [TugaPneus] Pesquisa progressiva: {_terms}")
            _found = False
            for _term in _terms:
                print(f"  [TugaPneus] Tentativa: '{_term}'")
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
                await asyncio.sleep(4)
                try:
                    await page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    pass
                if await _has_results():
                    print(f"  [TugaPneus] Resultados encontrados com '{_term}'")
                    _found = True
                    break
                print(f"  [TugaPneus] Sem resultados para '{_term}', próximo nível...")

            content = await page.content()

            # Check "sem resultados" — só termina se nenhuma tentativa funcionou
            no_results_texts = [
                "sem resultado", "nenhum registo", "não foram encontrados",
                "nenhum produto", "sem produtos", "0 resultado", "0 produtos"
            ]
            if not _found and any(t in content.lower() for t in no_results_texts):
                result["error"] = f"No products found for {medida_slashed}"
            else:
                # Parser estruturado: "PNEU MARCA MEDIDA ÍNDICE MODELO"
                # Ex: "PNEU MICHELIN 205/60R16 96H PRIMACY 5 XL"
                # Extracção de preço SEM depender de € no textContent
                # (TugaPneus pode renderizar € via CSS ::after)
                products = await page.evaluate(r'''() => {
                    const products = [];

                    function parseTugaDesc(raw) {
                        const text = raw.toUpperCase();
                        // PNEU [MARCA 1-2 palavras] [XXX/XXRXX] [ÍNDICE] [MODELO...]
                        const m = text.match(
                            /PNEU\s+([\w\-]+(?:\s+[\w\-]+)?)\s+(\d{3}\/\d{2}R\d{2})\s+(\d{2,3}[A-Z]{1,2}(?:\s+XL)?)\s*(.*)/
                        );
                        if (!m) return null;
                        return {
                            marca:  m[1].trim(),
                            medida: m[2].trim(),
                            indice: m[3].trim(),
                            modelo: m[4].trim()
                        };
                    }

                    function extractPrice(text) {
                        // Extrai todos os números decimais do texto (sem exigir €)
                        // e devolve o mais pequeno no intervalo [15, 800]
                        const nums = (text.match(/\d+[,.]\d{2}/g) || [])
                            .map(n => parseFloat(n.replace(',', '.')))
                            .filter(p => p > 15 && p < 800);
                        return nums.length ? Math.min(...nums) : null;
                    }

                    // Prioridade: linhas de tabela com "PNEU ..." (estrutura TugaPneus)
                    const productRows = [...document.querySelectorAll('tr')]
                        .filter(tr => /PNEU\s+\w/i.test(tr.textContent));

                    const source = productRows.length > 0
                        ? productRows
                        : [...document.querySelectorAll(
                            '.product, .product-item, .produto, [class*="product"], .item, .card'
                          )].filter(el => /PNEU\s+\w/i.test(el.textContent));

                    for (const el of source) {
                        const text = el.textContent || '';
                        const price = extractPrice(text);
                        if (price === null) continue;
                        const parsed = parseTugaDesc(text);
                        products.push({
                            brand:  parsed ? parsed.marca  : '',
                            model:  parsed ? parsed.modelo : '',
                            medida: parsed ? parsed.medida : '',
                            indice: parsed ? parsed.indice : '',
                            price
                        });
                    }

                    // Dedup: mesma marca+medida+índice+modelo → fica o mais barato
                    const seen = new Map();
                    for (const p of products) {
                        const k = `${p.brand}|${p.medida}|${p.indice}|${p.model}`;
                        if (!seen.has(k) || p.price < seen.get(k).price) seen.set(k, p);
                    }
                    return [...seen.values()];
                }''')

                if products:
                    result["products"] = products
                    result["price"] = min(p['price'] for p in products)
                    result["all_prices"] = sorted(p['price'] for p in products)[:10]
                    print(f"  [TugaPneus] {len(products)} produtos, melhor €{result['price']}")
                else:
                    # Fallback regex
                    prices = extract_prices(content)
                    if prices:
                        result["price"] = min(prices)
                        result["all_prices"] = sorted(prices)[:10]
                        print(f"  [TugaPneus] Fallback regex: {len(prices)} preços, melhor €{result['price']}")
                    else:
                        result["error"] = "No products found"

        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()

    return result


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
    else:
        result = {"supplier": supplier, "price": None, "error": f"Unknown supplier: {supplier}"}
    
    # Output result as JSON
    print(json.dumps(result))

if __name__ == "__main__":
    asyncio.run(main())
