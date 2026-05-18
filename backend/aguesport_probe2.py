"""Probe v2 do site Aguesport — usa campo Medida correcto."""
import asyncio
from playwright.async_api import async_playwright

USERNAME = "pneusdpedrov@mail.telepac.pt"
PASSWORD = "m3vNH8NNuv"
URL_LOGIN = "https://encomendas.aguesport.com/login"
MEDIDA    = "2055516"  # formato normalizado (sem / e R)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = await ctx.new_page()

        # ── LOGIN ───────────────────────────────────────────────────────
        print(f"[probe] Login...")
        await page.goto(URL_LOGIN, wait_until="networkidle", timeout=60000)
        await page.locator('input[type="email"]').first.fill(USERNAME)
        await page.locator('input[type="password"]').first.fill(PASSWORD)
        await page.locator('button[type="submit"]').first.click()
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        print(f"[probe] URL após login: {page.url}")

        # ── PESQUISA ────────────────────────────────────────────────────
        # Campo correcto: input[type="text"] com placeholder "Medida (ex: 2254517)"
        medida_field = page.locator('input[placeholder*="Medida"]').first
        if await medida_field.count() == 0:
            medida_field = page.locator('input[placeholder*="2254"]').first
        if await medida_field.count() == 0:
            medida_field = page.locator('input[type="text"]').first

        print(f"[probe] Campo medida encontrado: {await medida_field.count() > 0}")
        await medida_field.fill(MEDIDA)
        await asyncio.sleep(0.5)

        # Clicar botão submit
        btn = page.locator('button[type="submit"]').first
        if await btn.count() > 0:
            await btn.click()
        else:
            await medida_field.press("Enter")

        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        print(f"[probe] URL após pesquisa: {page.url}")

        html = await page.content()
        with open("aguesport_results2.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[probe] HTML guardado: {len(html)} chars")

        # ── INSPECÇÃO DOS RESULTADOS ─────────────────────────────────────
        # Procurar preços no HTML
        import re
        prices_found = re.findall(r'\d+[.,]\d{2}\s*€', html)
        print(f"[probe] Preços encontrados: {prices_found[:10]}")

        # Procurar marcas de pneus
        brands = re.findall(r'MICHELIN|CONTINENTAL|PIRELLI|BRIDGESTONE|GOODYEAR|HANKOOK|YOKOHAMA', html, re.I)
        print(f"[probe] Marcas encontradas: {list(set(b.upper() for b in brands))}")

        # Inspecionar estrutura via JS (seguro)
        rows_info = await page.evaluate("""() => {
            const info = {};
            // Tabelas
            info.tables = document.querySelectorAll('table').length;
            // Linhas de tabela
            const trows = document.querySelectorAll('tr');
            info.tr_count = trows.length;
            // Primeiras 3 linhas
            info.sample_rows = [...trows].slice(0, 5).map(r =>
                [...r.querySelectorAll('td,th')].map(c => c.textContent.trim().substring(0, 60))
            );
            // Divs com classes potencialmente relevantes
            const divs = [...document.querySelectorAll('div[class]')];
            info.div_classes = [...new Set(divs.map(d => d.getAttribute('class')))].filter(c => c).slice(0, 30);
            // Elementos com "pneu" no texto
            const pneuEls = [...document.querySelectorAll('*')].filter(el =>
                el.children.length === 0 &&
                el.textContent.trim().length > 5 &&
                el.textContent.trim().length < 200
            );
            info.text_samples = pneuEls.slice(0, 20).map(el => ({
                tag: el.tagName,
                cls: String(el.className || '').substring(0, 50),
                txt: el.textContent.trim().substring(0, 80)
            }));
            return info;
        }""")

        print(f"\n[probe] Tabelas: {rows_info['tables']}")
        print(f"[probe] Linhas <tr>: {rows_info['tr_count']}")
        print(f"[probe] Amostra linhas:")
        for row in rows_info['sample_rows']:
            if any(c.strip() for c in row):
                print(f"  {row}")
        print(f"\n[probe] Classes div:")
        for cls in rows_info['div_classes']:
            print(f"  .{cls}")
        print(f"\n[probe] Amostras de texto:")
        for s in rows_info['text_samples']:
            if s['txt'].strip():
                print(f"  <{s['tag']} class='{s['cls']}'> {s['txt']!r}")

        # Snippet HTML à volta do preço ou medida
        for keyword in [MEDIDA, "205/55", "€", "pneu"]:
            idx = html.lower().find(keyword.lower())
            if idx >= 0:
                snippet = html[max(0, idx-100):idx+400]
                print(f"\n[probe] === SNIPPET HTML perto de '{keyword}' ===")
                print(snippet[:600])
                break

        await browser.close()

asyncio.run(main())
