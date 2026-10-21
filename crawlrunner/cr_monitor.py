import redis
import psycopg2
import networkx as nx
import pandas as pd
import time
import logging
import json
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("CrawlRunner_Monitor")

class CrawlRunnerMonitor:
    def __init__(self, target_url):
        self.r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        self.conn = psycopg2.connect(
            dbname="crawlrunner", 
            user="brandon-maloney", 
            password="", 
            host="localhost",
            port="5432"
        )
        self.conn.autocommit = True
        
        parsed_url = urlparse(target_url)
        self.target_domain = parsed_url.netloc
        self.root_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    def wait_for_completion(self):
        logger.info("👁️ Overseer Online. Watching Swarm activity...")
        idle_seconds = 0
        
        while True:
            # Check all active working queues
            priority_count = self.r.llen("cr_priority_urls")
            crawl_count = self.r.llen("cr_crawl_jobs")
            nav_count = self.r.llen("cr_nav_jobs")
            
            total_active = priority_count + crawl_count + nav_count
            
            if total_active == 0:
                idle_seconds += 2
                # If queues are completely empty for 10 seconds, the crawl is done
                if idle_seconds >= 10:
                    logger.info("🏁 SWARM IDLE: Crawl complete. Triggering Phase 2 Architecture Analysis...")
                    self.finalize_crawl()
                    break
            else:
                idle_seconds = 0 # Reset if activity resumes
                
            time.sleep(2)

    def finalize_crawl(self):
        """Runs Graph Math and updates PostgreSQL"""
        G = nx.DiGraph()
        
        # 1. Pull the validated link map
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT url, audit_json->'link_map' 
                FROM audit_metrics 
                WHERE domain = %s;
            """, (self.target_domain,))
            rows = cur.fetchall()

        if not rows:
            logger.error("❌ No data found to graph.")
            # We still need to send the stop signal so the bash script continues
            self.r.set("cr_stop_signal", "true")
            return

        # 2. Populate the Graph
        for row in rows:
            source_url = row[0]
            links = row[1]
            if not G.has_node(source_url):
                G.add_node(source_url)
            if links:
                for link in links:
                    if link.get('u'):
                        G.add_edge(source_url, link.get('u'))

        # 3. Calculate Math
        pagerank_scores = nx.pagerank(G, alpha=0.85)
        try:
            depth_scores = nx.shortest_path_length(G, source=self.root_url)
        except nx.NetworkXError:
            depth_scores = {}

        # 4. Save to Database & Structure Report
        logger.info("💾 Saving PageRank and Click Depth to PostgreSQL...")
        report_data = []
        
        with self.conn.cursor() as cur:
            for node in G.nodes():
                if self.target_domain in node:
                    pr = round(pagerank_scores.get(node, 0), 5)
                    depth = depth_scores.get(node, 999) # 999 = Unreachable/Orphan
                    
                    # Package the new metrics
                    graph_metrics = {"pagerank": pr, "click_depth": depth}
                    
                    # Update the existing JSONB payload in PostgreSQL
                    cur.execute("""
                        UPDATE audit_metrics 
                        SET audit_json = jsonb_set(
                            COALESCE(audit_json, '{}'::jsonb), 
                            '{graph_metrics}', 
                            %s::jsonb
                        )
                        WHERE url = %s;
                    """, (json.dumps(graph_metrics), node))

                    report_data.append({"URL": node.replace(self.root_url, ""), "Internal_PR": pr, "Click_Depth": depth})

        # 5. Print the Report
        df = pd.DataFrame(report_data).sort_values(by="Internal_PR", ascending=False).reset_index(drop=True)
        print("\n" + "="*70)
        print(f"🏛️ FINAL ARCHITECTURE REPORT: {self.target_domain}")
        print("="*70)
        print(df.to_string(index=False))
        print("="*70 + "\n")
        
        # 6. Shut down the engine!
        logger.info("🛑 Sending Stop Signal to Swarm via Redis...")
        self.r.set("cr_stop_signal", "true")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="The root URL of the crawl")
    args = parser.parse_args()
    
    # Wait a few seconds to let the ignite script populate the queues before checking
    time.sleep(3) 
    CrawlRunnerMonitor(args.url).wait_for_completion()