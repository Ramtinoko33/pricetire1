#!/usr/bin/env python3
"""
Final MP24 test using matchcode search
"""
import asyncio
import re
import os
from pathlib import Path
from playwright.async_api import async_playwright

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

SCREENSHOTS_DIR = Path("/app/tmp/playwright_debug")

def extract_prices(content: str) -> list:
    price_patterns = [
        r'€\s*(\d+[,\.]\d{2})',
        r'(\d+[,\.]\d{2})\s*€',
        r'"purchasePrice"\s*:\s*(\d+\.?\d*)',
        r'"price"\s*:\s*(\d+\.?\d*)',
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

async def test_mp24_matchcode():
    """Test MP24 using matchcode search field"""
    print("\n" + "=" * 60)
    print("TESTING MP24 - MATCHCODE SEARCH")
    print("=" * 60)
    
    MP24 = {
        "url": "https://pt.mp24.online/pt_PT",
        "username": "PTO02101",
        "password": "Sl6dBhGf"
    }
    
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
            # Step 1: Login
            print(f"\n[1] Logging in to {MP24['url']}...")
            await page.goto(MP24['url'], wait_until="networkidle", timeout=60000)
            await page.locator('input[name="_username"]').fill(MP24['username'])
            await page.locator('input[name="_password"]').fill(MP24['password'])
            await page.locator('a:has-text("Início de sessão")').click()
            await asyncio.sleep(3)
            print("    Login successful!")
            
            # Step 2: Go to tyres page
            print("\n[2] Navigating to tyres page...")
            await page.goto("https://pt.mp24.online/pt_PT/tyres/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            # Step 3: Use matchcode search (format: width/profile/rim like 2055516)
            print("\n[3] Using matchcode search...")
            
            # The matchcode field accepts patterns like S1956515H or just 2055516
            matchcode = "2055516"  # 205/55R16 normalized
            
            matchcode_input = page.locator('#matchcodeField')
            if await matchcode_input.count() > 0:
                await matchcode_input.fill(matchcode)
                print(f"    Filled matchcode: {matchcode}")
                await asyncio.sleep(1)
                await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v4_01_matchcode.png"))
                
                # Submit the form
                submit_btn = page.locator('button[type="submit"]').first
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                    print("    Clicked search button")
                else:
                    await matchcode_input.press("Enter")
                    print("    Pressed Enter")
                
                await asyncio.sleep(5)
                await page.wait_for_load_state("networkidle")
                await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v4_02_results.png"))
                
                content = await page.content()
                
                # Save HTML
                with open(SCREENSHOTS_DIR / "mp24_v4_results.html", 'w') as f:
                    f.write(content)
                
                # Extract prices
                prices = extract_prices(content)
                print(f"\n[4] Found {len(prices)} prices")
                
                if prices:
                    prices = sorted(prices)
                    print(f"    Prices: {prices[:10]}...")
                    print(f"\n✅ SUCCESS! Best price: €{min(prices)}")
                else:
                    print("\n    No prices extracted, trying filter method...")
                    
                    # Alternative: Use the dropdown filters
                    print("\n[5] Trying dropdown filters...")
                    
                    # Select Largura = 205
                    await page.select_option('#filterTop12', '205')
                    print("    Selected width: 205")
                    await asyncio.sleep(1)
                    
                    # Select Perfil = 55
                    await page.select_option('#filterTop13', '55')
                    print("    Selected profile: 55")
                    await asyncio.sleep(1)
                    
                    # Select Jante = 16
                    await page.select_option('#filterTop14', '16')
                    print("    Selected rim: 16")
                    await asyncio.sleep(2)
                    
                    await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v4_03_filters.png"))
                    
                    # Wait for AJAX update
                    await asyncio.sleep(3)
                    
                    content = await page.content()
                    with open(SCREENSHOTS_DIR / "mp24_v4_filter_results.html", 'w') as f:
                        f.write(content)
                    
                    prices = extract_prices(content)
                    print(f"\n    Found {len(prices)} prices after filtering")
                    
                    if prices:
                        print(f"\n✅ SUCCESS! Best price: €{min(prices)}")
                    else:
                        print("❌ No prices found")
                        # Check what's in the response
                        if 'productList' in content.lower() or 'article' in content.lower():
                            print("    Products seem to exist but prices not extracted")
            else:
                print("    Matchcode field not found!")
                
        except Exception as e:
            print(f"\n[ERROR] {str(e)}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=str(SCREENSHOTS_DIR / "mp24_v4_error.png"))
        
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_mp24_matchcode())
