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
        if f116 and isinstance(f116, (int, float)) and f116 > 0:
            result["pe"] = round(float(f116), 1)
        f162 = fields.get("f162")
        if f162 and isinstance(f162, (int, float)) and f162 > 0:
            result["dividend"] = round(float(f162), 2)
        return result
    except Exception as e:
        print(f"  [FAIL] nav {code}: {e}")
        return None

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

def fetch_nav_history(code: str, days: int = 250) -> list:
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid=1.{code}&fields1=f1,f2,f3,f4,f5,f6"
           f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
           f"&klt=101&fqt=1&end=20500101&lmt={days}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        klines = data.get("data", {}).get("klines", [])
        return [{"date": line.split(",")[0], "close": float(line.split(",")[2])} for line in klines]
    except Exception as e:
        print(f"  [FAIL] nav_history {code}: {e}")
        return []

def calc_annual_deviation(code: str) -> dict:
    history = fetch_nav_history(code, 250)
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
    """10-Year China Government Bond Yield"""
    codes = ["019547", "019650", "019453"]
    for secid in codes:
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{secid}&fields=f43,f170,f171"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            fields = data.get("data", {})
            if not fields:
                continue
            f171 = fields.get("f171", 0)
            if f171 and isinstance(f171, (int, float)) and 0.5 < float(f171) < 6:
                val = float(f171)
                return round(val / 100 if val > 10 else val, 4)
            f43 = fields.get("f43", 0)
            if f43 and isinstance(f43, (int, float)):
                price = float(f43)
                if 90 < price < 120:
                    return round(100 - price, 4)
        except Exception:
            pass
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
        history = fetch_nav_history(code, 250)
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

    # Indoor fund prices (513650 SPX, 518680 Gold ETF)
    for code, name in [("513650", "SPX ETF"), ("518680", "Gold ETF")]:
        ind = fetch_fund_nav(code)
        if ind:
            market["funds"][code] = {**market["funds"].get(code, {}), **ind}
            print(f"  [OK] {name}({code}): {ind['price']} ({ind['change_pct']:+.2f}%)")

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

    # 563020 dividend (from nav data if available)
    div = fetch_563020_dividend()
    if div:
        print(f"  [OK] 563020 dividend: {div:.2f}%")
        market["risk"]["dividend"] = div
        if "dividend" not in market["funds"].get("563020", {}):
            market["funds"].setdefault("563020", {})["dividend"] = div
    else:
        market["risk"]["dividend"] = None

    # PE percentile for each non-gold fund
    for code in ["159222", "563020", "513650"]:
        pct = fetch_pe_percentile(code)
        if pct is not None:
            market["funds"].setdefault(code, {})["pe_pct"] = pct
            print(f"  [OK] {code} PE历史: {pct:.1f}%")

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
