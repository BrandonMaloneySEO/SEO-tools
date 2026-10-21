import json
import redis
import psycopg2
import logging
import time
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("CrawlRunner_Oracle")

class CrawlRunnerOracle:
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
        logger.info("🧠 CrawlRunner Oracle: Deterministic Diffing Engine Online.")

    def analyze_dom_diff(self, url, raw_html, rendered_links_payload):
        soup = BeautifulSoup(raw_html, 'lxml')
        
        raw_links = set()
        for a_tag in soup.find_all('a', href=True):
            clean_url = urljoin(url, a_tag['href']).split('#')[0].rstrip('/')
            if clean_url:
                raw_links.add(clean_url)
                
        rendered_links = set()
        link_map = [] 
        for link_obj in rendered_links_payload:
            clean_url = urljoin(url, link_obj['u']).split('#')[0].rstrip('/')
            if clean_url:
                rendered_links.add(clean_url)
                link_map.append({"u": clean_url, "t": link_obj['t']})
        
        js_dependent_links = list(rendered_links - raw_links)
        lost_in_render_links = list(raw_links - rendered_links) 
        
        title = soup.title.string.strip() if soup.title and soup.title.string else None
        h1_tags = [h1.get_text().strip() for h1 in soup.find_all('h1')]
        
        canonical = soup.find('link', rel='canonical')
        canonical_url = canonical['href'] if canonical and canonical.has_attr('href') else None
        
        meta_robots = soup.find('meta', attrs={'name': 'robots'})
        robots_directive = meta_robots['content'] if meta_robots and meta_robots.has_attr('content') else None

        meta_desc = soup.find('meta', attrs={'name': 'description'})
        description_content = meta_desc['content'] if meta_desc and meta_desc.has_attr('content') else None

        return {
            "seo_baseline": {
                "title": title,
                "meta_description": description_content,
                "h1_count": len(h1_tags),
                "h1_content": h1_tags,
                "canonical": canonical_url,
                "meta_robots": robots_directive
            },
            "render_diff": {
                "raw_link_count": len(raw_links),
                "rendered_link_count": len(rendered_links),
                "js_dependent_links": js_dependent_links,
                "js_dependent_count": len(js_dependent_links),
                "lost_in_render_count": len(lost_in_render_links)
            },
            "link_map": link_map 
        }

    def run(self):
        while True:
            if self.r.get("cr_stop_signal") == "true":
                logger.info("🛑 Oracle received stop signal. Shutting down...")
                break
                
            self.r.set("hb_oracle", time.time())
            result = self.r.brpop("cr_crawl_jobs", timeout=5)
            if not result: continue
            
            payload = json.loads(result[1])
            url = payload.get('url')
            raw_html = payload.get('raw_html')
            rendered_links_payload = payload.get('discovered_links', [])
            
            if not raw_html or raw_html.startswith("Raw Fetch Error"):
                logger.error(f"❌ Skipping diff for {url} due to raw fetch failure.")
                continue

            start_perf = time.time()
            
            audit_results = self.analyze_dom_diff(url, raw_html, rendered_links_payload)
            audit_results["latency_ms"] = round((time.time() - start_perf) * 1000, 2)
            
            try:
                with self.conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO audit_metrics (url, domain, audit_json) VALUES (%s, %s, %s) "
                        "ON CONFLICT (url) DO UPDATE SET audit_json = EXCLUDED.audit_json",
                        (url, urlparse(url).netloc, json.dumps(audit_results))
                    )
                
                self.r.lpush("cr_nav_jobs", json.dumps({
                    "url": url, 
                    "link_map": audit_results['link_map']
                }))
                
                js_count = audit_results['render_diff']['js_dependent_count']
                logger.info(f"✅ Oracle Analyzed {url} | Flagged {js_count} JS-Dependent Links")
                
            except Exception as e:
                logger.error(f"❌ DB Write Error for {url}: {e}")

if __name__ == "__main__":
    CrawlRunnerOracle().run()