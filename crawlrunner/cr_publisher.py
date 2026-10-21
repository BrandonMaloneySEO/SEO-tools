import asyncio
import json
import redis
import time
import httpx
import logging
from urllib.parse import urlparse
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("CrawlRunner_Publisher")

class CrawlRunnerPublisher:
    def __init__(self):
        self.r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        logger.info("🕸️ Publisher Swarm Node Online. Ready to scout.")

    async def fetch_raw_html(self, url):
        """Fetches the unrendered HTML for comparison against the rendered DOM."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(url, follow_redirects=True)
                return response.text
            except Exception as e:
                return f"Raw Fetch Error: {str(e)}"

    async def scout_page(self, context, url):
        # 1. Canonicalization & Deduplication check
        canonical_url = url.split('#')[0].split('?')[0].rstrip('/')
        if self.r.sismember("cr_processed_urls", canonical_url):
            return
        
        self.r.sadd("cr_processed_urls", canonical_url)
        page = await context.new_page()
        
        try:
            logger.info(f"🛰️ Scouting: {url}")
            
            # 2. Grab Raw HTML for diffing
            raw_html = await self.fetch_raw_html(url)
            
            # 3. Render DOM with Playwright
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # 4. Extract mapped links and anchor text
            # THE FIX: Boilerplate Link Stripping to clear up the Graph Map
            discovered_links = await page.evaluate("""() => 
                Array.from(document.querySelectorAll('a[href]'))
                .filter(a => !a.closest('nav, header, footer, .nav, .menu, .sidebar, #sidebar'))
                .map(a => ({
                    u: a.href,
                    t: a.innerText.trim() || a.getAttribute('aria-label') || a.getAttribute('title') || ''
                }))
            """)
            
            # 5. Push to Oracle for diffing and Postgres storage
            payload = {
                "url": url,
                "raw_html": raw_html,
                "discovered_links": discovered_links
            }
            
            self.r.lpush("cr_crawl_jobs", json.dumps(payload))
            
        except Exception as e:
            logger.error(f"❌ Scout Error @ {url}: {str(e)}")
        finally:
            # Prevent memory leaks by always closing the tab
            await page.close()

    async def run_swarm(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="CrawlRunner/1.0")
            
            logger.info("🚀 Headless browser context initialized. Waiting for URLs...")
            
            while True:
                # Heartbeat pulse
                self.r.set("hb_publisher", time.time())
                
                # Instant Kill Switch
                if self.r.get("cr_stop_signal") == "true":
                    logger.info("🛑 Publisher received stop signal. Shutting down browser...")
                    break

                urls_to_crawl = []
                for _ in range(3): # Concurrency batch size
                    res = self.r.brpop("cr_priority_urls", timeout=1)
                    if res:
                        urls_to_crawl.append(res[1])
                
                if not urls_to_crawl:
                    continue

                # Run Playwright tasks concurrently
                tasks = [self.scout_page(context, url) for url in urls_to_crawl]
                await asyncio.gather(*tasks)
                
                # Polite crawl delay
                delay = float(self.r.get("cr_crawl_delay") or 1.0)
                await asyncio.sleep(delay)

if __name__ == "__main__":
    asyncio.run(CrawlRunnerPublisher().run_swarm())