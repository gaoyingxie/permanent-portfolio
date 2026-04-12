#!/usr/bin/env python3
"""
Permanent Portfolio Data Fetcher
Fetches latest market data for all holdings
"""

import json
import urllib.request
import ssl
import os
import re
from datetime import datetime, timezone, timedelta

os.environ['TZ'] = 'Asia/Shanghai'
_tz = timezone(timedelta(hours=8))
ssl._create_default_https_context = ssl._create_unverified_context

FUNDS = {
    "159222": {"name": "自由现金流ETF", "target": 0.70},
    "563020": {"name": "红利低波", "target": 0.20},
    "513650": {"name": "标普500ETF", "target": 0.20},
    "518680": {"name": "黄金ETF", "target": 0.10},
}

def fetch_fund_data(code: str) -> dict:
    url = f"https://fundgz.1234567.com.cn/js/{code}.js"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8")
        text = text.replace("jsonpgz(", "").rstrip(");")
        data = json.loads(text)
        return {
            "code": data.get("fundcode"),
            "name": data.get("name"),
            "price": float(data.get("gsz", 0)),
            "change_pct": float(data.get("gszzl", 0)),
            "date": data.get("gztime", "")[:10],
        }
    except Exception as e:
        print(f"  [FAIL] fund {code}: {e}")
        return None

def fetch_fund_nav(code: str) -> dict:
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{code}&fields=f43,f170,f116,f162"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        fields = data.get("data", {})
        if not fields:
            return None
        f43 = fields.get("f43")
        f170 = fields.get("f170")
        if not isinstance(f43, (int, float)) or not isinstance(f170, (int, float)):
            return None
        result = {
            "price": round(float(f43) / 100, 4),
            "change_pct": round(float(f170) / 100, 2),
        }
        f116 = fields.get("f116")
        if f116 and isinstance(f116, (int, float)) and 0 < f116 < 300:
            result["pe"] = round(float(f116), 1)
        f162 = fields.get("f162")
        if f162 and isinstance(f162, (int, float)) and 0 < f162 < 50:
            result["dividend"] = round(float(f162), 2)
        return result
    except Exception as e:
        print(f"  [FAIL] nav {code}: {e}")
        return None

def fetch_fund_indicators(code: str) -> dict:
    """Fetch PE, dividend yield and PE historical percentile for indoor funds.
    Uses Tencent fund API for PE/dividend, and price history for percentile.
    Returns {pe: float, dividend: float, pe_percent: float} or partial dict.
    """
    prefix = "sz" if code == "159222" else "sh"
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    result = {}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        m = re.search(r'"([^"]+)"', text)
        if m:
            fields = m.group(1).split("~")
            if len(fields) >= 80:
                f74 = fields[74] if len(fields) > 74 else None
                f79 = fields[79] if len(fields) > 79 else None
                if f74:
                    try:
                        pe_raw = float(f74)
                        if 1 < pe_raw < 200:
                            if code == "563020" and pe_raw > 15:
                                result["pe"] = round(pe_raw / 2.1, 1)
                            else:
                                result["pe"] = round(pe_raw, 1)
                    except (ValueError, TypeError):
                        pass
                if f79:
                    try:
                        div_raw = float(f79)
                        if 0 < div_raw < 50:
                            if code == "563020" and div_raw > 5:
                                result["dividend"] = round(div_raw / 2.1, 2)
                            else:
                                result["dividend"] = round(div_raw, 2)
                    except (ValueError, TypeError):
                        pass
    except Exception as e:
        print(f"  [FAIL] fund indicators {code}: {e}")

    # PE percentile: compute from price history vs annual range
    try:
        secid = "0." + code if code == "159222" else "1." + code
        history = fetch_nav_history(secid, 250)
        if history and len(history) >= 20:
            closes = [h["close"] for h in history]
            curr = closes[-1]
            avg = sum(closes) / len(closes)
            mn, mx = min(closes), max(closes)
            if mx > mn:
                pct = (curr - mn) / (mx - mn) * 100
                result["pe_percent"] = round(pct, 1)
    except Exception as e:
        print(f"  [FAIL] pe_percent {code}: {e}")

    if result:
        print(f"  [OK] {code} indicators: {result}")
    return result if result else None

def fetch_index(code: str, name: str) -> dict:
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{code}&fields=f43,f170"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        fields = data.get("data", {})
        return {
            "price": fields.get("f43", 0) / 100,
            "change_pct": round(fields.get("f170", 0) / 100, 2),
        }
    except Exception as e:
        print(f"  [FAIL] index {code}: {e}")
        return None

def fetch_us_index(secid: str, name: str) -> dict:
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f170"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        fields = data.get("data", {})
        return {
            "price": fields.get("f43", 0) / 100,
            "change_pct": round(fields.get("f170", 0) / 100, 2),
        }
    except Exception as e:
        print(f"  [FAIL] us_index {name}: {e}")
        return None

def fetch_nav_history(secid: str, days: int = 250) -> list:
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
           f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
           f"&klt=101&fqt=1&end=20500101&lmt={days}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        klines = data.get("data", {}).get("klines", []) if data.get("data") else []
        return [{"date": line.split(",")[0], "close": float(line.split(",")[2])} for line in klines]
    except Exception as e:
        print(f"  [FAIL] nav_history {secid}: {e}")
        return []

def calc_annual_deviation(code: str) -> dict:
    # secid mapping: 159222=深圳基金(0), others=上海(1)
    hist_code = "0." + code if code == "159222" else "1." + code
    history = fetch_nav_history(hist_code, 250)
    if not history or len(history) < 10:
        return None
    closes = [h["close"] for h in history]
    avg = sum(closes) / len(closes)
    curr = closes[-1]
    dev = (curr / avg - 1) * 100
    if dev < 0:
        sig, txt, color = "buy", "买入", "green"
    elif dev <= 10:
        sig, txt, color = "hold", "持有", "yellow"
    else:
        sig, txt, color = "sell", "卖出", "red"
    return {
        "price": round(curr, 3),
        "annual_avg": round(avg, 3),
        "dev": round(dev, 2),
        "signal": sig, "signal_text": txt, "color": color,
    }

def fetch_gold() -> dict:
    """Get both international (COMEX USD/oz) and domestic (SGE CNY/g) gold prices"""
    result = {}
    # COMEX international gold (USD/oz)
    try:
        url_g = "https://hq.sinajs.cn/list=hf_GC"
        req_g = urllib.request.Request(url_g, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn/"
        })
        with urllib.request.urlopen(req_g, timeout=8) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        m = re.search(r'"([^"]+)"', text)
        if m:
            result["global"] = round(float(m.group(1).split(",")[0]), 2)
    except Exception as e:
        print(f"  [FAIL] COMEX gold: {e}")
    # SGE Au99.99 domestic price (CNY/g) - fetch last 3 days to handle weekends
    try:
        today = datetime.now(_tz)
        # Try last 3 days (handles weekends)
        for days_ago in range(3):
            dt = today - timedelta(days=days_ago)
            date_str = dt.strftime("%Y-%m-%d")
            url_sge = (f"https://www.sge.com.cn/sjzx/quotation_daily_new"
                       f"?start_date={date_str}&end_date={date_str}&product=Au99.99")
            req_sge = urllib.request.Request(url_sge, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.sge.com.cn/"
            })
            with urllib.request.urlopen(req_sge, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            rows = re.findall(r"<tr[^>]*>.*?</tr>", html, re.DOTALL)
            for row in rows:
                if "iAu99.99" in row:  # 国际板 AU9999
                    cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
                    clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
                    if len(clean) > 5 and clean[3]:
                        result["sge"] = round(float(clean[3]), 2)
                        break
            if "sge" in result:
                break
    except Exception as e:
        print(f"  [FAIL] SGE gold: {e}")
    return result if result else None

def fetch_fx_usdcny() -> dict:
    """USD/CNY exchange rate"""
    try:
        url = "https://hq.sinajs.cn/list=fx_susdcny"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn/"
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read().decode("gbk", errors="ignore")
        m = re.search(r'"([^"]+)"', text)
        if m:
            parts = m.group(1).split(",")
            if len(parts) > 2:
                curr = float(parts[1])
                prev = float(parts[2])
                chg_pct = round((curr - prev) / prev * 100, 2) if prev else None
                return {"rate": round(curr, 4), "change_pct": chg_pct}
    except Exception as e:
        print(f"  [FAIL] USD/CNY: {e}")
    return None

def fetch_bond_yield() -> float:
    """10-Year China Government Bond Yield - multiple sources"""
    import subprocess
    # Source 1: Trading Economics (web scraping)
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '8', '-A', 'Mozilla/5.0',
             'https://zh.tradingeconomics.com/china/government-bond-yield'],
            capture_output=True, text=True, timeout=12
        )
        text = result.stdout
        if text and len(text) > 500:
            matches = re.findall(r'(\d+\.\d+)%', text)
            for m in matches:
                val = float(m)
                if 1.0 < val < 5.0:
                    print(f"  [OK] 10年国债收益率(tradingeconomics): {val}%")
                    return round(val, 2)
    except Exception as e:
        print(f"  [FAIL] 10年国债收益率(tradingeconomics): {e}")

    # Source 2: Sina CN10YT bond yield
    try:
        url = "https://hq.sinajs.cn/list=cn10yt"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn/"
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        m = re.search(r'"([^"]+)"', text)
        if m:
            fields = m.group(1).split(',')
            if len(fields) > 1:
                val_str = fields[1].strip()
                if val_str.replace('.', '').isdigit():
                    val = float(val_str)
                    if 1.0 < val < 5.0:
                        print(f"  [OK] 10年国债收益率(sina cn10yt): {val}%")
                        return round(val, 2)
    except Exception as e:
        print(f"  [FAIL] 10年国债收益率(sina): {e}")

    # Source 3: macroview.club via curl
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '8', '-A', 'Mozilla/5.0',
             '-H', 'Referer: https://www.macroview.club/',
             'https://www.macroview.club/data?code=cn_bond_tenyear'],
            capture_output=True, text=True, timeout=10
        )
        text = result.stdout
        if text and '登录' not in text and len(text) > 1000:
            matches = re.findall(r'<em>\s*([\d.]+)\s*</em>', text)
            if len(matches) >= 2:
                val = float(matches[1])
                if 0.5 < val < 10:
                    print(f"  [OK] 10年国债收益率(macroview): {val}%")
                    return round(val, 4)
    except Exception as e:
        print(f"  [FAIL] 10年国债收益率(macroview): {e}")

    return None

def fetch_563020_dividend() -> float:
    """563020 dividend yield"""
    try:
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.563020&fields=f10"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        div = data.get("data", {}).get("f10", 0)
        if div:
            return round(float(div), 2)
    except Exception as e:
        print(f"  [FAIL] 563020 dividend: {e}")
    return None

def fetch_pe_percentile(code: str) -> float | None:
    """Fetch PE historical percentile for a fund from eastmoney"""
    try:
        url = (f"https://datacenter.eastmoney.com/securities/api/data/v1/get"
               f"?reportName=RPT_FUND_BASIC_INFO"
               f"&columns=SECURITY_CODE,PE_TTM_HISTORY_PECT"
               f"&filter=SECURITY_CODE%3D%22{code}%22")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = data.get("result", {})
        if result:
            items = result.get("data", [])
            if items:
                pct = items[0].get("PE_TTM_HISTORY_PECT")
                if pct and isinstance(pct, (int, float)):
                    return round(float(pct), 1)
    except Exception:
        pass
    # Fallback: use price-based approximation from nav history
    try:
        secid = "0." + code if code == "159222" else "1." + code
        history = fetch_nav_history(secid, 250)
        if not history or len(history) < 20:
            return None
        closes = [h["close"] for h in history]
        curr = closes[-1]
        min_p = min(closes)
        max_p = max(closes)
        if max_p == min_p:
            return None
        pct = (curr - min_p) / (max_p - min_p) * 100
        return round(pct, 1)
    except Exception:
        return None

def main():
    now = datetime.now(_tz).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] Fetching market data...")

    market = {
        "updated": now,
        "updated_date": datetime.now(_tz).strftime("%Y-%m-%d"),
        "funds": {},
        "index": {},
    }

    # Funds via 天天基金
    for code, info in FUNDS.items():
        fund = fetch_fund_data(code)
        if fund:
            market["funds"][code] = fund
            print(f"  [OK] {info['name']}({code}): {fund['price']} ({fund['change_pct']:+.2f}%)")

    # Note: 腾讯 indoor 接口 (secid 1.xxx) 单位与 fundgz 不一致，会导致价格错误，
    # 故 indoor 基金改价直接用 fundgz 数据，不再用腾讯接口覆盖。
    # PE/股息率改为单独从腾讯基金接口获取。

    # Fetch PE and dividend for each fund
    print(f"\n  -- Fetching fund indicators (PE/dividend)...")
    for code in FUNDS:
        ind = fetch_fund_indicators(code)
        if ind:
            market["funds"][code].update(ind)
            pe_str = f"{ind['pe']:.1f}" if 'pe' in ind else 'N/A'
            div_str = f"{ind['dividend']:.2f}%" if 'dividend' in ind else 'N/A'
            print(f"  [OK] {code}: PE={pe_str}, 股息率={div_str}")

    # 563020 annual deviation
    print(f"\n  -- Calculating 563020 annual deviation...")
    dev_result = calc_annual_deviation("563020")
    if dev_result:
        market["funds"]["563020"].update(dev_result)
        print(f"  [OK] 563020 deviation: {dev_result['dev']:+.2f}% -> {dev_result['signal_text']}")

    # Gold prices
    print(f"\n  -- Fetching gold prices...")
    gold = fetch_gold()
    if gold:
        market["gold"] = gold
        if gold.get("global"):
            print(f"  [OK] COMEX: {gold['global']} USD/oz")
        if gold.get("sge"):
            print(f"  [OK] SGE Au99.99: {gold['sge']} CNY/g")
    else:
        market["gold"] = None

    # Bond yield
    print(f"\n  -- Fetching 10Y bond yield...")
    bond = fetch_bond_yield()
    if bond:
        print(f"  [OK] 10Y bond: {bond:.4f}%")
    market["risk"] = {"rate": bond}

    # USD/CNY
    print(f"\n  -- Fetching USD/CNY...")
    fx = fetch_fx_usdcny()
    if fx:
        market["fx"] = fx
        print(f"  [OK] USD/CNY: {fx['rate']:.4f}")
    else:
        market["fx"] = {"rate": None, "change_pct": None}

    # Shanghai Index
    sh = fetch_index("000001", "SSE")
    if sh:
        market["index"]["sh000001"] = sh
        print(f"\n  [OK] SSE: {sh['price']} ({sh['change_pct']:+.2f}%)")

    # S&P 500
    spx = fetch_us_index("100.SPX", "S&P 500")
    if spx:
        market["index"]["spx"] = spx
        print(f"  [OK] S&P 500: {spx['price']} ({spx['change_pct']:+.2f}%)")

    # Save
    with open("data/market.json", "w", encoding="utf-8") as f:
        json.dump(market, f, ensure_ascii=False, indent=2)
    print(f"\n  [DONE] data/market.json saved")

if __name__ == "__main__":
    main()
