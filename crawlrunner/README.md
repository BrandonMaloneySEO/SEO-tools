# CrawlRunner 🚀
## Distributed Technical SEO, Generative Engine Optimization (GEO), and Semantic Web Architecture Engine

## 🌟 Executive Summary:

CrawlRunner is an advanced, local-first technical search engine optimization and site architecture analysis platform designed to audit modern web applications at scale. Moving beyond traditional surface-level scrapers, CrawlRunner combines headless browser rendering (Playwright) with unrendered HTML extraction (httpx) to isolate client-side JavaScript dependency risks (cr_oracle.py).
It incorporates local vector embeddings (PostgreSQL pgvector and nomic-embed-text), ontology schema mapping via extruct, and local AI intent classification via Ollama (gemma2) to evaluate semantic context for Generative Engine Optimization (GEO) and Answer Engine Optimization (AEO).
The system features a ultra-fast, glassmorphic Flask web interface (app.py) providing real-time diagnostic overviews, visual internal link network graphs, payload-vs-authority scatter plots, and vector space nearest-neighbor comparisons.

### 📸 Command Center Dashboard & Visual UI
Below are high-level diagnostic captures from the CrawlRunner Glass Dashboard UI:

Global Command Center Overview

Internal Link Network Graph

Real-time metrics, directory trees, and search intent diagnostics.

Interactive Apache ECharts directed graph showing internal PageRank flow.

Payload vs. Authority Matrix

Semantic Vector Similarity Space


Correlating payload weight (KB) against internal link equity.
Nearest-neighbor content clusters via pgvector & nomic-embed-text.

### 🎯 The Challenge & Engineering Objectives

Modern web applications frequently suffer from hidden structural bottlenecks: content locked behind client-side JavaScript rendering, poor internal equity distribution via weak PageRank graphs, broken heading hierarchies, and missing schema implementations that limit GEO/AEO search engine visibility.

## Key Engineering Objectives:

Asynchronous Rendering & DOM Diffing: Compare raw HTTP responses against fully rendered browser Document Object Models to instantly quantify client-side JavaScript indexing vulnerabilities.
Graph-Based Architecture & Equity Flow: Construct directed network graphs using NetworkX on the fly to compute internal PageRank, shortest-path click depth from the root domain, and link distributions.
Semantic Ingestion & Vector Intelligence: Mine JSON-LD ontologies, validate accessibility markup, extract AI-driven search intent, and generate vector embeddings for spatial content similarity mapping.
Interactive Diagnostic UI: Deliver a responsive, zero-bloat Flask dashboard utilizing Apache ECharts and HTMX for seamless exploration of global metrics and deep-dive URL diagnostics.

##🏗️ System Architecture & Data Flow

              [Seed URL / Sitemap.xml]
                           │
                           ▼
          [Redis Queue Manager (cr_ignite.py)]
                           │
                           ▼
     [Playwright Scout & HTTP Fetcher (cr_publisher.py)]
                           │
                           ▼
        [DOM Diffing & Oracle Engine (cr_oracle.py)]
                           │
                           ▼
     [Navigation & Link Trap Filter (cr_navigation.py)]
                           │
                           ▼
  [PostgreSQL Storage Layer & Semantic Miner (cr_semantics.py)]
                           │
                           ▼
   [Local Performance & Lighthouse Audit (cr_performance.py)]
                           │
                           ▼
       [Flask Command Center & ECharts UI (app.py)]

###Layer Breakdown:
Ingestion & Queue Management: Managed by Redis (cr_ignite.py, cr_publisher.py), handling queue priorities, sitemap parsing, and headless browser worker pools via Playwright.
Processing & Diffing Engine: Handled by cr_oracle.py, executing raw vs. rendered DOM comparisons, isolating JavaScript-dependent links, and evaluating SEO baseline metadata.
Storage & Vector Layer: PostgreSQL with the pgvector extension, storing JSONB audit metrics and high-dimensional embeddings for semantic similarity scoring.
Presentation Layer: A Flask web application (app.py) featuring interactive ECharts visualizations, tab-based directory navigation, and real-time contextual semantic vector search.

## 🔑 Key Engineering Implementations

1. Raw vs. Rendered DOM Diffing Engine
To uncover hidden crawling hazards, cr_oracle.py fetches unrendered markup using httpx and compares it against the fully executed DOM captured by Playwright. Links present only in the rendered DOM are isolated as JavaScript-dependent, alerting operators to potential rendering blind spots for search engine bots.

2. Directed Graph Architecture & Math on the Fly
Using NetworkX (cr_graph.py, cr_monitor.py), CrawlRunner builds a directed graph of the site's internal link structure. It computes internal PageRank scores (using a standard 0.85 damping factor) and measures click depth from the root homepage via shortest-path algorithms, flagging isolated or orphaned pages.

3. Local AI Semantic Extraction & Vector Space Mapping
cr_semantics.py extracts JSON-LD structured data graphs via extruct, evaluates accessibility markers (such as missing alt attributes and HTML5 semantic landmarks), and passes cleaned body text to a local Ollama instance (gemma2) to classify primary search intent and core topical entities. Concurrently, nomic-embed-text generates vector embeddings stored in PostgreSQL (pgvector) for precise nearest-neighbor content matching.

4. High-Performance Glass-Panel Dashboard UI
The Flask application (app.py) uses server-side rendering combined with interactive Apache ECharts components to display Lighthouse performance distributions, payload-to-power matrices, and interactive link maps without heavy frontend framework overhead.

## ⚡ Quickstart Guide

1. Spin Up Local Services (PostgreSQL + Redis)
Ensure Docker is running, then start backing services with Docker Compose:
docker compose up -d

2. Pull Required Local Ollama Models
Ensure Ollama is running on your Mac (ollama serve), then pull the required models:
ollama pull gemma2
ollama pull nomic-embed-text

3. Execute a Full Audit
Run the automated multi-phase orchestrator script against any target web application:
chmod +x start_crawlrunner.sh


4. Launch the Command Center UI
Once the crawl and post-analytics complete, launch the Flask UI:
python app/app.py

Navigate to http://localhost:5000 in your browser to explore your site's technical architecture.

## 📈 Technical Takeaways & Impact

Comprehensive Visibility: Uncovers invisible client-side rendering traps and structural SEO deficiencies that standard static crawlers miss.
Automated Equity Distribution: Quantifies internal link equity flow instantly via programmatic PageRank and click-depth calculations.
Local Privacy & Zero Cloud Dependency: Leverages local Redis queues, PostgreSQL databases, and local Ollama models—eliminating external API costs and data privacy risks.

## 📄 License

Distributed under the MIT License. See LICENSE for more information.


