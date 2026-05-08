#!/bin/bash
set -e

echo "Starting Streamlit Kraken Tax Calculator app..."

# Run Streamlit app
uv run streamlit run main.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
