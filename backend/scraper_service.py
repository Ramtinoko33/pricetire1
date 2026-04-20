import asyncio
import re
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout
import logging
from datetime import datetime
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Create screenshots directory
SCREENSHOTS_DIR = Path("/app/backend/screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# Check if Playwright browsers are available
PLAYWRIGHT_AVAILABLE = True
try:
    pw_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/pw-browsers')
    chromium_dirs = list(Path(pw_path).glob('chromium_headless_shell-*'))
    if not chromium_dirs:
        PLAYWRIGHT_AVAILABLE = False
        logger.warning(f"Playwright browsers not found at {pw_path}. Scraping features will be disabled.")
except Exception as e:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning(f"Error checking Playwright availability: {e}. Scraping features will be disabled.")

class ScraperBase(ABC):
    """Base class for supplier-specific scrapers"""
    
    def __init__(self, supplier_id: str, supplier_name: str, url_login: str, url_search: str, 
                 username: str, password: str, selectors: Optional[Dict[str, str]] = None):
        self.supplier_id = supplier_id
        self.supplier_name = supplier_name
        self.url_login = url_login
        self.url_search = url_search
        self.username = username
        self.password = password
        self.selectors = selectors or {}
        self.page: Optional[Page] = None
        self.browser: Optional[Browser] = None
        self.playwright = None  # Store playwright instance for cleanup
        
    async def init_browser(self):
        """Initialize browser and page with anti-detection"""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright browsers are not installed. Scraping is disabled in this environment.")
        
        self.playwright = await async_playwright().start()
        # Launch with anti-detection args
        self.browser = await self.playwright.chromium.launch(
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
        # Create context with fake user agent and viewport
        context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
            timezone_id='Europe/Lisbon',
        )
        self.page = await context.new_page()
        
        # Remove webdriver flag
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        self.page.set_default_timeout(30000)  # 30s timeout
        
    async def close_browser(self):
        """Close browser and playwright"""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        self.page = None
            
    async def take_screenshot(self, name: str) -> str:
        """Take screenshot and return path"""
        if not self.page:
            return ""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.supplier_name}_{name}_{timestamp}.png"
        filepath = SCREENSHOTS_DIR / filename
        await self.page.screenshot(path=str(filepath))
        return str(filepath)
    
    @abstractmethod
    async def login(self) -> tuple[bool, str]:
        """Login to supplier website. Returns (success, message)"""
        pass
    
    @abstractmethod
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search for product and return price. Returns None if not found."""
        pass
    
    async def test_login(self) -> tuple[bool, str, Optional[str]]:
        """Test login and return (success, message, screenshot_path)"""
        try:
            await self.init_browser()
            success, message = await self.login()
            screenshot = await self.take_screenshot("test_login")
            await self.close_browser()
            return success, message, screenshot
        except Exception as e:
            logger.error(f"Test login error for {self.supplier_name}: {str(e)}")
            screenshot = await self.take_screenshot("test_login_error") if self.page else None
            await self.close_browser()
            return False, f"Error: {str(e)}", screenshot

class SJoseAdapter(ScraperBase):
    """Adapter for S. José B2B website"""
    
    async def login(self) -> tuple[bool, str]:
        """Login to S. José"""
        try:
            logger.info(f"Navigating to {self.url_login}")
            await self.page.goto(self.url_login, wait_until="domcontentloaded", timeout=60000)
            
            await asyncio.sleep(3)
            
            # Check if already logged in - look for specific elements that only appear after login
            # After login, usually there's a search form or products visible
            already_logged_in = await self.page.locator("input[placeholder*='Medidas'], input[name*='medida']").count() > 0
            if already_logged_in:
                logger.info("Already logged in to S. José")
                return True, "Already logged in"
            
            # Fill username - first text input
            username_inputs = self.page.locator('input[type="text"]')
            if await username_inputs.count() > 0:
                await username_inputs.first.fill(self.username)
                logger.info(f"Filled username: {self.username}")
                await asyncio.sleep(0.5)
            
            # Fill password
            password_inputs = self.page.locator('input[type="password"]')
            if await password_inputs.count() > 0:
                await password_inputs.first.fill(self.password)
                logger.info("Filled password")
                await asyncio.sleep(0.5)
            
            await self.take_screenshot("before_login")
            
            # Click ENTRAR button - look for text or submit button
            login_button = self.page.locator('text=ENTRAR, input[type="submit"], button[type="submit"], button:has-text("ENTRAR")').first
            if await login_button.count() > 0:
                await login_button.click()
                logger.info("Clicked ENTRAR button")
            else:
                # If button not found, try submitting the form directly
                await self.page.keyboard.press("Enter")
                logger.info("Submitted form via Enter key")
            
            # Wait for navigation after login
            await asyncio.sleep(4)
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            
            # CRITICAL FIX: If still on login page after submit, force navigate
            current_url = self.page.url
            if "login.aspx" in current_url.lower():
                logger.warning("Still on login.aspx, forcing navigation to catalog...")
                catalog_urls = [
                    "https://b2b.sjosepneus.com/articles.aspx",
                    "https://b2b.sjosepneus.com/default.aspx",
                ]
                for url in catalog_urls:
                    try:
                        await self.page.goto(url, wait_until="domcontentloaded", timeout=10000)
                        await asyncio.sleep(2)
                        has_content = await self.page.locator('input[type="text"]').count() > 0
                        if has_content:
                            logger.info(f"Successfully navigated to {url}")
                            break
                    except:
                        continue
            
            # Check if login successful - multiple indicators:
            # 1. Search form is visible
            # 2. Product listings are visible  
            # 3. NOT on login page anymore
            success_indicators = [
                await self.page.locator("input[placeholder*='Medidas'], input[name*='medida']").count() > 0,
                await self.page.locator("text=MICHELIN, text=CONTINENTAL, text=BRIDGESTONE").count() > 0,
                await self.page.locator("text=UTILIZADOR").count() == 0,  # Login form gone
                await self.page.locator("input[type='text']").count() > 0,  # Any input present
            ]
            
            success = any(success_indicators)
            logger.info(f"Login check - indicators: {success_indicators}")
            
            await self.take_screenshot("after_login")
            
            # Be more lenient - if we have any text input, proceed
            if success or await self.page.locator("input[type='text']").count() > 0:
                logger.info("Login successful - proceeding with scraping")
                return True, "Login successful"
            else:
                logger.warning(f"Login unclear - indicators: {success_indicators}")
                # Even if unclear, try to continue - might be logged in
                return True, "Login completed (verification unclear)"
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            await self.take_screenshot("login_error")
            return False, f"Login error: {str(e)}"
    
    def normalize_medida(self, medida: str) -> str:
        """Normalize medida format: remove / and R (ex: 195/55R16 -> 1955516)"""
        return medida.replace('/', '').replace('R', '').replace('r', '')
    
    def normalize_indice(self, indice: str) -> str:
        """Normalize indice: remove XL (ex: 94W XL -> 94W)"""
        return indice.replace(' XL', '').replace('XL', '').strip()
    
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search for tire on S. José and return price"""
        try:
            medida_normalized = self.normalize_medida(medida)
            indice_normalized = self.normalize_indice(indice)
            
            logger.info(f"Searching: {medida} → {medida_normalized} | {marca} | {modelo} | {indice} → {indice_normalized}")
            
            await asyncio.sleep(1)
            
            # Find and fill search input (Medidas field)
            medida_input = self.page.locator('input[type="text"], input[placeholder*="Medida"]').first
            await medida_input.clear()
            await medida_input.fill(medida_normalized)
            logger.info(f"Filled search with: {medida_normalized}")
            await asyncio.sleep(0.5)
            
            # Select marca (brand) if dropdown exists
            marca_select = self.page.locator('select').first
            if await marca_select.count() > 0:
                try:
                    # Try exact match first
                    await marca_select.select_option(label=marca)
                    logger.info(f"Selected brand: {marca}")
                except:
                    # Try partial match
                    try:
                        options = await marca_select.locator('option').all_text_contents()
                        for option in options:
                            if marca.lower() in option.lower():
                                await marca_select.select_option(label=option)
                                logger.info(f"Selected brand (partial): {option}")
                                break
                    except:
                        logger.warning(f"Could not select brand: {marca}")
            
            await asyncio.sleep(0.5)
            
            # Click search button
            search_button = self.page.locator('text=PESQUISAR, button:has-text("PESQUISAR"), input[value*="Pesqui"]').first
            if await search_button.count() > 0:
                await search_button.click()
                logger.info("Clicked PESQUISAR")
            else:
                # Fallback: press Enter
                await medida_input.press("Enter")
                logger.info("Pressed Enter to search")
            
            # Wait for results to load
            await asyncio.sleep(3)
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            
            await self.take_screenshot(f"search_results_{medida_normalized}")
            
            # Get page content
            content = await self.page.content()
            
            # Check for "no results"
            if any(text in content.lower() for text in ["sem resultado", "nenhum registo", "não foram encontrados"]):
                logger.info(f"No results found for {medida_normalized}")
                return None
            
            # Extract prices using multiple patterns
            # Pattern 1: XX,XX€ (comma as decimal separator, common in PT)
            # Pattern 2: €XX,XX
            # Pattern 3: Price in text/spans
            
            import re
            
            price_patterns = [
                r'(\d+[,\.]\d{2})\s*€',  # 77,85€ or 77.85€
                r'€\s*(\d+[,\.]\d{2})',  # €77,85
                r'(\d+[,\.]\d{2})€',     # 77,85€
            ]
            
            found_prices = []
            for pattern in price_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    try:
                        # Normalize: replace comma with dot
                        price_str = match.replace(',', '.')
                        price = float(price_str)
                        # Reasonable tire price range: 10-1000 euros
                        if 10 < price < 1000:
                            found_prices.append(price)
                    except ValueError:
                        continue
            
            if found_prices:
                # Return the lowest price found (best deal)
                best_price = min(found_prices)
                logger.info(f"Found {len(found_prices)} prices, lowest: €{best_price}")
                return best_price
            
            logger.warning(f"No valid prices found in results for {medida_normalized}")
            return None
            
        except Exception as e:
            logger.error(f"Search error for {medida}: {str(e)}")
            await self.take_screenshot(f"search_error_{self.normalize_medida(medida)}")
            return None

class EuromaisAdapter(ScraperBase):
    """Adapter for Euromais/Eurotyre B2B website"""
    
    def normalize_medida(self, medida: str) -> str:
        """Normalize medida format: remove / and R"""
        return medida.replace('/', '').replace('R', '').replace('r', '')
    
    def normalize_indice(self, indice: str) -> str:
        """Normalize indice: remove XL"""
        return indice.replace(' XL', '').replace('XL', '').strip()
    
    async def login(self) -> tuple[bool, str]:
        """Login to Euromais"""
        try:
            logger.info(f"Navigating to {self.url_login}")
            await self.page.goto(self.url_login, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            
            # Check if already logged in
            already_logged_in = await self.page.locator("text=Sair, text=Logout").count() > 0
            if already_logged_in:
                logger.info("Already logged in to Euromais")
                return True, "Already logged in"
            
            # Fill username/email  
            username_inputs = self.page.locator('input[type="text"], input[type="email"], input[name*="user"], input[name*="email"], input[name*="login"]')
            if await username_inputs.count() > 0:
                await username_inputs.first.fill(self.username)
                logger.info(f"Filled username: {self.username}")
                await asyncio.sleep(0.5)
            
            # Fill password
            password_inputs = self.page.locator('input[type="password"]')
            if await password_inputs.count() > 0:
                await password_inputs.first.fill(self.password)
                logger.info("Filled password")
                await asyncio.sleep(0.5)
            
            await self.take_screenshot("before_login")
            
            # Click LOGIN button
            login_button = self.page.locator('text=LOGIN, button:has-text("LOGIN"), input[value*="Login"], button[type="submit"], input[type="submit"]').first
            if await login_button.count() > 0:
                async with self.page.expect_navigation(timeout=15000, wait_until="domcontentloaded"):
                    await login_button.click()
                logger.info("Clicked LOGIN button")
            else:
                await self.page.keyboard.press("Enter")
                await asyncio.sleep(2)
                logger.info("Pressed Enter to login")
            
            await asyncio.sleep(3)
            
            # Navigate directly to tire catalog (from screenshot: eurotyrepl.log/consulta-de-pneus)
            catalog_urls = [
                "https://eurotyrepl.log/consulta-de-pneus/?tab=pneus&subtab=pneus",
                "https://www.eurotyre.pt/pt/consulta-de-pneus/?tab=pneus&subtab=pneus",
                "https://www.eurotyre.pt/pt/pneus",
            ]
            
            for url in catalog_urls:
                try:
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=10000)
                    await asyncio.sleep(2)
                    # Check if we have search elements
                    has_search = await self.page.locator('input[type="text"], input[type="search"]').count() > 0
                    if has_search:
                        logger.info(f"Found catalog at {url}")
                        break
                except Exception as e:
                    logger.debug(f"Catalog URL {url} failed: {str(e)}")
                    continue
            
            await self.take_screenshot("after_login")
            
            # Check login success - be lenient
            success_indicators = [
                await self.page.locator("text=Sair, text=Logout").count() > 0,
                await self.page.locator("input[type='text'], input[type='search']").count() > 0,
                "login" not in self.page.url.lower(),
            ]
            
            success = any(success_indicators)
            logger.info(f"Login indicators: {success_indicators}")
            
            if success or await self.page.locator("input[type='text']").count() > 0:
                logger.info("Login successful to Euromais")
                return True, "Login successful"
            else:
                logger.warning("Login verification unclear - proceeding")
                return True, "Login completed (verification unclear)"
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            await self.take_screenshot("login_error")
            return False, f"Login error: {str(e)}"
    
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search for tire on Euromais"""
        try:
            medida_normalized = self.normalize_medida(medida)
            indice_normalized = self.normalize_indice(indice)
            
            logger.info(f"Searching Euromais: {medida} → {medida_normalized} | {marca}")
            
            await asyncio.sleep(1)
            
            # Find and fill search input (first text input on catalog page)
            search_inputs = await self.page.locator('input[type="text"]').all()
            if search_inputs:
                await search_inputs[0].clear()
                await search_inputs[0].fill(medida_normalized)
                logger.info(f"Filled search: {medida_normalized}")
                await asyncio.sleep(1)
                
                # Press Enter or click search icon
                await search_inputs[0].press("Enter")
                logger.info("Submitted search")
            else:
                logger.warning("No search input found")
                return None
            
            # Wait for results
            await asyncio.sleep(4)
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            
            await self.take_screenshot(f"search_results_{medida_normalized}")
            
            # Get page content
            content = await self.page.content()
            
            # Check for no results
            if any(text in content.lower() for text in ["sem resultado", "não encontrado", "nenhum produto", "nenhum registo"]):
                logger.info(f"No results for {medida_normalized}")
                return None
            
            # Extract prices from PREÇO column (based on screenshot)
            # Prices appear in format: € 36.99, € 29.98, etc.
            import re
            
            # Multiple patterns for PT price format
            price_patterns = [
                r'€\s*(\d+[,\.]\d{2})',  # € 36.99 or € 36,99
                r'(\d+[,\.]\d{2})\s*€',  # 36.99€ or 36,99€
                r'"price"\s*:\s*"?(\d+[,\.]\d{2})"?',  # JSON price
                r'PREÇO.*?€\s*(\d+[,\.]\d{2})',  # After PREÇO label
            ]
            
            found_prices = []
            for pattern in price_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    try:
                        price_str = match.replace(',', '.')
                        price = float(price_str)
                        # Reasonable tire price range
                        if 15 < price < 500:
                            found_prices.append(price)
                            logger.debug(f"Found price: €{price}")
                    except ValueError:
                        continue
            
            if found_prices:
                # Remove duplicates and get lowest
                found_prices = list(set(found_prices))
                best_price = min(found_prices)
                logger.info(f"Found {len(found_prices)} unique prices, lowest: €{best_price}")
                return best_price
            
            logger.warning(f"No valid prices extracted for {medida_normalized}")
            return None
            
        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            await self.take_screenshot(f"search_error_{self.normalize_medida(medida)}")
            return None

class MP24Adapter(ScraperBase):
    """Adapter for MP24 (Euromaster Marketplace) using Playwright"""
    
    def normalize_medida(self, medida: str) -> str:
        return medida.replace('/', '').replace('R', '').replace('r', '')
    
    def normalize_indice(self, indice: str) -> str:
        return indice.replace(' XL', '').replace('XL', '').strip()
    
    async def login(self) -> tuple[bool, str]:
        """Login to MP24"""
        try:
            logger.info(f"MP24: Navigating to {self.url_login}")
            await self.page.goto(self.url_login, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            
            # Check if already logged in
            content = await self.page.content()
            if 'sair' in content.lower() or 'logout' in content.lower():
                logger.info("MP24: Already logged in")
                return True, "Already logged in"
            
            # Fill credentials
            await self.page.locator('input[name="_username"]').fill(self.username)
            logger.info(f"MP24: Filled username: {self.username}")
            
            await self.page.locator('input[name="_password"]').fill(self.password)
            logger.info("MP24: Filled password")
            
            await asyncio.sleep(1)
            
            # Submit form via JavaScript (same as the site does)
            await self.page.evaluate("document.getElementById('login_form').submit()")
            logger.info("MP24: Submitted form via JavaScript")
            
            # Wait for navigation
            await asyncio.sleep(4)
            await self.page.wait_for_load_state("networkidle")
            
            # Check if logged in
            current_url = self.page.url
            content = await self.page.content()
            logger.info(f"MP24: Post-login URL: {current_url}")
            logger.info(f"MP24: Has login_form: {'login_form' in content.lower()}, Has sair: {'sair' in content.lower()}")
            
            if 'sair' in content.lower() or 'logout' in content.lower():
                logger.info("MP24: Login successful")
                return True, "Login successful"
            
            # Navigate to tyres page (use tyres2v0 which seems to work better)
            logger.info("MP24: Navigating to tyres2v0 page to verify login...")
            await self.page.goto("https://pt.mp24.online/pt_PT/tyres2v0", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            
            current_url = self.page.url
            content = await self.page.content()
            logger.info(f"MP24: Tyres page URL: {current_url}")
            logger.info(f"MP24: Has matchcodeField: {'matchcodeField' in content}")
            
            if 'login' in current_url.lower() or 'conecte-se' in content.lower():
                logger.error("MP24: Login failed - redirected to login page")
                return False, "Login failed - credentials may be incorrect"
            
            if 'matchcodeField' in content:
                logger.info("MP24: Login verified - matchcodeField present")
                return True, "Login successful"
            
            logger.info("MP24: Login appears successful")
            return True, "Login completed"
            
        except Exception as e:
            logger.error(f"MP24 login error: {str(e)}")
            return False, f"Login error: {str(e)}"
    
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search for tire on MP24 using matchcode"""
        try:
            medida_normalized = self.normalize_medida(medida)
            logger.info(f"MP24 search: {medida} → {medida_normalized}")
            
            # Ensure we're on tyres page (use tyres2v0)
            current_url = self.page.url
            if 'tyres' not in current_url:
                logger.info("MP24: Navigating to tyres2v0 page...")
                await self.page.goto("https://pt.mp24.online/pt_PT/tyres2v0", wait_until="networkidle", timeout=45000)
                await asyncio.sleep(5)
            
            # Check for login redirect
            if 'login' in self.page.url.lower():
                logger.warning("MP24: Session expired - on login page")
                return None
            
            # Wait for page to fully load
            await asyncio.sleep(3)
            
            # Check page content
            content = await self.page.content()
            has_matchcode = 'matchcodeField' in content
            has_filterTop = 'filterTop' in content
            logger.info(f"MP24: Page contains matchcodeField: {has_matchcode}, filterTop: {has_filterTop}")
            
            # Wait for matchcode field with longer timeout
            try:
                await self.page.wait_for_selector('#matchcodeField', timeout=15000)
                logger.info("MP24: matchcodeField found!")
            except:
                logger.warning("MP24: matchcodeField not found after wait")
                # Try alternative - use dropdown filters instead
                if has_filterTop:
                    logger.info("MP24: Trying filter dropdowns instead...")
                    return await self._search_with_filters(medida_normalized)
                return None
            
            # Fill matchcode and search
            await self.page.locator('#matchcodeField').fill(medida_normalized)
            logger.info(f"MP24: Filled matchcode: {medida_normalized}")
            
            await asyncio.sleep(1)
            
            # Click submit button
            submit_btn = self.page.locator('button[type="submit"]').first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                logger.info("MP24: Clicked search button")
            else:
                await self.page.locator('#matchcodeField').press("Enter")
                logger.info("MP24: Pressed Enter")
            
            # Wait for results
            await asyncio.sleep(5)
            await self.page.wait_for_load_state("networkidle")
            
            # Extract prices
            return await self._extract_prices_from_page()
            
        except Exception as e:
            logger.error(f"MP24 search error: {str(e)}")
            return None
    
    async def _search_with_filters(self, medida_normalized: str) -> Optional[float]:
        """Alternative search using dropdown filters"""
        try:
            # Parse medida: 2055516 -> width=205, profile=55, rim=16
            if len(medida_normalized) >= 6:
                width = medida_normalized[:3]  # 205
                profile = medida_normalized[3:5]  # 55
                rim = medida_normalized[5:]  # 16
                
                logger.info(f"MP24: Using filters - width={width}, profile={profile}, rim={rim}")
                
                # Select filters
                await self.page.select_option('#filterTop12', width)
                await asyncio.sleep(1)
                await self.page.select_option('#filterTop13', profile)
                await asyncio.sleep(1)
                await self.page.select_option('#filterTop14', rim)
                await asyncio.sleep(3)
                
                return await self._extract_prices_from_page()
        except Exception as e:
            logger.error(f"MP24 filter search error: {str(e)}")
        return None
    
    async def _extract_prices_from_page(self) -> Optional[float]:
        """Extract prices from current page"""
        content = await self.page.content()
        
        price_patterns = [
            r'€\s*(\d+[,\.]\d{2})',
            r'(\d+[,\.]\d{2})\s*€',
            r'"purchasePrice"\s*:\s*"?(\d+\.?\d*)"?',
            r'"price"\s*:\s*"?(\d+\.?\d*)"?',
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
        
        if found_prices:
            best_price = min(found_prices)
            logger.info(f"MP24: Found {len(found_prices)} prices, best: €{best_price}")
            return best_price
        
        logger.info("MP24: No prices found")
        return None


class PrismanilAdapter(ScraperBase):
    """Adapter for Prismanil B2B using Playwright"""
    
    def normalize_medida(self, medida: str) -> str:
        return medida.replace('/', '').replace('R', '').replace('r', '')
    
    def normalize_indice(self, indice: str) -> str:
        return indice.replace(' XL', '').replace('XL', '').strip()
    
    async def login(self) -> tuple[bool, str]:
        """Login to Prismanil"""
        try:
            logger.info(f"Prismanil: Navigating to {self.url_login}")
            await self.page.goto(self.url_login, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            
            # Check if already logged in (search field visible)
            content = await self.page.content()
            if "txtPesquisa" in content and "btnPesquisar" in content:
                logger.info("Prismanil: Already logged in")
                return True, "Already logged in"
            
            # Fill username
            username_input = self.page.locator('input[type="text"]').first
            if await username_input.count() > 0:
                await username_input.fill(self.username)
                logger.info(f"Filled username: {self.username}")
            
            # Fill password
            password_input = self.page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(self.password)
                logger.info("Filled password")
            
            await asyncio.sleep(1)
            
            # Submit
            submit_btn = self.page.locator('button:has-text("Entrar")').first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                logger.info("Clicked Entrar button")
            else:
                await password_input.press("Enter")
                logger.info("Pressed Enter")
            
            await asyncio.sleep(5)
            await self.page.wait_for_load_state("networkidle")
            
            # Wait for search elements to appear
            try:
                await self.page.wait_for_selector('#txtPesquisa', timeout=15000)
                logger.info("Prismanil login successful - search field visible")
                return True, "Login successful"
            except:
                # Check content anyway
                content = await self.page.content()
                if "Pneus" in content or "pesquisa" in content.lower():
                    logger.info("Prismanil login completed")
                    return True, "Login completed"
            
            return True, "Login completed"
            
        except Exception as e:
            logger.error(f"Prismanil login error: {str(e)}")
            return False, f"Login error: {str(e)}"
    
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search for tire on Prismanil"""
        try:
            medida_normalized = self.normalize_medida(medida)
            logger.info(f"Prismanil search: {medida} → {medida_normalized}")
            
            # Ensure we're on the search page
            current_url = self.page.url
            logger.info(f"Prismanil: Current URL: {current_url}")
            
            if 'pesquisa' not in current_url:
                logger.info("Prismanil: Navigating to pesquisa page...")
                await self.page.goto("https://www.prismanil.pt/b2b/pesquisa", wait_until="load", timeout=30000)
                await asyncio.sleep(5)
            
            # Take screenshot for debugging
            await self.take_screenshot(f"prismanil_search_page_{medida_normalized}")
            
            # Check page content
            content = await self.page.content()
            logger.info(f"Prismanil: Page has 'txtPesquisa': {'txtPesquisa' in content}")
            logger.info(f"Prismanil: Page has 'btnPesquisar': {'btnPesquisar' in content}")
            
            # Wait for search field
            try:
                await self.page.wait_for_selector('#txtPesquisa', timeout=15000)
                logger.info("Prismanil: txtPesquisa found")
            except:
                logger.warning("Prismanil: txtPesquisa not found after wait")
                # Maybe we need to login again
                await self.take_screenshot("prismanil_no_search_field")
                return None
            
            # Fill search field
            search_input = self.page.locator('#txtPesquisa')
            if await search_input.count() > 0:
                await search_input.clear()
                await search_input.fill(medida_normalized)
                logger.info(f"Prismanil: Filled search with {medida_normalized}")
            else:
                logger.warning("Prismanil: #txtPesquisa locator returned 0")
                return None
            
            await asyncio.sleep(1)
            
            # Click search button
            search_btn = self.page.locator('#btnPesquisar')
            if await search_btn.count() > 0:
                await search_btn.click()
                logger.info("Prismanil: Clicked Pesquisar")
            else:
                await search_input.press("Enter")
                logger.info("Prismanil: Pressed Enter")
            
            # Wait for results
            await asyncio.sleep(6)
            await self.page.wait_for_load_state("networkidle")
            
            await self.take_screenshot(f"prismanil_results_{medida_normalized}")
            
            # Extract prices
            content = await self.page.content()
            
            price_patterns = [
                r'€\s*(\d+[,\.]\d{2})',
                r'(\d+[,\.]\d{2})\s*€',
                r'"preco"\s*:\s*"?(\d+[,\.]\d{2})"?',
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
            
            if found_prices:
                best_price = min(found_prices)
                logger.info(f"Prismanil: Found {len(found_prices)} prices, best: €{best_price}")
                return best_price
            
            logger.info(f"Prismanil: No prices found for {medida_normalized}")
            return None
            
        except Exception as e:
            logger.error(f"Prismanil search error: {str(e)}")
            return None
            return None
            
        except Exception as e:
            logger.error(f"Prismanil search error: {str(e)}")
            return None
            return None
            
        except Exception as e:
            logger.error(f"Prismanil search error: {str(e)}")
            return None

class TugaPneusAdapter(ScraperBase):
    """Adapter for TugaPneus B2B website (tugapneus.pt)"""

    def normalize_medida(self, medida: str) -> str:
        return medida.replace('/', '').replace('R', '').replace('r', '')

    def normalize_indice(self, indice: str) -> str:
        return indice.replace(' XL', '').replace('XL', '').strip()

    async def login(self) -> tuple[bool, str]:
        """Login to TugaPneus portal"""
        try:
            logger.info(f"TugaPneus: Navigating to {self.url_login}")
            await self.page.goto(self.url_login, wait_until="domcontentloaded", timeout=60000)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            await asyncio.sleep(3)

            current_url = self.page.url
            if '/produtos' in current_url or 'login' not in current_url.lower():
                return True, "Already logged in"

            await self.take_screenshot("before_login")

            # Fill email — use type() to simulate human input (avoids bot detection)
            email_input = self.page.locator(
                'input[type="email"], input[name="email"], input[name*="mail"], '
                'input[name="username"], input[type="text"]'
            ).first
            if await email_input.count() > 0:
                await email_input.click()
                await email_input.type(self.username, delay=80)
                await asyncio.sleep(0.5)
            else:
                return False, "Email input not found"

            # Fill password
            password_input = self.page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.click()
                await password_input.type(self.password, delay=80)
                await asyncio.sleep(0.5)
            else:
                return False, "Password input not found"

            # Submit — o botão chama-se "EFETUAR LOGIN"
            submit_btn = self.page.locator(
                'button:has-text("EFETUAR LOGIN"), '
                'button:has-text("Efetuar Login"), '
                'button[type="submit"], input[type="submit"], '
                'button:has-text("Login"), button:has-text("Entrar"), '
                'a:has-text("EFETUAR LOGIN")'
            ).first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                logger.info("TugaPneus: Botão de login clicado")
            else:
                await password_input.press("Enter")
                logger.info("TugaPneus: Submit via Enter")

            # Aguardar até o campo password desaparecer (login AJAX)
            for _i in range(40):  # até 20 segundos
                await asyncio.sleep(0.5)
                if await self.page.locator('input[type="password"]').count() == 0:
                    logger.info(f"TugaPneus: Campo password desapareceu ao fim de ~{_i*0.5:.0f}s")
                    break
            else:
                logger.warning("TugaPneus: Campo password ainda visível após 20s")

            try:
                await self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            await asyncio.sleep(2)

            # Tratar popup obrigatório "TOMEI CONHECIMENTO"
            try:
                popup_btn = self.page.locator(
                    'button:has-text("TOMEI CONHECIMENTO"), '
                    'button:has-text("Tomei Conhecimento"), '
                    'a:has-text("TOMEI CONHECIMENTO"), '
                    '[class*="modal"] button, [class*="popup"] button, '
                    '[role="dialog"] button'
                ).first
                if await popup_btn.count() > 0:
                    await popup_btn.click()
                    logger.info("TugaPneus: Popup 'TOMEI CONHECIMENTO' dispensado")
                    await asyncio.sleep(2)
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                else:
                    await asyncio.sleep(3)
                    if await popup_btn.count() > 0:
                        await popup_btn.click()
                        logger.info("TugaPneus: Popup dispensado (2ª tentativa)")
                        await asyncio.sleep(2)
            except Exception as pe:
                logger.warning(f"TugaPneus: Aviso popup: {pe}")

            await self.take_screenshot("after_login")

            current_url = self.page.url
            content = await self.page.content()
            logger.info(f"TugaPneus: URL após submit = {current_url}")

            # Verificar sucesso
            pw_still_visible = await self.page.locator('input[type="password"]').count() > 0
            url_ok = 'produtos' in current_url.lower() or 'conhecimento' in current_url.lower()
            content_ok = any(t in content.lower() for t in [
                'sair', 'logout', 'minha conta', 'bem-vindo', 'olá,', 'carrinho'
            ])

            if pw_still_visible and not url_ok and not content_ok:
                error_msg = ""
                for err_sel in ['.alert-danger', '.error', '[class*="error"]', '.invalid-feedback']:
                    err_el = self.page.locator(err_sel).first
                    if await err_el.count() > 0:
                        error_msg = (await err_el.text_content() or "").strip()[:100]
                        break
                return False, f"Login falhou — credenciais rejeitadas{': ' + error_msg if error_msg else ''}"

            # Se ficou em /produtos após popup = sucesso total
            if url_ok:
                return True, f"Login efectuado com sucesso (URL: {current_url})"

            # Navegar para produtos como verificação final
            await self.page.goto("https://www.tugapneus.pt/produtos",
                                 wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(3)
            if 'login' not in self.page.url.lower():
                return True, "Login efectuado com sucesso"
            return False, f"Login falhou — página de produtos redireccionou para login ({self.page.url})"

        except Exception as e:
            logger.error(f"TugaPneus login error: {str(e)}")
            await self.take_screenshot("login_error")
            return False, f"Login error: {str(e)}"

    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Pesquisa pneu no TugaPneus com pesquisa progressiva e devolve melhor preço.

        Níveis de pesquisa (mais específico → mais geral):
          1. "pneu [marca] [medida] [modelo]"   ex: pneu michelin 205/60R16 primacy 5
          2. "pneu [marca] [medida]"             ex: pneu michelin 205/60R16
          3. "[medida]"                           ex: 205/60R16

        Medida sempre no formato com / e R (205/60R16), nunca normalizado.
        Entre tentativas clica LIMPAR ou limpa o campo manualmente.

        Parse da descrição "PNEU MICHELIN 205/60R16 96H PRIMACY 5 XL":
          marca  = MICHELIN
          medida = 205/60R16
          indice = 96H
          modelo = PRIMACY 5 XL
        """
        try:
            import re as _re
            medida_norm = self.normalize_medida(medida)
            _m = _re.match(r'^(\d{3})(\d{2})(\d{2})$', medida_norm)
            # Medida com / e R: 205/60R16 (nunca normalizado)
            medida_slashed = f"{_m.group(1)}/{_m.group(2)}R{_m.group(3)}" if _m else medida_norm

            await asyncio.sleep(1)

            if '/produtos' not in self.page.url.lower():
                await self.page.goto("https://www.tugapneus.pt/produtos",
                                     wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

            if 'login' in self.page.url.lower():
                return None

            # ── Termos de pesquisa progressivos ──────────────────────────────
            terms: list[str] = []
            if marca and modelo:
                terms.append(f"pneu {marca} {medida_slashed} {modelo}".lower())
            if marca:
                terms.append(f"pneu {marca} {medida_slashed}".lower())
            terms.append(medida_slashed)

            # ── Localizar campo de pesquisa ───────────────────────────────────
            search_input = None
            for _sel in [
                'input[type="search"]',
                'input[name*="search" i]',
                'input[name*="pesq" i]',
                'input[placeholder*="pesq" i]',
                '#search',
                '.search-input input',
                'input[type="text"]',
            ]:
                _el = self.page.locator(_sel).first
                if await _el.count() > 0:
                    search_input = _el
                    break

            # ── Helper LIMPAR ─────────────────────────────────────────────────
            async def _limpar():
                limpar_btn = self.page.locator(
                    'button:has-text("LIMPAR"), button:has-text("Limpar"), '
                    'button:has-text("Clear"), a:has-text("LIMPAR")'
                ).first
                if await limpar_btn.count() > 0:
                    await limpar_btn.click()
                    await asyncio.sleep(0.4)
                elif search_input:
                    await search_input.clear()

            # ── Pesquisa progressiva ──────────────────────────────────────────
            logger.info(f"TugaPneus pesquisa progressiva: {terms}")
            found = False
            for i, term in enumerate(terms):
                logger.info(f"TugaPneus nível {i+1}: '{term}'")

                if i > 0:
                    await _limpar()

                if search_input:
                    await search_input.clear()
                    await search_input.fill(term)
                    await asyncio.sleep(0.4)
                    pesquisar_btn = self.page.locator(
                        'button:has-text("PESQUISAR"), button:has-text("Pesquisar"), '
                        'button:has-text("Buscar"), button[type="submit"], .search-btn'
                    ).first
                    if await pesquisar_btn.count() > 0:
                        await pesquisar_btn.click()
                    else:
                        await search_input.press("Enter")
                else:
                    await self.page.goto(
                        f"https://www.tugapneus.pt/produtos?search={term.replace(' ', '+')}",
                        wait_until="domcontentloaded", timeout=30000
                    )

                # Espera activa até produtos aparecerem no DOM (evita race condition AJAX)
                try:
                    await self.page.wait_for_function(
                        r"[...document.querySelectorAll('tr')].some(tr => /PNEU\s+\w/i.test(tr.textContent))",
                        timeout=12000
                    )
                    logger.info(f"TugaPneus nível {i+1}: resultados encontrados com '{term}'")
                    found = True
                    break
                except Exception:
                    logger.info(f"TugaPneus nível {i+1}: sem resultados para '{term}' → próximo nível")

            if not found:
                logger.info(f"TugaPneus: nenhum resultado para {medida_slashed}")
                return None

            # ── Extracção e parse dos produtos ───────────────────────────────
            # Descrição: "PNEU MICHELIN 205/60R16 96H PRIMACY 5 XL"
            #   marca  = MICHELIN
            #   medida = 205/60R16
            #   indice = 96H
            #   modelo = PRIMACY 5 XL
            products = await self.page.evaluate(r'''() => {
                const products = [];

                function parseTugaDesc(raw) {
                    const text = raw.toUpperCase();
                    // PNEU [MARCA (1-2 palavras)] [XXX/XXRXX] [ÍNDICE] [MODELO...]
                    // Ex: PNEU MICHELIN 205/60R16 96H PRIMACY 5 XL
                    // Ex: PNEU THREE-A 205/55R16 91W P606
                    // Ex: PNEU BF GOODRICH 205/55R16 91V G-FORCE SPORT
                    const m = text.match(
                        /PNEU\s+([\w\-]+(?:\s+[\w\-]+)?)\s+(\d{3}\/\d{2}[R]\d{2})\s+(\d{2,3}[A-Z]{1,2}(?:\s+XL)?)\s*(.*)/
                    );
                    if (!m) return null;
                    return {
                        marca:  m[1].trim(),
                        medida: m[2].trim(),
                        indice: m[3].trim(),   // inclui XL se estiver junto ao índice
                        modelo: m[4].trim()
                    };
                }

                const priceRe = /(\d+[,.]\d{2})\s*€|€\s*(\d+[,.]\d{2})/;

                // Tenta primeiro por linhas de tabela (estrutura TugaPneus)
                const rows = [...document.querySelectorAll('tr')].filter(r => {
                    const t = r.textContent || '';
                    return /PNEU\s+\w/i.test(t) && priceRe.test(t);
                });

                const source = rows.length > 0
                    ? rows
                    : [...document.querySelectorAll(
                        '.product, .product-item, .produto, [class*="product"], .item, .card'
                      )].filter(el => {
                          const t = el.textContent || '';
                          return /PNEU\s+\w/i.test(t) && priceRe.test(t);
                      });

                for (const el of source) {
                    const text = el.textContent || '';
                    const pm = text.match(priceRe);
                    if (!pm) continue;
                    const price = parseFloat((pm[1] || pm[2]).replace(',', '.'));
                    if (price < 15 || price > 800) continue;

                    const parsed = parseTugaDesc(text);
                    products.push({
                        brand:  parsed ? parsed.marca  : '',
                        medida: parsed ? parsed.medida : '',
                        indice: parsed ? parsed.indice : '',
                        model:  parsed ? parsed.modelo : text.trim().substring(0, 120),
                        price
                    });
                }

                // Dedup: mesma marca+medida+indice+modelo → fica com o mais barato
                const seen = new Map();
                for (const p of products) {
                    const k = `${p.brand}|${p.medida}|${p.indice}|${p.model}`;
                    if (!seen.has(k) || p.price < seen.get(k).price) seen.set(k, p);
                }
                return [...seen.values()];
            }''')

            if products:
                best = min(p['price'] for p in products)
                logger.info(f"TugaPneus: {len(products)} produto(s), melhor €{best}")
                for p in products:
                    logger.info(
                        f"  marca={p.get('brand')} medida={p.get('medida')} "
                        f"indice={p.get('indice')} modelo={p.get('model')} preço=€{p.get('price')}"
                    )
                return best

            # Fallback: preços em bruto no HTML
            content = await self.page.content()
            raw_prices: list[float] = []
            for pat in [r'(\d+[,\.]\d{2})\s*€', r'€\s*(\d+[,\.]\d{2})']:
                for m in re.findall(pat, content, re.IGNORECASE):
                    try:
                        p = float(m.replace(',', '.'))
                        if 15 < p < 800:
                            raw_prices.append(p)
                    except ValueError:
                        pass
            if raw_prices:
                logger.info(f"TugaPneus fallback regex: melhor €{min(raw_prices)}")
                return min(raw_prices)
            return None

        except Exception as e:
            logger.error(f"TugaPneus search_product error ({medida}): {e}")
            return None


class InterSprintAdapter(ScraperBase):
    """Adapter for Inter-Sprint B2B portal (customers.inter-sprint.nl).

    O portal usa HTTP Basic Auth — o contexto é criado com http_credentials
    através de init_browser() sobrescrito.
    """

    def normalize_medida(self, medida: str) -> str:
        return medida.replace('/', '').replace('R', '').replace('r', '')

    async def init_browser(self):
        """Inicializa browser com http_credentials para Basic Auth do InterSprint."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright browsers are not installed.")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox', '--disable-setuid-sandbox',
                '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled',
            ]
        )
        context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
            http_credentials={'username': self.username, 'password': self.password},
        )
        self.page = await context.new_page()
        await self.page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

    async def login(self) -> tuple[bool, str]:
        """Login Inter-Sprint via HTTP Basic Auth.

        Navega directamente para customers.inter-sprint.nl — o contexto tem
        http_credentials configuradas, pelo que o 401 Basic Auth é resolvido
        automaticamente. Se houver também form HTML de login, preenche-o.
        """
        try:
            _portal_url = self.url_search or "https://customers.inter-sprint.nl/#ecommerce"
            logger.info(f"InterSprint: Navegando para {_portal_url} (Basic Auth via contexto)")
            await self.page.goto(_portal_url, wait_until="domcontentloaded", timeout=60000)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await asyncio.sleep(2)

            # Guardar HTML para debug
            try:
                with open('/tmp/intersprint_pre_login.html', 'w', encoding='utf-8') as _f:
                    _f.write(await self.page.content())
            except Exception:
                pass

            # Verificar se Basic Auth falhou (401)
            _title = await self.page.title()
            if '401' in _title or 'unauthorized' in _title.lower():
                return False, f"HTTP Basic Auth falhou — verificar credenciais (título: {_title})"

            logger.info(f"InterSprint: Após Basic Auth: {self.page.url} (título: {_title})")

            # Caso o portal tenha também formulário HTML de login (além de Basic Auth)
            if await self.page.locator('input[type="password"]').count() > 0:
                logger.info("InterSprint: Form login HTML detectado — a preencher")
                user_input = self.page.locator(
                    'input[name="username"], input[name="user"], input[name="login"], '
                    'input[id*="user" i], input[id*="name" i], input[type="text"]'
                ).first
                pass_input = self.page.locator('input[type="password"]').first
                if await user_input.count() > 0:
                    await user_input.clear()
                    await user_input.type(self.username, delay=60)
                await pass_input.clear()
                await pass_input.type(self.password, delay=60)
                await asyncio.sleep(0.5)
                submit_btn = self.page.locator(
                    'button[type="submit"], input[type="submit"], '
                    'button:has-text("Login"), button:has-text("Inloggen"), '
                    'button:has-text("Entrar"), button:has-text("OK")'
                ).first
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                else:
                    await pass_input.press("Enter")
                await asyncio.sleep(5)
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(2)
                logger.info(f"InterSprint: Após form login: {self.page.url}")

            logger.info(f"InterSprint: Login com sucesso ({self.page.url})")
            return True, f"Login efectuado ({self.page.url})"

        except Exception as e:
            logger.error(f"InterSprint login error: {e}")
            return False, f"Login error: {e}"

    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Pesquisa progressiva InterSprint. Devolve melhor preço ou None."""
        import re as _re
        try:
            medida_norm = self.normalize_medida(medida)
            _m = _re.match(r'^(\d{3})(\d{2})(\d{2})$', medida_norm)
            medida_fmt = f"{_m.group(1)}/{_m.group(2)}R{_m.group(3)}" if _m else medida_norm
            marca_upper = (marca or '').strip().upper()

            # Garantir que estamos na página certa
            if 'customers.inter-sprint.nl' not in self.page.url:
                await self.page.goto(
                    self.url_search or "https://customers.inter-sprint.nl/#ecommerce",
                    wait_until="domcontentloaded", timeout=30000
                )
                await asyncio.sleep(3)

            # Detectar frame principal (portal usa <frameset>)
            await asyncio.sleep(3)
            _ctx = self.page  # fallback
            _named = self.page.frame(name="mainFrame")
            if _named:
                _ctx = _named
                logger.info(f"InterSprint search: frame 'mainFrame' detectado: {_named.url}")
            else:
                for _fr in self.page.frames:
                    if _fr.url and 'cgirpc32' in _fr.url:
                        _ctx = _fr
                        logger.info(f"InterSprint search: frame detectado: {_fr.url}")
                        break

            # Registar todos os inputs do frame para diagnóstico
            try:
                _all_inputs = await _ctx.evaluate('''() =>
                    Array.from(document.querySelectorAll("input,select,textarea")).map(el => ({
                        tag: el.tagName, type: el.type, name: el.name,
                        id: el.id, placeholder: el.placeholder
                    }))
                ''')
                logger.info(f"InterSprint search: inputs no frame ({len(_all_inputs)}): {_all_inputs[:15]}")
            except Exception as _e:
                logger.warning(f"InterSprint search: não listou inputs: {_e}")

            # Clicar "Procura por pneus" se necessário
            procura_link = _ctx.locator(
                'a:has-text("Procura por pneus"), button:has-text("Procura por pneus"), '
                'a:has-text("procura por pneus"), span:has-text("Procura por pneus"), '
                'a:has-text("Tyre search"), a:has-text("Zoek band"), '
                'a:has-text("Banden zoeken"), a:has-text("Bandenzoeker"), '
                'a:has-text("Banden"), a:has-text("Tyres"), '
                'a[href*="pneus"], a[href*="tyres"], a[href*="band"]'
            ).first
            if await procura_link.count() > 0:
                await procura_link.click()
                await asyncio.sleep(2)

            async def _limpar():
                for sel in [
                    'form[name="f"] input[name="artkode"], input[name="artkode"][class="form2"], input[name="artkode"]',
                    'input[name="lisi"], input[placeholder*="LI" i], input[id*="lisi" i]',
                ]:
                    el = _ctx.locator(sel).first
                    if await el.count() > 0:
                        await el.clear()
                msel = _ctx.locator(
                    'select[name="merk"], select[id*="marca" i], select[name*="marca" i], '
                    'select[id*="brand" i], select[name*="brand" i]'
                ).first
                if await msel.count() > 0:
                    try:
                        await msel.select_option(index=0)
                    except Exception:
                        pass

            async def _tem_resultados() -> bool:
                content = await _ctx.content()
                return bool(_re.search(r'€\s*\d+[,.]\d{2}|\d+[,.]\d{2}\s*€', content))

            async def _pesquisar(use_marca: bool, use_indice: bool, medida_str: str = None) -> bool:
                _val = medida_str or medida_norm
                artigo = _ctx.locator(
                    'form[name="f"] input[name="artkode"], '
                    'input[name="artkode"][class="form2"], '
                    'input[name="artkode"], '
                    'input[id*="artikel" i], input[name*="artikel" i], '
                    'input[id*="artnr" i], input[name*="artnr" i], '
                    'input[placeholder*="Artigo" i], input[id*="artigo" i], '
                    'input[name*="artigo" i], input[placeholder*="article" i], '
                    'input[id*="article" i], input[name*="article" i], '
                    'input[placeholder*="code" i], input[id*="code" i], input[name*="code" i]'
                ).first
                if await artigo.count() > 0:
                    await artigo.clear()
                    await artigo.fill(_val)
                else:
                    _fallback = _ctx.locator('input[type="text"]:visible').first
                    if await _fallback.count() > 0:
                        logger.info("InterSprint search: campo artkode não encontrado; fallback 1º input text")
                        await _fallback.clear()
                        await _fallback.fill(_val)
                        artigo = _fallback
                    else:
                        return False

                if use_marca and marca_upper:
                    msel = _ctx.locator(
                        'select[name="merk"], select[id*="marca" i], select[name*="marca" i], '
                        'select[id*="brand" i], select[name*="brand" i]'
                    ).first
                    if await msel.count() > 0:
                        try:
                            opts = await msel.evaluate(
                                'el => Array.from(el.options).map(o => ({value: o.value, text: o.text}))'
                            )
                            matched = next(
                                (o['value'] for o in opts if marca_upper in o['text'].upper()), None
                            )
                            if matched is not None:
                                await msel.select_option(value=str(matched))
                        except Exception:
                            pass

                if use_indice and indice:
                    lisi = _ctx.locator(
                        'input[name="lisi"], input[placeholder*="LI" i], input[id*="lisi" i]'
                    ).first
                    if await lisi.count() > 0:
                        await lisi.clear()
                        await lisi.fill(indice)

                btn = _ctx.locator(
                    'button:has-text("Procura"), input[value*="Procura" i], '
                    'button:has-text("Search"), input[value*="Search" i], '
                    'button:has-text("Zoeken"), input[value*="Zoeken" i], '
                    'button:has-text("Zoek"), input[value*="Zoek" i], '
                    'button[type="submit"], input[type="submit"]'
                ).first
                if await btn.count() > 0:
                    await btn.click()
                else:
                    await artigo.press("Enter")

                await asyncio.sleep(5)
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                await asyncio.sleep(1)
                return await _tem_resultados()

            logger.info(f"InterSprint: medida_norm={medida_norm} medida_fmt={medida_fmt} marca={marca_upper} indice={indice}")
            found = False
            if marca_upper and indice:
                if await _pesquisar(True, True):
                    found = True
            if not found and marca_upper:
                await _limpar()
                if await _pesquisar(True, False):
                    found = True
            if not found:
                await _limpar()
                if await _pesquisar(False, False):
                    found = True
            if not found and medida_fmt != medida_norm:
                await _limpar()
                if await _pesquisar(False, False, medida_str=medida_fmt):
                    found = True

            if not found:
                logger.info("InterSprint: sem resultados")
                return None

            content = await _ctx.content()

            # Parser de tabela — mesma lógica de isolated_scraper._parse_intersprint_isolated
            price_re = _re.compile(r'€\s*(\d+[,.]\d{2})|(\d+[,.]\d{2})\s*€', _re.IGNORECASE)
            brand_re = _re.compile(
                r'\b(MICHELIN|BRIDGESTONE|CONTINENTAL|PIRELLI|GOODYEAR|DUNLOP|HANKOOK|'
                r'YOKOHAMA|FIRESTONE|KUMHO|TOYO|NEXEN|FALKEN|NOKIAN|VREDESTEIN|MAXXIS|'
                r'GENERAL|UNIROYAL|GISLAVED|FULDA|SEMPERIT|SAVA|KLEBER|BF.?GOODRICH|'
                r'COOPER|MINERVA|WESTLAKE|THREE-A|MASSIMO|LASSA|LANDSAIL|NANKANG|'
                r'SAILUN|WINDFORCE|WANLI|DAVANTI|ATLAS|TORQUE|DOUBLESTAR|LINGLONG|'
                r'ACCELERA|APLUS|GT.?RADIAL|CACHLAND|HIFLY|MILESTONE)\b',
                _re.IGNORECASE,
            )
            tag_re = _re.compile(r'<[^>]+>')
            row_re = _re.compile(r'<tr[^>]*>(.*?)</tr>', _re.IGNORECASE | _re.DOTALL)

            product_prices = []
            for row_m in row_re.finditer(content):
                row_text = _re.sub(r'\s+', ' ', tag_re.sub(' ', row_m.group(1))).strip()
                if len(row_text) < 10:
                    continue
                pm = price_re.search(row_text)
                if not pm:
                    continue
                try:
                    v = float((pm.group(1) or pm.group(2)).replace(',', '.'))
                except ValueError:
                    continue
                if not (15 < v < 800):
                    continue
                bm = brand_re.search(row_text)
                brand = bm.group(1).upper() if bm else 'UNKNOWN'
                product_prices.append(v)
                logger.debug(f"InterSprint produto: {brand} €{v}")

            if product_prices:
                best = min(product_prices)
                logger.info(f"InterSprint: {len(product_prices)} produtos, melhor €{best}")
                return best

            # Fallback: regex global de preços (menos preciso)
            fallback_prices = []
            for m in price_re.finditer(content):
                try:
                    v = float((m.group(1) or m.group(2)).replace(',', '.'))
                    if 15 < v < 800:
                        fallback_prices.append(v)
                except ValueError:
                    pass
            if fallback_prices:
                best = min(fallback_prices)
                logger.info(f"InterSprint: fallback preço €{best}")
                return best

            return None

        except Exception as e:
            logger.error(f"InterSprint search error: {e}")
            return None


class ScraperService:
    """Main scraper service that orchestrates scraping jobs"""
    
    def __init__(self):
        self.adapters: Dict[str, ScraperBase] = {}
    
    def create_adapter(self, supplier: Dict[str, Any]) -> ScraperBase:
        """Create a new adapter for supplier (always creates fresh instance)"""
        supplier_id = supplier['id']
        supplier_name_lower = supplier['name'].lower()
        supplier_url_lower = supplier.get('url_login', '').lower()
        
        # Use password_raw if available, otherwise fall back to password
        password = supplier.get('password_raw') or supplier.get('password', '')
        
        # Select appropriate adapter based on supplier
        if 'mp24' in supplier_name_lower or 'mp24' in supplier_url_lower:
            logger.info(f"Creating MP24Adapter for {supplier['name']}")
            return MP24Adapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=password,
                selectors=supplier.get('selectors')
            )
        elif 'prismanil' in supplier_name_lower or 'prismanil' in supplier_url_lower:
            logger.info(f"Creating PrismanilAdapter for {supplier['name']}")
            return PrismanilAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=password,
                selectors=supplier.get('selectors')
            )
        elif 'sjose' in supplier_name_lower or 'sjose' in supplier_url_lower:
            logger.info(f"Creating SJoseAdapter for {supplier['name']}")
            return SJoseAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=password,
                selectors=supplier.get('selectors')
            )
        elif 'euromais' in supplier_name_lower or 'eurotyre' in supplier_url_lower:
            logger.info(f"Creating EuromaisAdapter for {supplier['name']}")
            return EuromaisAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=password,
                selectors=supplier.get('selectors')
            )
        elif 'tugapneus' in supplier_name_lower or 'tuga' in supplier_name_lower or 'tugapneus' in supplier_url_lower:
            logger.info(f"Creating TugaPneusAdapter for {supplier['name']}")
            return TugaPneusAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier.get('url_login') or 'https://www.tugapneus.pt/login',
                url_search=supplier.get('url_search') or 'https://www.tugapneus.pt/produtos',
                username=supplier['username'],
                password=password,
                selectors=supplier.get('selectors')
            )
        elif 'intersprint' in supplier_name_lower or 'inter-sprint' in supplier_name_lower or 'inter-sprint' in supplier_url_lower:
            logger.info(f"Creating InterSprintAdapter for {supplier['name']}")
            return InterSprintAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier.get('url_login') or 'https://www.inter-sprint.com/',
                url_search=supplier.get('url_search') or 'https://customers.inter-sprint.nl/#ecommerce',
                username=supplier['username'],
                password=password,
                selectors=supplier.get('selectors')
            )
        else:
            # Default: Use SJoseAdapter as generic fallback
            logger.info(f"Creating generic SJoseAdapter for {supplier['name']}")
            return SJoseAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=password,
                selectors=supplier.get('selectors')
            )
    
    def get_adapter(self, supplier: Dict[str, Any]) -> ScraperBase:
        """Get or create adapter for supplier (for backward compatibility)"""
        supplier_id = supplier['id']
        
        # Return existing adapter if available
        if supplier_id in self.adapters:
            return self.adapters[supplier_id]
        
        adapter = self.create_adapter(supplier)
        self.adapters[supplier_id] = adapter
        return adapter
    
    async def test_supplier_login(self, supplier: Dict[str, Any]) -> tuple[bool, str, Optional[str]]:
        """Test login for a supplier"""
        adapter = self.create_adapter(supplier)
        return await adapter.test_login()
    
    async def scrape_product_isolated(self, supplier: Dict[str, Any], medida: str,
                                       marca: str = '', modelo: str = '') -> Optional[float]:
        """Scrape product using background process with file-based communication"""
        import subprocess
        import json
        import uuid
        import time
        
        # Create unique file names for this scrape job
        job_id = str(uuid.uuid4())[:8]
        config_file = f"/app/tmp/scrape_config_{job_id}.json"
        result_file = f"/app/tmp/scrape_result_{job_id}.json"
        
        config = {
            "supplier": supplier['name'],
            "username": supplier['username'],
            "password": supplier.get('password_raw') or supplier.get('password', ''),
            "medida": medida,
            "marca": marca,
            "modelo": modelo
        }
        
        try:
            logger.info(f"Running background scraper for {supplier['name']} - {medida}")
            
            # Write config to file
            with open(config_file, 'w') as f:
                json.dump(config, f)
            
            # Run scraper as completely independent background process
            env = os.environ.copy()
            env['PLAYWRIGHT_BROWSERS_PATH'] = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/pw-browsers')
            
            process = subprocess.Popen(
                ['python3', '/app/backend/background_scraper.py', config_file, result_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                cwd='/app/backend',
                start_new_session=True  # Completely detach from parent
            )
            
            # Wait for result with timeout
            timeout = 120  # 2 minutes
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                # Check if result file exists
                if os.path.exists(result_file):
                    await asyncio.sleep(0.5)  # Small delay to ensure file is fully written
                    try:
                        with open(result_file, 'r') as f:
                            data = json.load(f)
                        
                        # Clean up files
                        os.remove(config_file)
                        os.remove(result_file)
                        
                        price = data.get('price')
                        error = data.get('error')
                        
                        if error:
                            logger.warning(f"Background scraper error for {supplier['name']}: {error}")
                        
                        if price:
                            logger.info(f"Background scraper found price for {supplier['name']}: €{price}")
                            return float(price)
                        else:
                            logger.info(f"Background scraper: No price found for {supplier['name']}")
                            return None
                    except json.JSONDecodeError:
                        # File not fully written yet
                        await asyncio.sleep(1)
                        continue
                
                # Check if process has finished with error
                if process.poll() is not None and not os.path.exists(result_file):
                    logger.error(f"Background scraper process died without result for {supplier['name']}")
                    break
                
                await asyncio.sleep(2)
            
            # Timeout - kill process if still running
            if process.poll() is None:
                process.kill()
            
            # Clean up files if they exist
            if os.path.exists(config_file):
                os.remove(config_file)
            if os.path.exists(result_file):
                os.remove(result_file)
            
            logger.error(f"Background scraper timeout for {supplier['name']}")
            return None
                
        except Exception as e:
            logger.error(f"Background scraper exception for {supplier['name']}: {str(e)}")
            # Clean up
            if os.path.exists(config_file):
                os.remove(config_file)
            if os.path.exists(result_file):
                os.remove(result_file)
            return None
    
    async def scrape_product(self, supplier: Dict[str, Any], medida: str, marca: str,
                            modelo: str, indice: str) -> Optional[float]:
        """Scrape single product from supplier - uses isolated subprocess for reliability"""
        return await self.scrape_product_isolated(supplier, medida, marca=marca, modelo=modelo)
    
    async def cleanup_supplier(self, supplier_id: str):
        """Close browser for supplier"""
        if supplier_id in self.adapters:
            await self.adapters[supplier_id].close_browser()
            del self.adapters[supplier_id]
