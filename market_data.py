"""
Market Data Fetcher & Aggregator
Collects data from Yahoo Finance, Naver Finance API, CNN Fear & Greed, and KRX Cache.
"""

import os
import json
import requests
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
from config import INDICATORS_META, INTEGER_ONLY_TICKERS

def get_fear_and_greed():
    """Fetch CNN Fear & Greed Index score and historical data."""
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://edition.cnn.com/markets/fear-and-greed"
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            fg = data.get("fear_and_greed", {})
            score = fg.get("score")
            prev_close = fg.get("previous_close", score)
            change_amt = score - prev_close if score is not None and prev_close is not None else 0
            change_pct = (change_amt / prev_close) * 100 if prev_close else 0

            hist_raw = data.get("fear_and_greed_historical", {}).get("data", [])
            history = [
                {"date": datetime.fromtimestamp(item["x"] / 1000).strftime("%Y-%m-%d"), "value": round(float(item["y"]), 2)}
                for item in hist_raw if "x" in item and "y" in item
            ][-60:]

            return {
                "ticker": "FEAR_GREED",
                "name": INDICATORS_META.get("FEAR_GREED", {}).get("name", "CNN Fear & Greed Index"),
                "price": round(score, 1) if score is not None else None,
                "change_amt": round(change_amt, 1),
                "change_percent": round(change_pct, 2),
                "open": None, "high": None, "low": None, "close": round(score, 1) if score is not None else None,
                "history": history,
                "negative_favorable": False,
                "is_integer_only": False,
                "is_percent": False
            }
    except Exception as e:
        print(f"Error fetching Fear & Greed: {e}")
    return None

def get_krx_cache_data():
    """Read data from local krx_cache.json if available."""
    cache_path = os.path.join(os.path.dirname(__file__), "krx_cache.json")
    if not os.path.exists(cache_path):
        return {}

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            krx_raw = json.load(f)

        krx_map = {}
        key_to_ticker = {
            "vkospi": "VKOSPI",
            "kospi200_night": "KOSPI200_NIGHT",
            "kospi200_futures": "KOSPI200_FUTURES",
            "kospi_rsi": "KOSPI_RSI",
            "kospi_adr": "ADR_INFO",
            "per": "KOSPI_PER",
            "pbr": "KOSPI_PBR",
            "kospi_trade_value": "KOSPI_TRADE_VALUE",
            "customer_deposits": "CUSTOMER_DEPOSITS",
            "credit_balance": "CREDIT_BALANCE",
            "margin_call": "MARGIN_CALL"
        }

        for json_key, ticker in key_to_ticker.items():
            item = krx_raw.get(json_key)
            if not item:
                continue

            meta = INDICATORS_META.get(ticker, {})
            hist_raw = item.get("history", [])
            history = []
            for h in hist_raw:
                d_str = h.get("date", "").split("T")[0]
                val = h.get("value")
                if d_str and val is not None:
                    history.append({"date": d_str, "value": val})

            krx_map[ticker] = {
                "ticker": ticker,
                "name": meta.get("name", ticker),
                "price": item.get("price"),
                "change_amt": item.get("changeAmt"),
                "change_percent": item.get("changePercent"),
                "open": item.get("open"),
                "high": item.get("high"),
                "low": item.get("low"),
                "close": item.get("close"),
                "history": history[-60:],
                "negative_favorable": meta.get("negative_favorable", False),
                "is_integer_only": ticker in INTEGER_ONLY_TICKERS,
                "is_percent": meta.get("is_percent", False)
            }
        return krx_map
    except Exception as e:
        print(f"Error reading krx_cache.json: {e}")
        return {}

def fetch_naver_price(ticker):
    """Fetch recent price data for Korean stocks and indexes using Naver Mobile API."""
    try:
        naver_code = ticker.replace(".KS", "").replace(".KQ", "")
        if ticker == "^KS11":
            naver_code = "KOSPI"
        elif ticker == "^KQ11":
            naver_code = "KOSDAQ"

        url = f"https://m.stock.naver.com/api/stock/{naver_code}/price?pageSize=60&page=1"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                latest = data[0]
                price = float(latest["closePrice"].replace(",", ""))
                open_val = float(latest["openPrice"].replace(",", ""))
                high_val = float(latest["highPrice"].replace(",", ""))
                low_val = float(latest["lowPrice"].replace(",", ""))
                change_amt = float(latest["compareToPreviousClosePrice"].replace(",", ""))
                change_pct = float(latest["fluctuationsRatio"].replace(",", ""))

                # History in chronological order
                history = [
                    {"date": item["localTradedAt"][:10], "value": float(item["closePrice"].replace(",", ""))}
                    for item in reversed(data)
                ]

                meta = INDICATORS_META.get(ticker, {})
                return {
                    "ticker": ticker,
                    "name": meta.get("name", ticker),
                    "price": price,
                    "change_amt": change_amt,
                    "change_percent": change_pct,
                    "open": open_val,
                    "high": high_val,
                    "low": low_val,
                    "close": price,
                    "history": history[-60:],
                    "negative_favorable": meta.get("negative_favorable", False),
                    "is_integer_only": ticker in INTEGER_ONLY_TICKERS,
                    "is_percent": False
                }
    except Exception:
        pass
    return None

def fetch_yahoo_bulk(tickers):
    """Fetch daily OHLCV and history for multiple tickers via yfinance."""
    results = {}
    if not tickers:
        return results

    try:
        df = yf.download(tickers, period="3mo", interval="1d", group_by="ticker", progress=False, threads=True)
        if df.empty:
            return results

        is_multi = isinstance(df.columns, pd.MultiIndex)

        for ticker in tickers:
            try:
                if is_multi:
                    if ticker not in df.columns.levels[0]:
                        continue
                    tdf = df[ticker].dropna(subset=["Close"])
                else:
                    tdf = df.dropna(subset=["Close"])

                if len(tdf) < 2:
                    continue

                latest_row = tdf.iloc[-1]
                prev_row = tdf.iloc[-2]

                price = float(latest_row["Close"])
                prev_close = float(prev_row["Close"])
                change_amt = price - prev_close
                change_pct = (change_amt / prev_close) * 100 if prev_close else 0.0

                open_val = float(latest_row["Open"]) if "Open" in latest_row and not pd.isna(latest_row["Open"]) else price
                high_val = float(latest_row["High"]) if "High" in latest_row and not pd.isna(latest_row["High"]) else price
                low_val = float(latest_row["Low"]) if "Low" in latest_row and not pd.isna(latest_row["Low"]) else price
                close_val = price

                history = [
                    {"date": idx.strftime("%Y-%m-%d"), "value": round(float(row["Close"]), 4)}
                    for idx, row in tdf.iterrows()
                ][-60:]

                meta = INDICATORS_META.get(ticker, {})
                results[ticker] = {
                    "ticker": ticker,
                    "name": meta.get("name", ticker),
                    "price": price,
                    "change_amt": change_amt,
                    "change_percent": change_pct,
                    "open": open_val,
                    "high": high_val,
                    "low": low_val,
                    "close": close_val,
                    "history": history,
                    "negative_favorable": meta.get("negative_favorable", False),
                    "is_integer_only": ticker in INTEGER_ONLY_TICKERS,
                    "is_percent": meta.get("is_percent", False)
                }
            except Exception as item_err:
                print(f"Error parsing Yahoo data for {ticker}: {item_err}")
    except Exception as e:
        print(f"Error in fetch_yahoo_bulk: {e}")

    return results

def compute_skhy_premium(skhy_data, krw_data, hynix_data):
    """
    Calculate SKHY ADR Premium based on:
    premiumPrice = (SKHY * KRW * 10) - HYNIX
    premiumPercent = (premiumPrice / HYNIX) * 100
    """
    if not skhy_data or not krw_data or not hynix_data:
        return None

    skhy_hist = {h["date"]: h["value"] for h in skhy_data.get("history", [])}
    krw_hist = {h["date"]: h["value"] for h in krw_data.get("history", [])}
    hynix_hist = {h["date"]: h["value"] for h in hynix_data.get("history", [])}

    all_dates = sorted(list(set(skhy_hist.keys()) | set(krw_hist.keys()) | set(hynix_hist.keys())))

    last_skhy = None
    last_krw = None
    last_hynix = None
    aligned = []

    for d in all_dates:
        if d in skhy_hist:
            last_skhy = skhy_hist[d]
        if d in krw_hist:
            last_krw = krw_hist[d]
        if d in hynix_hist:
            last_hynix = hynix_hist[d]

        if last_skhy is not None and last_krw is not None and last_hynix is not None and last_hynix > 0:
            p_price = (last_skhy * last_krw * 10) - last_hynix
            p_pct = (p_price / last_hynix) * 100
            aligned.append({
                "date": d,
                "price": p_price,
                "percent": round(p_pct, 2)
            })

    if len(aligned) >= 2:
        latest = aligned[-1]
        prev = aligned[-2]
        chg_amt = latest["price"] - prev["price"]
        chg_pct = (chg_amt / abs(prev["price"])) * 100 if prev["price"] != 0 else 0

        hist = [{"date": a["date"], "value": a["percent"]} for a in aligned][-60:]

        meta = INDICATORS_META.get("SKHY_ADR_PREMIUM", {})
        return {
            "ticker": "SKHY_ADR_PREMIUM",
            "name": meta.get("name", "SKHY ADR Premium"),
            "price": latest["price"],
            "change_amt": chg_amt,
            "change_percent": chg_pct,
            "open": None, "high": None, "low": None, "close": latest["price"],
            "history": hist,
            "negative_favorable": False,
            "is_integer_only": True,
            "is_percent": True
        }
    return None

def fetch_all_market_data():
    """Fetch and aggregate all indicators across US, K-Market, and Semiconductor tabs."""
    all_data = {}

    # 1. KRX Cache Data
    krx_data = get_krx_cache_data()
    all_data.update(krx_data)

    # 2. CNN Fear & Greed
    fg_data = get_fear_and_greed()
    if fg_data:
        all_data["FEAR_GREED"] = fg_data

    # 3. Korean stocks via Naver Finance API
    korean_tickers = ["005930.KS", "009150.KS", "402340.KS", "000660.KS", "^KS11", "^KQ11"]
    with ThreadPoolExecutor(max_workers=6) as executor:
        naver_results = list(executor.map(fetch_naver_price, korean_tickers))

    for item in naver_results:
        if item:
            all_data[item["ticker"]] = item

    # 4. Determine remaining tickers to query from Yahoo Finance
    all_meta_tickers = list(INDICATORS_META.keys())
    excluded = set(krx_data.keys()) | {"FEAR_GREED", "SKHY_ADR_PREMIUM"} | set(all_data.keys())
    yahoo_tickers = [t for t in all_meta_tickers if t not in excluded]

    # Ensure required tickers for SKHY premium are fetched
    for req_t in ["SKHY", "KRW=X", "000660.KS"]:
        if req_t not in all_data and req_t not in yahoo_tickers:
            yahoo_tickers.append(req_t)

    # Fetch Yahoo data in bulk
    yahoo_data = fetch_yahoo_bulk(yahoo_tickers)
    all_data.update(yahoo_data)

    # 5. Compute SKHY ADR Premium
    skhy_row = compute_skhy_premium(
        all_data.get("SKHY"),
        all_data.get("KRW=X"),
        all_data.get("000660.KS")
    )
    if skhy_row:
        all_data["SKHY_ADR_PREMIUM"] = skhy_row

    return all_data
