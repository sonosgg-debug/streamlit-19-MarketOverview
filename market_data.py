"""
Market Data Fetcher & Aggregator
Collects data from Yahoo Finance, Naver Finance API, CNN Fear & Greed, and KRX Cache.
"""

import os
import sys
import json
import requests
import subprocess
import threading
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from config import INDICATORS_META, INTEGER_ONLY_TICKERS

_krx_update_lock = threading.Lock()
_krx_updating = False

def trigger_krx_background_update(wait=False):
    """Trigger get_kospi_fundamentals.py in background (or synchronously if wait=True) if cache is stale or requested."""
    global _krx_updating
    with _krx_update_lock:
        if _krx_updating:
            return
        _krx_updating = True

    def _worker():
        global _krx_updating
        try:
            script_path = os.path.join(os.path.dirname(__file__), "get_kospi_fundamentals.py")
            if os.path.exists(script_path):
                subprocess.run([sys.executable, script_path, "--batch"], cwd=os.path.dirname(__file__), timeout=180)
        except Exception as e:
            print(f"Background KRX cache update error: {e}")
        finally:
            with _krx_update_lock:
                _krx_updating = False

    if wait:
        _worker()
    else:
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

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
            ][-200:]

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

def get_krx_cache_data(force_update=False, wait=False):
    """Read data from local krx_cache.json if available and trigger refresh if stale or forced."""
    cache_path = os.path.join(os.path.dirname(__file__), "krx_cache.json")

    if force_update:
        trigger_krx_background_update(wait=wait)
    elif not os.path.exists(cache_path):
        trigger_krx_background_update(wait=wait)
        return {}
    else:
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
            if (datetime.now() - mtime).total_seconds() > 14400:
                trigger_krx_background_update(wait=wait)
        except Exception:
            pass

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
                "history": history[-200:],
                "negative_favorable": meta.get("negative_favorable", False),
                "is_integer_only": ticker in INTEGER_ONLY_TICKERS,
                "is_percent": meta.get("is_percent", False)
            }
        return krx_map
    except Exception as e:
        print(f"Error reading krx_cache.json: {e}")
        return {}

def fetch_naver_price(ticker):
    """Fetch recent price data for Korean stocks, indices, and futures using Naver Mobile API (up to 200 trading days)."""
    try:
        if ticker == "^KS11":
            url_type = "index"
            naver_code = "KOSPI"
        elif ticker == "^KQ11":
            url_type = "index"
            naver_code = "KOSDAQ"
        elif ticker == "KOSPI200_FUTURES":
            url_type = "index"
            naver_code = "FUT"
        else:
            url_type = "stock"
            naver_code = ticker.replace(".KS", "").replace(".KQ", "")

        headers = {"User-Agent": "Mozilla/5.0"}
        raw_items = []
        for p in range(1, 5):
            url = f"https://m.stock.naver.com/api/{url_type}/{naver_code}/price?pageSize=60&page={p}"
            res = requests.get(url, headers=headers, timeout=4)
            if res.status_code == 200:
                p_data = res.json()
                if isinstance(p_data, list) and len(p_data) > 0:
                    raw_items.extend(p_data)
                else:
                    break
            else:
                break

        if raw_items:
            latest = raw_items[0]
            price = float(latest["closePrice"].replace(",", ""))
            open_val = float(latest["openPrice"].replace(",", ""))
            high_val = float(latest["highPrice"].replace(",", ""))
            low_val = float(latest["lowPrice"].replace(",", ""))
            change_amt = float(latest["compareToPreviousClosePrice"].replace(",", ""))

            # Adjust sign based on compareToPreviousPrice direction
            cmp_price = latest.get("compareToPreviousPrice", {})
            if isinstance(cmp_price, dict) and cmp_price.get("name") == "FALLING":
                if change_amt > 0:
                    change_amt = -change_amt
            change_pct = float(latest["fluctuationsRatio"].replace(",", ""))
            if change_amt < 0 and change_pct > 0:
                change_pct = -change_pct

            # History in chronological order (up to 200)
            history = [
                {"date": item["localTradedAt"][:10], "value": float(item["closePrice"].replace(",", ""))}
                for item in reversed(raw_items)
            ][-200:]

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
                "history": history,
                "negative_favorable": meta.get("negative_favorable", False),
                "is_integer_only": ticker in INTEGER_ONLY_TICKERS,
                "is_percent": False
            }
    except Exception as e:
        print(f"Error fetching Naver price for {ticker}: {e}")
    return None

def compute_kospi_rsi(ks11_item):
    """Dynamically compute 14-day RSI for KOSPI using closing history."""
    if not ks11_item or not ks11_item.get("history"):
        return None
    hist = ks11_item["history"]
    if len(hist) < 15:
        return None
    closes = pd.Series([h["value"] for h in hist], index=[h["date"] for h in hist])
    delta = closes.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi_series = (100 - (100 / (1 + rs))).dropna()
    if len(rsi_series) < 2:
        return None
    latest_rsi = round(float(rsi_series.iloc[-1]), 2)
    prev_rsi = round(float(rsi_series.iloc[-2]), 2)
    change_amt = round(latest_rsi - prev_rsi, 2)
    change_pct = round((change_amt / prev_rsi) * 100, 2) if prev_rsi != 0 else 0.0
    rsi_hist = [{"date": d, "value": round(float(v), 2)} for d, v in rsi_series.items()][-200:]
    meta = INDICATORS_META.get("KOSPI_RSI", {})
    return {
        "ticker": "KOSPI_RSI",
        "name": meta.get("name", "KOSPI RSI(14, %)"),
        "price": latest_rsi,
        "change_amt": change_amt,
        "change_percent": change_pct,
        "open": None, "high": None, "low": None, "close": latest_rsi,
        "history": rsi_hist,
        "negative_favorable": meta.get("negative_favorable", False),
        "is_integer_only": False,
        "is_percent": False
    }

def fetch_kospi_trade_value(existing_item=None):
    """Fetch recent KOSPI trading value from Naver Finance table."""
    try:
        url = "https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI&page=1"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        if res.status_code == 200:
            soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
            tbl = soup.find("table", class_="type_1")
            if tbl:
                rows = []
                for tr in tbl.find_all("tr"):
                    cols = [td.text.strip() for td in tr.find_all("td") if td.text.strip()]
                    if len(cols) >= 6 and "." in cols[0]:
                        d_str = cols[0].replace(".", "-")
                        val_raw = float(cols[5].replace(",", "")) / 100.0  # 백만원 -> 억원
                        rows.append({"date": d_str, "value": round(val_raw, 2)})
                if len(rows) >= 2:
                    latest = rows[0]
                    prev = rows[1]
                    chg_amt = round(latest["value"] - prev["value"], 2)
                    chg_pct = round((chg_amt / prev["value"]) * 100, 2) if prev["value"] != 0 else 0.0

                    hist = []
                    if existing_item and existing_item.get("history"):
                        hist = list(existing_item["history"])
                        if hist and hist[-1]["date"] == latest["date"]:
                            hist[-1]["value"] = latest["value"]
                        elif hist and hist[-1]["date"] < latest["date"]:
                            hist.append(latest)
                    else:
                        hist = list(reversed(rows))

                    meta = INDICATORS_META.get("KOSPI_TRADE_VALUE", {})
                    return {
                        "ticker": "KOSPI_TRADE_VALUE",
                        "name": meta.get("name", "KOSPI 거래대금 (단위:억원)"),
                        "price": latest["value"],
                        "change_amt": chg_amt,
                        "change_percent": chg_pct,
                        "open": None, "high": None, "low": None, "close": latest["value"],
                        "history": hist[-200:],
                        "negative_favorable": meta.get("negative_favorable", False),
                        "is_integer_only": True,
                        "is_percent": False
                    }
    except Exception as e:
        print(f"Error fetching KOSPI trade value: {e}")
    return existing_item

def fetch_yahoo_bulk(tickers):
    """Fetch daily OHLCV and history for multiple tickers via yfinance (up to 200 trading days)."""
    results = {}
    if not tickers:
        return results

    try:
        df = yf.download(tickers, period="1y", interval="1d", group_by="ticker", progress=False, threads=True)
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
                ][-200:]

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

def fetch_all_market_data(force_refresh=False, wait_for_krx=False):
    """Fetch and aggregate all indicators across US, K-Market, and Semiconductor tabs."""
    all_data = {}

    # 1. KRX Cache Data (provides KOFIA deposits/credit/margin_call, VKOSPI, Night Futures, PER, PBR, ADR)
    krx_data = get_krx_cache_data(force_update=force_refresh, wait=wait_for_krx)
    all_data.update(krx_data)

    # 2. CNN Fear & Greed
    fg_data = get_fear_and_greed()
    if fg_data:
        all_data["FEAR_GREED"] = fg_data

    # 3. Korean stocks, indices, and KOSPI200 Futures via Naver Mobile API (live and independent of cache)
    korean_tickers = [
        "005930.KS", "009150.KS", "402340.KS", "000660.KS",
        "^KS11", "^KQ11", "KOSPI200_FUTURES"
    ]
    with ThreadPoolExecutor(max_workers=7) as executor:
        naver_results = list(executor.map(fetch_naver_price, korean_tickers))

    for item in naver_results:
        if item:
            all_data[item["ticker"]] = item

    # 3b. Compute KOSPI RSI dynamically from live KOSPI (^KS11) daily close history
    ks11_item = all_data.get("^KS11")
    if ks11_item:
        rsi_item = compute_kospi_rsi(ks11_item)
        if rsi_item:
            all_data["KOSPI_RSI"] = rsi_item

    # 3c. Fetch KOSPI Trade Value dynamically from Naver Finance
    tv_item = fetch_kospi_trade_value(all_data.get("KOSPI_TRADE_VALUE"))
    if tv_item:
        all_data["KOSPI_TRADE_VALUE"] = tv_item

    # 4. Determine remaining tickers to query from Yahoo Finance
    all_meta_tickers = list(INDICATORS_META.keys())
    excluded = set(all_data.keys()) | {"FEAR_GREED"}
    yahoo_tickers = [t for t in all_meta_tickers if t not in excluded]

    # Fetch Yahoo data in bulk
    yahoo_data = fetch_yahoo_bulk(yahoo_tickers)
    all_data.update(yahoo_data)

    return all_data
