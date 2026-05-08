"""Kraken Tax Calculator – French crypto tax helper (Form 2086 & 2042-C-PRO)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import backoff
import httpx
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KRAKEN_API_BASE = "https://api.kraken.com"
API_VERSION = "0"

ASSET_MAP: dict[str, str] = {
    "XXBT": "BTC",
    "XBT": "BTC",
    "XETH": "ETH",
    "ETH": "ETH",
    "XLTC": "LTC",
    "LTC": "LTC",
    "XXRP": "XRP",
    "XRP": "XRP",
    "XXLM": "XLM",
    "XLM": "XLM",
    "XDOT": "DOT",
    "DOT": "DOT",
    "ADA": "ADA",
    "XADA": "ADA",
    "SOL": "SOL",
    "MATIC": "MATIC",
    "POL": "POL",
    "LINK": "LINK",
    "ATOM": "ATOM",
    "AVAX": "AVAX",
    "ALGO": "ALGO",
    "MANA": "MANA",
    "SAND": "SAND",
    "UNI": "UNI",
    "AAVE": "AAVE",
    "CRV": "CRV",
    "DOGE": "DOGE",
    "TRX": "TRX",
    "NEAR": "NEAR",
    "GRT": "GRT",
    "ENJ": "ENJ",
    "COMP": "COMP",
    "MKR": "MKR",
    "SNX": "SNX",
    "YFI": "YFI",
    "SUSHI": "SUSHI",
    "BAT": "BAT",
    "ZEC": "ZEC",
    "XZEC": "ZEC",
    "XMR": "XMR",
    "XXMR": "XMR",
    "DASH": "DASH",
    "XDASH": "DASH",
    "EOS": "EOS",
    "XEOS": "EOS",
    "SHIB": "SHIB",
    "FTM": "FTM",
    "ICP": "ICP",
    "ZEUR": "EUR",
    "EUR": "EUR",
    "ZUSD": "USD",
    "USD": "USD",
    "ZGBP": "GBP",
    "GBP": "GBP",
    "USDT": "USDT",
    "USDC": "USDC",
    "DAI": "DAI",
    "ETH2": "ETH2",
    "ETH2.S": "ETH2",
}

FIAT_AND_STABLECOINS = {"EUR", "USD", "GBP", "USDT", "USDC", "DAI", "BUSD", "TUSD"}

EUR_PAIRS: dict[str, str] = {
    "BTC": "XXBTZEUR",
    "ETH": "XETHZEUR",
    "LTC": "XLTCZEUR",
    "XRP": "XXRPZEUR",
    "XLM": "XXLMZEUR",
    "DOT": "DOTZEUR",
    "ADA": "ADAEUR",
    "SOL": "SOLEUR",
    "MATIC": "MATICEUR",
    "LINK": "LINKEUR",
    "ATOM": "ATOMEUR",
    "AVAX": "AVAXEUR",
    "ALGO": "ALGOEUR",
    "MANA": "MANAEUR",
    "SAND": "SANDEUR",
    "UNI": "UNIEUR",
    "AAVE": "AAVEEUR",
    "CRV": "CRVEUR",
    "DOGE": "XDOGEZEUR",
    "TRX": "TRXEUR",
    "NEAR": "NEAREUR",
    "GRT": "GRTEUR",
    "ENJ": "ENJEUR",
    "COMP": "COMPEUR",
    "MKR": "MKREUR",
    "SNX": "SNXEUR",
    "YFI": "YFIEUR",
    "SUSHI": "SUSHIEUR",
    "BAT": "BATEUR",
    "ZEC": "XZECZEUR",
    "XMR": "XXMRZEUR",
    "ETH2": "ETH2.SEUR",
}

# ---------------------------------------------------------------------------
# Kraken API client
# ---------------------------------------------------------------------------


def _sign(uri_path: str, data: dict, secret: str) -> str:
    post_data = urllib.parse.urlencode(data)
    encoded = (str(data["nonce"]) + post_data).encode()
    message = uri_path.encode() + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()


def kraken_private(key: str, secret: str, endpoint: str, params: dict | None = None) -> dict:
    uri_path = f"/{API_VERSION}/private/{endpoint}"
    data: dict = {"nonce": str(int(time.time() * 1000))}
    if params:
        data.update(params)
    headers = {
        "API-Key": key,
        "API-Sign": _sign(uri_path, data, secret),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    resp = httpx.post(KRAKEN_API_BASE + uri_path, data=data, headers=headers, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if result.get("error"):
        raise ValueError(f"Kraken API error: {result['error']}")
    return result["result"]


def kraken_public(endpoint: str, params: dict | None = None) -> dict:
    uri_path = f"/{API_VERSION}/public/{endpoint}"
    resp = httpx.get(KRAKEN_API_BASE + uri_path, params=params, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if result.get("error"):
        raise ValueError(f"Kraken API error: {result['error']}")
    return result["result"]


# ---------------------------------------------------------------------------
# Data fetching  (with local CSV cache in data/)
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
TRADES_CSV = DATA_DIR / "trades.csv"
LEDGERS_CSV = DATA_DIR / "ledgers.csv"
PRICES_CSV = DATA_DIR / "prices.csv"


def _load_trades_csv() -> pd.DataFrame | None:
    if not TRADES_CSV.exists():
        return None
    df = pd.read_csv(TRADES_CSV, parse_dates=["time"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def _load_ledgers_csv() -> pd.DataFrame | None:
    if not LEDGERS_CSV.exists():
        return None
    df = pd.read_csv(LEDGERS_CSV, parse_dates=["time"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_all_trades(key: str, secret: str, force_refresh: bool = False) -> pd.DataFrame:
    if not force_refresh:
        cached = _load_trades_csv()
        if cached is not None:
            return cached

    rows: list[dict] = []
    offset = 0
    while True:
        result = kraken_private(key, secret, "TradesHistory", {"ofs": offset})
        trades = result.get("trades", {})
        if not trades:
            break
        for txid, t in trades.items():
            t["txid"] = txid
            rows.append(t)
        if len(rows) >= result.get("count", 0):
            break
        offset += len(trades)
        time.sleep(1)

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    for col in ["price", "cost", "fee", "vol"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("time").reset_index(drop=True)
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(TRADES_CSV, index=False)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_all_ledgers(key: str, secret: str, force_refresh: bool = False) -> pd.DataFrame:
    if not force_refresh:
        cached = _load_ledgers_csv()
        if cached is not None:
            return cached

    rows: list[dict] = []
    offset = 0
    while True:
        result = kraken_private(key, secret, "Ledgers", {"ofs": offset})
        ledgers = result.get("ledger", {})
        if not ledgers:
            break
        for lid, l in ledgers.items():
            l["lid"] = lid
            rows.append(l)
        if len(rows) >= result.get("count", 0):
            break
        offset += len(ledgers)
        time.sleep(1)

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    for col in ["amount", "fee", "balance"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("time").reset_index(drop=True)
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(LEDGERS_CSV, index=False)
    return df


# Module-level price cache: only stores successful lookups so failed requests
# are retried on the next call instead of being cached as None.
_price_cache: dict[tuple[str, str], float] = {}
# Tracks (asset, date) pairs where price lookup failed after all retries.
_price_failures: set[tuple[str, str]] = set()


def _load_prices_csv() -> None:
    """Populate _price_cache from data/prices.csv on startup."""
    if not PRICES_CSV.exists():
        return
    df = pd.read_csv(PRICES_CSV)
    for _, row in df.iterrows():
        _price_cache[(row["pair"], row["date"])] = float(row["price"])


def _save_prices_csv() -> None:
    """Persist current _price_cache to data/prices.csv."""
    DATA_DIR.mkdir(exist_ok=True)
    rows = [{"pair": pair, "date": date, "price": price} for (pair, date), price in _price_cache.items()]
    pd.DataFrame(rows).sort_values(["pair", "date"]).to_csv(PRICES_CSV, index=False)


_load_prices_csv()  # load on module import


@backoff.on_exception(
    backoff.expo,
    (httpx.HTTPStatusError, httpx.RequestError, ValueError),
    max_tries=4,
    base=2,
    factor=1,
)
def _fetch_ohlc(pair: str, since: int) -> list:
    """Fetch daily OHLC candles from Kraken public API with exponential backoff."""
    result = kraken_public("OHLC", {"pair": pair, "interval": 1440, "since": since})
    return list(result.values())[0]


def get_eur_price(asset: str, date: datetime) -> float | None:
    ticker = normalize(asset)
    if ticker == "EUR":
        return 1.0
    if ticker in FIAT_AND_STABLECOINS:
        return None
    if ticker == "ETH2":
        ticker = "ETH"
    pair = EUR_PAIRS.get(ticker)
    if not pair:
        return None

    day_key = date.strftime("%Y-%m-%d")
    cache_key = (pair, day_key)
    if cache_key in _price_cache:
        return _price_cache[cache_key]

    ts = int(date.timestamp())
    try:
        time.sleep(2)  # respect Kraken public rate limit (1 req/s)
        candles = _fetch_ohlc(pair, ts - 86400 * 2)
        if not candles:
            _price_failures.add((ticker, day_key))
            return None
        best = min(candles, key=lambda c: abs(c[0] - ts))
        price = float(best[4])
        _price_cache[cache_key] = price
        _save_prices_csv()
        return price
    except Exception:
        _price_failures.add((ticker, day_key))
        return None


# ---------------------------------------------------------------------------
# Asset helpers
# ---------------------------------------------------------------------------


def normalize(asset: str) -> str:
    # Strip Kraken flexible/bonded staking suffixes (.F, .S, .M, .B, .P, .X)
    # e.g. SOL.F → SOL, ETH2.S → ETH2
    clean = asset
    for suffix in (".F", ".S", ".M", ".B", ".P", ".X"):
        if clean.endswith(suffix):
            clean = clean[: -len(suffix)]
            break
    return ASSET_MAP.get(clean, ASSET_MAP.get(asset, asset))


def is_fiat(asset: str) -> bool:
    return normalize(asset) in FIAT_AND_STABLECOINS


def parse_pair(pair: str) -> tuple[str, str]:
    for suffix in ["ZEUR", "ZUSD", "ZGBP", "EUR", "USD", "GBP", "USDT", "USDC", "XBT", "ETH", "BTC"]:
        if pair.endswith(suffix):
            base = pair[: -len(suffix)]
            return normalize(base), normalize(suffix)
    mid = len(pair) // 2
    return normalize(pair[:mid]), normalize(pair[mid:])


# ---------------------------------------------------------------------------
# Holdings snapshot
# ---------------------------------------------------------------------------


def holdings_at(ledgers: pd.DataFrame, ts: datetime) -> dict[str, float]:
    subset = ledgers[ledgers["time"] <= ts]
    h: dict[str, float] = {}
    for _, row in subset.iterrows():
        asset = normalize(row["asset"])
        if asset in FIAT_AND_STABLECOINS:
            continue
        h[asset] = h.get(asset, 0.0) + float(row["amount"])
    return {k: v for k, v in h.items() if v > 1e-10}


def portfolio_eur_value(holdings: dict[str, float], ts: datetime) -> float:
    total = 0.0
    for asset, qty in holdings.items():
        price = get_eur_price(asset, ts)
        if price is not None:
            total += qty * price
    return total


# ---------------------------------------------------------------------------
# Form 2086
# ---------------------------------------------------------------------------


def calc_form_2086(trades: pd.DataFrame, ledgers: pd.DataFrame, year: int) -> pd.DataFrame:
    """
    Méthode du portefeuille global (art. 150 VH bis CGI).
    PV = L218 - (L223 x L217 / L212)
    """
    if trades.empty or ledgers.empty:
        return pd.DataFrame()

    _price_failures.clear()
    pmta = 0.0
    recovered_all_time = 0.0
    year_recovered = 0.0
    in_year = False
    year_rows: list[dict] = []

    all_trades = trades.sort_values("time").reset_index(drop=True)
    progress = st.progress(0, text="Calcul des plus-values… récupération des prix de marché journaliers")
    total = len(all_trades)

    for i, (_, t) in enumerate(all_trades.iterrows()):
        progress.progress(
            (i + 1) / total,
            text=f"Transaction {i + 1}/{total} — {t['pair']} {t['type']} ({pd.Timestamp(t['time']).strftime('%d/%m/%Y')})",
        )
        base, quote = parse_pair(t["pair"])
        ts: datetime = t["time"]

        if t["type"] == "buy" and is_fiat(quote):
            cost_eur = float(t["cost"]) + float(t["fee"])
            if quote != "EUR":
                rate = get_eur_price(quote, ts)
                cost_eur = cost_eur * rate if rate else 0.0
            pmta += cost_eur

        elif t["type"] == "sell" and is_fiat(quote):
            sale_eur = float(t["cost"])
            fee_eur = float(t["fee"])
            if quote != "EUR":
                rate = get_eur_price(quote, ts)
                if rate:
                    sale_eur *= rate
                    fee_eur *= rate
                else:
                    sale_eur = fee_eur = 0.0

            h = holdings_at(ledgers, ts)
            l212 = round(portfolio_eur_value(h, ts), 2) or round(sale_eur, 2)
            l213 = round(sale_eur, 2)
            l214 = round(fee_eur, 2)
            l215 = round(l213 - l214, 2)
            l216 = 0.0
            l217 = round(l213 - l216, 2)
            l218 = round(l213 - l214 - l216, 2)
            l220 = round(pmta, 2)
            l221 = round(year_recovered if ts.year == year else recovered_all_time, 2)
            l222 = 0.0
            l223 = round(l220 - l221 - l222, 2)

            if l212 > 0:
                pv = round(l218 - l223 * l217 / l212, 2)
                recovered = round(l223 * l217 / l212, 2)
            else:
                pv = recovered = 0.0

            recovered_all_time += recovered
            if ts.year == year:
                year_recovered += recovered

            pmta = max(0.0, pmta - recovered)

            if ts.year == year:
                year_rows.append(
                    {
                        "Date (L211)": ts.strftime("%d/%m/%Y"),
                        "Valeur portefeuille (L212)": l212,
                        "Prix de cession (L213)": l213,
                        "Frais cession (L214)": l214,
                        "Net frais (L215)": l215,
                        "Soulte (L216)": l216,
                        "Net soultes (L217)": l217,
                        "Net frais+soultes (L218)": l218,
                        "Prix total acq. PMTA (L220)": l220,
                        "Capital récupéré préc. (L221)": l221,
                        "Soultes échanges ant. (L222)": l222,
                        "Acq. net (L223)": l223,
                        "Plus/Moins-value": pv,
                        "Pair": t["pair"],
                        "Volume vendu": round(float(t["vol"]), 8),
                        "txid": t["txid"],
                    }
                )

    progress.empty()
    df = pd.DataFrame(year_rows)
    if not df.empty:
        df["L224 cumul PV"] = df["Plus/Moins-value"].cumsum().round(2)
    if _price_failures:
        missing = sorted(_price_failures)
        lines = "\n".join(f"- **{asset}** le {date}" for asset, date in missing)
        st.warning(
            f"⚠️ Prix EUR introuvables pour {len(missing)} entrée(s) — ces transactions sont exclues du calcul L212.\n\n{lines}"
        )
    return df


# ---------------------------------------------------------------------------
# Staking income
# ---------------------------------------------------------------------------


def calc_staking_income(ledgers: pd.DataFrame, year: int) -> pd.DataFrame:
    if ledgers.empty:
        return pd.DataFrame()
    staking_types = {"staking", "reward", "earn"}
    mask = ledgers["type"].str.lower().isin(staking_types) & (ledgers["time"].dt.year == year)
    staking = ledgers[mask].copy()
    if staking.empty:
        return pd.DataFrame()

    _price_failures.clear()
    rows = []
    staking_list = list(staking.iterrows())
    progress = st.progress(0, text="Récupération des prix EUR pour les récompenses de staking…")
    for i, (_, row) in enumerate(staking_list):
        progress.progress(
            (i + 1) / len(staking_list),
            text=f"Prix EUR pour transaction {i + 1}/{len(staking_list)} ({row['asset']}, {row['time'].strftime('%d/%m/%Y')})…",
        )
        asset = normalize(row["asset"])
        amount = float(row["amount"])
        if amount <= 0:
            continue
        price = get_eur_price(asset, row["time"])
        eur_value = round(amount * price, 2) if price else None
        rows.append(
            {
                "Date": row["time"].strftime("%d/%m/%Y"),
                "Asset": asset,
                "Montant reçu": round(amount, 8),
                "Prix EUR (jour)": price,
                "Valeur EUR": eur_value,
                "Type": row["type"],
            }
        )
    progress.empty()
    df = pd.DataFrame(rows)
    if _price_failures:
        missing = sorted(_price_failures)
        lines = "\n".join(f"- **{asset}** le {date}" for asset, date in missing)
        st.warning(
            f"⚠️ Prix EUR introuvables pour {len(missing)} entrée(s) — valeur EUR affichée comme None.\n\n{lines}"
        )
    return df


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="Kraken Tax Calculator 🇫🇷",
        page_icon="📊",
        layout="wide",
    )

    st.title("📊 Kraken Tax Calculator – Déclaration Crypto Française")
    st.caption(
        "Outil de préparation uniquement. Ne soumet aucune donnée aux autorités fiscales. "
        "Vérifiez les chiffres avant de remplir votre déclaration."
    )

    with st.sidebar:
        st.header("⚙️ Configuration")
        api_key = st.text_input("Clé API Kraken", type="password", placeholder="Lecture seule suffisante")
        api_secret = st.text_input("Secret API Kraken", type="password")

        current_year = datetime.now(timezone.utc).year
        tax_year = st.selectbox(
            "Année fiscale",
            options=list(range(current_year - 1, current_year - 5, -1)),
            index=0,
        )

        force_refresh = st.checkbox(
            "🔁 Forcer le rechargement depuis Kraken",
            value=False,
            help="Désactiver pour utiliser le cache local (data/trades.csv)",
        )
        fetch_btn = st.button("🔄 Charger les données", type="primary", use_container_width=True)

        # Show cache status
        if TRADES_CSV.exists():
            mtime = datetime.fromtimestamp(TRADES_CSV.stat().st_mtime)
            st.caption(f"Cache local : {mtime.strftime('%d/%m/%Y %H:%M')}")
        else:
            st.caption("Pas de cache local.")

        st.divider()
        st.markdown(
            "**Droits API requis :** Query Funds, Query Orders & Trades, Query Ledger Entries\n\n"
            "Créez une clé **lecture seule** sur "
            "[Kraken API Management](https://www.kraken.com/u/security/api)."
        )

    # Auto-load from local CSV cache on startup — no API key needed
    if "trades_df" not in st.session_state and TRADES_CSV.exists() and not fetch_btn:
        st.session_state["trades_df"] = _load_trades_csv()
        loaded_ledgers = _load_ledgers_csv()
        st.session_state["ledgers_df"] = loaded_ledgers if loaded_ledgers is not None else pd.DataFrame()

    # Only block on missing key if there's nothing cached and user wants to fetch
    if fetch_btn and (not api_key or not api_secret):
        st.warning("Clé API et secret requis pour charger depuis Kraken.")
        return

    if not api_key and not api_secret and "trades_df" not in st.session_state:
        st.info(
            "Entrez vos clés API Kraken dans la barre latérale pour commencer, ou montez un dossier `data/` avec un cache existant."
        )
        return

    if fetch_btn or "trades_df" in st.session_state:
        if fetch_btn:
            label = "Rechargement depuis Kraken…" if force_refresh else "Chargement (cache ou Kraken)…"
            with st.spinner(label):
                try:
                    st.session_state["trades_df"] = fetch_all_trades(api_key, api_secret, force_refresh)
                except Exception as e:
                    st.error(f"Erreur trades : {e}")
                    return
            with st.spinner(label):
                try:
                    st.session_state["ledgers_df"] = fetch_all_ledgers(api_key, api_secret, force_refresh)
                except Exception as e:
                    st.error(f"Erreur ledger : {e}")
                    return

        trades_df: pd.DataFrame = st.session_state.get("trades_df", pd.DataFrame())
        ledgers_df: pd.DataFrame = st.session_state.get("ledgers_df", pd.DataFrame())

        if trades_df.empty:
            st.warning("Aucun trade trouvé.")
            return

        st.success(f"✅ {len(trades_df)} trades — {len(ledgers_df)} entrées de ledger chargées.")

        tab_overview, tab_2086, tab_staking, tab_help = st.tabs(
            ["📋 Aperçu", "📄 Formulaire 2086", "💰 Staking (2042-C-PRO)", "ℹ️ Aide"]
        )

        # Aperçu ---------------------------------------------------------------
        with tab_overview:
            year_trades = trades_df[trades_df["time"].dt.year == tax_year]
            st.metric(f"Trades {tax_year}", len(year_trades))
            disp = [c for c in ["time", "pair", "type", "vol", "price", "cost", "fee"] if c in year_trades.columns]
            st.dataframe(year_trades[disp], use_container_width=True)

            if not ledgers_df.empty:
                st.subheader("Ledger")
                year_ledger = ledgers_df[ledgers_df["time"].dt.year == tax_year]
                st.dataframe(
                    year_ledger[["time", "type", "asset", "amount", "fee", "balance"]], use_container_width=True
                )

        # Form 2086 ------------------------------------------------------------
        with tab_2086:
            st.subheader(f"Annexe 2086 – Plus/Moins-values {tax_year}")
            st.info("Calcul selon l'art. 150 VH bis CGI. Portefeuille = actifs Kraken uniquement.")

            with st.spinner("Calcul des plus-values…"):
                df_2086 = calc_form_2086(trades_df, ledgers_df, tax_year)

            if df_2086.empty:
                st.warning("Aucune cession taxable détectée pour cette année.")
            else:
                total_pv = round(df_2086["Plus/Moins-value"].sum(), 2)
                c1, c2, c3 = st.columns(3)
                c1.metric("Cessions", len(df_2086))
                c2.metric("Plus/Moins-value globale (L224)", f"{total_pv:+,.2f} €")
                c3.metric(
                    "Résultat", "Plus-value ✅" if total_pv > 0 else ("Moins-value 🔴" if total_pv < 0 else "Neutre")
                )

                fmt_cols = {
                    c: "{:,.2f} €" for c in df_2086.columns if c not in ("Date (L211)", "Pair", "txid", "Volume vendu")
                }
                st.dataframe(
                    df_2086.drop(columns=["txid"]).style.format(fmt_cols),
                    use_container_width=True,
                )

                csv = df_2086.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
                st.download_button("⬇️ CSV 2086", csv, f"form_2086_{tax_year}.csv", "text/csv")

                st.markdown(f"""
---
### Reporter sur le formulaire 2086
| Ligne | Description | Valeur |
|-------|-------------|--------|
| 211 | Date de chaque cession | *voir tableau* |
| 212 | Valeur portefeuille à la cession | *voir tableau* |
| 213 | Prix de cession | *voir tableau* |
| 214 | Frais de cession | *voir tableau* |
| 218 | Net frais + soultes | *voir tableau* |
| 220 | Prix total d'acquisition (PMTA) | *voir tableau* |
| 221 | Capital récupéré cessions précédentes | *voir tableau* |
| 223 | Acq. net | *voir tableau* |
| **224** | **Plus/Moins-value globale** | **{total_pv:+,.2f} €** |
                """)

        # Staking --------------------------------------------------------------
        with tab_staking:
            st.subheader(f"Revenus de staking {tax_year} – 2042-C-PRO")
            st.info("BNC imposables à réception. Reporter ligne **5HQ** (non-pro) ou **5HP** (pro).")

            with st.spinner("Calcul…"):
                df_staking = calc_staking_income(ledgers_df, tax_year)

            if df_staking.empty:
                st.warning("Aucun revenu de staking détecté.")
            else:
                total_stk = df_staking["Valeur EUR"].sum()
                c1, c2 = st.columns(2)
                c1.metric("Récompenses", len(df_staking))
                c2.metric("Total EUR", f"{total_stk:,.2f} €")

                st.dataframe(df_staking, use_container_width=True)
                csv_s = df_staking.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
                st.download_button("⬇️ CSV Staking", csv_s, f"staking_{tax_year}.csv", "text/csv")

                st.markdown(f"""
---
### Reporter sur le formulaire 2042-C-PRO
| Ligne | Valeur |
|-------|--------|
| **5HQ** (non-professionnel) | **{total_stk:,.2f} €** |
| **5HP** (professionnel) | {total_stk:,.2f} € |
                """)

        # Aide -----------------------------------------------------------------
        with tab_help:
            st.markdown("""
## Comment utiliser cet outil

1. Créez une **clé API Kraken lecture seule** avec droits : Query Funds, Query Orders & Trades, Query Ledger Entries.
2. Saisissez clé + secret dans la barre latérale.
3. Sélectionnez l'année fiscale.
4. Cliquez **Charger les données**.
5. Onglet **2086** → vérifiez chaque ligne → reportez sur impots.gouv.fr.
6. Onglet **Staking** → reportez le total ligne 5HQ sur votre 2042-C-PRO.

## Limites importantes

- ⚠️ **Portefeuille Kraken uniquement** — les actifs sur d'autres exchanges faussent L212.
- ⚠️ **Historique pré-Kraken** — le PMTA (L220) sera sous-estimé si vous déteniez des cryptos avant.
- ⚠️ **Swaps crypto-crypto** — cessions taxables non encore calculées.
- ⚠️ **Prix EUR** — estimés via OHLC journalier Kraken ; peuvent différer du prix exact de la transaction.
- ℹ️ Ce n'est pas un conseil fiscal. Consultez un comptable ou avocat fiscaliste.

## Références
- [Art. 150 VH bis CGI](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000041471515)
- [Formulaire 2086 CERFA 15140](https://www.impots.gouv.fr/formulaire/2086/declaration-des-cessions-dactifs-numeriques)
- [BOFiP – Actifs numériques](https://bofip.impots.gouv.fr/bofip/11668-PGP.html)
            """)


if __name__ == "__main__":
    main()
