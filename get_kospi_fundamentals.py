import os
import sys
import json
import time
from datetime import datetime, timedelta
import concurrent.futures
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from dotenv import load_dotenv
import ssl

# Workaround for SSLEOFError on KRX server (fixes legacy TLS negotiation with Python 3.10+ / OpenSSL 3.0+)
try:
    orig_create_default_context = ssl.create_default_context
    def custom_create_default_context(*args, **kwargs):
        ctx = orig_create_default_context(*args, **kwargs)
        ctx.options |= 0x4  # ssl.OP_LEGACY_SERVER_CONNECT
        return ctx
    ssl.create_default_context = custom_create_default_context
except Exception:
    pass

# Load KRX environment variables
# Load from workspace root .env first, then fallback to D:\AI Investing\KRXdata\.env
load_dotenv()
krx_env_path = r"D:\AI Investing\KRXdata\.env"
if os.path.exists(krx_env_path):
    load_dotenv(krx_env_path)

try:
    from pykrx import stock
    from pykrx.website.krx.krxio import KrxWebIo
except ImportError:
    print(json.dumps({"error": "pykrx is not installed"}))
    sys.exit(1)

if "--batch" in sys.argv:
    # Silence stdout but keep stderr for error logging
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')


def format_iso_date(date_str):
    # Convert 'YYYY-MM-DD' or datetime to 'YYYY-MM-DDT00:00:00.000Z'
    if isinstance(date_str, str):
        clean_date = date_str.replace('/', '-')
        dt = datetime.strptime(clean_date, "%Y-%m-%d")
    else:
        dt = date_str
    return dt.strftime("%Y-%m-%dT00:00:00.000Z")

def fetch_page(page, headers):
    url = f"https://finance.naver.com/sise/sise_index_day.naver?code=FUT&page={page}"
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return res.content
    except Exception:
        pass
    return None

def get_naver_futures():
    data_list = []
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 1. Scrape history in parallel (11 pages)
    pages = list(range(1, 12))
    with concurrent.futures.ThreadPoolExecutor(max_workers=11) as executor:
        contents = list(executor.map(lambda p: fetch_page(p, headers), pages))
        
    for content in contents:
        if not content:
            continue
        try:
            soup = BeautifulSoup(content.decode("euc-kr", "replace"), "html.parser")
            table = soup.find("table", class_="type_1")
            if not table:
                continue
            rows = table.find_all("tr")
            for r in rows:
                cols = r.find_all("td")
                if len(cols) >= 6:
                    date_str = cols[0].text.strip()
                    if not date_str or "." not in date_str:
                        continue
                    close_str = cols[1].text.strip().replace(",", "")
                    try:
                        date_obj = datetime.strptime(date_str, "%Y.%m.%d")
                        close_val = float(close_str)
                        data_list.append({"Date": date_obj, "Close": close_val})
                    except Exception:
                        pass
        except Exception:
            pass
            
    if not data_list:
        return None
        
    df = pd.DataFrame(data_list)
    df = df.drop_duplicates(subset=["Date"])
    df = df.set_index("Date")
    df = df.sort_index()
    
    # 2. Scrape current quote details
    open_val = None
    high_val = None
    low_val = None
    price_val = None
    change_val = None
    pct_val = None
    quote_date_str = None
    
    try:
        url_curr = "https://finance.naver.com/sise/sise_index.naver?code=FUT"
        res_curr = requests.get(url_curr, headers=headers, timeout=5)
        if res_curr.status_code == 200:
            soup_curr = BeautifulSoup(res_curr.content, "html.parser", from_encoding="euc-kr")
            
            # Parse quote date from time span
            time_span = soup_curr.find("span", id="time")
            if time_span:
                time_text = time_span.get_text()
                match = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", time_text)
                if match:
                    quote_date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
            
            for tr in soup_curr.find_all("tr"):
                cells = tr.find_all(["th", "td"])
                texts = [c.get_text(strip=True) for c in cells]
                for idx, text in enumerate(texts):
                    if "선물(" in text:
                        price_val = float(texts[idx+1].replace(",", ""))
                    elif "시가" in text:
                        open_val = float(texts[idx+1].replace(",", ""))
                    elif "전일대비" in text:
                        val_str = "".join(c for c in texts[idx+1] if c.isdigit() or c == ".")
                        if val_str:
                            change_val = float(val_str)
                            # Fixed down arrow character check: '▼' and '↓' indicate a negative change
                            if "-" in texts[idx+1] or "하락" in texts[idx+1] or "▼" in texts[idx+1] or "↓" in texts[idx+1]:
                                change_val = -change_val
                    elif "고가" in text:
                        high_val = float(texts[idx+1].replace(",", ""))
                    elif "저가" in text:
                        low_val = float(texts[idx+1].replace(",", ""))
                    elif "등락률" in text:
                        pct_str = texts[idx+1].replace("%", "").strip()
                        pct_val = float(pct_str)
    except Exception:
        pass
        
    # fallback to latest historical if current quote fails
    latest_hist_date = df.index[-1]
    latest_hist_close = float(df["Close"].iloc[-1])
    
    if price_val is None:
        price_val = latest_hist_close
    if open_val is None:
        open_val = price_val
    if high_val is None:
        high_val = price_val
    if low_val is None:
        low_val = price_val
        
    if change_val is None or pct_val is None:
        if len(df) >= 2:
            prev_close = float(df["Close"].iloc[-2])
            change_val = price_val - prev_close
            pct_val = (change_val / prev_close) * 100 if prev_close != 0 else 0.0
            
    latest_hist_str = latest_hist_date.strftime("%Y-%m-%d")
    
    df_60 = df.tail(60)
    history_list = [{"date": dt.strftime("%Y-%m-%dT00:00:00.000Z"), "value": round(float(row["Close"]), 2)} for dt, row in df_60.iterrows()]
    
    # Fallback quote_date_str if none parsed (only on weekdays after 9am)
    if quote_date_str is None:
        now = datetime.now()
        if now.weekday() < 5 and now.hour >= 9:
            quote_date_str = now.strftime("%Y-%m-%d")
        else:
            quote_date_str = latest_hist_str

    # Decide whether to append or update history
    if quote_date_str > latest_hist_str:
        history_list.append({
            "date": datetime.strptime(quote_date_str, "%Y-%m-%d").strftime("%Y-%m-%dT00:00:00.000Z"),
            "value": price_val
        })
        if len(history_list) > 60:
            history_list = history_list[-60:]
    elif quote_date_str == latest_hist_str:
        if history_list:
            history_list[-1]["value"] = price_val
            
    return {
        "price": price_val,
        "changeAmt": change_val,
        "changePercent": pct_val,
        "open": open_val,
        "high": high_val,
        "low": low_val,
        "close": price_val,
        "history": history_list
    }

def fetch_kofia_deposits_credit(start_date, end_date):
    url = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Referer": "https://freesis.kofia.or.kr/stat/FreeSIS.do",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    deposit_map = {}
    payload_dep = {
        "dmSearch": {
            "tmpV40": "1000000",
            "tmpV41": "1",
            "tmpV1": "D",
            "tmpV45": start_date,
            "tmpV46": end_date,
            "OBJ_NM": "STATSCU0100000060BO"
        }
    }
    try:
        res_dep = requests.post(url, headers=headers, json=payload_dep, timeout=5)
        if res_dep.status_code == 200:
            items = res_dep.json().get("ds1", [])
            for item in items:
                date_raw = str(item.get("TMPV1"))
                if len(date_raw) == 8:
                    date_str = f"{date_raw[0:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
                    val = float(item.get("TMPV2", 0)) * 0.01
                    deposit_map[date_str] = round(val, 2)
    except Exception as e:
        print(f"Error fetching KOFIA deposits: {e}", file=sys.stderr)
                
    credit_map = {}
    payload_cred = {
        "dmSearch": {
            "tmpV40": "1000000",
            "tmpV41": "1",
            "tmpV1": "D",
            "tmpV45": start_date,
            "tmpV46": end_date,
            "OBJ_NM": "STATSCU0100000070BO"
        }
    }
    try:
        res_cred = requests.post(url, headers=headers, json=payload_cred, timeout=5)
        if res_cred.status_code == 200:
            items = res_cred.json().get("ds1", [])
            for item in items:
                date_raw = str(item.get("TMPV1"))
                if len(date_raw) == 8:
                    date_str = f"{date_raw[0:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
                    val = float(item.get("TMPV2", 0)) * 0.01
                    credit_map[date_str] = round(val, 2)
    except Exception as e:
        print(f"Error fetching KOFIA credit: {e}", file=sys.stderr)
                
    return deposit_map, credit_map

def fetch_kofia_liquidation(start_date, end_date):
    url = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Referer": "https://freesis.kofia.or.kr/stat/FreeSIS.do",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    liq_map = {}
    payload = {
        "dmSearch": {
            "tmpV40": "1000000",
            "tmpV41": "1",
            "tmpV1": "D",
            "tmpV45": start_date,
            "tmpV46": end_date,
            "OBJ_NM": "STATSCU0100000060BO"
        }
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=5)
        if res.status_code == 200:
            items = res.json().get("ds1", [])
            for item in items:
                date_raw = str(item.get("TMPV1"))
                if len(date_raw) == 8:
                    date_str = f"{date_raw[0:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
                    val = float(item.get("TMPV6", 0)) * 0.01
                    liq_map[date_str] = round(val, 2)
    except Exception as e:
        print(f"Error fetching KOFIA liquidation: {e}", file=sys.stderr)
    return liq_map

def task_kofia_preload():
    try:
        today_k = datetime.now()
        start_date_k = (today_k - timedelta(days=15)).strftime("%Y%m%d")
        end_date_k = today_k.strftime("%Y%m%d")
        
        # Fetch deposits & credit
        deposit_map, credit_map = fetch_kofia_deposits_credit(start_date_k, end_date_k)
        dep_path = r"D:\AI Investing\Daily_Check_K\deposits_history.json"
        if os.path.exists(dep_path):
            with open(dep_path, "r", encoding="utf-8") as f:
                dep_history = json.load(f)
            hist_map = {item['date']: item for item in dep_history}
            common_dates = set(deposit_map.keys()) & set(credit_map.keys())
            for d_str in common_dates:
                hist_map[d_str] = {
                    'date': d_str,
                    'deposit': deposit_map[d_str],
                    'credit': credit_map[d_str]
                }
            new_dep_history = list(hist_map.values())
            new_dep_history.sort(key=lambda x: x['date'])
            new_dep_history = new_dep_history[-100:]
            with open(dep_path, "w", encoding="utf-8") as f:
                json.dump(new_dep_history, f, indent=4)
        
        # Fetch liquidation
        liq_map = fetch_kofia_liquidation(start_date_k, end_date_k)
        liq_path = r"D:\AI Investing\Daily_Check_K\liquidation_history.json"
        if os.path.exists(liq_path):
            with open(liq_path, "r", encoding="utf-8") as f:
                liq_history = json.load(f)
            hist_map_liq = {item['date']: item['liquidation'] for item in liq_history}
            for d_str, val in liq_map.items():
                hist_map_liq[d_str] = val
            new_liq_history = [{"date": d, "liquidation": v} for d, v in hist_map_liq.items()]
            new_liq_history.sort(key=lambda x: x['date'])
            new_liq_history = new_liq_history[-100:]
            with open(liq_path, "w", encoding="utf-8") as f:
                json.dump(new_liq_history, f, indent=4)
    except Exception as kofia_err:
        print(f"Error updating KOFIA data in background scraper: {kofia_err}", file=sys.stderr)

def task_fundamentals(start_date, end_date):
    result = {}
    try:
        df_fund = stock.get_index_fundamental(start_date, end_date, "1001")
        if df_fund is not None and not df_fund.empty:
            df_fund_filtered = df_fund[(df_fund['PER'] != 0) & (df_fund['PBR'] != 0)].copy()
            if len(df_fund_filtered) >= 2:
                df_fund_60 = df_fund_filtered.tail(60)
                
                # PER
                per_history = [{"date": format_iso_date(dt), "value": round(float(row['PER']), 2)} for dt, row in df_fund_60.iterrows()]
                latest_per = round(float(df_fund_filtered['PER'].iloc[-1]), 2)
                prev_per = round(float(df_fund_filtered['PER'].iloc[-2]), 2)
                per_change = round(latest_per - prev_per, 2)
                per_pct = round((per_change / prev_per) * 100, 2) if prev_per != 0 else 0.0
                
                result["per"] = {
                    "price": latest_per,
                    "changeAmt": per_change,
                    "changePercent": per_pct,
                    "history": per_history
                }
                
                # PBR
                pbr_history = [{"date": format_iso_date(dt), "value": round(float(row['PBR']), 2)} for dt, row in df_fund_60.iterrows()]
                latest_pbr = round(float(df_fund_filtered['PBR'].iloc[-1]), 2)
                prev_pbr = round(float(df_fund_filtered['PBR'].iloc[-2]), 2)
                pbr_change = round(latest_pbr - prev_pbr, 2)
                pbr_pct = round((pbr_change / prev_pbr) * 100, 2) if prev_pbr != 0 else 0.0
                
                result["pbr"] = {
                    "price": latest_pbr,
                    "changeAmt": pbr_change,
                    "changePercent": pbr_pct,
                    "history": pbr_history
                }
    except Exception as e:
        print(f"Error in task_fundamentals: {e}", file=sys.stderr)
    return result

class KrxMdc(KrxWebIo):
    @property
    def bld(self):
        return 'dbms/MDC/STAT/standard/MDCSTAT01201'

def task_vkospi(start_date, end_date):
    result = {}
    try:
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
            close_p = price
            
            chronological = list(reversed(output))[-60:]
            history = [
                {
                    "date": format_iso_date(row['TRD_DD']),
                    "value": round(float(str(row['CLSPRC_IDX']).replace(',', '')), 2)
                }
                for row in chronological
            ]
            
            result["vkospi"] = {
                "price": price,
                "changeAmt": change,
                "changePercent": pct,
                "history": history,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p
            }
    except Exception as e:
        print(f"Error in task_vkospi: {e}", file=sys.stderr)
    return result

def task_ohlcv_rsi(start_date, end_date):
    result = {}
    try:
        data_list = []
        headers = {"User-Agent": "Mozilla/5.0"}
        
        s_dt = datetime.strptime(start_date, "%Y%m%d")
        e_dt = datetime.strptime(end_date, "%Y%m%d")
        
        def fetch_naver_page(page):
            url = f"https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI&page={page}"
            try:
                res = requests.get(url, headers=headers, timeout=5)
                if res.status_code == 200:
                    return res.content
            except Exception:
                pass
            return None
            
        pages = list(range(1, 16))
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            contents = list(executor.map(fetch_naver_page, pages))
            
        for content in contents:
            if not content:
                continue
            try:
                soup = BeautifulSoup(content.decode("euc-kr", "replace"), "html.parser")
                table = soup.find("table", class_="type_1")
                if not table:
                    continue
                rows = table.find_all("tr")
                for r in rows:
                    cols = r.find_all("td")
                    if len(cols) >= 6:
                        date_str = cols[0].text.strip()
                        if not date_str or "." not in date_str:
                            continue
                        
                        try:
                            date_obj = datetime.strptime(date_str, "%Y.%m.%d")
                            if not (s_dt <= date_obj <= e_dt):
                                continue
                                
                            close_val = float(cols[1].text.strip().replace(",", ""))
                            value_val = float(cols[5].text.strip().replace(",", ""))
                            
                            data_list.append({
                                "Date": date_obj,
                                "Close": close_val,
                                "Value": value_val
                            })
                        except Exception:
                            pass
            except Exception:
                pass
                
        if not data_list:
            raise ValueError("No KOSPI data scraped from Naver Finance")
            
        df = pd.DataFrame(data_list)
        df = df.drop_duplicates(subset=["Date"])
        df = df.set_index("Date")
        df = df.sort_index()
        
        val_series = df["Value"] / 100
        val_series = val_series[val_series > 0].copy()
        
        if len(val_series) >= 2:
            val_60 = val_series.tail(60)
            history_val = [{"date": format_iso_date(dt), "value": round(float(val), 2)} for dt, val in val_60.items()]
            latest_val = round(float(val_series.iloc[-1]), 2)
            prev_val = round(float(val_series.iloc[-2]), 2)
            val_change = round(latest_val - prev_val, 2)
            val_pct = round((val_change / prev_val) * 100, 2) if prev_val != 0 else 0.0
            
            result["kospi_trade_value"] = {
                "price": latest_val,
                "changeAmt": val_change,
                "changePercent": val_pct,
                "history": history_val
            }
            
        close_series = df["Close"].copy()
        if len(close_series) >= 15:
            delta = close_series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_series = 100 - (100 / (1 + rs))
            rsi_series = rsi_series.dropna()
            
            if len(rsi_series) >= 2:
                rsi_60 = rsi_series.tail(60)
                history_rsi = [{"date": format_iso_date(dt), "value": round(float(val), 2)} for dt, val in rsi_60.items()]
                latest_rsi = round(float(rsi_series.iloc[-1]), 2)
                prev_rsi = round(float(rsi_series.iloc[-2]), 2)
                rsi_change = round(latest_rsi - prev_rsi, 2)
                rsi_pct = round((rsi_change / prev_rsi) * 100, 2) if prev_rsi != 0 else 0.0
                
                result["kospi_rsi"] = {
                    "price": latest_rsi,
                    "changeAmt": rsi_change,
                    "changePercent": rsi_pct,
                    "history": history_rsi
                }
    except Exception as e:
        print(f"Error in task_ohlcv_rsi: {e}", file=sys.stderr)
    return result

def task_local_kofia_adr():
    result = {}
    try:
        # Read Customer Deposits & Credit Balance
        dep_path = r"D:\AI Investing\Daily_Check_K\deposits_history.json"
        if os.path.exists(dep_path):
            with open(dep_path, "r", encoding="utf-8") as f:
                dep_data = json.load(f)
            if dep_data and len(dep_data) >= 2:
                dep_60 = dep_data[-60:]
                
                # Customer Deposits
                dep_history = [{"date": format_iso_date(item['date']), "value": round(float(item['deposit']), 2)} for item in dep_60]
                latest_dep = round(float(dep_data[-1]['deposit']), 2)
                prev_dep = round(float(dep_data[-2]['deposit']), 2)
                dep_change = round(latest_dep - prev_dep, 2)
                dep_pct = round((dep_change / prev_dep) * 100, 2) if prev_dep != 0 else 0.0
                
                result["customer_deposits"] = {
                    "price": latest_dep,
                    "changeAmt": dep_change,
                    "changePercent": dep_pct,
                    "history": dep_history
                }
                
                # Credit Balance
                cred_history = [{"date": format_iso_date(item['date']), "value": round(float(item['credit']), 2)} for item in dep_60]
                latest_cred = round(float(dep_data[-1]['credit']), 2)
                prev_cred = round(float(dep_data[-2]['credit']), 2)
                cred_change = round(latest_cred - prev_cred, 2)
                cred_pct = round((cred_change / prev_cred) * 100, 2) if prev_cred != 0 else 0.0
                
                result["credit_balance"] = {
                    "price": latest_cred,
                    "changeAmt": cred_change,
                    "changePercent": cred_pct,
                    "history": cred_history
                }

        # Read Margin Call / Liquidation Amount
        liq_path = r"D:\AI Investing\Daily_Check_K\liquidation_history.json"
        if os.path.exists(liq_path):
            with open(liq_path, "r", encoding="utf-8") as f:
                liq_data = json.load(f)
            if liq_data and len(liq_data) >= 2:
                liq_60 = liq_data[-60:]
                liq_history = [{"date": format_iso_date(item['date']), "value": round(float(item['liquidation']), 2)} for item in liq_60]
                latest_liq = round(float(liq_data[-1]['liquidation']), 2)
                prev_liq = round(float(liq_data[-2]['liquidation']), 2)
                liq_change = round(latest_liq - prev_liq, 2)
                liq_pct = round((liq_change / prev_liq) * 100, 2) if prev_liq != 0 else 0.0
                
                result["margin_call"] = {
                    "price": latest_liq,
                    "changeAmt": liq_change,
                    "changePercent": liq_pct,
                    "history": liq_history
                }

        # Read & Compute KOSPI ADR(20, %)
        adr_path = r"D:\AI Investing\Daily_Check_K\adv_dec_history.json"
        
        # Scrape and update today's KOSPI advance/decline counts first to ensure we have the latest ADR
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            url = 'https://finance.naver.com/sise/sise_index.naver?code=KOSPI'
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
                
                # 1. Parse date from span id="time"
                time_span = soup.find('span', id='time')
                parsed_date = None
                if time_span:
                    text = time_span.text.strip()
                    match = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', text)
                    if match:
                        parsed_date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                
                # 2. Parse rise/fall counts
                subtop = soup.find('div', class_='subtop_sise_detail')
                if subtop and parsed_date:
                    tbl = subtop.find('table', class_='table_kos_index')
                    if tbl:
                        lst_sh = tbl.find('li', class_='lst')
                        lst_ss = tbl.find('li', class_='lst2')
                        lst_hr = tbl.find('li', class_='lst4')
                        lst_hh = tbl.find('li', class_='lst5')
                        
                        sanghan = int(lst_sh.find('a').find('span').text.replace(',', '')) if lst_sh else 0
                        sangseung = int(lst_ss.find('a').find('span').text.replace(',', '')) if lst_ss else 0
                        harak = int(lst_hr.find('a').find('span').text.replace(',', '')) if lst_hr else 0
                        hahan = int(lst_hh.find('a').find('span').text.replace(',', '')) if lst_hh else 0
                        
                        adv = sanghan + sangseung
                        dec = harak + hahan
                        
                        if adv != 0 or dec != 0:
                            history = []
                            if os.path.exists(adr_path):
                                with open(adr_path, "r", encoding="utf-8") as f:
                                    history = json.load(f)
                            
                            found = False
                            for item in history:
                                if item['date'] == parsed_date:
                                    item['adv'] = adv
                                    item['dec'] = dec
                                    found = True
                                    break
                            
                            if not found:
                                history.append({'date': parsed_date, 'adv': adv, 'dec': dec})
                            
                            history.sort(key=lambda x: x['date'])
                            history = history[-100:]
                            with open(adr_path, "w", encoding="utf-8") as f:
                                json.dump(history, f, indent=4)
        except Exception as adr_up_err:
            print(f"Error updating ADR history in scraper: {adr_up_err}", file=sys.stderr)

        if os.path.exists(adr_path):
            with open(adr_path, "r", encoding="utf-8") as f:
                adr_data = json.load(f)
            if adr_data and len(adr_data) >= 20:
                adr_computed = []
                for i in range(len(adr_data)):
                    if i < 19:
                        continue
                    recent_20 = adr_data[i-19 : i+1]
                    sum_adv = sum(item['adv'] for item in recent_20)
                    sum_dec = sum(item['dec'] for item in recent_20)
                    val = (sum_adv / sum_dec) * 100 if sum_dec != 0 else 0.0
                    adr_computed.append({
                        "date": adr_data[i]['date'],
                        "value": round(val, 2)
                    })
                if len(adr_computed) >= 2:
                    adr_60 = adr_computed[-60:]
                    adr_history = [{"date": format_iso_date(item['date']), "value": item['value']} for item in adr_60]
                    latest_adr = adr_computed[-1]['value']
                    prev_adr = adr_computed[-2]['value']
                    adr_change = round(latest_adr - prev_adr, 2)
                    adr_pct = round((adr_change / prev_adr) * 100, 2) if prev_adr != 0 else 0.0
                    
                    result["kospi_adr"] = {
                        "price": latest_adr,
                        "changeAmt": adr_change,
                        "changePercent": adr_pct,
                        "history": adr_history
                    }
    except Exception as e:
        print(f"Error in task_local_kofia_adr: {e}", file=sys.stderr)
    return result

def task_night_futures(futures_price_ref):
    result = {}
    try:
        night_path = r"D:\AI Investing\Daily_Check\DailyData\kospif_ngt_history.json"
        if os.path.exists(night_path):
            with open(night_path, "r", encoding="utf-8") as f:
                night_data = json.load(f)
            if night_data and len(night_data) >= 2:
                latest_night_from_file = round(float(night_data[-1]['price']), 2)
                
                open_p = latest_night_from_file
                high_p = latest_night_from_file
                low_p = latest_night_from_file
                close_p = latest_night_from_file
                has_live = False
                pts = []
                
                try:
                    cache_url = "https://esignal.co.kr/data/cache/kospif_ngt.js"
                    cache_headers = {
                        'User-Agent': 'Mozilla/5.0',
                        'Referer': 'https://esignal.co.kr/kospi200-futures-night/'
                    }
                    r_cache = requests.get(cache_url, headers=cache_headers, timeout=5)
                    if r_cache.status_code == 200:
                        cache_json = r_cache.json()
                        open_p = float(cache_json.get('open', latest_night_from_file))
                        pts = cache_json.get('data', [])
                        if len(pts) > 0:
                            prices = [float(pt[1]) for pt in pts]
                            high_p = max(prices)
                            low_p = min(prices)
                            close_p = prices[-1]
                            has_live = True
                except Exception:
                    pass

                session_date_str = None
                if has_live and len(pts) > 0:
                    try:
                        from datetime import timezone
                        ts = pts[-1][0] / 1000.0
                        dt_kst = datetime.fromtimestamp(ts, timezone(timedelta(hours=9)))
                        session_date_str = dt_kst.strftime("%Y-%m-%d")
                    except Exception:
                        pass

                last_hist_date = night_data[-1]['date']
                
                night_60 = night_data[-60:]
                night_history = [{"date": format_iso_date(item['date']), "value": round(float(item['price']), 2)} for item in night_60]
                
                if futures_price_ref is None:
                    try:
                        script_dir = os.path.dirname(os.path.abspath(__file__))
                        cache_path = os.path.join(script_dir, 'krx_cache.json')
                        if os.path.exists(cache_path):
                            with open(cache_path, 'r', encoding='utf-8') as f_old:
                                old_cache = json.load(f_old)
                                if isinstance(old_cache, dict):
                                    futures_price_ref = old_cache.get("kospi200_futures", {}).get("price")
                    except Exception:
                        pass

                if has_live:
                    current_price = close_p
                    if session_date_str and session_date_str > last_hist_date:
                        prev_price = latest_night_from_file
                        night_history.append({"date": format_iso_date(session_date_str), "value": round(current_price, 2)})
                        if len(night_history) > 60:
                            night_history = night_history[-60:]
                    elif session_date_str == last_hist_date:
                        prev_price = round(float(night_data[-2]['price']), 2) if len(night_data) >= 2 else latest_night_from_file
                        night_history[-1]['value'] = round(current_price, 2)
                    else:
                        prev_price = round(float(night_data[-2]['price']), 2) if len(night_data) >= 2 else latest_night_from_file
                else:
                    current_price = latest_night_from_file
                    prev_price = round(float(night_data[-2]['price']), 2) if len(night_data) >= 2 else latest_night_from_file
                
                change_base_price = futures_price_ref if futures_price_ref is not None else prev_price
                night_change = round(current_price - change_base_price, 2)
                night_pct = round((night_change / change_base_price) * 100, 2) if change_base_price != 0 else 0.0
                
                result["kospi200_night"] = {
                    "price": round(current_price, 2),
                    "changeAmt": night_change,
                    "changePercent": night_pct,
                    "history": night_history,
                    "open": round(open_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "close": round(close_p, 2)
                }
    except Exception as e:
        print(f"Error in task_night_futures: {e}", file=sys.stderr)
    return result

def main():
    try:
        today = datetime.now()
        start_date = (today - timedelta(days=120)).strftime("%Y%m%d")
        end_date = today.strftime("%Y%m%d")
        
        result = {}
        
        # Parallel Execution using ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            # 1. Run KOFIA Preload, Naver Futures, fundamentals, ohlcv, and vkospi in parallel
            future_preload = executor.submit(task_kofia_preload)
            future_futures = executor.submit(get_naver_futures)
            future_fundamentals = executor.submit(task_fundamentals, start_date, end_date)
            future_ohlcv_rsi = executor.submit(task_ohlcv_rsi, start_date, end_date)
            future_vkospi = executor.submit(task_vkospi, start_date, end_date)
            
            # Wait for KOFIA preload to finish before executing task_local_kofia_adr
            future_preload.result()
            
            # Run local reading task in parallel now that preload is done
            future_local = executor.submit(task_local_kofia_adr)
            
            # Gather results
            try:
                f_data = future_futures.result()
                if f_data:
                    result["kospi200_futures"] = f_data
            except Exception as e:
                print(f"Error fetching Naver futures in thread: {e}", file=sys.stderr)
                
            try:
                fund_data = future_fundamentals.result()
                result.update(fund_data)
            except Exception as e:
                print(f"Error fetching fundamentals in thread: {e}", file=sys.stderr)
                
            try:
                ohlcv_data = future_ohlcv_rsi.result()
                result.update(ohlcv_data)
            except Exception as e:
                print(f"Error fetching ohlcv in thread: {e}", file=sys.stderr)
                
            try:
                vkospi_data = future_vkospi.result()
                result.update(vkospi_data)
            except Exception as e:
                print(f"Error fetching vkospi in thread: {e}", file=sys.stderr)
                
            try:
                local_data = future_local.result()
                result.update(local_data)
            except Exception as e:
                print(f"Error fetching local data in thread: {e}", file=sys.stderr)

        # 2. Run night futures afterwards (since it relies on futures price)
        futures_price_ref = result.get("kospi200_futures", {}).get("price")
        night_data = task_night_futures(futures_price_ref)
        result.update(night_data)
        
        # ==========================================
        # Write results to krx_cache.json
        # ==========================================
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cache_path = os.path.join(script_dir, 'krx_cache.json')
        
        # Merge with existing cache if keys are missing (to prevent accidental overwrite of existing keys)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    old_cache = json.load(f)
                if isinstance(old_cache, dict):
                    # Keep old keys unless updated
                    for k, v in old_cache.items():
                        if k not in result:
                            result[k] = v
            except Exception:
                pass
                
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            
        print(json.dumps(result, ensure_ascii=False))
        
    except Exception as e:
        print(json.dumps({"error": f"Exception occurred: {str(e)}"}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
