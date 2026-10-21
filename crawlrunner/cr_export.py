import psycopg2
import pandas as pd
import argparse
import json
from urllib.parse import urlparse

class CrawlRunnerMasterExport:
    def __init__(self):
        self.conn = psycopg2.connect(
            dbname="crawlrunner", 
            user="brandon-maloney", 
            password="", 
            host="localhost",
            port="5432"
        )

    def export_the_enchilada(self, target_domain):
        print(f"📦 Compiling The Whole Enchilada for {target_domain}...")
        
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT url, audit_json 
                FROM audit_metrics 
                WHERE domain = %s;
            """, (target_domain,))
            rows = cur.fetchall()

        if not rows:
            print("❌ No data found for that domain.")
            return

        master_data = []

        for row in rows:
            url = row[0]
            data = row[1] if row[1] else {}

            # --- Extract Top-Level Modules ---
            baseline = data.get('seo_baseline', {})
            render = data.get('render_diff', {})
            graph = data.get('graph_metrics', {})
            semantics = data.get('semantics', {})
            perf = data.get('performance', {}).get('lighthouse_lab_data', {})
            
            # --- Sub-Module Extractions ---
            ai = semantics.get('ai_intent', {}) if isinstance(semantics.get('ai_intent'), dict) else {}
            anchors_dict = semantics.get('inbound_anchors', {}).get('anchor_distribution', {})
            dom = semantics.get('dom_architecture', {})
            ontology = semantics.get('ontology', {})

            # --- Data Flattening & Formatting ---
            
            # 1. Anchors
            top_anchor = max(anchors_dict, key=anchors_dict.get) if anchors_dict else "None"
            total_inbound = semantics.get('inbound_anchors', {}).get('total_inbound_internal', 0)
            
            # 2. Headings (Flatten H1-H6 into a single readable string)
            h_structure = dom.get('heading_structure', [])
            flattened_headings = " | ".join([f"H{h['level']}: {h['text']}" for h in h_structure]) if h_structure else "None"
            
            # 3. AI Entities
            entities = ", ".join(ai.get('core_entities', [])) if ai.get('core_entities') else "None"
            
            # 4. Schema Mapping (Flatten into readable string)
            mapped_schemas = ontology.get('mapped_entities', [])
            flattened_schemas = " | ".join([f"{s.get('type', 'Unknown')} ({s.get('name', 'No Name')})" for s in mapped_schemas]) if mapped_schemas else "None"
            
            # 5. JS Links
            js_links = ", ".join(render.get('js_dependent_links', [])) if render.get('js_dependent_links') else "None"

            # 6. Status Check
            status = "200 OK" if data.get('performance') else "Error / 404"

            # --- ASSEMBLE THE MASTER ROW ---
            flat_row = {
                "URL": url,
                "Status": status,
                
                # --- Architecture & Graph Math ---
                "Internal PageRank": graph.get('pagerank', 0),
                "Click Depth": graph.get('click_depth', 'Unreachable'),
                "Total Inbound Internal Links": total_inbound,
                "Total Outbound Links (Raw DOM)": render.get('raw_link_count', 0),
                "Total Outbound Links (Rendered DOM)": render.get('rendered_link_count', 0),
                
                # --- Semantic Relevance & AI ---
                "Primary AI Intent": ai.get('primary_intent', 'None'),
                "Core Entities (AI)": entities,
                "Top Inbound Anchor Text": top_anchor,
                
                # --- Technical SEO & Directives ---
                "Title Tag": baseline.get('title', 'None'),
                "Meta Description": baseline.get('meta_description', 'Not Extracted'),
                "Canonical URL": baseline.get('canonical', 'None'),
                "Meta Robots (Nofollow/Noindex)": baseline.get('meta_robots', 'None'),
                
                # --- Content & DOM Skeleton ---
                "H1 Count": baseline.get('h1_count', 0),
                "Full Heading Structure": flattened_headings,
                "Has <main> Tag": dom.get('landmarks', {}).get('has_main', False),
                "Has <nav> Tag": dom.get('landmarks', {}).get('has_nav', False),
                "Has <article> Tag": dom.get('landmarks', {}).get('has_article', False),
                
                # --- Accessibility & Rendering ---
                "Total Images": dom.get('total_images', 0),
                "Missing Alt Attributes": dom.get('missing_alt_count', 0),
                "JS-Dependent Link Count": render.get('js_dependent_count', 0),
                "Lost in Render Link Count": render.get('lost_in_render_count', 0),
                "Specific JS Links": js_links,
                
                # --- Knowledge Graph / Entities ---
                "Total Schemas Found": ontology.get('raw_schema_count', 0),
                "Mapped Schema Entities": flattened_schemas,
                
                # --- Performance (Payload & CWV) ---
                "Server Latency (ms)": data.get('latency_ms', 0),
                "Total Byte Weight (KB)": round(perf.get('total_byte_weight', 0) / 1024, 2) if perf.get('total_byte_weight') else 0,
                "Unused JS (KB)": round(perf.get('unused_javascript', 0) / 1024, 2) if perf.get('unused_javascript') else 0,
                "Lighthouse LCP (ms)": perf.get('LCP_ms', 0),
                "Lighthouse TBT (ms)": perf.get('TBT_ms', 0),
                "Lighthouse CLS": perf.get('CLS_score', 0)
            }
            
            master_data.append(flat_row)

        df = pd.DataFrame(master_data)
        df = df.sort_values(by="Internal PageRank", ascending=False)
        
        filename = f"{target_domain.replace('.', '_')}_the_whole_enchilada.csv"
        df.to_csv(filename, index=False)
        
        print(f"✅ SUCCESS! Master audit exported to: {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export CrawlRunner DB to an absolute unit of a CSV.")
    parser.add_argument("url", help="The target domain (e.g., https://standardsyntax.com)")
    args = parser.parse_args()
    
    parsed_url = urlparse(args.url)
    domain = parsed_url.netloc if parsed_url.netloc else parsed_url.path
    
    CrawlRunnerMasterExport().export_the_enchilada(domain)