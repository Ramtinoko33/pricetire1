#!/usr/bin/env python3
"""
Improved Playwright test for Prismanil - B2B tire supplier
"""
import asyncio
import re
import os
from pathlib import Path
from playwright.async_api import async_playwright

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

SCREENSHOTS_DIR = Path("/app/tmp/playwright_debug")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Prismanil credentials
PRISMANIL = {
    "url_login": "https://www.prismanil.pt/b2b/pesquisa",
    "username": "dpedrov287",
    "password": "dompedro4785"
}

def extract_prices(content: str) -> list:
    """Extract prices from HTML content"""
    price_patterns = [
        r'€\s*(\d+[,\.]\d{2})',
        r'(\d+[,\.]\d{2})\s*€',
        r'"preco"\s*:\s*"?(\d+[,\.]\d{2})"?',
        r'"price"\s*:\s*"?(\d+[,\.]\d{2})"?',
        r'(\d+\.\d{2})\s*EUR',
        r'class="[^"]*price[^"]*"[^>]*>(\d+[,\.]\d{2})',
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

async def test_prismanil_improved():
    """Test Prismanil with improved selectors"""
    print("\n" + "=" * 60)
    print("TESTING PRISMANIL - IMPROVED VERSION")
    print("=" * 60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
        )
        
        page = await context.new_page()
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        try:
            # Step 1: Navigate to login page
            print(f"\n[1] Navigating to {PRISMANIL['url_login']}...")
            await page.goto(PRISMANIL['url_login'], wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "prismanil_v2_01_initial.png"))
            
            # Step 2: Check if we need to login or already logged in
            content = await page.content()
            is_logged_in = "Pneus V.comercio" in content or "txtPesquisa" in content
            print(f"    Already logged in: {is_logged_in}")
            
            if not is_logged_in:
                # Fill login form
                print("\n[2] Filling login form...")
                
                # Find username input - typically first text input
                username_input = page.locator('input[type="text"]').first
                if await username_input.count() > 0:
                    await username_input.fill(PRISMANIL['username'])
                    print(f"    Username filled: {PRISMANIL['username']}")
                
                # Find password input
                password_input = page.locator('input[type="password"]').first
                if await password_input.count() > 0:
                    await password_input.fill(PRISMANIL['password'])
                    print("    Password filled")
                
                await page.screenshot(path=str(SCREENSHOTS_DIR / "prismanil_v2_02_form.png"))
                
                # Submit - look for Entrar button
                submit_btn = page.locator('button:has-text("Entrar"), input[type="submit"]').first
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                    print("    Clicked submit")
                else:
                    # Try pressing Enter
                    await password_input.press("Enter")
                    print("    Pressed Enter")
                
                await asyncio.sleep(5)
                await page.wait_for_load_state("networkidle")
            
            await page.screenshot(path=str(SCREENSHOTS_DIR / "prismanil_v2_03_logged_in.png"))
            
            # Step 3: Now search for tire
            print("\n[3] Searching for tire...")
            medida = "205/55R16"  # Format with / and R
            medida_normalized = "2055516"  # Without / and R
            
            # The Prismanil page has specific fields:
            # - #txtPesquisa (Pesquisa 1 - probably width like 205)
            # - #txtPesquisa2 (Pesquisa 2 - probably ratio like 55)
            # Or it might accept the full normalized medida
            
            # Try the main search field first
            search_input = page.locator('#txtPesquisa')
            if await search_input.count() > 0:
                await search_input.fill(medida_normalized)
                print(f"    Filled #txtPesquisa with: {medida_normalized}")
            else:
                # Fallback to placeholder search
                search_input = page.locator('input[placeholder*="Pesquisa"]').first
                if await search_input.count() > 0:
                    await search_input.fill(medida_normalized)
                    print(f"    Filled search placeholder with: {medida_normalized}")
            
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "prismanil_v2_04_search_filled.png"))
            
            # Click search button
            search_btn = page.locator('#btnPesquisar, button:has-text("Pesquisar"), a:has-text("Pesquisar")')
            if await search_btn.count() > 0:
                await search_btn.first.click()
                print("    Clicked Pesquisar button")
            else:
                # Try Enter
                await search_input.press("Enter")
                print("    Pressed Enter to search")
            
            # Wait for results
            print("\n[4] Waiting for results...")
            await asyncio.sleep(5)
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path=str(SCREENSHOTS_DIR / "prismanil_v2_05_results.png"))
            
            # Get page content
            content = await page.content()
            
            # Save HTML for debugging
            html_path = SCREENSHOTS_DIR / "prismanil_v2_results.html"
            with open(html_path, 'w') as f:
                f.write(content)
            print(f"    Saved HTML to: {html_path}")
            
            # Check for results
            print("\n[5] Analyzing results...")
            
            # Look for product elements
            product_indicators = [
                'class="card-body"',
                'pneu',
                'tire',
                'produto',
            ]
            has_products = any(ind in content.lower() for ind in product_indicators)
            print(f"    Has product indicators: {has_products}")
            
            # Extract prices
            prices = extract_prices(content)
            print(f"    Found {len(prices)} prices: {prices}")
            
            if prices:
                print(f"\n✅ SUCCESS! Best price: €{min(prices)}")
            else:
                print("\n❌ No prices found - checking for errors...")
                
                # Check for common issues
                if "sem resultado" in content.lower() or "nenhum" in content.lower():
                    print("    -> No results message detected")
                elif "login" in content.lower() and "password" in content.lower():
                    print("    -> Still on login page - auth failed")
                else:
                    print("    -> Unknown issue - check HTML file")
            
            # Try alternative: check if there's an API call we can intercept
            print("\n[6] Looking for AJAX data...")
            
            # Check if results are loaded via AJAX
            # Look for data in script tags or JSON
            json_patterns = [
                r'"preco"\s*:\s*(\d+\.?\d*)',
                r'"valor"\s*:\s*(\d+\.?\d*)',
                r'"price"\s*:\s*(\d+\.?\d*)',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    print(f"    Found JSON prices: {matches[:5]}")
            
        except Exception as e:
            print(f"\n[ERROR] {str(e)}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=str(SCREENSHOTS_DIR / "prismanil_v2_error.png"))
        
        finally:
            await browser.close()

async def test_mp24_improved():
    """Test MP24 with improved login flow"""
    print("\n" + "=" * 60)
    print("TESTING MP24 - IMPROVED VERSION")
    print("=" * 60)
    
    MP24 = {
        "url_login": "https://pt.mp24.online/pt_PT",
        "username": "PTO02101",
        "password": "Sl6dBhGf"
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
        )
        
        page = await context.new_page()
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        try:
            print(f"\n[1] Navigating to {MP24['url_login']}...")
            await page.goto(MP24['url_login'], wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v2_01_initial.png"))
            
            # Check for login form - MP24 has specific form structure
            content = await page.content()
            print(f"    Page length: {len(content)} chars")
            
            # MP24 login form:
            # <input type="text" name="_username" placeholder="Nome de utilizador">
            # <input type="password" name="_password" placeholder="Senha">
            # <a href="javascript:void(0);" onclick="document.getElementById('login_form').submit();">
            
            print("\n[2] Filling login form...")
            
            # Fill username using name attribute
            username_input = page.locator('input[name="_username"]')
            if await username_input.count() > 0:
                await username_input.fill(MP24['username'])
                print(f"    Username filled: {MP24['username']}")
            else:
                # Fallback
                await page.locator('input[type="text"]').first.fill(MP24['username'])
                print("    Username filled (fallback)")
            
            # Fill password
            password_input = page.locator('input[name="_password"]')
            if await password_input.count() > 0:
                await password_input.fill(MP24['password'])
                print("    Password filled")
            else:
                await page.locator('input[type="password"]').first.fill(MP24['password'])
                print("    Password filled (fallback)")
            
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v2_02_form_filled.png"))
            
            # Submit login
            print("\n[3] Submitting login...")
            
            # MP24 uses JavaScript submit: onclick="document.getElementById('login_form').submit();"
            # Try clicking the login link/button
            login_btn = page.locator('a:has-text("Início de sessão"), a:has-text("Login")')
            if await login_btn.count() > 0:
                await login_btn.first.click()
                print("    Clicked login link")
            else:
                # Try form submit
                await page.evaluate("document.getElementById('login_form')?.submit()")
                print("    Submitted form via JS")
            
            await asyncio.sleep(5)
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v2_03_after_login.png"))
            
            # Check login result
            print("\n[4] Checking login status...")
            content = await page.content()
            current_url = page.url
            print(f"    Current URL: {current_url}")
            
            logged_in_indicators = ['logout', 'sair', 'carrinho', 'cart', 'bem-vindo', 'welcome']
            is_logged_in = any(ind in content.lower() for ind in logged_in_indicators)
            still_login = 'login_form' in content
            
            print(f"    Logged in: {is_logged_in}")
            print(f"    Still on login page: {still_login}")
            
            # Save HTML
            with open(SCREENSHOTS_DIR / "mp24_v2_after_login.html", 'w') as f:
                f.write(content)
            
            if is_logged_in or not still_login:
                # Try searching
                print("\n[5] Searching for tire...")
                medida = "2055516"
                
                # MP24 search - try going to search page
                search_url = "https://pt.mp24.online/pt_PT/tires"
                print(f"    Navigating to: {search_url}")
                await page.goto(search_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)
                await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v2_04_tires_page.png"))
                
                # Look for search input
                search_input = page.locator('input[type="search"], input[name*="search"], input[placeholder*="search"]').first
                if await search_input.count() > 0:
                    await search_input.fill(medida)
                    await search_input.press("Enter")
                    print(f"    Searched for: {medida}")
                    
                    await asyncio.sleep(5)
                    await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v2_05_search_results.png"))
                    
                    content = await page.content()
                    prices = extract_prices(content)
                    print(f"\n    Found prices: {prices}")
                    
                    if prices:
                        print(f"\n✅ SUCCESS! Best price: €{min(prices)}")
                    else:
                        print("\n❌ No prices found")
                else:
                    print("    No search input found")
            else:
                print("\n❌ Login failed - cannot proceed to search")
            
        except Exception as e:
            print(f"\n[ERROR] {str(e)}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v2_error.png"))
        
        finally:
            await browser.close()

async def main():
    print("=" * 60)
    print("IMPROVED PLAYWRIGHT SCRAPING TEST")
    print("=" * 60)
    
    await test_prismanil_improved()
    await test_mp24_improved()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print(f"Screenshots saved to: {SCREENSHOTS_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
