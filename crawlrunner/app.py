from flask import Flask, render_template, request, jsonify
import psycopg2
import json
import ollama
from urllib.parse import urlparse

app = Flask(__name__)

def get_db():
    conn = psycopg2.connect(
        dbname="crawlrunner", 
        user="brandon-maloney", 
        password="", 
        host="localhost",
        port="5432"
    )
    conn.autocommit = True
    return conn

def build_folder_tree(urls, domain):
    tree = {}
    for url in urls:
        path = urlparse(url).path
        if not path or path == "/":
            tree['/ (Homepage)'] = {'_url': url}
            continue
        parts = [p for p in path.split('/') if p]
        if not parts:
            tree['/ (Homepage)'] = {'_url': url}
            continue
        current = tree
        for i, part in enumerate(parts):
            if part not in current: current[part] = {}
            if i == len(parts) - 1: current[part]['_url'] = url
            current = current[part]
    return tree

@app.route("/")
def dashboard():
    domain = request.args.get('domain', 'standardsyntax.com')
    with get_db().cursor() as cur:
        cur.execute("SELECT DISTINCT domain FROM audit_metrics ORDER BY domain;")
        domains = [row[0] for row in cur.fetchall()]
        if not domains: domains = [domain]
        elif domain not in domains: domain = domains[0]
            
        cur.execute("SELECT url FROM audit_metrics WHERE domain = %s ORDER BY url;", (domain,))
        urls = [row[0] for row in cur.fetchall()]
        
    tree = build_folder_tree(urls, domain)
    return render_template("index.html", domain=domain, domains=domains, tree=tree)

def fetch_url_data(domain, url):
    with get_db().cursor() as cur:
        cur.execute("SELECT audit_json FROM audit_metrics WHERE domain = %s AND url = %s;", (domain, url))
        row = cur.fetchone()
        data = row[0] if row else {}
        
        cur.execute("""
            SELECT pr_percentile FROM (
                SELECT url, PERCENT_RANK() OVER(ORDER BY COALESCE(CAST(audit_json->'graph_metrics'->>'pagerank' AS NUMERIC), 0)) * 100 AS pr_percentile 
                FROM audit_metrics WHERE domain = %s
            ) AS ranks WHERE url = %s;
        """, (domain, url))
        pr_row = cur.fetchone()
        pr_percentile = round(pr_row[0], 1) if pr_row and pr_row[0] is not None else 0.0
        return data, pr_percentile

def generate_red_flags(data):
    flags = []
    score = data.get('performance', {}).get('lighthouse_lab_data', {}).get('performance_score')
    if isinstance(score, (int, float)):
        if score < 50: flags.append(f"<span style='color: #ef4444; font-weight: 800;'>[CRITICAL] Poor Performance:</span> Lighthouse score is critically low ({score}/100).")
        elif score < 90: flags.append(f"<span style='color: #f59e0b; font-weight: 800;'>[WARNING] Mediocre Performance:</span> Lighthouse score is {score}/100.")
            
    js_links = data.get('render_diff', {}).get('js_dependent_count', 0)
    if js_links > 0: flags.append(f"<span style='color: #f59e0b; font-weight: 800;'>[WARNING] Rendering Risk:</span> {js_links} internal links are locked behind client-side JavaScript.")
        
    missing_alts = data.get('semantics', {}).get('dom_architecture', {}).get('missing_alt_count', 0)
    if missing_alts > 0: flags.append(f"<span style='color: #ef4444; font-weight: 800;'>[ERROR] Accessibility:</span> {missing_alts} image elements are missing ALT text attributes.")
        
    landmarks = data.get('semantics', {}).get('dom_architecture', {}).get('landmarks', {})
    if not landmarks.get('has_main'): flags.append("<span style='color: #ef4444; font-weight: 800;'>[ERROR] Architecture:</span> Missing <code>&lt;main&gt;</code> HTML5 landmark.")
        
    h1_count = data.get('seo_baseline', {}).get('h1_count', 0)
    if h1_count == 0: flags.append("<span style='color: #ef4444; font-weight: 800;'>[ERROR] Hierarchy:</span> Page is missing an H1 tag.")
    elif h1_count > 1: flags.append("<span style='color: #f59e0b; font-weight: 800;'>[WARNING] Hierarchy:</span> Multiple H1 tags detected on page.")

    if not flags: return "<p style='color: #10b981; font-weight: 700;'>✅ No critical technical errors detected.</p>"
        
    html = "<ul style='padding-left: 20px; color: #0f172a; line-height: 1.8;'>"
    for f in flags: html += f"<li style='margin-bottom: 8px;'>{f}</li>"
    return html + "</ul>"

@app.route("/api/overview")
def get_overview():
    domain = request.args.get('domain')
    filter_path = request.args.get('path', '')
    exact_url = request.args.get('exact_url')
    
    if exact_url:
        clean_url = exact_url.replace(f"https://{domain}", "") or "/"
        return f"""
            <div style="margin-bottom: 20px;">
                <h2 style="margin: 0; color: #9333ea; font-size: 1.5em; word-break: break-all;">{clean_url}</h2>
                <a href="{exact_url}" target="_blank" style="color: #64748b; font-size: 0.85em; text-decoration: none;">🔗 Open Live Page</a>
            </div>
            <div class="glass-panel tab-container">
                <button class="tab-btn active" hx-get="/api/tab/overview?domain={domain}&url={exact_url}" hx-target="#tab-content" onclick="activateTab(this)">Diagnostic Overview</button>
                <button class="tab-btn" hx-get="/api/tab/performance?domain={domain}&url={exact_url}" hx-target="#tab-content" onclick="activateTab(this)">Performance</button>
                <button class="tab-btn" hx-get="/api/tab/semantics?domain={domain}&url={exact_url}" hx-target="#tab-content" onclick="activateTab(this)">Entity Semantics</button>
                <button class="tab-btn" hx-get="/api/tab/architecture?domain={domain}&url={exact_url}" hx-target="#tab-content" onclick="activateTab(this)">Architecture</button>
                <button class="tab-btn" hx-get="/api/tab/graph?domain={domain}&url={exact_url}" hx-target="#tab-content" onclick="activateTab(this)">Internal Link Map</button>
            </div>
            <div id="tab-content" hx-get="/api/tab/overview?domain={domain}&url={exact_url}" hx-trigger="load"></div>
        """
    else:
        return generate_global_dashboard(domain, filter_path)

@app.route("/api/tab/overview")
def tab_overview():
    domain = request.args.get('domain')
    url = request.args.get('url')
    data, pr_percentile = fetch_url_data(domain, url)
    
    intent = data.get('semantics', {}).get('ai_intent', {}).get('primary_intent', 'Unknown')
    pr = round(data.get('graph_metrics', {}).get('pagerank', 0), 5)
    perf = data.get('performance', {}).get('lighthouse_lab_data', {})
    score = perf.get('performance_score', 'N/A')
    
    return f"""
        <div class="stat-grid">
            <div class="stat-box glass-panel brand"><h3>Semantic Intent</h3><p style="font-size: 1.5em; line-height: 1.2;">{intent}</p></div>
            <div class="stat-box glass-panel"><h3>Authority Percentile</h3><p>{pr_percentile}%</p></div>
            <div class="stat-box glass-panel {'warning' if isinstance(score, (int, float)) and score < 90 else ''}"><h3>Lighthouse Score</h3><p>{score}</p></div>
            <div class="stat-box glass-panel"><h3>Raw PageRank</h3><p style="font-size: 1.5em;">{pr}</p></div>
        </div>
        <div class="viz-card glass-panel" style="margin-bottom: 20px;">
            <div class="card-header">Diagnostic Callouts</div>
            {generate_red_flags(data)}
        </div>
    """

@app.route("/api/tab/performance")
def tab_performance():
    domain = request.args.get('domain')
    url = request.args.get('url')
    data, _ = fetch_url_data(domain, url)
    perf = data.get('performance', {}).get('lighthouse_lab_data', {})
    return f"""
        <div class="viz-grid">
            <div class="viz-card glass-panel">
                <div class="card-header">Core Web Vitals & Speed</div>
                <table class="data-table">
                    <tr><th>Performance Score</th><td><strong style="font-size: 1.2em; color: {'#10b981' if type(perf.get('performance_score')) in [int, float] and perf.get('performance_score') > 85 else '#ef4444'};">{perf.get('performance_score', 'N/A')} / 100</strong></td></tr>
                    <tr><th>First Contentful Paint (FCP)</th><td>{perf.get('fcp', 'N/A')}</td></tr>
                    <tr><th>Largest Contentful Paint (LCP)</th><td>{perf.get('lcp', 'N/A')}</td></tr>
                    <tr><th>Total Blocking Time (TBT)</th><td>{perf.get('tbt', 'N/A')}</td></tr>
                    <tr><th>Cumulative Layout Shift (CLS)</th><td>{perf.get('cls', 'N/A')}</td></tr>
                </table>
            </div>
            <div class="viz-card glass-panel">
                <div class="card-header">Payload & Network</div>
                <table class="data-table">
                    <tr><th>Server Response Latency</th><td>{data.get('latency_ms', 'Unknown')} ms</td></tr>
                    <tr><th>Total Page Weight</th><td><strong>{round(perf.get('total_byte_weight', 0) / 1024, 2) if perf.get('total_byte_weight') else 0} KB</strong></td></tr>
                    <tr><th>Unused JavaScript Weight</th><td><strong>{round(perf.get('unused_javascript', 0) / 1024, 2) if perf.get('unused_javascript') else 0} KB</strong></td></tr>
                </table>
            </div>
        </div>
    """

@app.route("/api/tab/semantics")
def tab_semantics():
    domain = request.args.get('domain')
    url = request.args.get('url')
    data, _ = fetch_url_data(domain, url)
    
    semantics = data.get('semantics', {})
    entities = semantics.get('ai_intent', {}).get('core_entities', [])
    schema = semantics.get('ontology', {})
    schemas = schema.get('mapped_entities', [])
    
    entity_badges = "".join([f"<span class='badge badge-purple'>{e}</span>" for e in entities])
    schema_badges = "".join([f"<span class='badge badge-blue'>{s.get('type', 'Unknown')}</span>" for s in schemas])
    
    raw_schema_data = schema.get('raw_data', schemas)
    schema_json_str = json.dumps(raw_schema_data, indent=2) if raw_schema_data else "No schema payload extracted for this URL."
    
    neighbors_html = ""
    with get_db().cursor() as cur:
        cur.execute("""
            SELECT url, ROUND((1 - (content_vector <=> (SELECT content_vector FROM audit_metrics WHERE url = %s)))::numeric, 4) AS similarity
            FROM audit_metrics WHERE url != %s AND content_vector IS NOT NULL
            ORDER BY content_vector <=> (SELECT content_vector FROM audit_metrics WHERE url = %s) LIMIT 5;
        """, (url, url, url))
        for n_url, sim in cur.fetchall():
            pct = float(sim) * 100
            color = "#ef4444" if pct >= 90 else ("#f59e0b" if pct >= 75 else "#10b981")
            neighbors_html += f"<li style='margin-bottom: 12px;'><div style='display: flex; justify-content: space-between; font-size: 0.9em; margin-bottom: 5px;'><span style='color: #9333ea; font-weight: 600; cursor: pointer;' hx-get='/api/overview?domain={domain}&exact_url={n_url}' hx-target='#overview-board'>{n_url.replace(f'https://{domain}', '') or '/'}</span><strong>{pct:.1f}% Match</strong></div><div style='background: rgba(15,23,42,0.05); height: 6px; border-radius: 3px;'><div style='background: {color}; width: {pct}%; height: 100%;'></div></div></li>"

    return f"""
        <div class="viz-grid">
            <div class="viz-card glass-panel">
                <div class="card-header">Semantic Extraction Summary</div>
                <div style="margin-bottom: 20px;"><strong style="display: block; color: #64748b; margin-bottom: 5px;">Primary Intent Focus:</strong><span style="font-size: 1.3em; font-weight: 800; color: #0f172a;">{semantics.get('ai_intent', {}).get('primary_intent', 'Unknown')}</span></div>
                <div style="margin-bottom: 20px;"><strong style="display: block; color: #64748b; margin-bottom: 10px;">Extracted Entities ({len(entities)}):</strong><div style="display: flex; flex-wrap: wrap; gap: 8px;">{entity_badges if entities else '<i>None</i>'}</div></div>
                <div><strong style="display: block; color: #64748b; margin-bottom: 10px;">JSON-LD Types Injected:</strong><div style="display: flex; flex-wrap: wrap; gap: 8px;">{schema_badges if schemas else '<i>None</i>'}</div></div>
            </div>
            <div class="viz-card glass-panel">
                <div class="card-header">Vector Space Nearest Neighbors</div>
                <ul style="list-style: none; padding: 0; margin: 0;">{neighbors_html if neighbors_html else "<i>No vector map found.</i>"}</ul>
            </div>
            <div class="viz-card glass-panel" style="grid-column: span 2;">
                <div class="card-header">Raw Schema JSON-LD Maps</div>
                <pre style="background: rgba(15,23,42,0.02); padding: 15px; border-radius: 8px; overflow-x: auto; font-size: 0.85em; color: #334155; border: 1px solid rgba(15,23,42,0.05);"><code>{schema_json_str}</code></pre>
            </div>
        </div>
    """

@app.route("/api/tab/architecture")
def tab_architecture():
    domain = request.args.get('domain')
    url = request.args.get('url')
    data, _ = fetch_url_data(domain, url)
    baseline = data.get('seo_baseline', {})
    dom = data.get('semantics', {}).get('dom_architecture', {})
    
    headings_html = "".join([f"<div style='margin-left: {(h.get('level', 1) - 1) * 20}px; padding: 4px 0; border-bottom: 1px solid rgba(15,23,42,0.02);'><strong style='color: #9333ea;'>H{h.get('level')}:</strong> <span style='color: #334155; font-size: 0.9em;'>{h.get('text')}</span></div>" for h in dom.get('heading_structure', [])])

    return f"""
        <div class="viz-grid">
            <div class="viz-card glass-panel">
                <div class="card-header">Baseline Metadata</div>
                <table class="data-table">
                    <tr><th>Title Tag</th><td><strong>{baseline.get('title', 'Missing')}</strong></td></tr>
                    <tr><th>Meta Description</th><td style="font-size: 0.85em;">{baseline.get('meta_description', 'Missing')}</td></tr>
                    <tr><th>Canonical Tag</th><td style="word-break: break-all;">{baseline.get('canonical', 'Missing')}</td></tr>
                </table>
            </div>
            <div class="viz-card glass-panel">
                <div class="card-header">A11y & DOM Structure</div>
                <table class="data-table">
                    <tr><th>Missing Image Alts</th><td><strong style="color: {'#ef4444' if dom.get('missing_alt_count', 0) > 0 else '#10b981'};">{dom.get('missing_alt_count', 0)} tags empty</strong></td></tr>
                </table>
            </div>
            <div class="viz-card glass-panel" style="grid-column: span 2;">
                <div class="card-header">Heading Hierarchy ({baseline.get('h1_count', 0)} H1s)</div>
                <div style="background: rgba(15,23,42,0.02); padding: 15px; border-radius: 8px; max-height: 250px; overflow-y: auto;">{headings_html if headings_html else '<i>No headings found.</i>'}</div>
            </div>
        </div>
    """

@app.route("/api/tab/graph")
def tab_graph():
    domain = request.args.get('domain')
    url = request.args.get('url')
    data, pr_percentile = fetch_url_data(domain, url)
    
    clean_center_url = url.replace(f"https://{domain}", "").replace(f"http://{domain}", "") or "/"
    node_names = {clean_center_url}
    inbound_nodes, outbound_nodes, graph_links = [], [], []
    
    for link in data.get('link_map', []):
        target_raw = link.get('u', '')
        if domain in target_raw or target_raw.startswith('/'):
            target_clean = target_raw.replace(f"https://{domain}", "").replace(f"http://{domain}", "") or "/"
            if target_clean not in node_names:
                outbound_nodes.append({"name": target_clean, "category": 2, "symbolSize": 8})
                node_names.add(target_clean)
            graph_links.append({"source": clean_center_url, "target": target_clean})
            
    with get_db().cursor() as cur:
        cur.execute("SELECT url FROM audit_metrics, jsonb_array_elements(audit_json->'link_map') elem WHERE (elem->>'u' = %s OR elem->>'u' = %s) AND domain = %s LIMIT 40;", (url, url.rstrip('/'), domain))
        for r in cur.fetchall():
            src_clean = r[0].replace(f"https://{domain}", "").replace(f"http://{domain}", "") or "/"
            if src_clean not in node_names:
                inbound_nodes.append({"name": src_clean, "category": 1, "symbolSize": 12})
                node_names.add(src_clean)
            graph_links.append({"source": src_clean, "target": clean_center_url})
            
    url_graph_json = json.dumps({"nodes": [{"name": clean_center_url, "category": 0, "symbolSize": 25}] + inbound_nodes + outbound_nodes, "links": graph_links})
    
    return f"""
        <div class="viz-grid">
            <div class="viz-card glass-panel"><div class="card-header">Target URL Link Map</div><div id="urlGraphChart" style="width: 100%; height: 350px;"></div></div>
            <div class="viz-card glass-panel">
                <div class="card-header">Authority Metrics</div>
                <table class="data-table">
                    <tr><th>Relative Authority Percentile</th><td><strong style="color: #9333ea; font-size: 1.2em;">Top {100 - pr_percentile:.1f}%</strong></td></tr>
                    <tr><th>Click Depth from Root</th><td><strong>{data.get('graph_metrics', {}).get('click_depth', 'Unknown')}</strong></td></tr>
                </table>
            </div>
        </div>
        <script>
            (function() {{
                const chartDom = document.getElementById('urlGraphChart');
                if (chartDom) {{
                    const myChart = echarts.init(chartDom);
                    const graphData = {url_graph_json};
                    myChart.setOption({{
                        textStyle: {{ fontFamily: 'Montserrat' }},
                        tooltip: {{ formatter: '{{b}}' }},
                        legend: [{{ data: ['Target URL', 'Inbound Links', 'Outbound Links'] }}],
                        series: [{{
                            type: 'graph', layout: 'force',
                            data: graphData.nodes, links: graphData.links,
                            categories: [{{name: 'Target URL', itemStyle: {{color: '#9333ea'}}}}, {{name: 'Inbound Links', itemStyle: {{color: '#10b981'}}}}, {{name: 'Outbound Links', itemStyle: {{color: '#64748b'}}}}],
                            roam: true, label: {{ show: false }}, force: {{ repulsion: 150, edgeLength: 40 }}
                        }}]
                    }});
                }}
            }})();
        </script>
    """

def generate_global_dashboard(domain, filter_path):
    with get_db().cursor() as cur:
        cur.execute("SELECT url, audit_json FROM audit_metrics WHERE domain = %s AND url LIKE %s;", (domain, f"%{filter_path}%"))
        rows = cur.fetchall()
        
    if not rows: return "<div class='glass-panel' style='padding: 20px; color: #ef4444;'>No data found for this scope.</div>"

    total_urls, total_404s, total_js_links, total_payload_kb = 0, 0, 0, 0
    scatter_data, graph_nodes, graph_links, entity_tracker = [], [], [], set()
    perf_counts = {"Good": 0, "Needs Work": 0, "Poor": 0}
    
    link_counts = {}
    for row in rows:
        for link in (row[1].get('link_map', []) if row[1] else []):
            tgt = link.get('u', '').replace(f"https://{domain}", "").replace(f"http://{domain}", "") or "/"
            link_counts[tgt] = link_counts.get(tgt, 0) + 1
            
    for row in rows:
        total_urls += 1
        url, data = row[0], row[1] if row[1] else {}
        clean_url = url.replace(f"https://{domain}", "").replace(f"http://{domain}", "") or "/"
        
        perf = data.get('performance', {}).get('lighthouse_lab_data', {})
        score = perf.get('performance_score')
        if isinstance(score, (int, float)):
            if score >= 90: perf_counts["Good"] += 1
            elif score >= 50: perf_counts["Needs Work"] += 1
            else: perf_counts["Poor"] += 1
            
        pr = round(data.get('graph_metrics', {}).get('pagerank', 0), 5)
        payload = round(perf.get('total_byte_weight', 0) / 1024, 2) if perf.get('total_byte_weight') else 0
        if payload > 0: scatter_data.append([payload, pr, clean_url])
        if not data.get('seo_baseline'): total_404s += 1
            
        total_js_links += data.get('render_diff', {}).get('js_dependent_count', 0)
        total_payload_kb += payload
        
        node_size = min(max(link_counts.get(clean_url, 0) * 2, 10), 60)
        graph_nodes.append({"id": clean_url, "name": clean_url, "symbolSize": node_size, "category": 0})
        
        for ent in data.get('semantics', {}).get('ai_intent', {}).get('core_entities', []):
            ent_id = f"ent_{ent.lower().strip()}"
            if ent_id not in entity_tracker:
                graph_nodes.append({"id": ent_id, "name": ent, "symbolSize": 12, "category": 1})
                entity_tracker.add(ent_id)
            graph_links.append({"source": clean_url, "target": ent_id, "value": 0.1, "lineStyle": {"width": 1, "color": "rgba(15, 23, 42, 0.1)"}})

    with get_db().cursor() as cur:
        cur.execute("""
            SELECT a.url, b.url, ROUND((1 - (a.content_vector <=> b.content_vector))::numeric, 4) AS sim
            FROM audit_metrics a JOIN audit_metrics b ON a.domain = b.domain AND a.url < b.url
            WHERE a.domain = %s AND a.content_vector IS NOT NULL AND b.content_vector IS NOT NULL
            AND (1 - (a.content_vector <=> b.content_vector)) > 0.80;
        """, (domain,))
        for src, tgt, sim in cur.fetchall():
            src_c = src.replace(f"https://{domain}", "").replace(f"http://{domain}", "") or "/"
            tgt_c = tgt.replace(f"https://{domain}", "").replace(f"http://{domain}", "") or "/"
            graph_links.append({
                "source": src_c, "target": tgt_c, 
                "value": float(sim),
                "lineStyle": {"width": float(sim) * 5, "color": "rgba(239, 68, 68, 0.5)", "curveness": 0.2}
            })

    pie_data = [
        {"name": "Good (90+)", "value": perf_counts["Good"], "itemStyle": {"color": "#10b981"}},
        {"name": "Needs Work (50-89)", "value": perf_counts["Needs Work"], "itemStyle": {"color": "#f59e0b"}},
        {"name": "Poor (<50)", "value": perf_counts["Poor"], "itemStyle": {"color": "#ef4444"}}
    ]
    
    chart_json = json.dumps({"scatter": scatter_data, "nodes": graph_nodes, "links": graph_links, "pie": [x for x in pie_data if x["value"] > 0]})
    
    return f"""
        <div class="stat-grid">
            <div class="stat-box glass-panel brand"><h3>URLs in Scope</h3><p>{total_urls}</p></div>
            <div class="stat-box glass-panel"><h3>Average Payload</h3><p>{round(total_payload_kb / total_urls, 2) if total_urls else 0} KB</p></div>
            <div class="stat-box glass-panel warning"><h3>JS-Dependent Links</h3><p>{total_js_links}</p></div>
            <div class="stat-box glass-panel danger"><h3>Broken Scrapes</h3><p>{total_404s}</p></div>
        </div>
        <p class="filter-note">Viewing Aggregations For: <strong style="color: #9333ea;">{filter_path or 'Entire Domain'}</strong></p>

        <div class="viz-grid">
            <div class="viz-card glass-panel"><div class="card-header">Lighthouse Performance Distribution</div><div id="pieChart" style="width: 100%; height: 350px;"></div></div>
            <div class="viz-card glass-panel"><div class="card-header">Payload vs. Power Matrix</div><div id="scatterChart" style="width: 100%; height: 350px;"></div></div>
            <div class="viz-card glass-panel" style="grid-column: span 2;">
                <div class="card-header">Semantic Vector Space Map (Red lines denote high contextual overlap)</div>
                <div id="graphChart" style="width: 100%; height: 450px;"></div>
            </div>
        </div>

        <script>
            document.body.dispatchEvent(new CustomEvent("renderCharts", {{ detail: {chart_json} }}));
        </script>
    """

@app.route("/api/search", methods=["POST"])
def semantic_search():
    query = request.form.get('query', '').strip()
    domain = request.args.get('domain', 'standardsyntax.com')
    if not query: return "<i>Type a concept to search your crawl data contextually...</i>"

    try:
        query_vector = ollama.embeddings(model='nomic-embed-text', prompt=query)['embedding']
        with get_db().cursor() as cur:
            cur.execute("""
                SELECT url, ROUND((1 - (content_vector <=> %s::vector))::numeric, 4) AS similarity
                FROM audit_metrics WHERE domain = %s AND content_vector IS NOT NULL
                ORDER BY content_vector <=> %s::vector LIMIT 5;
            """, (query_vector, domain, query_vector))
            html = "<ul style='list-style: none; padding: 0; margin: 0;'>"
            for url, sim in cur.fetchall():
                html += f"<li style='padding: 15px; border-bottom: 1px solid rgba(15, 23, 42, 0.05);'><a href='#' style='color: #9333ea; font-weight: 700; font-size: 0.9em; text-decoration: none;' hx-get='/api/overview?domain={domain}&exact_url={url}' hx-target='#overview-board'>{url.replace(f'https://{domain}', '') or '/'}</a> <span style='float: right; color: #64748b; font-size: 0.75em; font-weight: 800;'>{float(sim) * 100:.1f}% Match</span></li>"
            return html + "</ul>" if cur.rowcount > 0 else "<div style='color: #ef4444; padding: 10px;'>No matches found.</div>"
    except Exception as e: return f"<div style='color: #ef4444; padding: 10px;'>Search Error: {str(e)}</div>"

if __name__ == "__main__":
    app.run(debug=True, port=5000)