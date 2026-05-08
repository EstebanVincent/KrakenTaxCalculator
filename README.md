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

## Hosted version

A public instance is live at **[krakentaxcalculator.streamlit.app](https://krakentaxcalculator.streamlit.app)** and redeploys automatically on every push to `main`.

Your API keys are never written to disk — they live in session memory only and are gone when you close the tab.

---

## `APP_ENV` modes

The app behaviour is controlled by the `APP_ENV` environment variable:

| Value             | Trades & ledgers                                    | Prices                         |
| ----------------- | --------------------------------------------------- | ------------------------------ |
| `LOCAL` (default) | Persisted to `data/trades.csv` / `data/ledgers.csv` | Persisted to `data/prices.csv` |
| `CLOUD`           | Session memory only (never written to disk)         | Persisted to `data/prices.csv` |

Set it via Docker `-e APP_ENV=CLOUD`, a `.env` file locally, or the Secrets section on Streamlit Community Cloud.

---

## Run with Docker

```bash
# Build
docker build -t kraken-tax-calculator .

# LOCAL mode — mounts ./data/ so all CSVs persist on your machine
docker run --rm -it \
  -p 8501:8501 \
  -v "$(pwd)/data:/app/data" \
  --name kraken-tax-calculator-container \
  kraken-tax-calculator

# CLOUD mode — only prices cached, trades/ledgers in memory
docker run --rm -it \
  -p 8501:8501 \
  -e APP_ENV=CLOUD \
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

`APP_ENV` defaults to `LOCAL`. To override, set it in your shell or a `.env` file (loaded via `python-dotenv`, included as a dev dependency).

---

## Local data cache (LOCAL mode)

After the first successful fetch, trade history is saved to `data/trades.csv` and `data/ledgers.csv`.  
On subsequent runs the app loads from cache automatically — no API call needed.  
Use the **"Forcer le rechargement"** checkbox in the sidebar to pull fresh data from Kraken.

`data/trades.csv` and `data/ledgers.csv` are gitignored and never committed.  
`data/prices.csv` (public Kraken OHLC data) is also gitignored but safe to keep locally.

---

## Deploy to Streamlit Community Cloud

1. Fork / push this repo to your GitHub account (must be public)
2. Go to [share.streamlit.io](https://share.streamlit.io) → **Create app**
3. Select this repo, branch `main`, main file `main.py`
4. Open **Advanced settings → Secrets** and add:
   ```toml
   APP_ENV = "CLOUD"
   ```
5. Click **Deploy**

Streamlit Community Cloud watches the `main` branch and **redeploys automatically** on every push — no CI/CD configuration required.

---

## Limitations

- Portfolio value (L212) only reflects assets held on Kraken — holdings on other exchanges are not included
- PMTA (L220) is calculated from your Kraken history only — holdings acquired before using Kraken will understate the cost basis
- Crypto-to-crypto swaps are not yet treated as taxable disposals
- EUR prices use Kraken daily OHLC close — may differ slightly from exact transaction price
- In CLOUD mode the price cache is lost on app restart — the first calculation after a cold start will be slower

**This is not tax advice. Verify all figures and consult a _comptable_ or _avocat fiscaliste_ before filing.**
