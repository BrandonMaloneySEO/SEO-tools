import redis
import argparse
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("CrawlRunner_Ignite")

class CrawlRunnerIgnition:
    def __init__(self):
        self.r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        self.r.flushall()
        logger.info("☢️ Redis memory flushed. Clean slate achieved.")

    def spark(self, url):
        """Seeds the crawl. Handles domain seeds and sitemap ingestion."""
        
        # THE FIX: Enforce strict canonicalization to prevent graph fractures
        url = url.split('#')[0].split('?')[0].rstrip('/')
        
        if url.endswith(".xml") or "sitemap" in url.lower():
            logger.info(f"📄 Sitemap detected. Ingesting full domain list...")
            try:
                headers = {"User-Agent": "CrawlRunner/1.0"}
                r = requests.get(url, headers=headers, timeout=15)
                soup = BeautifulSoup(r.content, 'xml')
                
                links = [loc.text for loc in soup.find_all('loc')]
                
                added_count = 0
                for link in links:
                    if not link.endswith(".xml"):
                        # Clean sitemap URLs too just to be safe
                        clean_link = link.split('#')[0].split('?')[0].rstrip('/')
                        self.r.lpush("cr_priority_urls", clean_link)
                        self.r.sadd("cr_queued_urls", clean_link)
                        added_count += 1
                
                logger.info(f"✅ SUCCESS: Ingested {added_count} URLs from sitemap.")
                return
            except Exception as e:
                logger.error(f"❌ Sitemap Ingestion Failed: {e}")

        # Standard Seed Ignition
        self.r.lpush("cr_priority_urls", url)
        self.r.sadd("cr_queued_urls", url)
        logger.info(f"🔥 CRAWLRUNNER IGNITED: Seed URL '{url}' is live.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="The URL to start the crawl (homepage or sitemap.xml)")
    args = parser.parse_args()
    
    CrawlRunnerIgnition().spark(args.url)