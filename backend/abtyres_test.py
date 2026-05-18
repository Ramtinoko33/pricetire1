"""Test standalone do scraper ABTyres — sem DB."""
import asyncio, re
from datetime import datetime, timezone
from playwright.async_api import async_playwright

USERNAME = "pneusdpedrov@mail.telepac.pt"
PASSWORD = "Ab123456"
MEDIDAS  = ["2055516", "1956515"]

def normalize_medida(s: str) -> str:
    return re.sub(r'[/Rr]', '', s.strip())

def _parse_abtyres_html(html: str) -> list:
    nome_re  = re.compile(
        r'[\d/\s]+R\s*\d+\s*-\s*(\d{2,3}[A-Z]{1,2}(?:\s+XL)?)\s*-\s*(.*)',
        re.IGNORECASE,
    )
    row_re   = re.compile(r'<tr\b[^>]*role=["\']row["\'][^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    input_re = re.compile(r'<input\b[^>]*name=["\'](\w+)["\'][^>]*value=["\']([^"\']*)["\']', re.IGNORECASE)
    products = []
    for row_m in row_re.finditer(html):
        row_html = row_m.group(0)
        if 'FFF63D' in row_html or 'fff63d' in row_html:
            continue
        fields = {m.group(1): m.group(2) for m in input_re.finditer(row_html)}
        marca  = fields.get('marca', '').strip().upper()
        nome   = fields.get('nome', '').strip()
        preco  = fields.get('preco', '').strip()
        if not nome or not preco:
            continue
        try:
            price = float(preco.replace(',', '.'))
        except ValueError:
            continue
        if price <= 0:
            continue
        m = nome_re.match(nome)
        if not m:
            continue
        products.append({
            'brand':      marca,
            'model':      m.group(2).strip().upper(),
            'load_index': m.group(1).strip().upper(),
            'price':      price,
        })
    return products


async def scrape_abtyres(page, username, password, medida, skip_login=False):
    result = {"supplier": "ABTyres", "price": None, "error": None, "products": []}
    try:
        if not skip_login:
            print("  [ABTyres] Login...")
            await page.goto("https://b2b.abtyres.pt/menu", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(1)
            current = page.url
            if 'menu' not in current and 'pneus' not in current:
                await page.goto("https://b2b.abtyres.pt/", wait_until="networkidle", timeout=60000)
                await asyncio.sleep(1)
                await page.locator('input[name="user"]').first.fill(username)
                await page.locator('input[type="password"]').first.fill(password)
                await page.locator('button:has-text("Entrar")').first.click()
                await asyncio.sleep(4)
                try:
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                print(f"  [ABTyres] URL após login: {page.url}")
        else:
            await page.goto("https://b2b.abtyres.pt/pneus", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(1)

        medida_norm = normalize_medida(medida)
        print(f"  [ABTyres] Pesquisa: {medida_norm}")
        await page.goto("https://b2b.abtyres.pt/pneus", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(1)

        pesq = page.locator('input[name="pesq"]').first
        await pesq.fill(medida_norm)
        await asyncio.sleep(0.3)
        await page.locator('button:has-text("PESQUISA")').first.click()

        try:
            await page.wait_for_selector('#loading', state='hidden', timeout=30000)
        except Exception:
            await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        html = await page.content()
        products = _parse_abtyres_html(html)
        result["products"] = products
        if products:
            result["price"] = min(p["price"] for p in products)
            print(f"  [ABTyres] {medida}: {len(products)} produtos, mín €{result['price']}")
            for p in products[:5]:
                print(f"    {p['brand']:15} {p['model']:30} {p['load_index']:6} €{p['price']:.2f}")
        else:
            result["error"] = "Nenhum produto encontrado"
            print(f"  [ABTyres] {medida}: sem produtos")
            # Debug snippet
            idx = html.lower().find('row')
            if idx >= 0:
                print(f"  [DBG] snippet: {html[max(0,idx-50):idx+300][:400]}")
    except Exception as e:
        result["error"] = str(e)
        print(f"  [ABTyres] Erro: {e}")
    return result


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
        )
        first = True
        for medida in MEDIDAS:
            page = await ctx.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            result = await scrape_abtyres(page, USERNAME, PASSWORD, medida, skip_login=(not first))
            first = False
            print(f"  => {medida}: {len(result['products'])} produtos, preço mín: €{result['price']}, erro: {result['error']}")
            await page.close()
        await browser.close()

asyncio.run(main())
