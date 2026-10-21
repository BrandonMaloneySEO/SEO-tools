#!/bin/bash

# Ensure a URL was provided
if [ -z "$1" ]; then
    echo "❌ Error: Please provide a target URL or sitemap."
    echo "Usage: ./start_crawlrunner.sh https://example.com"
    exit 1
fi

TARGET_URL=$1

# Extract the clean domain name (removes https:// and trailing paths)
DOMAIN=$(echo "$TARGET_URL" | sed -e 's|^[^/]*//||' -e 's|/.*$||')

echo "========================================================"
echo "🚀 INITIALIZING CRAWLRUNNER FOR: $DOMAIN"
echo "========================================================"

# 1. Ignite the Queue (This will also trigger the flushall fix)
echo "🔥 Phase 1: Igniting Redis Queues..."
poetry run python cr_ignite.py "$TARGET_URL"

# 2. Launch the Swarm
echo "🕷️ Phase 2: Launching Scout Swarm..."
poetry run python cr_oracle.py &
ORACLE_PID=$!

poetry run python cr_navigation.py &
NAV_PID=$!

poetry run python cr_publisher.py &
PUB_PID=$!

# Catch manual Ctrl+C to gracefully kill background processes
trap "echo '🛑 Manual Stop...'; kill $ORACLE_PID $NAV_PID $PUB_PID 2>/dev/null; exit" INT

# 3. Launch the Overseer (Graph Math & Stop Signal)
# This script blocks the terminal until the crawl is finished
echo "👁️ Phase 3: Launching Overseer (Monitor & Graph Math)..."
poetry run python cr_monitor.py "$TARGET_URL"

# Wait for the background swarm workers to exit after receiving the stop signal
echo "⏳ Waiting for swarm to safely shut down..."
wait $ORACLE_PID $NAV_PID $PUB_PID

echo "✅ Crawl & Graph Math Complete! Moving to Post-Crawl Analytics..."
echo "--------------------------------------------------------"

# 4. Performance & Web Vitals
echo "🚦 Phase 4: Running Asynchronous Lighthouse Audits..."
poetry run python cr_performance.py "$TARGET_URL"

echo "--------------------------------------------------------"

# 5. Semantic AI & Vector Embeddings
echo "🧠 Phase 5: Engaging Local AI Semantic Miner & pgvector..."
poetry run python cr_semantics.py "$DOMAIN"

echo "========================================================"
echo "🎉 ALL PHASES COMPLETE! Command Center is ready for $DOMAIN."
echo "========================================================"