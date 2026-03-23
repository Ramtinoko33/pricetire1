#!/usr/bin/env python3
"""
Final test for MP24 tyres page structure
"""
import asyncio
import re
import os
from pathlib import Path
from playwright.async_api import async_playwright

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

SCREENSHOTS_DIR = Path("/app/tmp/playwright_debug")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

def extract_prices(content: str) -> list:
    price_patterns = [
        r'€\s*(\d+[,\.]\d{2})',
        r'(\d+[,\.]\d{2})\s*€',
        r'"price"\s*:\s*"?(\d+[,\.]\d{2})"?',
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

async def test_mp24_tyres():
    """Test MP24 tyres page"""
    print("\n" + "=" * 60)
    print("TESTING MP24 - TYRES PAGE")
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
            # Step 1: Login
            print(f"\n[1] Navigating to {MP24['url_login']}...")
            await page.goto(MP24['url_login'], wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            
            # Fill login
            await page.locator('input[name="_username"]').fill(MP24['username'])
            await page.locator('input[name="_password"]').fill(MP24['password'])
            
            # Submit
            await page.locator('a:has-text("Início de sessão")').click()
            await asyncio.sleep(3)
            await page.wait_for_load_state("networkidle")
            
            print("    Logged in!")
            
            # Step 2: Navigate to tyres page
            print("\n[2] Navigating to tyres page...")
            await page.goto("https://pt.mp24.online/pt_PT/tyres/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v3_01_tyres_page.png"))
            
            content = await page.content()
            print(f"    Page length: {len(content)} chars")
            
            # Save HTML
            with open(SCREENSHOTS_DIR / "mp24_v3_tyres.html", 'w') as f:
                f.write(content)
            
            # Step 3: Look for filter/search options
            print("\n[3] Looking for filter options...")
            
            # Check for filter selects (width, profile, diameter)
            filter_patterns = [
                'select', 'filter', 'width', 'largura', 'profile', 'perfil', 'diameter', 'diâmetro', 'aro'
            ]
            
            for pattern in filter_patterns:
                if pattern in content.lower():
                    print(f"    Found: {pattern}")
            
            # Look for select elements
            selects = await page.locator('select').all()
            print(f"    Found {len(selects)} select elements")
            
            for i, select in enumerate(selects[:5]):
                try:
                    name = await select.get_attribute('name') or await select.get_attribute('id') or f"select_{i}"
                    print(f"      - {name}")
                except:
                    pass
            
            # Step 4: Try to filter by size 205/55R16
            print("\n[4] Trying to filter by size 205/55R16...")
            
            # Try width dropdown (205)
            width_select = page.locator('select[name*="width"], select[id*="width"]')
            if await width_select.count() > 0:
                try:
                    await width_select.select_option(label="205")
                    print("    Selected width: 205")
                except:
                    print("    Could not select width 205")
            
            # Try profile dropdown (55)
            profile_select = page.locator('select[name*="profile"], select[id*="profile"], select[name*="ratio"]')
            if await profile_select.count() > 0:
                try:
                    await profile_select.select_option(label="55")
                    print("    Selected profile: 55")
                except:
                    print("    Could not select profile 55")
            
            # Try diameter dropdown (16)
            diameter_select = page.locator('select[name*="diameter"], select[name*="rim"], select[id*="diameter"]')
            if await diameter_select.count() > 0:
                try:
                    await diameter_select.select_option(label="16")
                    print("    Selected diameter: 16")
                except:
                    print("    Could not select diameter 16")
            
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v3_02_filters.png"))
            
            # Submit search
            search_btn = page.locator('button:has-text("Pesquisar"), button:has-text("Search"), input[type="submit"]')
            if await search_btn.count() > 0:
                await search_btn.first.click()
                print("    Clicked search button")
                await asyncio.sleep(5)
            
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v3_03_results.png"))
            
            # Get results
            content = await page.content()
            with open(SCREENSHOTS_DIR / "mp24_v3_results.html", 'w') as f:
                f.write(content)
            
            prices = extract_prices(content)
            print(f"\n[5] Found {len(prices)} prices: {sorted(prices)[:10]}")
            
            if prices:
                print(f"\n✅ SUCCESS! Best price: €{min(prices)}")
            else:
                print("\n❌ No prices found")
                print("    Checking page structure...")
                
                # Check what's on the page
                if "sem resultado" in content.lower():
                    print("    -> No results message")
                elif "product" in content.lower() or "artigo" in content.lower():
                    print("    -> Products found but prices not extracted")
                    # Try alternative price extraction
                    alt_prices = re.findall(r'(\d{2,3}[,\.]\d{2})', content)
                    print(f"    -> Alternative numbers found: {alt_prices[:10]}")
            
        except Exception as e:
            print(f"\n[ERROR] {str(e)}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v3_error.png"))
        
        finally:
            await browser.close()

async def main():
    await test_mp24_tyres()

if __name__ == "__main__":
    asyncio.run(main())
