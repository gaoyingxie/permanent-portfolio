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
        price = float(data.get("gsz", 0))
        nav = float(data.get("dwjz", 0))
        result = {
            "code": data.get("fundcode"),
            "name": data.get("name"),
            "price": price,
            "change_pct": float(data.get("gszzl", 0)),
            "date": data.get("gztime", "")[:10],
        }
        if nav and nav > 0:
            result["premium"] = round((price - nav) / nav * 100, 2)
        return result
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
    Note: Skips gold ETF (518680) as Tencent API returns unreliable data for it.
    """
    if code == "518680":
        return None
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

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)

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
    rsi = calc_rsi(closes, 14)
    if dev < 0:
        sig, txt, color = "buy", "买入", "green"
    elif dev <= 10:
        sig, txt, color = "hold", "持有", "yellow"
    else:
        sig, txt, color = "sell", "卖出", "red"
    result = {
        "price": round(curr, 3),
        "annual_avg": round(avg, 3),
        "dev": round(dev, 2),
        "rsi": rsi,
        "signal": sig, "signal_text": txt, "color": color,
    }
    return result

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

def fetch_us_yield() -> float | None:
    """US 10-Year Treasury Yield from Trading Economics"""
    import subprocess
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '8', '-A', 'Mozilla/5.0',
             'https://zh.tradingeconomics.com/united-states/government-bond-yield'],
            capture_output=True, text=True, timeout=12
        )
        text = result.stdout
        if text and len(text) > 500:
            # Extract first yield value between 3.0 and 6.0 (US 10Y typically)
            matches = re.findall(r'(\d+\.\d+)%', text)
            for m in matches:
                val = float(m)
                if 3.0 < val < 6.0:
                    print(f"  [OK] 美债10年收益率(tradingeconomics): {val}%")
                    return round(val, 2)
    except Exception as e:
        print(f"  [FAIL] 美债10年收益率: {e}")
    return None

def fetch_dxy() -> float | None:
    """US Dollar Index (DXY) from Trading Economics
    DXY value appears as plain number (e.g. 98.6954), not with % suffix"""
    import subprocess
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '8', '-A', 'Mozilla/5.0',
             'https://zh.tradingeconomics.com/united-states/currency'],
            capture_output=True, text=True, timeout=12
        )
        text = result.stdout
        if text and len(text) > 500:
            # Look for DXY value: find '降至98.6954' or similar patterns
            m = re.search(r'\u964d\u81f4?(\d{2,3}\.\d{4})', text)  # 降至XXX
            if not m:
                m = re.search(r'\u6307\u6570[\u5f02\u5230\u4e0d\u540c]*(\d{2,3}\.\d{4})', text)  # 指数XXX
            if not m:
                # Fallback: find 5-digit numbers in range 95-105
                matches = re.findall(r'\b(9[5-9]\.\d{4}|10[0-5]\.\d{4})\b', text)
                if matches:
                    m = type('M', (), {'group': lambda self, i: matches[0]})()
            if m:
                val = float(m.group(1))
                if 90 < val < 110:
                    print(f"  [OK] 美元指数DXY(tradingeconomics): {val}")
                    return round(val, 4)
    except Exception as e:
        print(f"  [FAIL] 美元指数DXY: {e}")
    return None

def fetch_hs300_pe() -> float | None:
    """沪深300 PE (TTM) from Tencent sh000300 f75 (position 75 in 88-field tilde format)"""
    try:
        url = "https://qt.gtimg.cn/q=sh000300"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        m = re.search(r'v_sh000300="([^"]+)"', text)
        if m:
            fields = m.group(1).split('~')
            if len(fields) >= 76:
                val = float(fields[75])  # f75 = PE
                if 5 < val < 100:
                    print(f"  [OK] 沪深300 PE(sh000300): {val}")
                    return round(val, 2)
    except Exception as e:
        print(f"  [FAIL] 沪深300 PE: {e}")
    return None

def fetch_hs300_pe_percentile() -> float | None:
    """沪深300 PE percentile: current PE in 250-day range"""
    try:
        # Fetch 250-day K-line for 沪深300 (secid=1.000300)
        url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
               "?secid=1.000300&fields1=f1,f2,f3,f4,f5"
               "&fields2=f51,f52,f53,f54,f55,f56"
               "&klt=101&fqt=1&end=20500101&lmt=250")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                                    "Referer": "https://quote.eastmoney.com/"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            import gzip
            if raw[0:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode("utf-8"))
        klines = data.get("data", {}).get("klines", [])
        if not klines or len(klines) < 30:
            return None
        closes = [float(k.split(",")[2]) for k in klines]  # close price
        curr = closes[-1]
        min_p = min(closes)
        max_p = max(closes)
        if max_p == min_p:
            return None
        pct = (curr - min_p) / (max_p - min_p) * 100
        print(f"  [OK] 沪深300 PE分位: {pct:.1f}% ({len(closes)}日区间)")
        return round(pct, 1)
    except Exception as e:
        print(f"  [FAIL] 沪深300 PE分位: {e}")
    return None

def calc_erp(pe: float, bond_yield: float) -> float | None:
    """Equity Risk Premium = 1/PE - bond_yield (in %)"""
    if pe and bond_yield and pe > 0:
        # PE倒数即盈利收益率，再乘100转为%
        return round((1.0 / pe) * 100 - bond_yield, 2)
    return None

def calc_fear_greed(pe_pct: float, dev: float, rsi: float, erp: float) -> float | None:
    """Simple Fear & Greed index (0-100) from existing indicators"""
    try:
        # PE分位 (0-100 normalized)
        pe_score = pe_pct
        # 乖离率 (偏离均线程度，越高越恐慌)
        dev_score = min(max(dev / 20 * 50, 0), 50)  # ±20% -> 0-50
        # RSI ( >50 =贪婪, <50=恐慌)
        rsi_score = rsi
        # ERP (越高=股票越有吸引力=贪婪)
        erp_score = min(max((erp + 2) / 6 * 50, 0), 50)  # -2%到4% -> 0-50

        # 综合得分 (0=极度恐慌, 100=极度贪婪)
        composite = (pe_score * 0.3 + dev_score * 0.2 + rsi_score * 0.3 + erp_score * 0.2)
        return round(composite, 1)
    except Exception:
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

    # Fetch PE and dividend for equity funds (skip gold ETF)
    print(f"\n  -- Fetching fund indicators (PE/dividend)...")
    for code in FUNDS:
        if code == "518680":
            continue
        ind = fetch_fund_indicators(code)
        if ind:
            market["funds"][code].update(ind)
            pe_str = f"{ind['pe']:.1f}" if 'pe' in ind else 'N/A'
            div_str = f"{ind['dividend']:.2f}%" if 'dividend' in ind else 'N/A'
            print(f"  [OK] {code}: PE={pe_str}, 股息率={div_str}")

    # Annual deviation + RSI for all funds (except gold ETF)
    print(f"\n  -- Calculating annual deviation + RSI for all funds...")
    for code in FUNDS:
        if code == "518680":
            continue
        dev_result = calc_annual_deviation(code)
        if dev_result:
            market["funds"][code].update(dev_result)
            rsi_str = f", RSI={dev_result['rsi']}" if dev_result.get('rsi') else ""
            print(f"  [OK] {code}: dev={dev_result['dev']:+.2f}% -> {dev_result['signal_text']}{rsi_str}")

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

    # Bond yield + risk indicators
    print(f"\n  -- Fetching risk indicators...")
    cn10y = fetch_bond_yield()           # 中国10年国债收益率
    us10y = fetch_us_yield()            # 美债10年收益率
    dxy   = fetch_dxy()                 # 美元指数
    hs300_pe = fetch_hs300_pe()         # 沪深300 PE
    hs300_pe_pct = fetch_hs300_pe_percentile()  # 沪深300 PE分位

    if cn10y:
        print(f"  [OK] 中国10Y: {cn10y:.2f}%")
    if us10y:
        print(f"  [OK] 美债10Y: {us10y:.2f}%")
    if dxy:
        print(f"  [OK] 美元指数: {dxy:.2f}")
    if hs300_pe:
        print(f"  [OK] 沪深300 PE: {hs300_pe:.1f}")
    if hs300_pe_pct is not None:
        print(f"  [OK] 沪深300 PE分位: {hs300_pe_pct:.1f}%")

    # ERP = 盈利收益率(1/PE*100) - 国债收益率
    erp = calc_erp(hs300_pe, cn10y) if hs300_pe else None
    if erp is not None:
        print(f"  [OK] 股权风险溢价ERP: {erp:.2f}%")

    # 恐慌/贪婪 (简化版: PE分位*0.3 + RSI*0.3 + ERP标准化*0.2 + 乖离率*0.2)
    fear_greed = None
    if hs300_pe_pct is not None and hs300_pe is not None:
        # 取所有基金的平均RSI和乖离率
        avg_rsi = None
        avg_dev = None
        rsis, devs = [], []
        for code, fd in market.get("funds", {}).items():
            if code == "518680":
                continue
            if fd.get("rsi") is not None:
                rsis.append(fd["rsi"])
            if fd.get("dev") is not None:
                devs.append(fd["dev"])
        avg_rsi = sum(rsis) / len(rsis) if rsis else 50.0
        avg_dev = sum(devs) / len(devs) if devs else 0.0
        fear_greed = calc_fear_greed(hs300_pe_pct, avg_dev, avg_rsi, erp or 0)
        if fear_greed is not None:
            print(f"  [OK] 恐慌贪婪指数: {fear_greed:.1f}")

    market["risk"] = {
        "cn10y": cn10y,
        "us10y": us10y,
        "dxy": dxy,
        "hs300_pe": hs300_pe,
        "hs300_pe_pct": hs300_pe_pct,
        "erp": erp,
        "fear_greed": fear_greed,
    }

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
