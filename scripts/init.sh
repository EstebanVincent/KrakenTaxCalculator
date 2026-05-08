#!/bin/bash
set -e

echo "Starting Streamlit PII Cleaner..."

# Run Streamlit app
uv run streamlit run main.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
