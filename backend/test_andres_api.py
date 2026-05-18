import asyncio
import aiohttp
import json
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # Login directo em online.grupoandres.com
        await page.goto("https://online.grupoandres.com/login",
                        wait_until="domcontentloaded", timeout=30000)
        await page.locator('input[name="data[Usuario][user]"]').fill("10273000")
        await page.locator('input[name="data[Usuario][pass]"]').fill("pneusdpv")
        await page.locator('form#login_form').evaluate("f => f.submit()")
        await asyncio.sleep(4)
        try:
            await page.wait_for_url("**/online.grupoandres.com/**", timeout=15000)
        except Exception:
            pass
        print("URL apos login:", page.url)

        # Extrair cookies
        cookies = await ctx.cookies()
        cookie_str = '; '.join([f"{c['name']}={c['value']}" for c in cookies])

        # Chamar API
        url = ("https://online.grupoandres.com/search/tyres"
               "?page=0&step=1&filterWithStock=true&isNewSearch=true"
               "&sortBy=null&sortOrder=null&sortLoadSpeed=null"
               "&category=cubiertas&searchText=2055516")

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={
                'Cookie': cookie_str,
                'Accept': 'application/json',
                'Referer': 'https://online.grupoandres.com/',
            }) as resp:
                data = await resp.json(content_type=None)

        # Mostrar estrutura completa
        print("STATUS:", resp.status)
        print("CHAVES RAIZ:", list(data.keys()) if isinstance(data, dict) else "E lista")
        if isinstance(data, list) and len(data) > 0:
            print("CAMPOS item[0]:", list(data[0].keys()))
            print("item[0] completo:", json.dumps(data[0], indent=2, ensure_ascii=False))
            if len(data) > 1:
                print("item[1] completo:", json.dumps(data[1], indent=2, ensure_ascii=False))
            print(f"\nTotal items page=0: {len(data)}")
        elif isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, list) and len(val) > 0:
                    print(f"data['{key}'][0] campos:", list(val[0].keys()))
                    print(f"data['{key}'][0]:", json.dumps(val[0], indent=2, ensure_ascii=False))
                    break

        await browser.close()

asyncio.run(test())
