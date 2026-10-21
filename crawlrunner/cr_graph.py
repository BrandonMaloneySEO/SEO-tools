import psycopg2
import networkx as nx
import pandas as pd
import logging
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("CrawlRunner_Graph")

class CrawlRunnerGraph:
    def __init__(self):
        # Connect to the local CrawlRunner warehouse
        self.conn = psycopg2.connect(
            dbname="crawlrunner", 
            user="brandon-maloney", 
            password="", 
            host="localhost",
            port="5432"
        )

    def analyze_architecture(self, target_domain, root_url):
        logger.info(f"🕸️ Building Directed Graph for {target_domain}...")
        
        G = nx.DiGraph()
        
        # 1. Pull the validated link map from the database
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT url, audit_json->'link_map' 
                FROM audit_metrics 
                WHERE domain = %s;
            """, (target_domain,))
            rows = cur.fetchall()

        if not rows:
            logger.error("❌ No data found for that domain. Is the crawl finished?")
            return

        # 2. Populate the NetworkX Graph
        for row in rows:
            source_url = row[0]
            links = row[1]
            
            # Ensure the source node exists even if it has no outbound links
            if not G.has_node(source_url):
                G.add_node(source_url)
                
            if links:
                for link in links:
                    target_url = link.get('u')
                    if target_url:
                        # Add directional edge from Source -> Target
                        G.add_edge(source_url, target_url)

        logger.info(f"📊 Graph constructed: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

        # 3. Math on the Fly: Internal PageRank
        logger.info("🧮 Calculating Internal PageRank...")
        # Alpha 0.85 is the standard damping factor used in the original Google algorithm
        pagerank_scores = nx.pagerank(G, alpha=0.85)

        # 4. Math on the Fly: Click Depth
        logger.info("📏 Calculating Click Depth from Root...")
        try:
            # Calculates the shortest path from the root homepage to every other node
            depth_scores = nx.shortest_path_length(G, source=root_url)
        except nx.NetworkXError:
            logger.warning(f"⚠️ Root URL {root_url} not found in graph. Check your exact protocol/trailing slashes.")
            depth_scores = {}

        # 5. Structure the Output
        data = []
        for node in G.nodes():
            # Only analyze nodes that belong to the target domain (ignoring external links)
            if target_domain in node:
                data.append({
                    "URL": node.replace(root_url, ""), # Strip root for cleaner terminal reading
                    "Internal_PR": round(pagerank_scores.get(node, 0), 5),
                    "Click_Depth": depth_scores.get(node, "Isolated / Unreachable")
                })

        # 6. Render the Report
        df = pd.DataFrame(data)
        # Sort by highest internal equity
        df = df.sort_values(by="Internal_PR", ascending=False).reset_index(drop=True)
        
        print("\n" + "="*70)
        print(f"🏛️ ARCHITECTURE REPORT: {target_domain}")
        print("="*70)
        print(df.to_string(index=False))
        print("="*70 + "\n")

if __name__ == "__main__":
    import argparse
    from urllib.parse import urlparse

    parser = argparse.ArgumentParser(description="Generate an Architecture Report from the CrawlRunner DB.")
    parser.add_argument("url", help="The root URL of the crawl (e.g., https://standardsyntax.com)")
    args = parser.parse_args()

    # Automatically extract the domain and root so you only pass one argument
    parsed_url = urlparse(args.url)
    target_domain = parsed_url.netloc
    root_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    CrawlRunnerGraph().analyze_architecture(target_domain, root_url)