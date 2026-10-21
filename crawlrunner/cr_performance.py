import asyncio
import json
import psycopg2
import logging
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("CrawlRunner_LocalPerformance")

class CrawlRunnerLocalPerformance:
    def __init__(self):
        self.conn = psycopg2.connect(
            dbname="crawlrunner", 
            user="brandon-maloney", 
            password="", 
            host="localhost",
            port="5432"
        )
        self.conn.autocommit = True
        logger.info("🚦 Lighthouse Engine Online. Ready to audit.")

    async def run_lighthouse(self, url, semaphore):
        """Runs the Lighthouse CLI locally inside a throttled async wrapper."""
        async with semaphore:
            logger.info(f"⚡ Auditing: {url}")
            
            cmd = f'npx lighthouse "{url}" --output json --quiet --chrome-flags="--headless --no-sandbox"'
            
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # Anti-Zombie Timeout (90 seconds max per page)
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    logger.warning(f"⚠️ Lighthouse timeout on {url}. Process killed.")
                    return None

                if proc.returncode != 0:
                    logger.error(f"❌ Lighthouse failed for {url}")
                    return None
                    
                report = json.loads(stdout.decode('utf-8'))
                
                audits = report.get('audits', {})
                metrics = {
                    "performance_score": report.get('categories', {}).get('performance', {}).get('score', 0) * 100,
                    "fcp": audits.get('first-contentful-paint', {}).get('displayValue', 'N/A'),
                    "lcp": audits.get('largest-contentful-paint', {}).get('displayValue', 'N/A'),
                    "tbt": audits.get('total-blocking-time', {}).get('displayValue', 'N/A'),
                    "cls": audits.get('cumulative-layout-shift', {}).get('displayValue', 'N/A'),
                    "speed_index": audits.get('speed-index', {}).get('displayValue', 'N/A'),
                    "total_byte_weight": audits.get('total-byte-weight', {}).get('numericValue', 0),
                    "unused_javascript": audits.get('unused-javascript', {}).get('numericValue', 0),
                    "dom_size": audits.get('dom-size', {}).get('numericValue', 0)
                }
                
                return {"lighthouse_lab_data": metrics}
                
            except Exception as e:
                logger.error(f"❌ Error executing Lighthouse for {url}: {e}")
                return None

    async def process_url(self, url, semaphore):
        performance_data = await self.run_lighthouse(url, semaphore)
        
        if performance_data:
            try:
                with self.conn.cursor() as cur:
                    # Non-destructive update: Merges performance data into existing JSON
                    cur.execute("""
                        UPDATE audit_metrics 
                        SET audit_json = jsonb_set(
                            COALESCE(audit_json, '{}'::jsonb), 
                            '{performance}', 
                            %s::jsonb
                        )
                        WHERE url = %s;
                    """, (json.dumps(performance_data), url))
                logger.info(f"✅ Saved Vitals for {url}")
            except Exception as e:
                logger.error(f"❌ Database error for {url}: {e}")

    async def audit_domain(self, domain):
        logger.info(f"🚀 Starting Local Concurrent Performance Audit for {domain}...")

        with self.conn.cursor() as cur:
            # Only pull URLs that haven't been audited for performance yet
            cur.execute("""
                SELECT url FROM audit_metrics 
                WHERE domain = %s AND NOT (audit_json ? 'performance');
            """, (domain,))
            urls = [row[0] for row in cur.fetchall()]

        if not urls:
            logger.info("✅ No new URLs to audit. Performance data is up to date.")
            return

        # THE BOUNCER: Strictly limits us to 3 concurrent Lighthouse instances
        semaphore = asyncio.Semaphore(3)
        
        tasks = [self.process_url(url, semaphore) for url in urls]
        await asyncio.gather(*tasks)
        
        logger.info("🏁 Phase 4 Local Performance Audit Complete!")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Phase 4: Local Async Core Web Vitals")
    parser.add_argument("url", help="The target domain (e.g., https://standardsyntax.com)")
    args = parser.parse_args()
    
    parsed_url = urlparse(args.url)
    domain = parsed_url.netloc if parsed_url.netloc else parsed_url.path
    
    asyncio.run(CrawlRunnerLocalPerformance().audit_domain(domain))