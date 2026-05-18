"""Probe v2 Grupo Andres — login directo em online.grupoandres.com."""
import asyncio, re
from playwright.async_api import async_playwright

USERNAME = "pneusdpedrov@mail.telepac.pt"
PASSWORD = "Pb123456"
MEDIDA   = "2055516"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        # LOGIN directo em online.grupoandres.com
        print("[probe2] Login em online.grupoandres.com...")
        await page.goto("https://online.grupoandres.com/login", wait_until="domcontentloaded", timeout=60000)
        await page.locator('input[name="data[Usuario][user]"]').fill(USERNAME)
        await page.locator('input[name="data[Usuario][pass]"]').fill(PASSWORD)
        await page.locator('form#login_form').evaluate("f => f.submit()")
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        print(f"[probe2] URL apos login: {page.url}")

        if 'login' in page.url:
            print("[probe2] ERRO: ainda na pagina de login!")
            html_login = await page.content()
            erros = re.findall(r'class="[^"]*error[^"]*"[^>]*>(.*?)</[a-z]+>', html_login, re.I|re.S)
            print(f"  Erros: {[e.strip()[:80] for e in erros[:5]]}")
            await browser.close()
            return

        # PESQUISA
        search_url = f"https://online.grupoandres.com/buscador?category=cubiertas&searchText={MEDIDA}"
        print(f"[probe2] Pesquisa: {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(2)

        # COUNT INICIAL
        html0 = await page.content()
        c_thumb = len(re.findall(r'result-thumbnail-tooltip=""', html0))
        c_desc  = len(re.findall(r'data-ajax-description="', html0))
        print(f"[probe2] Carga inicial: thumbnails={c_thumb}, ajax-descs={c_desc}")

        # INSPECAO DOM
        info = await page.evaluate("""() => {
            const r = {};
            r.ajax_descs = document.querySelectorAll('[data-ajax-description]').length;
            r.scroll_height = document.body.scrollHeight;
            r.client_height = window.innerHeight;

            // Texto total de resultados
            const full = document.body.innerText;
            const m = full.match(/(\\d+)\\s*(resultados?|produtos?|art[ií]culos?|items?)/i);
            r.total_label = m ? m[0] : null;

            // Paginação
            const pag = document.querySelector('[class*="pagination"], [class*="paging"], nav.pages');
            r.pagination_html = pag ? pag.innerHTML.slice(0, 300) : null;

            // Botão próxima página ou ver mais
            const btns = [...document.querySelectorAll('a, button')].filter(el =>
                /next|siguiente|mais|more|carregar|page-next/i.test(el.textContent + el.className + (el.getAttribute('rel') || ''))
            );
            r.nav_btns = btns.slice(0, 5).map(el => ({
                tag: el.tagName,
                text: el.textContent.trim().slice(0, 40),
                cls: el.className.slice(0, 60),
                href: el.getAttribute('href') || '',
                rel: el.getAttribute('rel') || ''
            }));

            // Amostra de 3 cards
            const cards = [...document.querySelectorAll('[data-ajax-description]')].slice(0, 3);
            r.sample_cards = cards.map(el => ({
                desc: el.getAttribute('data-ajax-description'),
                parent_html: el.parentElement?.outerHTML?.slice(0, 300) || ''
            }));
            return r;
        }""")
        print(f"[probe2] DOM ajax_descs={info['ajax_descs']} scroll_h={info['scroll_height']} client_h={info['client_height']}")
        print(f"[probe2] total_label={info['total_label']}")
        print(f"[probe2] pagination_html={info['pagination_html']}")
        print(f"[probe2] nav_btns={info['nav_btns']}")
        for i, card in enumerate(info.get('sample_cards', [])):
            print(f"[probe2] card[{i}] desc={card['desc']!r}")
            print(f"         parent: {card['parent_html'][:200]}")

        # SCROLL INFINITO
        print(f"\n[probe2] Scroll test...")
        prev = c_desc
        for rnd in range(10):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)
            html_s = await page.content()
            cur = len(re.findall(r'data-ajax-description="', html_s))
            print(f"  scroll #{rnd+1}: descs={cur}")
            if cur == prev:
                break
            prev = cur

        html_final = await page.content()
        c_final = len(re.findall(r'data-ajax-description="', html_final))
        print(f"\n[probe2] TOTAL final apos scroll: {c_final}")

        # Extrair precos e marcas do HTML final
        prices = re.findall(r'class="campaign-(?:price|base-price)"[^>]*>\s*<[^>]*>\s*([\d,.]+)', html_final)
        brands = re.findall(r'<img[^>]+title="([A-Z][A-Z0-9 \-/]+)"', html_final)
        descs  = re.findall(r'data-ajax-description="([^"]+)"', html_final)
        print(f"[probe2] Precos: {len(prices)} | Brands: {len(brands)} | Descs: {len(descs)}")
        print(f"  Brands unicos: {list(set(brands))[:10]}")
        print(f"  Primeiros 5 descs: {descs[:5]}")
        print(f"  Primeiros 5 precos: {prices[:5]}")

        # Michelin?
        mich = [d for d in descs if 'MICHELIN' in d.upper() or 'michelin' in d.lower()]
        print(f"  Michelin descs: {mich}")

        with open("andres_results2.html", "w", encoding="utf-8") as f:
            f.write(html_final)
        print(f"[probe2] HTML guardado: andres_results2.html")

        await browser.close()

asyncio.run(main())
