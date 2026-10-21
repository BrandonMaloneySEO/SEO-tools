import psycopg2
import pandas as pd
import argparse
from urllib.parse import urlparse

class CrawlRunnerSemanticReport:
    def __init__(self):
        self.conn = psycopg2.connect(
            dbname="crawlrunner", 
            user="brandon-maloney", 
            password="", 
            host="localhost",
            port="5432"
        )

    def generate_report(self, target_domain):
        print(f"📊 Pulling Semantic Insights for {target_domain}...\n")
        
        with self.conn.cursor() as cur:
            # Query only rows that have successfully been processed by the Semantic Miner
            cur.execute("""
                SELECT url, audit_json->'semantics' 
                FROM audit_metrics 
                WHERE domain = %s AND audit_json ? 'semantics';
            """, (target_domain,))
            rows = cur.fetchall()

        if not rows:
            print("❌ No semantic data found. Did the miner run successfully?")
            return

        report_data = []
        
        for row in rows:
            url = row[0].replace(f"https://{target_domain}", "") # Clean URL for display
            if not url: url = "/" # Homepage
            
            semantics = row[1]
            
            # --- Safely Extract AI Data ---
            ai_data = semantics.get('ai_intent', {})
            if isinstance(ai_data, dict):
                intent = ai_data.get('primary_intent', 'Parsing Error')
                entities = ", ".join(ai_data.get('core_entities', []))[:40] + "..." # Truncate for display
            else:
                intent = "AI Failed"
                entities = "N/A"

            # --- Safely Extract Anchor Data ---
            anchors = semantics.get('inbound_anchors', {}).get('anchor_distribution', {})
            top_anchor = "None"
            if anchors:
                # Find the anchor text used most frequently to link to this page
                top_anchor = max(anchors, key=anchors.get) 

            # --- Extract DOM/A11y Data ---
            missing_alt = semantics.get('dom_architecture', {}).get('missing_alt_count', 0)
            schema_count = semantics.get('ontology', {}).get('raw_schema_count', 0)

            report_data.append({
                "URL Path": url,
                "AI Primary Intent": intent,
                "Top Anchor Text": top_anchor,
                "Core Entities": entities,
                "Missing Alts": missing_alt,
                "Schemas": schema_count
            })

        # Format and Print the DataFrame
        df = pd.DataFrame(report_data)
        
        # Adjust Pandas display options so the terminal doesn't truncate our columns
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 200)
        pd.set_option('display.max_colwidth', 30)

        print("="*120)
        print(f"🧠 SEMANTIC & KNOWLEDGE GRAPH REPORT: {target_domain}")
        print("="*120)
        print(df.to_string(index=False))
        print("="*120 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="View the Semantic Mining results.")
    parser.add_argument("url", help="The target domain (e.g., standardsyntax.com)")
    args = parser.parse_args()
    
    parsed_url = urlparse(args.url)
    domain = parsed_url.netloc if parsed_url.netloc else parsed_url.path
    
    CrawlRunnerSemanticReport().generate_report(domain)