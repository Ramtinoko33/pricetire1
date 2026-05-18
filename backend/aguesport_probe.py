"""Probe do site Aguesport — captura HTML da página de resultados."""
import asyncio
from playwright.async_api import async_playwright

USERNAME = "pneusdpedrov@mail.telepac.pt"
PASSWORD = "m3vNH8NNuv"
URL_LOGIN = "https://encomendas.aguesport.com/login"
URL_HOME  = "https://encomendas.aguesport.com/"
MEDIDA    = "205/55R16"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = await ctx.new_page()

        # ── LOGIN ───────────────────────────────────────────────────────
        print(f"[probe] Navegando para {URL_LOGIN}")
        await page.goto(URL_LOGIN, wait_until="networkidle", timeout=60000)
        print(f"[probe] URL após goto: {page.url}")

        # Mostrar inputs disponíveis
        inputs = await page.evaluate("""() => {
            return [...document.querySelectorAll('input')].map(i => ({
                type: i.type, name: i.name, id: i.id, placeholder: i.placeholder
            }));
        }""")
        print(f"[probe] Inputs na página de login: {inputs}")

        # Preencher login
        for sel in ['input[name="username"]', 'input[name="email"]', 'input[type="email"]', 'input[type="text"]']:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.fill(USERNAME)
                print(f"[probe] Preencheu username com selector: {sel}")
                break

        for sel in ['input[name="password"]', 'input[type="password"]']:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.fill(PASSWORD)
                print(f"[probe] Preencheu password com selector: {sel}")
                break

        # Submit
        for sel in ['button[type="submit"]', 'input[type="submit"]', 'button:has-text("Login")', 'button:has-text("Entrar")']:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click()
                print(f"[probe] Clicou submit com selector: {sel}")
                break

        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        print(f"[probe] URL após login: {page.url}")

        # Guardar HTML do pós-login
        html_login = await page.content()
        with open("aguesport_after_login.html", "w", encoding="utf-8") as f:
            f.write(html_login)
        print(f"[probe] HTML pós-login guardado ({len(html_login)} chars)")

        # ── PESQUISA ────────────────────────────────────────────────────
        print(f"\n[probe] A pesquisar '{MEDIDA}'...")

        # Mostrar inputs disponíveis após login
        inputs2 = await page.evaluate("""() => {
            return [...document.querySelectorAll('input')].map(i => ({
                type: i.type, name: i.name, id: i.id, placeholder: i.placeholder, value: i.value
            }));
        }""")
        print(f"[probe] Inputs após login: {inputs2}")

        # Tentar encontrar campo de pesquisa
        search_found = False
        for sel in [
            'input[type="search"]',
            'input[name*="search" i]',
            'input[name*="pesq" i]',
            'input[name*="medida" i]',
            'input[placeholder*="medida" i]',
            'input[placeholder*="pesq" i]',
            'input[placeholder*="205" i]',
            'input[type="text"]',
        ]:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.fill(MEDIDA)
                print(f"[probe] Preencheu pesquisa com selector: {sel}")
                search_found = True
                # Tentar botão de pesquisa
                for btn_sel in ['button[type="submit"]', 'button:has-text("Pesqui")', 'button:has-text("Buscar")', '.btn-search']:
                    btn = page.locator(btn_sel).first
                    if await btn.count() > 0:
                        await btn.click()
                        print(f"[probe] Clicou pesquisa com: {btn_sel}")
                        break
                else:
                    await el.press("Enter")
                    print(f"[probe] Submit via Enter")
                break

        if not search_found:
            print("[probe] Campo de pesquisa não encontrado, tentando URL directo...")
            await page.goto(f"{URL_HOME}?search={MEDIDA.replace('/', '%2F')}", wait_until="networkidle", timeout=30000)

        await asyncio.sleep(4)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        print(f"[probe] URL após pesquisa: {page.url}")

        # ── CAPTURAR HTML DOS RESULTADOS ────────────────────────────────
        html = await page.content()
        with open("aguesport_results.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[probe] HTML resultados guardado ({len(html)} chars)")

        # Extrair estrutura relevante: elementos com preços
        structure = await page.evaluate("""() => {
            const results = [];

            // Tentar encontrar elementos com preços (€ ou EUR)
            const allText = document.body.innerText;
            const hasPrice = /\\d+[,.]\\d{2}\\s*€|€\\s*\\d/.test(allText);
            results.push({type: 'hasPrice', value: hasPrice});

            // Tentar encontrar tabelas
            const tables = document.querySelectorAll('table');
            results.push({type: 'tables', count: tables.length});
            if (tables.length > 0) {
                const t = tables[0];
                results.push({type: 'table_headers', value: [...t.querySelectorAll('th')].map(h => h.textContent.trim())});
                const rows = t.querySelectorAll('tr');
                results.push({type: 'table_rows', count: rows.length});
                if (rows.length > 1) {
                    results.push({type: 'first_row', value: [...rows[1].querySelectorAll('td')].map(td => td.textContent.trim().substring(0, 80))});
                }
            }

            // Encontrar divs com produto/preço
            const priceEls = [...document.querySelectorAll('*')].filter(el =>
                el.children.length === 0 &&
                /\\d+[,.]\\d{2}\\s*€/.test(el.textContent)
            );
            results.push({type: 'price_elements', count: priceEls.length});
            priceEls.slice(0, 5).forEach((el, i) => {
                results.push({
                    type: `price_el_${i}`,
                    tag: el.tagName,
                    class: el.className,
                    id: el.id,
                    text: el.textContent.trim().substring(0, 100),
                    parent_class: el.parentElement?.className,
                    parent_tag: el.parentElement?.tagName,
                });
            });

            // Listar todas as classes CSS presentes (para perceber estrutura)
            const classes = new Set();
            document.querySelectorAll('[class]').forEach(el => {
                el.className.split(' ').forEach(c => c && classes.add(c));
            });
            results.push({type: 'css_classes', value: [...classes].slice(0, 50)});

            return results;
        }""")

        print("\n[probe] === ESTRUTURA DA PÁGINA DE RESULTADOS ===")
        for item in structure:
            print(f"  {item}")

        # Mostrar snippet do HTML à volta de "205/55"
        idx = html.find("205/55")
        if idx >= 0:
            snippet = html[max(0, idx-200):idx+500]
            print(f"\n[probe] === SNIPPET HTML PERTO DE '205/55' ===")
            print(snippet)
        else:
            print("\n[probe] '205/55' não encontrado no HTML")
            # Mostrar primeiros 2000 chars do body
            body_start = html.find("<body")
            print(html[body_start:body_start+2000] if body_start >= 0 else html[:2000])

        await browser.close()

asyncio.run(main())
