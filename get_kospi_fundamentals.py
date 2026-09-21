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
# Load from workspace root .env first, then fallback to D:\AI Investing\KRXdata\.env or 00 API Key
load_dotenv()
krx_env_path = r"D:\AI Investing\KRXdata\.env"
if os.path.exists(krx_env_path):
    load_dotenv(krx_env_path)

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

def get_naver_futures_fast():
    headers = {"User-Agent": "Mozilla/5.0"}
    raw_items = []
    for p in range(1, 5):
        try:
            url = f"https://m.stock.naver.com/api/index/FUT/price?pageSize=60&page={p}"
            res = requests.get(url, headers=headers, timeout=4)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    raw_items.extend(data)
                else:
                    break
            else:
                break
        except Exception:
            break
            
    if not raw_items:
        return None
        
    latest = raw_items[0]
    price = float(latest["closePrice"].replace(",", ""))
    open_p = float(latest["openPrice"].replace(",", ""))
    high_p = float(latest["highPrice"].replace(",", ""))
    low_p = float(latest["lowPrice"].replace(",", ""))
    change_amt = float(latest["compareToPreviousClosePrice"].replace(",", ""))
    cmp_price = latest.get("compareToPreviousPrice", {})
    if isinstance(cmp_price, dict) and cmp_price.get("name") == "FALLING":
        if change_amt > 0:
            change_amt = -change_amt
    pct = float(latest["fluctuationsRatio"].replace(",", ""))
    if change_amt < 0 and pct > 0:
        pct = -pct
    
    history = [
        {"date": format_iso_date(item["localTradedAt"][:10]), "value": float(item["closePrice"].replace(",", ""))}
        for item in reversed(raw_items)
    ][-200:]
    
    return {
        "price": price,
        "changeAmt": change_amt,
        "changePercent": pct,
        "open": open_p,
        "high": high_p,
        "low": low_p,
        "close": price,
        "history": history
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
            new_dep_history = new_dep_history[-250:]
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
            new_liq_history = new_liq_history[-250:]
            with open(liq_path, "w", encoding="utf-8") as f:
                json.dump(new_liq_history, f, indent=4)
    except Exception as kofia_err:
        print(f"Error updating KOFIA data in background scraper: {kofia_err}", file=sys.stderr)

def task_fundamentals(start_date, end_date):
    result = {}
    for attempt in range(3):
        try:
            df_fund = stock.get_index_fundamental(start_date, end_date, "1001")
            if df_fund is not None and not df_fund.empty:
                df_fund_filtered = df_fund[(df_fund['PER'] != 0) & (df_fund['PBR'] != 0)].copy()
                if len(df_fund_filtered) >= 2:
                    df_fund_200 = df_fund_filtered.tail(200)
                    
                    # PER
                    per_history = [{"date": format_iso_date(dt), "value": round(float(row['PER']), 2)} for dt, row in df_fund_200.iterrows()]
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
                    pbr_history = [{"date": format_iso_date(dt), "value": round(float(row['PBR']), 2)} for dt, row in df_fund_200.iterrows()]
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
                    return result
        except Exception as e:
            print(f"Error in task_fundamentals (attempt {attempt + 1}/3): {e}", file=sys.stderr)
            time.sleep(1.0)
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
            
            chronological = list(reversed(output))[-200:]
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

def task_ohlcv_pykrx(start_date, end_date):
    result = {}
    try:
        df_ohlcv = stock.get_index_ohlcv_by_date(start_date, end_date, "1001")
        if df_ohlcv is not None and not df_ohlcv.empty:
            # 1. KOSPI Trade Value (원 -> 억원)
            df_val = df_ohlcv[df_ohlcv['거래대금'] > 0]
            if len(df_val) >= 2:
                df_val_200 = df_val.tail(200)
                history_val = [
                    {"date": format_iso_date(dt), "value": round(float(row['거래대금'] / 100000000.0), 2)}
                    for dt, row in df_val_200.iterrows()
                ]
                latest_val = round(float(df_val['거래대금'].iloc[-1] / 100000000.0), 2)
                prev_val = round(float(df_val['거래대금'].iloc[-2] / 100000000.0), 2)
                val_change = round(latest_val - prev_val, 2)
                val_pct = round((val_change / prev_val) * 100, 2) if prev_val != 0 else 0.0
                
                result["kospi_trade_value"] = {
                    "price": latest_val,
                    "changeAmt": val_change,
                    "changePercent": val_pct,
                    "history": history_val
                }
                
            # 2. KOSPI RSI (14-day)
            close_series = df_ohlcv["종가"].copy()
            if len(close_series) >= 15:
                delta = close_series.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi_series = (100 - (100 / (1 + rs))).dropna()
                if len(rsi_series) >= 2:
                    rsi_200 = rsi_series.tail(200)
                    history_rsi = [{"date": format_iso_date(dt), "value": round(float(val), 2)} for dt, val in rsi_200.items()]
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
        print(f"Error in task_ohlcv_pykrx: {e}", file=sys.stderr)
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
                dep_200 = dep_data[-200:]
                
                # Customer Deposits
                dep_history = [{"date": format_iso_date(item['date']), "value": round(float(item['deposit']), 2)} for item in dep_200]
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
                cred_history = [{"date": format_iso_date(item['date']), "value": round(float(item['credit']), 2)} for item in dep_200]
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
                liq_200 = liq_data[-200:]
                liq_history = [{"date": format_iso_date(item['date']), "value": round(float(item['liquidation']), 2)} for item in liq_200]
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
                            history = history[-250:]
                            with open(adr_path, "w", encoding="utf-8") as f:
                                json.dump(history, f, indent=4)
        except Exception as adr_up_err:
            print(f"Error updating ADR history in scraper: {adr_up_err}", file=sys.stderr)

        # Backfill any missing recent business days via pykrx
        try:
            if os.path.exists(adr_path):
                with open(adr_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            else:
                history = []
            
            existing_dates = {item['date'] for item in history}
            today_dt = datetime.now()
            needs_save = False
            for i in range(1, 8):
                check_dt = today_dt - timedelta(days=i)
                if check_dt.weekday() < 5:
                    d_str = check_dt.strftime("%Y-%m-%d")
                    if d_str not in existing_dates:
                        try:
                            df_change = stock.get_market_price_change_by_ticker(d_str.replace('-', ''), d_str.replace('-', ''), market='KOSPI')
                            if df_change is not None and not df_change.empty:
                                adv = len(df_change[df_change['등락률'] > 0])
                                dec = len(df_change[df_change['등락률'] < 0])
                                if adv > 0 or dec > 0:
                                    history.append({'date': d_str, 'adv': adv, 'dec': dec})
                                    existing_dates.add(d_str)
                                    needs_save = True
                        except Exception:
                            pass
            if needs_save:
                history.sort(key=lambda x: x['date'])
                history = history[-250:]
                with open(adr_path, "w", encoding="utf-8") as f:
                    json.dump(history, f, indent=4)
        except Exception as pykrx_adr_err:
            print(f"Error backfilling ADR via pykrx: {pykrx_adr_err}", file=sys.stderr)

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
                    adr_200 = adr_computed[-200:]
                    adr_history = [{"date": format_iso_date(item['date']), "value": item['value']} for item in adr_200]
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
                
                night_200 = night_data[-200:]
                night_history = [{"date": format_iso_date(item['date']), "value": round(float(item['price']), 2)} for item in night_200]
                
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
                    f_dates = {x['date']: x for x in night_data}
                    if session_date_str in f_dates:
                        f_dates[session_date_str]['price'] = round(current_price, 2)
                    else:
                        night_data.append({'date': session_date_str, 'price': round(current_price, 2)})
                    night_data.sort(key=lambda x: x['date'])
                    night_data = night_data[-200:]
                    try:
                        with open(night_path, "w", encoding="utf-8") as f_save:
                            json.dump(night_data, f_save, indent=4, ensure_ascii=False)
                    except Exception:
                        pass
                    night_history = [{"date": format_iso_date(item['date']), "value": round(float(item['price']), 2)} for item in night_data]
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

def update_krx_cache():
    """Fetch all K-Market indicators and save to krx_cache.json in-process. Returns the result dict."""
    today = datetime.now()
    start_date = (today - timedelta(days=365)).strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")
    
    result = {}
    
    # Parallel Execution: KOFIA Preload, Naver Futures, and Serialized KRX queries
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_preload = executor.submit(task_kofia_preload)
        future_futures = executor.submit(get_naver_futures_fast)
        
        # Execute KRX-dependent queries sequentially to prevent session cookie clashes and rate limits
        def run_krx_tasks():
            krx_res = {}
            try:
                fund_data = task_fundamentals(start_date, end_date)
                if fund_data:
                    krx_res.update(fund_data)
            except Exception as e:
                print(f"Error in task_fundamentals: {e}", file=sys.stderr)
                
            time.sleep(0.3)
            try:
                ohlcv_data = task_ohlcv_pykrx(start_date, end_date)
                if ohlcv_data:
                    krx_res.update(ohlcv_data)
            except Exception as e:
                print(f"Error in task_ohlcv_pykrx: {e}", file=sys.stderr)
                
            time.sleep(0.3)
            try:
                vkospi_data = task_vkospi(start_date, end_date)
                if vkospi_data:
                    krx_res.update(vkospi_data)
            except Exception as e:
                print(f"Error in task_vkospi: {e}", file=sys.stderr)
            return krx_res
            
        future_krx = executor.submit(run_krx_tasks)
        
        try:
            future_preload.result()
        except Exception as e:
            print(f"Error in future_preload: {e}", file=sys.stderr)
            
        future_local = executor.submit(task_local_kofia_adr)
        
        try:
            f_data = future_futures.result()
            if f_data:
                result["kospi200_futures"] = f_data
        except Exception as e:
            print(f"Error fetching Naver futures in thread: {e}", file=sys.stderr)
            
        try:
            krx_res = future_krx.result()
            if krx_res:
                result.update(krx_res)
        except Exception as e:
            print(f"Error executing KRX tasks in thread: {e}", file=sys.stderr)
            
        try:
            local_data = future_local.result()
            if local_data:
                result.update(local_data)
        except Exception as e:
            print(f"Error fetching local data in thread: {e}", file=sys.stderr)

    # 2. Run night futures afterwards (since it relies on futures price)
    try:
        futures_price_ref = result.get("kospi200_futures", {}).get("price")
        night_data = task_night_futures(futures_price_ref)
        if night_data:
            result.update(night_data)
    except Exception as e:
        print(f"Error in task_night_futures: {e}", file=sys.stderr)
        
    # 3. Add metadata for smart freshness checking
    # Only update last_batch_update if fundamentals were successfully gathered
    if "per" in result and "pbr" in result:
        result["_meta"] = {
            "last_batch_update": datetime.now().isoformat()
        }
    
    # 4. Write results to krx_cache.json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_path = os.path.join(script_dir, 'krx_cache.json')
    
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                old_cache = json.load(f)
            if isinstance(old_cache, dict):
                for k, v in old_cache.items():
                    if k not in result:
                        result[k] = v
        except Exception:
            pass
            
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        
    return result

def main():
    try:
        t0 = time.time()
        result = update_krx_cache()
        elapsed = time.time() - t0
        print(f"Elapsed: {elapsed:.2f} s, Items: {len(result)}")
        if "--batch" not in sys.argv:
            print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": f"Exception occurred: {str(e)}"}), file=sys.stderr)
        if __name__ == "__main__":
            sys.exit(1)

if __name__ == "__main__":
    main()

