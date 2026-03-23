#!/usr/bin/env python3
"""
Debug script that exactly replicates the service behavior
"""
import asyncio
import os
from playwright.async_api import async_playwright

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

async def test_like_service():
    """Test using exactly the same pattern as the service"""
    print("Testing with service-like pattern...")
    
    # This is how the service does it
    playwright = await async_playwright().start()
    
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
        ]
    )
    
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='pt-PT',
        timezone_id='Europe/Lisbon',
    )
    
    page = await context.new_page()
    
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)
    
    page.set_default_timeout(30000)
    
    try:
        # Login
        print("Navigating to MP24...")
        await page.goto("https://pt.mp24.online/pt_PT", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        await page.locator('input[name="_username"]').fill("PTO02101")
        print("Filled username")
        
        await page.locator('input[name="_password"]').fill("Sl6dBhGf")
        print("Filled password")
        
        await asyncio.sleep(1)
        
        # Try JavaScript submit (like service does)
        print("Submitting form via JS...")
        await page.evaluate("document.getElementById('login_form').submit()")
        
        await asyncio.sleep(4)
        await page.wait_for_load_state("networkidle")
        
        current_url = page.url
        print(f"Post-login URL: {current_url}")
        
        content = await page.content()
        print(f"Has login_form: {'login_form' in content}")
        print(f"Has sair: {'sair' in content.lower()}")
        
        # Navigate to tyres
        print("Navigating to tyres page...")
        await page.goto("https://pt.mp24.online/pt_PT/tyres/", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        
        current_url = page.url
        print(f"Tyres page URL: {current_url}")
        
        content = await page.content()
        print(f"Has matchcodeField: {'matchcodeField' in content}")
        print(f"Has login: {'login' in current_url.lower()}")
        
        if 'matchcodeField' in content:
            print("\n✅ SERVICE PATTERN WORKS!")
        else:
            print("\n❌ SERVICE PATTERN FAILED")
            # Save debug HTML
            with open("/app/tmp/service_pattern_debug.html", 'w') as f:
                f.write(content)
            print("Saved debug HTML to /app/tmp/service_pattern_debug.html")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await browser.close()
        await playwright.stop()

async def test_like_working_script():
    """Test using the pattern from the working test script"""
    print("\nTesting with working script pattern...")
    
    # This is how the working test script does it
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
            print("Navigating to MP24...")
            await page.goto("https://pt.mp24.online/pt_PT", wait_until="networkidle", timeout=60000)
            
            await page.locator('input[name="_username"]').fill("PTO02101")
            await page.locator('input[name="_password"]').fill("Sl6dBhGf")
            print("Filled credentials")
            
            # Click login link (like working script)
            await page.locator('a:has-text("Início de sessão")').click()
            await asyncio.sleep(3)
            print("Clicked login")
            
            # Navigate to tyres
            await page.goto("https://pt.mp24.online/pt_PT/tyres/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            current_url = page.url
            print(f"Tyres page URL: {current_url}")
            
            content = await page.content()
            print(f"Has matchcodeField: {'matchcodeField' in content}")
            
            if 'matchcodeField' in content:
                print("\n✅ WORKING SCRIPT PATTERN WORKS!")
            else:
                print("\n❌ WORKING SCRIPT PATTERN FAILED")
        
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await browser.close()

async def main():
    await test_like_service()
    await test_like_working_script()

if __name__ == "__main__":
    asyncio.run(main())
