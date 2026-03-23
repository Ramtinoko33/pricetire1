#!/usr/bin/env python3
"""
Test Playwright direct scraping for MP24 and Prismanil
Run: python3 test_playwright_direct.py
"""
import asyncio
import re
import os
from pathlib import Path
from playwright.async_api import async_playwright

# Set browser path
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

SCREENSHOTS_DIR = Path("/app/tmp/playwright_debug")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Test credentials
SUPPLIERS = {
    "mp24": {
        "url_login": "https://pt.mp24.online/pt_PT",
        "username": "PTO02101",
        "password": "Sl6dBhGf"
    },
    "prismanil": {
        "url_login": "https://www.prismanil.pt/b2b/pesquisa",
        "username": "dpedrov287",
        "password": "dompedro4785"
    }
}

def extract_prices(content: str) -> list:
    """Extract prices from HTML content"""
    price_patterns = [
        r'€\s*(\d+[,\.]\d{2})',
        r'(\d+[,\.]\d{2})\s*€',
        r'"price"\s*:\s*"?(\d+[,\.]\d{2})"?',
        r'(\d+\.\d{2})\s*EUR',
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

async def test_mp24():
    """Test MP24 with Playwright"""
    print("\n" + "=" * 60)
    print("TESTING MP24 (pt.mp24.online)")
    print("=" * 60)
    
    supplier = SUPPLIERS["mp24"]
    
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
        
        # Remove webdriver flag
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        try:
            # Step 1: Navigate to login page
            print(f"\n[1] Navigating to {supplier['url_login']}...")
            await page.goto(supplier['url_login'], wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_01_initial.png"))
            print(f"    Screenshot: mp24_01_initial.png")
            
            # Step 2: Look for login form or button
            print("\n[2] Looking for login elements...")
            
            # Check page content
            content = await page.content()
            print(f"    Page length: {len(content)} chars")
            
            # Look for login link/button
            login_selectors = [
                'a:has-text("Login")',
                'a:has-text("Entrar")',
                'button:has-text("Login")',
                '.login-link',
                'a[href*="login"]',
            ]
            
            for selector in login_selectors:
                try:
                    elem = page.locator(selector)
                    if await elem.count() > 0:
                        print(f"    Found login element: {selector}")
                        await elem.first.click()
                        await asyncio.sleep(2)
                        await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_02_after_login_click.png"))
                        break
                except:
                    continue
            
            # Step 3: Fill login form
            print("\n[3] Filling login form...")
            
            # Fill username
            username_selectors = [
                'input[type="text"]',
                'input[type="email"]',
                'input[name*="user"]',
                'input[name*="email"]',
                'input[placeholder*="user"]',
            ]
            
            for selector in username_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.count() > 0 and await elem.is_visible():
                        await elem.fill(supplier['username'])
                        print(f"    Filled username with selector: {selector}")
                        break
                except:
                    continue
            
            # Fill password
            pwd_elem = page.locator('input[type="password"]').first
            if await pwd_elem.count() > 0:
                await pwd_elem.fill(supplier['password'])
                print("    Filled password")
            
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_03_form_filled.png"))
            
            # Step 4: Submit login
            print("\n[4] Submitting login...")
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Login")',
                'button:has-text("Entrar")',
            ]
            
            for selector in submit_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.count() > 0 and await elem.is_visible():
                        await elem.click()
                        print(f"    Clicked: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(5)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_04_after_login.png"))
            
            # Step 5: Check if logged in
            print("\n[5] Checking login status...")
            content = await page.content()
            current_url = page.url
            print(f"    Current URL: {current_url}")
            
            # Save HTML for debugging
            with open(SCREENSHOTS_DIR / "mp24_after_login.html", 'w') as f:
                f.write(content)
            
            logged_in_indicators = ['logout', 'sair', 'carrinho', 'cart', 'minha conta', 'my account']
            is_logged_in = any(ind in content.lower() for ind in logged_in_indicators)
            print(f"    Logged in: {is_logged_in}")
            
            # Step 6: Try search
            print("\n[6] Searching for tire (2055516)...")
            medida = "2055516"
            
            # Look for search input
            search_selectors = [
                'input[type="search"]',
                'input[placeholder*="search"]',
                'input[placeholder*="pesqui"]',
                'input[name*="search"]',
                'input[name*="q"]',
                '.search-input',
            ]
            
            search_found = False
            for selector in search_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.count() > 0 and await elem.is_visible():
                        await elem.fill(medida)
                        await elem.press("Enter")
                        print(f"    Searched using: {selector}")
                        search_found = True
                        break
                except:
                    continue
            
            if not search_found:
                # Try navigating to search URL directly
                search_url = f"https://pt.mp24.online/pt_PT/search?q={medida}"
                print(f"    Navigating to: {search_url}")
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            
            await asyncio.sleep(5)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_05_search_results.png"))
            
            # Extract prices
            content = await page.content()
            with open(SCREENSHOTS_DIR / "mp24_search_results.html", 'w') as f:
                f.write(content)
            
            prices = extract_prices(content)
            print(f"\n[RESULT] Found prices: {prices}")
            if prices:
                print(f"[RESULT] ✅ Best price: €{min(prices)}")
            else:
                print("[RESULT] ❌ No prices found")
            
        except Exception as e:
            print(f"\n[ERROR] {str(e)}")
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_error.png"))
        
        finally:
            await browser.close()

async def test_prismanil():
    """Test Prismanil with Playwright"""
    print("\n" + "=" * 60)
    print("TESTING PRISMANIL (prismanil.pt)")
    print("=" * 60)
    
    supplier = SUPPLIERS["prismanil"]
    
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
            # Step 1: Navigate
            print(f"\n[1] Navigating to {supplier['url_login']}...")
            await page.goto(supplier['url_login'], wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "prismanil_01_initial.png"))
            print(f"    Screenshot: prismanil_01_initial.png")
            
            content = await page.content()
            print(f"    Page length: {len(content)} chars")
            
            # Step 2: Fill login
            print("\n[2] Filling login form...")
            
            # Username
            username_selectors = [
                'input[type="text"]',
                'input[name*="user"]',
                'input[name*="login"]',
                'input[placeholder*="user"]',
            ]
            
            for selector in username_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.count() > 0 and await elem.is_visible():
                        await elem.fill(supplier['username'])
                        print(f"    Filled username: {selector}")
                        break
                except:
                    continue
            
            # Password
            pwd_elem = page.locator('input[type="password"]').first
            if await pwd_elem.count() > 0:
                await pwd_elem.fill(supplier['password'])
                print("    Filled password")
            
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "prismanil_02_form_filled.png"))
            
            # Step 3: Submit
            print("\n[3] Submitting login...")
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Entrar")',
                'button:has-text("Login")',
            ]
            
            for selector in submit_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.count() > 0:
                        await elem.click()
                        print(f"    Clicked: {selector}")
                        break
                except:
                    continue
            
            await asyncio.sleep(5)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "prismanil_03_after_login.png"))
            
            # Step 4: Check login
            print("\n[4] Checking login status...")
            content = await page.content()
            current_url = page.url
            print(f"    Current URL: {current_url}")
            
            with open(SCREENSHOTS_DIR / "prismanil_after_login.html", 'w') as f:
                f.write(content)
            
            # Step 5: Search
            print("\n[5] Searching for tire (2055516)...")
            medida = "2055516"
            
            # Look for search/medida input
            search_selectors = [
                'input[name*="medida"]',
                'input[placeholder*="medida"]',
                'input[type="search"]',
                'input[type="text"]',
            ]
            
            for selector in search_selectors:
                try:
                    elems = page.locator(selector)
                    count = await elems.count()
                    for i in range(count):
                        elem = elems.nth(i)
                        if await elem.is_visible():
                            await elem.fill(medida)
                            await elem.press("Enter")
                            print(f"    Searched using: {selector} (index {i})")
                            break
                    break
                except:
                    continue
            
            await asyncio.sleep(5)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "prismanil_04_search_results.png"))
            
            # Extract prices
            content = await page.content()
            with open(SCREENSHOTS_DIR / "prismanil_search_results.html", 'w') as f:
                f.write(content)
            
            prices = extract_prices(content)
            print(f"\n[RESULT] Found prices: {prices}")
            if prices:
                print(f"[RESULT] ✅ Best price: €{min(prices)}")
            else:
                print("[RESULT] ❌ No prices found")
            
        except Exception as e:
            print(f"\n[ERROR] {str(e)}")
            await page.screenshot(path=str(SCREENSHOTS_DIR / "prismanil_error.png"))
        
        finally:
            await browser.close()

async def main():
    print("=" * 60)
    print("PLAYWRIGHT DIRECT SCRAPING TEST")
    print("=" * 60)
    
    await test_mp24()
    await test_prismanil()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print(f"Screenshots saved to: {SCREENSHOTS_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
