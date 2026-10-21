import json
import redis
import psycopg2
import time
import logging
from urllib.parse import urlparse, urljoin

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("CrawlRunner_Navigation")

class CrawlRunnerNavigation:
    def __init__(self):
        self.r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        
        self.conn = psycopg2.connect(
            dbname="crawlrunner", 
            user="brandon-maloney", 
            password="", 
            host="localhost",
            port="5432"
        )
        self.conn.autocommit = True
        logger.info("🗺️ Navigation Router Online. Trap detection active.")

    def is_valid_asset(self, url, domain):
        """Ensures we only queue internal HTML pages, ignoring PDFs, images, etc."""
        try:
            parsed = urlparse(url)
            if parsed.netloc != domain: 
                return False
                
            static_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.pdf', '.zip', '.svg', '.ico', '.mp4']
            if any(url.lower().endswith(ext) for ext in static_extensions): 
                return False
                
            return True
        except: 
            return False

    def is_trap(self, url, max_depth):
        """Catches infinite calendar loops or repeating directories."""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        segments = [s for s in path.split('/') if s]
        
        if len(segments) > max_depth:
            return True
            
        for i in range(len(segments) - 1):
            if segments[i] == segments[i+1]:
                return True
        return False

    def run(self):
        while True:
            if self.r.get("cr_stop_signal") == "true":
                logger.info("🛑 Navigation received stop signal. Shutting down...")
                break
                
            self.r.set("hb_navigation", time.time())
            
            result = self.r.brpop("cr_nav_jobs", timeout=5)
            if not result: continue
            
            payload = json.loads(result[1])
            source_url = payload.get('url')
            links = payload.get('link_map', [])
            
            parsed_source = urlparse(source_url)
            base_url = f"{parsed_source.scheme}://{parsed_source.netloc}"
            domain = parsed_source.netloc
            
            limit = int(self.r.get("cr_crawl_limit") or 150)
            max_depth = int(self.r.get("cr_max_depth") or 5)
            
            for link in links:
                raw_target = link.get('u')
                if not raw_target: continue

                target = urljoin(base_url, raw_target).split('#')[0].split('?')[0].rstrip('/')
                
                if self.is_valid_asset(target, domain) and not self.is_trap(target, max_depth):
                    with self.conn.cursor() as cur:
                        # 1. Check if we've already audited this URL
                        cur.execute("SELECT 1 FROM audit_metrics WHERE url = %s", (target,))
                        
                        # 2. Check if it's already in the Redis queue
                        if not cur.fetchone() and not self.r.sismember("cr_queued_urls", target):
                            
                            # 3. Check against our global URL limit
                            cur.execute("SELECT COUNT(*) FROM audit_metrics WHERE domain = %s", (domain,))
                            if cur.fetchone()[0] < limit:
                                self.r.lpush("cr_priority_urls", target)
                                self.r.sadd("cr_queued_urls", target)

if __name__ == "__main__":
    CrawlRunnerNavigation().run()