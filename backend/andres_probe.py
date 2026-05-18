"""Probe Grupo Andres — diagnóstico de paginação/scroll e count de produtos."""
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

        # ── LOGIN ────────────────────────────────────────────────────────────
        print("[probe] Login...")
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
            [USERNAME, PASSWORD]
        )
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        print(f"[probe] URL após login: {page.url}")

        # ── PESQUISA ─────────────────────────────────────────────────────────
        search_url = f"https://online.grupoandres.com/buscador?category=cubiertas&searchText={MEDIDA}"
        print(f"[probe] Navegar para: {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(2)

        # ── INSPECÇÃO INICIAL ─────────────────────────────────────────────────
        info = await page.evaluate("""() => {
            const r = {};
            // Contar thumbnails / cards de produto
            r.thumbnails = document.querySelectorAll('[result-thumbnail-tooltip]').length;
            r.thumbnails2 = document.querySelectorAll('[class*="product-item"], [class*="result-item"], [class*="thumbnail"]').length;

            // Texto de "total de resultados"
            const allText = document.body.innerText;
            const m = allText.match(/(\\d+)\\s*(result|produto|artigo|item)/i);
            r.total_text = m ? m[0] : null;

            // Elementos com data-ajax-description
            r.ajax_descs = document.querySelectorAll('[data-ajax-description]').length;

            // Paginação
            r.pagination = !!document.querySelector('[class*="pagination"], [class*="pager"], nav[role="navigation"]');
            r.next_btn = !!document.querySelector('a[rel="next"], [class*="next"], [aria-label="next"]');
            r.load_more = !!document.querySelector('[class*="load-more"], [class*="ver-mais"], button[id*="more"]');

            // Altura da página
            r.scroll_height = document.body.scrollHeight;
            r.client_height = window.innerHeight;

            // Classes relevantes
            const divClasses = [...new Set([...document.querySelectorAll('[class]')].map(e => e.className))];
            r.classes_sample = divClasses.filter(c => c && /result|product|item|card|thumb|page|more/i.test(c)).slice(0, 20);

            return r;
        }""")
        print(f"\n[probe] === INSPECÇÃO INICIAL ===")
        for k, v in info.items():
            print(f"  {k}: {v}")

        # ── GUARDAR HTML INICIAL ─────────────────────────────────────────────
        html0 = await page.content()
        count0 = len(re.findall(r'result-thumbnail-tooltip=""', html0))
        count0b = len(re.findall(r'data-ajax-description="', html0))
        print(f"\n[probe] Cards (result-thumbnail-tooltip): {count0}")
        print(f"[probe] data-ajax-description encontrados: {count0b}")

        # Snippet dos primeiros 2 cards
        cards = re.split(r'(?=result-thumbnail-tooltip="")', html0)[1:4]
        for i, c in enumerate(cards):
            print(f"\n[probe] --- Card {i+1} (primeiros 400 chars) ---")
            print(c[:400])

        # ── SCROLL INFINITO ──────────────────────────────────────────────────
        print(f"\n[probe] A fazer scroll para verificar carregamento adicional...")
        prev_count = count0b
        rounds = 0
        while rounds < 8:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)
            html_s = await page.content()
            new_count = len(re.findall(r'data-ajax-description="', html_s))
            print(f"  scroll #{rounds+1}: data-ajax-description = {new_count}")
            if new_count == prev_count:
                break
            prev_count = new_count
            rounds += 1

        html_final = await page.content()
        count_final = len(re.findall(r'data-ajax-description="', html_final))
        print(f"\n[probe] data-ajax-description FINAL após scroll: {count_final}")

        # Guardar HTML final para análise
        with open("andres_results.html", "w", encoding="utf-8") as f:
            f.write(html_final)
        print(f"[probe] HTML final guardado: andres_results.html ({len(html_final)} chars)")

        # ── INSPECÇÃO FINAL ──────────────────────────────────────────────────
        info2 = await page.evaluate("""() => {
            const r = {};
            r.ajax_descs = document.querySelectorAll('[data-ajax-description]').length;
            r.pagination_html = document.querySelector('[class*="pagination"]')?.innerHTML?.slice(0, 500) || 'N/A';
            r.next_btn_html = document.querySelector('a[rel="next"]')?.outerHTML || 'N/A';
            // Verificar botão "ver mais"
            const btns = [...document.querySelectorAll('button, a')].filter(el =>
                /more|mais|seguinte|next|carregar|load/i.test(el.textContent)
            );
            r.more_buttons = btns.slice(0, 5).map(el => ({tag: el.tagName, text: el.textContent.trim().slice(0, 50), class: el.className.slice(0, 50)}));
            return r;
        }""")
        print(f"\n[probe] === INSPECÇÃO FINAL ===")
        print(f"  ajax_descs no DOM: {info2['ajax_descs']}")
        print(f"  pagination_html: {info2['pagination_html'][:200]}")
        print(f"  next_btn_html: {info2['next_btn_html'][:200]}")
        print(f"  more_buttons: {info2['more_buttons']}")

        # ── PREÇOS VISÍVEIS ──────────────────────────────────────────────────
        prices_found = re.findall(r'class="campaign-(?:price|base-price)"[^>]*>\s*<[^>]*>\s*([\d,.]+)', html_final)
        print(f"\n[probe] Preços encontrados no HTML final: {len(prices_found)}")
        print(f"  Primeiros 10: {prices_found[:10]}")

        # Verificar Michelin especificamente
        if 'MICHELIN' in html_final.upper() or 'Michelin' in html_final:
            print("[probe] ✓ MICHELIN encontrado no HTML")
            idx = html_final.upper().find('MICHELIN')
            print(f"  Snippet: {html_final[max(0,idx-100):idx+200]}")
        else:
            print("[probe] ✗ MICHELIN NÃO encontrado no HTML")

        await browser.close()

asyncio.run(main())
