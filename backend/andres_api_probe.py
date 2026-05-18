"""Probe API JSON Grupo Andres.
Uso: python andres_api_probe.py <username> <password>
Faz login com Playwright, extrai cookies, chama a API JSON e mostra a estrutura.
"""
import asyncio, sys, json
import aiohttp
from playwright.async_api import async_playwright

MEDIDA = "2055516"

async def main(username: str, password: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        page = await ctx.new_page()

        # ── LOGIN ────────────────────────────────────────────────────────────
        print("[probe] Login em www.grupoandres.com/pt-pt/...")
        await page.goto("https://www.grupoandres.com/pt-pt/", wait_until="domcontentloaded", timeout=60000)
        await page.evaluate(
            'function(args) {'
            '  var forms = document.querySelectorAll("form");'
            '  for (var i = 0; i < forms.length; i++) {'
            '    var fields = forms[i].querySelectorAll("input");'
            '    for (var j = 0; j < fields.length; j++) {'
            '      if (fields[j].name.indexOf("[user]") >= 0) fields[j].value = args[0];'
            '      if (fields[j].name.indexOf("[pass]") >= 0) fields[j].value = args[1];'
            '    }'
            '    if (fields.length > 0) { forms[i].submit(); break; }'
            '  }'
            '}',
            [username, password]
        )
        await asyncio.sleep(4)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        print(f"[probe] URL apos login: {page.url}")

        # Tentar navegar para online.grupoandres.com para criar sessao la
        await page.goto("https://online.grupoandres.com/buscador?category=cubiertas&searchText=2055516",
                        wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)
        print(f"[probe] URL apos buscador goto: {page.url}")

        if 'login' in page.url.lower():
            print("[probe] Redirecionado para login — tentando login directo em online.grupoandres.com...")
            await page.goto("https://online.grupoandres.com/login", wait_until="domcontentloaded", timeout=60000)
            await page.locator('input[name="data[Usuario][user]"]').fill(username)
            await page.locator('input[name="data[Usuario][pass]"]').fill(password)
            await page.locator('form#login_form').evaluate("f => f.submit()")
            await asyncio.sleep(4)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            print(f"[probe] URL apos login directo: {page.url}")

        # ── EXTRAIR COOKIES ──────────────────────────────────────────────────
        cookies = await ctx.cookies()
        cookie_str = '; '.join([f"{c['name']}={c['value']}" for c in cookies])
        andres_cookies = [c for c in cookies if 'andres' in c.get('domain', '')]
        print(f"[probe] Total cookies: {len(cookies)}")
        print(f"[probe] Cookies andres: {[(c['name'], c['domain']) for c in andres_cookies]}")

        await browser.close()

    # ── TESTAR API JSON ──────────────────────────────────────────────────────
    print(f"\n[probe] A chamar API JSON para page=0...")
    api_url = (
        f"https://online.grupoandres.com/search/tyres"
        f"?page=0&step=1&filterWithStock=true&isNewSearch=true"
        f"&sortBy=null&sortOrder=null&sortLoadSpeed=null"
        f"&category=cubiertas&searchText={MEDIDA}"
    )
    headers = {
        'Cookie': cookie_str,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'https://online.grupoandres.com/buscador?category=cubiertas&searchText={MEDIDA}',
    }

    async with aiohttp.ClientSession() as session:
        # page=0
        async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            print(f"[probe] Status page=0: {resp.status}")
            print(f"[probe] Content-Type: {resp.headers.get('Content-Type', '?')}")
            text = await resp.text()
            print(f"[probe] Resposta (primeiros 2000 chars):\n{text[:2000]}")

            if resp.status == 200:
                try:
                    data = json.loads(text)
                    print(f"\n[probe] JSON type: {type(data)}")
                    if isinstance(data, list):
                        print(f"[probe] Lista com {len(data)} items")
                        if data:
                            print(f"[probe] Primeiro item keys: {list(data[0].keys()) if isinstance(data[0], dict) else type(data[0])}")
                            print(f"[probe] Primeiro item completo:\n{json.dumps(data[0], indent=2, ensure_ascii=False)}")
                            if len(data) > 1:
                                print(f"[probe] Segundo item:\n{json.dumps(data[1], indent=2, ensure_ascii=False)}")
                    elif isinstance(data, dict):
                        print(f"[probe] Dict keys: {list(data.keys())}")
                        print(f"[probe] Conteudo completo:\n{json.dumps(data, indent=2, ensure_ascii=False)[:3000]}")
                except json.JSONDecodeError as e:
                    print(f"[probe] NAO e JSON: {e}")

        # page=1 (verificar se existe)
        url_p1 = api_url.replace("page=0", "page=1")
        async with session.get(url_p1, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp2:
            text2 = await resp2.text()
            print(f"\n[probe] page=1 status={resp2.status}, len={len(text2)}")
            if text2.strip() not in ('[]', 'null', ''):
                try:
                    d2 = json.loads(text2)
                    if isinstance(d2, list):
                        print(f"[probe] page=1: {len(d2)} items")
                    else:
                        print(f"[probe] page=1: {text2[:300]}")
                except Exception:
                    print(f"[probe] page=1 raw: {text2[:300]}")
            else:
                print(f"[probe] page=1 vazia: {text2[:50]!r}")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Uso: python andres_api_probe.py <username> <password>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
