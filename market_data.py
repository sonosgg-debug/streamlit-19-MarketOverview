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
import socket
socket.setdefaulttimeout(15.0)
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
import pytz
import math
from config import INDICATORS_META, INTEGER_ONLY_TICKERS, KRX_HOLIDAYS

_krx_update_lock = threading.Lock()
_krx_updating = False

def load_krx_auth():
    """Load KRX credentials from workspace or 00 API Key folder."""
    if not os.getenv("KRX_ID") or not os.getenv("KRX_PW"):
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        api_key_path = os.path.join(parent_dir, "00 API Key", "KRX ID&PW.txt")
        if not os.path.exists(api_key_path):
            api_key_path = r"D:\AI Investing\00 API Key\KRX ID&PW.txt"
        if os.path.exists(api_key_path):
            try:
                with open(api_key_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("ID :") or line.startswith("ID:"):
                            os.environ["KRX_ID"] = line.split(":", 1)[1].strip()
                        elif line.startswith("PW :") or line.startswith("PW:"):
                            os.environ["KRX_PW"] = line.split(":", 1)[1].strip()
            except Exception:
                pass

load_krx_auth()

_CACHED_TRADING_DAYS = None

def get_krx_trading_days(count=120):
    """
    한국거래소(KRX)의 실제 거래일(개장일) 목록을 반환합니다.
    1. 네이버 증시 API를 통해 실시간 실제 거래일 리스트를 우선 확보
    2. 실패 시 사전 정의된 휴장일 캘린더 및 주말 제외 알고리즘으로 폴백
    """
    global _CACHED_TRADING_DAYS
    if _CACHED_TRADING_DAYS is not None and len(_CACHED_TRADING_DAYS) >= count:
        return _CACHED_TRADING_DAYS
        
    days = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    pages_needed = (count + 59) // 60
    for page in range(1, pages_needed + 1):
        try:
            url = f'https://m.stock.naver.com/api/stock/005930/price?pageSize=60&page={page}'
            r = requests.get(url, headers=headers, timeout=3)
            if r.status_code == 200:
                items = r.json()
                if items:
                    days.extend([item['localTradedAt'].replace('-', '') for item in items])
                else:
                    break
        except Exception:
            pass
            
    if days:
        _CACHED_TRADING_DAYS = sorted(list(set(days)))
        return _CACHED_TRADING_DAYS
        
    fallback_days = []
    now_kst = datetime.now(KST)
    d = now_kst
    for _ in range(count * 3):
        d_str = d.strftime('%Y%m%d')
        if d.weekday() < 5 and d_str not in KRX_HOLIDAYS:
            fallback_days.append(d_str)
            if len(fallback_days) >= count:
                break
        d -= timedelta(days=1)
        
    _CACHED_TRADING_DAYS = sorted(fallback_days)
    return _CACHED_TRADING_DAYS

def is_krx_trading_day(date_str):
    """주어진 날짜(YYYYMMDD 또는 YYYY-MM-DD)가 실제 거래일인지 판별합니다."""
    clean_date = str(date_str).replace('-', '')
    trading_days = get_krx_trading_days(120)
    if clean_date in trading_days:
        return True
    try:
        dt = datetime.strptime(clean_date, "%Y%m%d")
        return (dt.weekday() < 5) and (clean_date not in KRX_HOLIDAYS)
    except:
        return False

def get_latest_expected_trading_day(target_date: str = None) -> str:
    """
    가장 최근 거래 완료된 실제 영업일 YYYY-MM-DD 반환.
    - target_date가 전달된 경우: 해당 날짜가 거래일이면 그대로, 휴장일이면 직전 실제 거래일로 자동 보정
    - target_date가 없는 경우: KST 기준 15:45 이전이거나 오늘이 휴장일이면 최신 마감 거래일 반환
    """
    trading_days = get_krx_trading_days(120)
    
    if target_date:
        clean_date = str(target_date).replace('-', '')
        if clean_date in trading_days:
            return f"{clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:]}"
        earlier = [d for d in trading_days if d <= clean_date]
        if earlier:
            d_res = earlier[-1]
            return f"{d_res[:4]}-{d_res[4:6]}-{d_res[6:]}"
        try:
            dt = datetime.strptime(clean_date, "%Y%m%d")
            while True:
                d_str = dt.strftime("%Y%m%d")
                if dt.weekday() < 5 and d_str not in KRX_HOLIDAYS:
                    return f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
                dt -= timedelta(days=1)
        except Exception:
            return str(target_date)

    now_kst = datetime.now(KST)
    today_str = now_kst.strftime('%Y%m%d')

    if now_kst.hour > 15 or (now_kst.hour == 15 and now_kst.minute >= 45):
        if today_str in trading_days:
            return f"{today_str[:4]}-{today_str[4:6]}-{today_str[6:]}"

    prior_days = [d for d in trading_days if d < today_str]
    if prior_days:
        d_res = prior_days[-1]
        return f"{d_res[:4]}-{d_res[4:6]}-{d_res[6:]}"

    fallback_str = trading_days[-1] if trading_days else (now_kst - timedelta(days=1)).strftime('%Y%m%d')
    return f"{fallback_str[:4]}-{fallback_str[4:6]}-{fallback_str[6:]}"

_krx_update_lock = threading.Lock()
_krx_updating = False

def trigger_krx_background_update(wait=False):
    """Trigger update_krx_cache() in background or with safety timeout if wait=True."""
    global _krx_updating
    if wait:
        with _krx_update_lock:
            try:
                _krx_updating = True
                from get_kospi_fundamentals import update_krx_cache
                # Run with safety timeout so Cloud IP blocks don't freeze indefinitely
                def _run():
                    try:
                        update_krx_cache()
                    except Exception as err:
                        print(f"Error in update_krx_cache worker: {err}")

                worker_t = threading.Thread(target=_run, daemon=True)
                worker_t.start()
                worker_t.join(timeout=45.0)
                if worker_t.is_alive():
                    print("Warning: update_krx_cache timed out after 45.0s, proceeding with existing cache.")
            except Exception as e:
                print(f"Error in synchronous update_krx_cache: {e}")
            finally:
                _krx_updating = False
        return

    # Background non-blocking execution
    with _krx_update_lock:
        if _krx_updating:
            return
        _krx_updating = True

    def _worker():
        global _krx_updating
        try:
            from get_kospi_fundamentals import update_krx_cache
            update_krx_cache()
        except Exception as e:
            print(f"Error in background update_krx_cache: {e}")
        finally:
            with _krx_update_lock:
                _krx_updating = False

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

    should_update = False
    if force_update:
        should_update = True
        wait = True
    elif not os.path.exists(cache_path):
        should_update = True
        wait = True  # File doesn't exist, must wait so first run has data
    else:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                c_head = json.load(f)
            meta = c_head.get("_meta", {})
            last_update_str = meta.get("last_batch_update")
            if last_update_str:
                last_dt = datetime.fromisoformat(last_update_str)
                now_kst = datetime.now(KST)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=KST)
                if (now_kst - last_dt).total_seconds() > 14400:
                    should_update = True
            else:
                should_update = True

            # Check if PER history has the expected latest trading day's closing data
            expected_trading_day = get_latest_expected_trading_day()
            per_hist = c_head.get("per", {}).get("history", [])
            if per_hist:
                last_per_date = str(per_hist[-1].get("date", "")).split("T")[0]
                if last_per_date < expected_trading_day:
                    should_update = True
                    wait = True
            else:
                should_update = True
                wait = True
        except Exception:
            should_update = True
            wait = True

    if should_update:
        trigger_krx_background_update(wait=wait)


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

    # 2순위 폴백: FinanceDataReader (네이버 API 장애 또는 누락 시 KRX 공식 시세로 무결성 보장)
    return fetch_fdr_price(ticker)


def fetch_fdr_price(ticker):
    """
    Fetch price data for Korean stocks and indices via FinanceDataReader as a high-reliability fallback.
    Guarantees no phantom splits or pricing distortion.
    """
    try:
        if ticker == "^KS11":
            fdr_code = "KS11"
        elif ticker == "^KQ11":
            fdr_code = "KQ11"
        elif ticker.endswith(".KS") or ticker.endswith(".KQ"):
            fdr_code = ticker.replace(".KS", "").replace(".KQ", "")
        else:
            return None

        # 최근 1년 (약 250영업일) 데이터 수집
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        df = fdr.DataReader(fdr_code, start_date)
        if df is not None and not df.empty and len(df) >= 2:
            latest = df.iloc[-1]
            prev = df.iloc[-2]

            price = float(latest["Close"])
            prev_close = float(prev["Close"])
            open_val = float(latest["Open"]) if "Open" in latest and is_valid_num(latest["Open"]) else price
            high_val = float(latest["High"]) if "High" in latest and is_valid_num(latest["High"]) else price
            low_val = float(latest["Low"]) if "Low" in latest and is_valid_num(latest["Low"]) else price

            change_amt = round(price - prev_close, 2)
            change_pct = round((change_amt / prev_close) * 100, 2) if prev_close != 0 else 0.0

            history = [
                {"date": idx.strftime("%Y-%m-%d"), "value": round(float(row["Close"]), 2)}
                for idx, row in df.iterrows()
                if is_valid_num(row.get("Close"))
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
        print(f"Error fetching FDR price for {ticker}: {e}")
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
    """
    Fetch KOSPI trading value (단위: 억원).
    1순위: Daum 금융 API (초고속, 무인증, 200거래일 데이터 보장)
    2순위: Naver Mobile API (실시간 integration 당일 거래대금)
    3순위: pykrx / KRX MDC
    4순위: existing_item 폴백
    """
    expected_day = get_latest_expected_trading_day()
    if existing_item and existing_item.get("price") is not None:
        hist = existing_item.get("history", [])
        if hist:
            last_d = str(hist[-1].get("date", "")).split("T")[0]
            if last_d >= expected_day:
                return existing_item

    # 1순위: Daum 금융 API
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.daum.net/"
        }
        url = "https://finance.daum.net/api/market_index/days?page=1&perPage=60&market=KOSPI"
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            d_json = res.json()
            items = d_json.get("data", [])
            if items and len(items) >= 2:
                sorted_items = sorted(items, key=lambda x: x["date"][:10])
                history_val = [
                    {"date": it["date"][:10], "value": round(float(it["accTradePrice"]) / 100.0, 1)}
                    for it in sorted_items
                    if is_valid_num(it.get("accTradePrice"))
                ]
                if existing_item and existing_item.get("history"):
                    exist_map = {str(h["date"]).split("T")[0]: h["value"] for h in existing_item["history"]}
                    for h in history_val:
                        exist_map[h["date"]] = h["value"]
                    merged_dates = sorted(exist_map.keys())
                    final_history = [{"date": d, "value": exist_map[d]} for d in merged_dates][-200:]
                else:
                    final_history = history_val[-200:]

                latest_val = final_history[-1]["value"]
                prev_val = final_history[-2]["value"] if len(final_history) >= 2 else latest_val
                val_change = round(latest_val - prev_val, 1)
                val_pct = round((val_change / prev_val) * 100, 2) if prev_val != 0 else 0.0

                meta = INDICATORS_META.get("KOSPI_TRADE_VALUE", {})
                res_item = {
                    "ticker": "KOSPI_TRADE_VALUE",
                    "name": meta.get("name", "KOSPI 거래대금 (단위:억원)"),
                    "price": latest_val,
                    "change_amt": val_change,
                    "change_percent": val_pct,
                    "open": None, "high": None, "low": None, "close": latest_val,
                    "history": final_history,
                    "negative_favorable": meta.get("negative_favorable", False),
                    "is_integer_only": True,
                    "is_percent": False,
                    "trade_date": final_history[-1]["date"]
                }
                try:
                    cache_path = os.path.join(os.path.dirname(__file__), "krx_cache.json")
                    if os.path.exists(cache_path):
                        with open(cache_path, "r", encoding="utf-8") as f:
                            c_data = json.load(f)
                        if isinstance(c_data, dict):
                            c_data["kospi_trade_value"] = {
                                "price": latest_val,
                                "changeAmt": val_change,
                                "changePercent": val_pct,
                                "history": [{"date": f"{h['date']}T00:00:00.000Z", "value": h["value"]} for h in final_history]
                            }
                            with open(cache_path, "w", encoding="utf-8") as f:
                                json.dump(c_data, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
                return res_item
    except Exception as e:
        print(f"Error fetching KOSPI trade value from Daum: {e}")

    # 2순위: Naver Mobile API (실시간 당일 거래대금)
    try:
        url_nav = "https://m.stock.naver.com/api/index/KOSPI/integration"
        r_nav = requests.get(url_nav, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        if r_nav.status_code == 200:
            nav_data = r_nav.json()
            for tinfo in nav_data.get("totalInfos", []):
                if tinfo.get("code") == "accumulatedTradingValue":
                    raw_val_str = str(tinfo.get("value", "")).replace(",", "").replace("백만", "").strip()
                    if raw_val_str and is_valid_num(raw_val_str):
                        nav_val_eok = round(float(raw_val_str) / 100.0, 1)
                        expected_d = get_latest_expected_trading_day()
                        hist = list(existing_item.get("history", [])) if existing_item else []
                        if hist:
                            last_d = str(hist[-1].get("date", "")).split("T")[0]
                            if expected_d > last_d:
                                hist.append({"date": expected_d, "value": nav_val_eok})
                            else:
                                hist[-1]["value"] = nav_val_eok
                        else:
                            hist = [{"date": expected_d, "value": nav_val_eok}]

                        prev_v = hist[-2]["value"] if len(hist) >= 2 else nav_val_eok
                        chg_v = round(nav_val_eok - prev_v, 1)
                        chg_pct = round((chg_v / prev_v) * 100, 2) if prev_v != 0 else 0.0

                        meta = INDICATORS_META.get("KOSPI_TRADE_VALUE", {})
                        return {
                            "ticker": "KOSPI_TRADE_VALUE",
                            "name": meta.get("name", "KOSPI 거래대금 (단위:억원)"),
                            "price": nav_val_eok,
                            "change_amt": chg_v,
                            "change_percent": chg_pct,
                            "open": None, "high": None, "low": None, "close": nav_val_eok,
                            "history": hist[-200:],
                            "negative_favorable": meta.get("negative_favorable", False),
                            "is_integer_only": True,
                            "is_percent": False,
                            "trade_date": hist[-1]["date"]
                        }
    except Exception as e_nav:
        print(f"Error fetching KOSPI trade value from Naver: {e_nav}")

    return existing_item

def compute_kospi_adr(existing_item=None):
    """
    Compute 20-day KOSPI ADR (Advance Decline Ratio, %) dynamically.
    Combines local data/adv_dec_history.json with real-time Naver integration API upDownStockInfo.
    """
    adr_path = os.path.join(os.path.dirname(__file__), "data", "adv_dec_history.json")
    history_records = []
    if os.path.exists(adr_path):
        try:
            with open(adr_path, "r", encoding="utf-8") as f:
                history_records = json.load(f)
        except Exception:
            history_records = []

    # Check live Naver upDownStockInfo
    try:
        url_nav = "https://m.stock.naver.com/api/index/KOSPI/integration"
        r_nav = requests.get(url_nav, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        if r_nav.status_code == 200:
            nav_data = r_nav.json()
            up_down = nav_data.get("upDownStockInfo", {})
            rise = int(up_down.get("riseCount", 0)) + int(up_down.get("upperCount", 0))
            fall = int(up_down.get("fallCount", 0)) + int(up_down.get("lowerCount", 0))
            if rise > 0 or fall > 0:
                expected_d = get_latest_expected_trading_day()
                dates_set = {x["date"] for x in history_records}
                if expected_d not in dates_set:
                    history_records.append({"date": expected_d, "adv": rise, "dec": fall})
                    history_records.sort(key=lambda x: x["date"])
                    try:
                        with open(adr_path, "w", encoding="utf-8") as f_save:
                            json.dump(history_records[-250:], f_save, indent=4)
                    except Exception:
                        pass
                else:
                    for rec in history_records:
                        if rec["date"] == expected_d:
                            rec["adv"] = rise
                            rec["dec"] = fall
                            break
    except Exception as e:
        print(f"Error fetching live ADR counts from Naver: {e}")

    if not history_records or len(history_records) < 20:
        return existing_item

    adr_computed = []
    for i in range(len(history_records)):
        if i < 19:
            continue
        recent_20 = history_records[i-19 : i+1]
        sum_adv = sum(item["adv"] for item in recent_20)
        sum_dec = sum(item["dec"] for item in recent_20)
        val = (sum_adv / sum_dec) * 100 if sum_dec != 0 else 0.0
        adr_computed.append({"date": history_records[i]["date"], "value": round(val, 2)})

    if len(adr_computed) < 2:
        return existing_item

    adr_history = adr_computed[-200:]
    latest_adr = adr_history[-1]["value"]
    prev_adr = adr_history[-2]["value"]
    adr_change = round(latest_adr - prev_adr, 2)
    adr_pct = round((adr_change / prev_adr) * 100, 2) if prev_adr != 0 else 0.0

    meta = INDICATORS_META.get("ADR_INFO", {})
    res_item = {
        "ticker": "ADR_INFO",
        "name": meta.get("name", "KOSPI ADR(20, %)"),
        "price": latest_adr,
        "change_amt": adr_change,
        "change_percent": adr_pct,
        "open": None, "high": None, "low": None, "close": latest_adr,
        "history": adr_history,
        "negative_favorable": meta.get("negative_favorable", False),
        "is_integer_only": False,
        "is_percent": True,
        "trade_date": adr_history[-1]["date"]
    }
    try:
        cache_path = os.path.join(os.path.dirname(__file__), "krx_cache.json")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)
            if isinstance(c_data, dict):
                c_data["kospi_adr"] = {
                    "price": latest_adr,
                    "changeAmt": adr_change,
                    "changePercent": adr_pct,
                    "history": [{"date": f"{h['date']}T00:00:00.000Z", "value": h["value"]} for h in adr_history]
                }
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(c_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return res_item

def fetch_vkospi_direct(existing_item=None):
    """Fetch live VKOSPI from KRX MDCSTAT01201 using PyKRX with safe isolation."""
    expected_day = get_latest_expected_trading_day()
    if existing_item and existing_item.get("price") is not None:
        hist = existing_item.get("history", [])
        if hist:
            last_d = str(hist[-1].get("date", "")).split("T")[0]
            if last_d >= expected_day:
                return existing_item
        else:
            return existing_item

    try:
        load_krx_auth()
        from pykrx.website.krx.krxio import KrxWebIo

        class KrxMdc(KrxWebIo):
            @property
            def bld(self):
                return 'dbms/MDC/STAT/standard/MDCSTAT01201'

        today = datetime.now(KST)
        start_date = (today - timedelta(days=30)).strftime("%Y%m%d")
        end_date = today.strftime("%Y%m%d")

        krx = KrxMdc()
        res = krx.read(
            locale='ko_KR',
            indTpCd='1',
            idxIndCd='300',
            strtDd=start_date,
            endDd=end_date,
            share='1',
            money='1'
        )
        output = res.get('output', [])
        if output and len(output) >= 2:
            latest = output[0]
            prev = output[1]
            price = round(float(str(latest['CLSPRC_IDX']).replace(',', '')), 2)
            prev_price = round(float(str(prev['CLSPRC_IDX']).replace(',', '')), 2)
            change = round(price - prev_price, 2)
            pct = round((change / prev_price) * 100, 2) if prev_price != 0 else 0.0

            open_p = round(float(str(latest.get('OPNPRC_IDX', price)).replace(',', '')), 2)
            high_p = round(float(str(latest.get('HGPRC_IDX', price)).replace(',', '')), 2)
            low_p = round(float(str(latest.get('LWPRC_IDX', price)).replace(',', '')), 2)

            new_hist = []
            for row in reversed(output):
                d_str = str(row.get('TRD_DD', '')).strip().replace('/', '-')
                if len(d_str) == 8 and '-' not in d_str:
                    d_fmt = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
                else:
                    d_fmt = d_str
                if len(d_fmt) == 10:
                    new_hist.append({"date": d_fmt, "value": round(float(str(row['CLSPRC_IDX']).replace(',', '')), 2)})

            if existing_item and existing_item.get("history"):
                hist_map = {str(h["date"]).split("T")[0]: h["value"] for h in existing_item["history"]}
                for nh in new_hist:
                    hist_map[nh["date"]] = nh["value"]
                sorted_dates = sorted(hist_map.keys())
                final_hist = [{"date": d, "value": hist_map[d]} for d in sorted_dates][-200:]
            else:
                final_hist = new_hist[-200:]

            meta = INDICATORS_META.get("VKOSPI", {})
            result_item = {
                "ticker": "VKOSPI",
                "name": meta.get("name", "KOSPI200 변동성지수"),
                "price": price,
                "change_amt": change,
                "change_percent": pct,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": price,
                "history": final_hist,
                "negative_favorable": meta.get("negative_favorable", True),
                "is_integer_only": False,
                "is_percent": False,
                "trade_date": final_hist[-1]["date"]
            }

            try:
                cache_path = os.path.join(os.path.dirname(__file__), "krx_cache.json")
                if os.path.exists(cache_path):
                    with open(cache_path, "r", encoding="utf-8") as f:
                        c_data = json.load(f)
                    if isinstance(c_data, dict):
                        c_data["vkospi"] = {
                            "price": price,
                            "changeAmt": change,
                            "changePercent": pct,
                            "open": open_p,
                            "high": high_p,
                            "low": low_p,
                            "close": price,
                            "history": [{"date": f"{h['date']}T00:00:00.000Z", "value": h["value"]} for h in final_hist]
                        }
                        with open(cache_path, "w", encoding="utf-8") as f:
                            json.dump(c_data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

            return result_item
    except Exception as e:
        pass
    return existing_item


def fetch_kospi200_night_direct(existing_item=None, futures_item=None):
    """
    Fetch real-time KOSPI200 Night Futures data directly from eSignal API.
    Provides live quotes and maintains date-aligned history.
    Gracefully falls back to existing_item (from krx_cache.json) if unavailable.
    """
    try:
        url = "https://esignal.co.kr/data/cache/kospif_ngt.js"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://esignal.co.kr/kospi200-futures-night/"
        }
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            cdata = res.json()
            pts = cdata.get("data", [])
            if pts:
                prices = [float(p[1]) for p in pts]
                open_p = float(cdata.get("open", prices[0]))
                high_p = max(prices)
                low_p = min(prices)
                close_p = prices[-1]

                from datetime import timezone
                kst = timezone(timedelta(hours=9))
                ts_first = pts[0][0] / 1000.0
                ts_last = pts[-1][0] / 1000.0
                session_start_date = datetime.fromtimestamp(ts_first, kst).strftime("%Y-%m-%d")
                session_end_date = datetime.fromtimestamp(ts_last, kst).strftime("%Y-%m-%d")

                # Reference price for change calculation:
                # Night futures change is officially compared to daytime futures close of session_start_date.
                change_base_price = None
                if futures_item and isinstance(futures_item, dict):
                    f_hist = futures_item.get("history", [])
                    for h in reversed(f_hist):
                        if h.get("date") == session_start_date:
                            change_base_price = float(h.get("value"))
                            break
                    if change_base_price is None and f_hist:
                        if len(f_hist) >= 2:
                            change_base_price = float(f_hist[-2].get("value"))
                        else:
                            change_base_price = float(f_hist[-1].get("value"))

                # Load history from existing_item or local file
                history = []
                night_path = os.path.join(os.path.dirname(__file__), "data", "kospif_ngt_history.json")
                if os.path.exists(night_path):
                    try:
                        with open(night_path, "r", encoding="utf-8") as f:
                            raw_file_hist = json.load(f)
                            for item in raw_file_hist:
                                d = item.get("date")
                                p = item.get("price")
                                if d and p is not None:
                                    history.append({"date": d, "value": round(float(p), 2)})
                    except Exception:
                        pass

                if not history and existing_item and "history" in existing_item:
                    history = list(existing_item["history"])

                # Determine fallback change_base_price if still None
                if change_base_price is None:
                    if len(history) >= 2:
                        change_base_price = history[-2]["value"]
                    elif history:
                        change_base_price = history[-1]["value"]
                    else:
                        change_base_price = open_p

                # Update history with current session
                if history:
                    last_hist_date = history[-1]["date"]
                    if session_end_date > last_hist_date:
                        history.append({"date": session_end_date, "value": round(close_p, 2)})
                    elif session_end_date == last_hist_date:
                        history[-1]["value"] = round(close_p, 2)
                else:
                    history.append({"date": session_end_date, "value": round(close_p, 2)})

                history = history[-200:]

                # Save updated point back to file if possible
                if os.path.exists(night_path):
                    try:
                        with open(night_path, "r", encoding="utf-8") as f:
                            file_data = json.load(f)
                        f_dates = {x["date"]: x for x in file_data}
                        if session_end_date in f_dates:
                            f_dates[session_end_date]["price"] = round(close_p, 2)
                        else:
                            file_data.append({"date": session_end_date, "price": round(close_p, 2)})
                        file_data.sort(key=lambda x: x["date"])
                        file_data = file_data[-200:]
                        with open(night_path, "w", encoding="utf-8") as f:
                            json.dump(file_data, f, indent=4, ensure_ascii=False)
                    except Exception:
                        pass

                night_change = round(close_p - change_base_price, 2)
                night_pct = round((night_change / change_base_price) * 100, 2) if change_base_price else 0.0

                meta = INDICATORS_META.get("KOSPI200_NIGHT", {})
                result_item = {
                    "ticker": "KOSPI200_NIGHT",
                    "name": meta.get("name", "KOSPI200 야간 선물 지수"),
                    "price": round(close_p, 2),
                    "change_amt": night_change,
                    "change_percent": night_pct,
                    "open": round(open_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "close": round(close_p, 2),
                    "history": history,
                    "negative_favorable": meta.get("negative_favorable", False),
                    "is_integer_only": False,
                    "is_percent": False
                }

                # Update krx_cache.json in background so cache file stays fresh
                try:
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    cache_path = os.path.join(script_dir, "krx_cache.json")
                    if os.path.exists(cache_path):
                        with open(cache_path, "r", encoding="utf-8") as f:
                            c_data = json.load(f)
                        if isinstance(c_data, dict):
                            hist_iso = [{"date": f"{h['date']}T00:00:00.000Z", "value": h['value']} for h in history]
                            c_data["kospi200_night"] = {
                                "price": round(close_p, 2),
                                "changeAmt": night_change,
                                "changePercent": night_pct,
                                "open": round(open_p, 2),
                                "high": round(high_p, 2),
                                "low": round(low_p, 2),
                                "close": round(close_p, 2),
                                "history": hist_iso
                            }
                            with open(cache_path, "w", encoding="utf-8") as f:
                                json.dump(c_data, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

                return result_item
    except Exception as e:
        print(f"Error in fetch_kospi200_night_direct: {e}")

    return existing_item

def is_valid_num(val):
    if val is None:
        return False
    try:
        f = float(val)
        return not (math.isnan(f) or math.isinf(f))
    except (ValueError, TypeError):
        return False

def fetch_yahoo_bulk(tickers):
    """
    Fetch real-time quotes and daily OHLCV history for multiple tickers via yfinance.
    Uses ThreadPoolExecutor to fetch real-time fast_info and history_metadata in parallel,
    ensuring that the latest trading session (e.g. Friday close or live session) is never
    dropped even if Yahoo Finance's daily candle table has null/NaN in Close.
    """
    results = {}
    if not tickers:
        return results

    # 1. Fetch live quotes and session metadata in parallel (fast, ~2 seconds for 30 tickers)
    def fetch_live_info(sym):
        try:
            t = yf.Ticker(sym)
            meta = t.get_history_metadata() or {}
            fi = t.fast_info
            
            # Prioritize official regularMarketPrice from meta, then fast_info lastPrice
            lp = meta.get("regularMarketPrice")
            if not is_valid_num(lp):
                lp = fi.get("lastPrice")
            if not is_valid_num(lp):
                lp = None

            # Official Previous Close:
            # 1. meta previousClose
            # 2. fast_info regularMarketPreviousClose (for equities/ETFs/indices)
            # 3. fast_info previousClose (for crypto, forex, commodities where regularMarketPreviousClose is NaN)
            pc = meta.get("previousClose")
            if not is_valid_num(pc):
                pc = fi.get("regularMarketPreviousClose")
            if not is_valid_num(pc):
                pc = fi.get("previousClose")
            if not is_valid_num(pc):
                pc = None

            ypct = meta.get("regularMarketChangePercent")
            if not is_valid_num(ypct):
                ypct = None

            op = fi.get("open")
            if not is_valid_num(op):
                op = None
            hi = meta.get("regularMarketDayHigh") or fi.get("dayHigh")
            if not is_valid_num(hi):
                hi = None
            lo = meta.get("regularMarketDayLow") or fi.get("dayLow")
            if not is_valid_num(lo):
                lo = None
            tz_name = fi.timezone or meta.get("exchangeTimezoneName") or "America/New_York"

            rmt = meta.get("regularMarketTime")
            t_date = None
            if rmt:
                try:
                    t_date = datetime.fromtimestamp(rmt, pytz.timezone(tz_name)).strftime("%Y-%m-%d")
                except Exception:
                    pass
            return sym, {
                "price": lp,
                "prev_close": pc,
                "yahoo_pct": ypct,
                "open": op,
                "high": hi,
                "low": lo,
                "trade_date": t_date,
                "tz_name": tz_name
            }
        except Exception:
            return sym, None

    max_workers = min(16, len(tickers))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        live_infos = dict(ex.map(fetch_live_info, tickers))

    # 2. Bulk download 1-year historical daily candles
    try:
        df = yf.download(tickers, period="1y", interval="1d", group_by="ticker", progress=False, threads=True)
    except Exception as e:
        print(f"Error in yf.download: {e}")
        df = pd.DataFrame()

    is_multi = isinstance(df.columns, pd.MultiIndex)

    for ticker in tickers:
        try:
            live = live_infos.get(ticker)
            tdf = pd.DataFrame()
            candle_last_date = None
            if not df.empty:
                if is_multi:
                    if ticker in df.columns.levels[0]:
                        raw_tdf = df[ticker]
                        if not raw_tdf.empty:
                            candle_last_date = raw_tdf.index[-1].strftime("%Y-%m-%d")
                        tdf = raw_tdf.dropna(subset=["Close"])
                else:
                    if not df.empty:
                        candle_last_date = df.index[-1].strftime("%Y-%m-%d")
                    tdf = df.dropna(subset=["Close"])

            history = []
            if not tdf.empty:
                history = [
                    {"date": idx.strftime("%Y-%m-%d"), "value": round(float(row["Close"]), 4)}
                    for idx, row in tdf.iterrows()
                    if is_valid_num(row.get("Close"))
                ]

            price = None
            prev_close = None
            open_val = None
            high_val = None
            low_val = None

            last_hist_date = history[-1]["date"] if history else None

            tz_name = (live.get("tz_name") if live else None) or ("Asia/Tokyo" if ticker.endswith(".T") else "America/New_York")
            try:
                today_exchange = datetime.now(pytz.timezone(tz_name)).strftime("%Y-%m-%d")
            except Exception:
                today_exchange = datetime.now().strftime("%Y-%m-%d")

            live_date = live.get("trade_date") if live else None
            effective_date = live_date or candle_last_date or today_exchange

            # Integrate live session info if available
            if live and is_valid_num(live.get("price")):
                live_price = float(live["price"])
                live_prev = float(live["prev_close"]) if is_valid_num(live.get("prev_close")) else None

                hist_fallback_prev = None
                if len(history) >= 2 and is_valid_num(history[-2].get("value")):
                    hist_fallback_prev = float(history[-2]["value"])
                elif history and is_valid_num(history[-1].get("value")):
                    hist_fallback_prev = float(history[-1]["value"])

                price = live_price
                prev_close = live_prev if live_prev is not None else hist_fallback_prev
                open_val = float(live["open"]) if is_valid_num(live.get("open")) else price
                high_val = float(live["high"]) if is_valid_num(live.get("high")) else max(live_price, open_val)
                low_val = float(live["low"]) if is_valid_num(live.get("low")) else min(live_price, open_val)

                if history:
                    if effective_date > last_hist_date:
                        history.append({"date": effective_date, "value": round(live_price, 4)})
                    elif effective_date == last_hist_date:
                        history[-1]["value"] = round(live_price, 4)
                    else:
                        history[-1]["value"] = round(live_price, 4)
                else:
                    history = [{"date": effective_date, "value": round(live_price, 4)}]

            # Fallback to historical daily candle if live price is not available
            if (not is_valid_num(price)) and len(tdf) >= 2:
                latest_row = tdf.iloc[-1]
                prev_row = tdf.iloc[-2]
                if is_valid_num(latest_row["Close"]):
                    price = float(latest_row["Close"])
                    prev_close = float(prev_row["Close"]) if is_valid_num(prev_row["Close"]) else None
                    open_val = float(latest_row["Open"]) if "Open" in latest_row and is_valid_num(latest_row["Open"]) else price
                    high_val = float(latest_row["High"]) if "High" in latest_row and is_valid_num(latest_row["High"]) else price
                    low_val = float(latest_row["Low"]) if "Low" in latest_row and is_valid_num(latest_row["Low"]) else price

            if not is_valid_num(price):
                continue

            if is_valid_num(prev_close) and prev_close != 0:
                change_amt = round(price - prev_close, 2)
                if live and is_valid_num(live.get("yahoo_pct")):
                    change_pct = round(float(live["yahoo_pct"]), 2)
                else:
                    change_pct = round((change_amt / prev_close) * 100, 2)
            else:
                change_amt = 0.0
                change_pct = 0.0

            final_trade_date = effective_date or (history[-1]["date"] if history else None)

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
                "close": price,
                "history": history[-200:],
                "negative_favorable": meta.get("negative_favorable", False),
                "is_integer_only": ticker in INTEGER_ONLY_TICKERS,
                "is_percent": meta.get("is_percent", False),
                "trade_date": final_trade_date
            }
        except Exception as item_err:
            print(f"Error parsing Yahoo data for {ticker}: {item_err}")

    return results

def fetch_all_market_data(force_refresh=False, wait_for_krx=False):
    """Fetch and aggregate all indicators across US, K-Market, and Semiconductor tabs."""
    all_data = {}

    # 1. KRX Cache Data (provides KOFIA deposits/credit/margin_call, Night Futures, PER, PBR, ADR)
    krx_data = get_krx_cache_data(force_update=force_refresh, wait=wait_for_krx)
    all_data.update(krx_data)

    # 2. CNN Fear & Greed
    fg_data = get_fear_and_greed()
    if fg_data:
        all_data["FEAR_GREED"] = fg_data

    # 3. Korean stocks, indices, and KOSPI200 Futures via Naver Mobile API (live) & VKOSPI via KRX MDC
    korean_tickers = [
        "005930.KS", "009150.KS", "402340.KS", "000660.KS",
        "^KS11", "^KQ11", "KOSPI200_FUTURES"
    ]
    with ThreadPoolExecutor(max_workers=8) as executor:
        fut_naver = executor.map(fetch_naver_price, korean_tickers)
        fut_vkospi = executor.submit(fetch_vkospi_direct, all_data.get("VKOSPI"))
        naver_results = list(fut_naver)
        try:
            vk_item = fut_vkospi.result(timeout=12.0)
        except Exception:
            vk_item = all_data.get("VKOSPI")

    for item in naver_results:
        if item:
            all_data[item["ticker"]] = item

    if vk_item:
        all_data["VKOSPI"] = vk_item

    # 3b. Compute KOSPI RSI dynamically from live KOSPI (^KS11) daily close history
    ks11_item = all_data.get("^KS11")
    if ks11_item:
        rsi_item = compute_kospi_rsi(ks11_item)
        if rsi_item:
            all_data["KOSPI_RSI"] = rsi_item

    # 3c. Fetch KOSPI Trade Value dynamically (Daum -> Naver -> KRX)
    tv_item = fetch_kospi_trade_value(all_data.get("KOSPI_TRADE_VALUE"))
    if tv_item:
        all_data["KOSPI_TRADE_VALUE"] = tv_item

    # 3d. Compute KOSPI ADR dynamically from local history & Naver integration
    adr_item = compute_kospi_adr(all_data.get("ADR_INFO"))
    if adr_item:
        all_data["ADR_INFO"] = adr_item

    # 3e. Fetch KOSPI200 Night Futures dynamically from eSignal API
    night_item = fetch_kospi200_night_direct(
        existing_item=all_data.get("KOSPI200_NIGHT"),
        futures_item=all_data.get("KOSPI200_FUTURES")
    )
    if night_item:
        all_data["KOSPI200_NIGHT"] = night_item

    # 4. Determine remaining tickers to query from Yahoo Finance
    # 한국 종목 및 지수는 yfinance 왜곡(팬텀 스플릿, 호가 딜레이) 방지를 위해 Yahoo Finance 조회에서 영구 배제
    korean_excluded = {
        "005930.KS", "009150.KS", "402340.KS", "000660.KS",
        "^KS11", "^KQ11", "KOSPI200_FUTURES"
    }
    all_meta_tickers = list(INDICATORS_META.keys())
    excluded = set(all_data.keys()) | {"FEAR_GREED"} | korean_excluded
    yahoo_tickers = [t for t in all_meta_tickers if t not in excluded]

    # Fetch Yahoo data in bulk
    yahoo_data = fetch_yahoo_bulk(yahoo_tickers)
    all_data.update(yahoo_data)

    return all_data
