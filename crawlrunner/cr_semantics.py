import psycopg2
import extruct
import json
import logging
import requests
import ollama
import re
from bs4 import BeautifulSoup
from w3lib.html import get_base_url
from pgvector.psycopg2 import register_vector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("CrawlRunner_Semantics")

class CrawlRunnerSemantics:
    def __init__(self):
        self.conn = psycopg2.connect(
            dbname="crawlrunner", 
            user="brandon-maloney", 
            password="", 
            host="localhost",
            port="5432"
        )
        self.conn.autocommit = True
        logger.info("🧠 Semantic Miner Online. Connected to Postgres & Local AI.")

    def extract_ontology(self, html, url):
        """Extracts JSON-LD and captures the full raw payload for DB injection."""
        base_url = get_base_url(html, url)
        data = extruct.extract(html, base_url=base_url, syntaxes=['json-ld'])
        
        schemas = data.get('json-ld', [])
        entities = []
        
        for schema in schemas:
            if '@type' in schema:
                entities.append({
                    "type": schema.get('@type'),
                    "id": schema.get('@id', 'No ID (Disconnected Node)'),
                    "name": schema.get('name', 'Unnamed Entity'),
                    "raw_payload": schema # Store the entire raw chunk
                })
                
        return {"raw_schema_count": len(schemas), "mapped_entities": entities, "raw_data": schemas}

    def extract_inbound_anchors(self, target_url):
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT url AS source_url, elem->>'t' AS anchor_text
                FROM audit_metrics, jsonb_array_elements(audit_json->'link_map') elem
                WHERE elem->>'u' = %s;
            """, (target_url,))
            rows = cur.fetchall()
            
        inbound_links = [{"source": r[0], "anchor": r[1]} for r in rows if r[1]]
        anchor_distribution = {}
        for link in inbound_links:
            text = link['anchor'].lower()
            anchor_distribution[text] = anchor_distribution.get(text, 0) + 1
            
        return {"total_inbound_internal": len(inbound_links), "anchor_distribution": anchor_distribution}

    def validate_dom_architecture(self, html):
        soup = BeautifulSoup(html, 'lxml')
        landmarks = {
            "has_main": soup.find('main') is not None,
            "has_nav": soup.find('nav') is not None,
            "has_article": soup.find('article') is not None
        }
        images = soup.find_all('img')
        missing_alt = [img.get('src', 'Unknown') for img in images if not img.get('alt')]
        
        h_tags = []
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            h_tags.append({"level": int(tag.name[1]), "text": tag.get_text().strip()})
            
        return {
            "landmarks": landmarks, "total_images": len(images), 
            "missing_alt_count": len(missing_alt), "heading_structure": h_tags
        }

    def extract_ai_entities(self, html, title, anchors):
        soup = BeautifulSoup(html, 'lxml')
        for tag in soup(['nav', 'footer', 'aside', 'script', 'style', 'header']):
            tag.decompose()
        
        clean_text = soup.get_text(separator=' ', strip=True)[:4000] 
        
        prompt = f"""
        You are an elite Technical SEO analyzing a web page.
        Page Title: {title}
        Incoming Anchor Text: {list(anchors.keys())[:5]}
        Page Content: {clean_text}
        
        Analyze the text and return ONLY a valid JSON object with two keys:
        1. "primary_intent": A 3-word summary of the search intent.
        2. "core_entities": A list of the 15 most important topical entities discussed.
        """
        
        try:
            response = ollama.chat(model='gemma2', messages=[{'role': 'user', 'content': prompt}])
            raw_response = response['message']['content'].strip()
            
            # THE BULLETPROOF FIX: Regex extraction. 
            # Finds everything from the first { to the last }, ignoring all conversational filler and markdown.
            match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            
            if match:
                clean_json = match.group(0)
                return json.loads(clean_json)
            else:
                raise ValueError("No JSON payload found in AI response")
            
        except Exception as e:
            logger.error(f"❌ Entity Extraction failed for {title}: {e}")
            return {"primary_intent": "Unknown", "core_entities": []}

    def generate_and_store_embedding(self, url, html, title, intent):
        soup = BeautifulSoup(html, 'lxml')
        for tag in soup(['nav', 'footer', 'aside', 'script', 'style', 'header']):
            tag.decompose()
        
        clean_text = soup.get_text(separator=' ', strip=True)[:4000]
        text_to_embed = f"Title: {title}. Intent: {intent}. Content: {clean_text}"
        
        try:
            response = ollama.embeddings(model='nomic-embed-text', prompt=text_to_embed)
            vector = response['embedding']
            register_vector(self.conn)
            with self.conn.cursor() as cur:
                cur.execute("UPDATE audit_metrics SET content_vector = %s WHERE url = %s;", (vector, url))
            return True
        except Exception as e:
            return False

    def mine_database(self, domain):
        logger.info(f"⛏️ Starting Semantic Mining for {domain}...")
        with self.conn.cursor() as cur:
            cur.execute("SELECT url, audit_json FROM audit_metrics WHERE domain = %s;", (domain,))
            rows = cur.fetchall()

        for row in rows:
            url, audit_json = row[0], row[1] if row[1] else {}
            if audit_json.get('semantics'): continue
            
            try: html = requests.get(url, timeout=10).text
            except: continue
                
            title = audit_json.get('seo_baseline', {}).get('title', 'Unknown')
            logger.info(f"🔍 Analyzing: {url}")

            ontology_data = self.extract_ontology(html, url)
            anchor_data = self.extract_inbound_anchors(url)
            ai_data = self.extract_ai_entities(html, title, anchor_data['anchor_distribution'])
            dom_data = self.validate_dom_architecture(html)
            
            intent_label = ai_data.get('primary_intent', 'Unknown')
            self.generate_and_store_embedding(url, html, title, intent_label)
            
            semantics_payload = {
                "ontology": ontology_data,
                "inbound_anchors": anchor_data,
                "ai_intent": ai_data,
                "dom_architecture": dom_data
            }
            
            with self.conn.cursor() as cur:
                cur.execute("""
                    UPDATE audit_metrics 
                    SET audit_json = jsonb_set(COALESCE(audit_json, '{}'::jsonb), '{semantics}', %s::jsonb)
                    WHERE url = %s;
                """, (json.dumps(semantics_payload), url))

        logger.info("✅ Semantic Mining Complete. Database Updated.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("domain", help="The target domain to mine (e.g., standardsyntax.com)")
    args = parser.parse_args()
    CrawlRunnerSemantics().mine_database(args.domain)