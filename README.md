# 📊 Kraken Tax Calculator – Déclaration Crypto Française

Streamlit app to help French tax residents prepare their annual crypto tax declarations using Kraken data.

> **Outil de préparation uniquement.** Ne soumet aucune donnée aux autorités fiscales.

## What it does

- Connects to your Kraken account via read-only API key
- Fetches your full trade history and ledger entries
- Calculates capital gains/losses per the **méthode du portefeuille global** (art. 150 VH bis CGI)
- Generates tables for **Formulaire 2086** (plus/moins-values)
- Calculates staking rewards for **Formulaire 2042-C-PRO** (BNC, ligne 5HQ)
- Exports results as CSV for manual entry on impots.gouv.fr

## Kraken API key

Create a **read-only** API key at https://www.kraken.com/u/security/api with permissions:

- Query Funds
- Query Orders & Trades
- Query Ledger Entries

---

## Run with Docker (recommended)

```bash
# Build
docker build -t kraken-tax-calculator .

# Run  (mounts local ./data/ so CSVs persist on your machine)
docker run --rm -it \
  -p 8501:8501 \
  -v "$(pwd)/data:/app/data" \
  --name kraken-tax-calculator-container \
  kraken-tax-calculator
```

Then open http://localhost:8501

---

## Run locally

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
uv sync
uv run streamlit run main.py
```

Then open http://localhost:8501

---

## Local data cache

After the first successful fetch, trade history is saved to `data/trades.csv` and `data/ledgers.csv`.  
On subsequent runs the app loads from cache automatically — no API call needed.  
Use the **"Forcer le rechargement"** checkbox in the sidebar to pull fresh data from Kraken.

The `data/` folder is gitignored and never committed.

---

## Limitations

- Portfolio value (L212) only reflects assets held on Kraken — holdings on other exchanges are not included
- PMTA (L220) is calculated from your Kraken history only — holdings acquired before using Kraken will understate the cost basis
- Crypto-to-crypto swaps are not yet treated as taxable disposals
- EUR prices use Kraken daily OHLC close — may differ slightly from exact transaction price

**This is not tax advice. Verify all figures and consult a _comptable_ or _avocat fiscaliste_ before filing.**
