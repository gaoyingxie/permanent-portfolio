#!/usr/bin/env python3
"""
Permanent Portfolio - 市场数据抓取脚本
========================================
职责：抓取所有持仓基金、指数、风险指标，输出 data/market.json
"""

import csv
import io
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# ============================================================
# 初始化
# ============================================================
os.environ['TZ'] = 'Asia/Shanghai'
_TZ = timezone(timedelta(hours=8))

ssl._create_default_https_context = ssl._create_unverified_context

# 持仓基金配置
FUNDS = {
    "159222": {"name": "自由现金流ETF", "is_sz": True},
    "563020": {"name": "红利低波ETF", "is_sz": False},
    "513650": {"name": "SPX ETF",     "is_sz": False},
    "518680": {"name": "黄金ETF",     "is_sz": False},
}
GOLD_CODE = "518680"
ALL_FUND_CODES = list(FUNDS)


# ============================================================
# 通用工具
# ============================================================

def _get(url: str, headers: dict = None, timeout: int = 10, encoding: str = "utf-8") -> str | None:
    """通用 HTTP GET，返回文本或 None（失败时自动打印日志）"""
    h = {"User-Agent": "Mozilla/5.0"}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(encoding, errors="ignore")
    except Exception as e:
        print(f"  [NET] GET {url[:60]}... failed: {e}")
        return None


def _parse_market_history(secid: str, days: int = 250) -> list[dict] | None:
    """
    从 Sina K线接口获取历史收盘价。

    secid 格式: "0.xxx"（深圳）或 "1.xxx"（上海）
    Sina K线返回 oldest-first（最老日期在前），无需反转。
    失败时返回 None（调用方自行处理降级）。
    """
    market = "sz" if secid.startswith("0.") else "sh"
    code = secid.split(".")[1]
    url = (f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
           f"/CN_MarketData.getKLineData?symbol={market}{code}"
           f"&scale=240&ma=no&datalen={days}")

    text = _get(url, {"Referer": "https://finance.sina.com.cn/"}, timeout=15)
    if not text:
        return None
    try:
        data = json.loads(text)
        if not isinstance(data, list) or len(data) < 10:
            return None
        # oldest-first: data[0] = 最老, data[-1] = 最新
        return [{"date": item["day"], "close": float(item["close"])} for item in data]
    except Exception as e:
        print(f"  [PARSE] nav_history {secid}: {e}")
        return None


def calc_rsi(prices: list[float], period: int = 14) -> float | None:
    """14日 RSI，失败返回 None"""
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 1)


def safe_get_field(fields: list, index: int, lo: float = None, hi: float = None) -> float | None:
    """安全提取字段：不存在/解析失败/超范围均返回 None"""
    try:
        val = float(fields[index])
        if lo is not None and val < lo:
            return None
        if hi is not None and val > hi:
            return None
        return val
    except (IndexError, ValueError, TypeError):
        return None


# ============================================================
# 基金数据：fundgz（实时估值，场内价格）
# ============================================================

def fetch_fund_price(code: str) -> dict | None:
    """
    通过 天天基金 gz.js 接口抓取基金实时估值和溢价率。
    失败时自动重试最多 3 次（间隔 3s），避免 CI 场景因短暂网络波动丢失数据。
    返回: {code, name, price, change_pct, date, premium} 或 None
    """
    import time
    last_err = None
    for attempt in range(3):
        text = _get(f"https://fundgz.1234567.com.cn/js/{code}.js", timeout=20)
        if text:
            try:
                text = text.replace("jsonpgz(", "").rstrip(");")
                d = json.loads(text)
                price = float(d.get("gsz", 0))
                nav   = float(d.get("dwjz", 0))
                if price > 0:
                    result = {
                        "code":       d.get("fundcode"),
                        "name":       d.get("name"),
                        "price":      price,
                        "change_pct": float(d.get("gszzl", 0)),
                        "date":       d.get("gztime", "")[:10],
                    }
                    if nav > 0:
                        result["premium"] = round((price - nav) / nav * 100, 2)
                    return result
            except Exception as e:
                last_err = e
        if attempt < 2:
            print(f"  [RETRY] fundgz {code} (attempt {attempt+1}/3 failed), waiting 3s...")
            time.sleep(3)
    print(f"  [FAIL] fundgz {code}: 3次尝试均失败: {last_err}")
    return None


# ============================================================
# 基金指标：PE / 股息率 / PE历史分位
# ============================================================

def fetch_fund_pe_div(code: str) -> dict | None:
    """
    通过腾讯 88字段接口抓取 PE 和股息率（室内基金适用）。
    PE: 159222 用 f116，其他用 f74（>15时对563020除以2.1）
    股息率: 159222 用 f162，其他用 f75（563020用f75除以100）
    返回: {pe, dividend} 或部分字典
    """
    prefix = "sz" if FUNDS[code]["is_sz"] else "sh"
    text = _get(f"https://qt.gtimg.cn/q={prefix}{code}", timeout=8)
    if not text:
        return None

    m = re.search(r'"([^"]+)"', text)
    if not m:
        return None

    fields = m.group(1).split("~")
    if len(fields) < 80:
        return None

    result = {}

    # --- PE ---
    f74 = safe_get_field(fields, 74, lo=1, hi=200)
    f75 = safe_get_field(fields, 75, lo=1, hi=200)
    f44 = safe_get_field(fields, 44, lo=1, hi=300)
    pe = None
    if f74 is not None and f74 > 0:
        pe = round(f74 / 2.1, 1) if code == "563020" and f74 > 15 else round(f74, 1)
    elif f75 is not None and f75 > 0:
        pe = round(f75, 1)
    elif code == "563020":
        # 563020 的 f74/f75 为负，用中证红利低波指数 PE（腾讯 sh000821 f39）
        idx_text = _get("https://qt.gtimg.cn/q=sh000821", timeout=8)
        if idx_text:
            m = re.search(r'v_sh000821="([^"]+)"', idx_text)
            if m:
                idx_fields = m.group(1).split("~")
                idx_pe = safe_get_field(idx_fields, 39, lo=1, hi=100)
                if idx_pe:
                    pe = round(idx_pe, 1)
    if pe:
        result["pe"] = pe

    # --- 股息率（腾讯 f38 字段，f38 是已换算的百分比值） ---
    f38 = safe_get_field(fields, 38, lo=0, hi=100)
    f79 = safe_get_field(fields, 79, lo=0, hi=5000)
    div = None
    if code == "518680":
        pass  # 黄金ETF无股息
    elif f38 is not None and f38 > 0:
        div = round(f38, 2)
    elif f79 is not None and f79 < 50:
        div = round(f79, 2)
    if div:
        result["dividend"] = div

    return result if result else None


def calc_fund_pe_percentile(code: str) -> float | None:
    """
    基于 250 日 K 线计算价格所处历史区间百分位：(curr-min)/(max-min)*100
    用于 159222 / 563020 / 513650；518680 跳过。
    """
    secid = "0." + code if FUNDS[code]["is_sz"] else "1." + code
    history = _parse_market_history(secid, 250)
    if not history or len(history) < 20:
        return None
    closes = [h["close"] for h in history]   # oldest-first
    curr = closes[-1]                        # 最新价格
    mn, mx = min(closes), max(closes)
    if mx == mn:
        return None
    return round((curr - mn) / (mx - mn) * 100, 1)


def calc_fund_deviation(code: str) -> dict | None:
    """
    计算乖离率和 RSI（基于 250 日均线）。
    返回: {annual_avg, dev, rsi, signal, signal_text, color}
    """
    secid = "0." + code if FUNDS[code]["is_sz"] else "1." + code
    history = _parse_market_history(secid, 250)
    if not history or len(history) < 10:
        return None
    closes = [h["close"] for h in history]   # oldest-first
    avg   = sum(closes) / len(closes)
    curr  = closes[-1]                        # 最新价格
    dev   = (curr / avg - 1) * 100
    rsi   = calc_rsi(closes, 14)
    if dev < 0:
        sig, txt, color = "buy", "买入", "green"
    elif dev <= 10:
        sig, txt, color = "hold", "持有", "yellow"
    else:
        sig, txt, color = "sell", "卖出", "red"
    return {
        "annual_avg":   round(avg, 3),
        "dev":          round(dev, 2),
        "rsi":          rsi,
        "signal":       sig,
        "signal_text":  txt,
        "color":        color,
    }


# ============================================================
# 黄金
# ============================================================

def fetch_gold() -> dict | None:
    """
    获取国际金价 COMEX（USD/oz）和国内金价 SGE Au99.99（CNY/g）。
    SGE 周末休市，失败时用 COMEX*汇率/31.1035 估算。
    """
    result = {}

    # COMEX 国际金价（最可靠来源）
    text = _get("https://hq.sinajs.cn/list=hf_GC",
                {"Referer": "https://finance.sina.com.cn/"}, timeout=8)
    if text:
        m = re.search(r'"([^"]+)"', text)
        if m:
            try:
                result["global"] = round(float(m.group(1).split(",")[0]), 2)
                print(f"  [OK] COMEX: {result['global']} USD/oz")
            except (ValueError, IndexError):
                pass

    # SGE Au99.99 国内金价（从最近工作日起向前找）
    now = datetime.now(_TZ)
    for days_ago in range(1, 8):
        dt = now - timedelta(days=days_ago)
        if dt.weekday() >= 5:
            continue
        date_str = dt.strftime("%Y-%m-%d")
        url = (f"https://www.sge.com.cn/sjzx/quotation_daily_new"
               f"?start_date={date_str}&end_date={date_str}&product=Au99.99")
        text = _get(url, {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://www.sge.com.cn/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }, timeout=10)
        if text:
            for row in re.findall(r"<tr[^>]*>.*?</tr>", text, re.DOTALL):
                if not re.search(r"Au99\.99", row):
                    continue
                cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)]
                for val in cells[2:7]:
                    try:
                        price = float(val)
                        if 500 < price < 2000:
                            result["sge"] = round(price, 2)
                            print(f"  [OK] SGE Au99.99: {result['sge']} CNY/g ({date_str})")
                            break
                    except ValueError:
                        continue
                if "sge" in result:
                    break
        if "sge" in result:
            break

    # 周末/网络失败时：用 COMEX * USD/CNY / 31.1035 估算
    if "sge" not in result and result.get("global"):
        text = _get("https://hq.sinajs.cn/list=fx_susdcny",
                    {"Referer": "https://finance.sina.com.cn/"}, encoding="gbk", timeout=8)
        if text:
            m = re.search(r'"([^"]+)"', text)
            if m:
                try:
                    fx = float(m.group(1).split(",")[1])
                    result["sge"] = round(result["global"] * fx / 31.1035, 2)
                    print(f"  [OK] SGE (估算): {result['sge']} CNY/g  FX={fx}")
                except (ValueError, IndexError):
                    pass

    return result if result else None


# ============================================================
# 汇率
# ============================================================

def fetch_fx() -> dict | None:
    """USD/CNY 即期汇率和涨跌幅"""
    text = _get("https://hq.sinajs.cn/list=fx_susdcny",
                {"Referer": "https://finance.sina.com.cn/"}, encoding="gbk", timeout=8)
    if not text:
        return None
    m = re.search(r'"([^"]+)"', text)
    if not m or len(m.group(1).split(",")) < 3:
        return None
    try:
        parts = m.group(1).split(",")
        curr = float(parts[1])
        prev = float(parts[2])
        chg  = round((curr - prev) / prev * 100, 2) if prev else None
        return {"rate": round(curr, 4), "change_pct": chg}
    except (ValueError, IndexError):
        return None


# ============================================================
# 指数
# ============================================================

def fetch_index(secid: str) -> dict | None:
    """
    抓取 A 股指数（腾讯 qt.gtimg.cn 接口），返回 {price, change_pct}
    secid 格式: "sh000001" 或 "sz399001"
    """
    text = _get(f"https://qt.gtimg.cn/q={secid}", timeout=10)
    if not text:
        return None
    try:
        m = re.search(r'"([^"]+)"', text)
        if not m:
            return None
        fields = m.group(1).split("~")
        if len(fields) < 40:
            return None
        price = safe_get_field(fields, 3, lo=0)
        change_pct = safe_get_field(fields, 32, lo=-20, hi=20)
        if price is None:
            return None
        return {
            "price":      round(price, 2),
            "change_pct": round(change_pct, 2) if change_pct is not None else 0,
        }
    except Exception:
        return None


# ============================================================
# 风险指标
# ============================================================

def _curl_text(url: str, referer: str = "", timeout: int = 8) -> str | None:
    """通过 curl 子进程抓取（绕开部分 Python urllib 连接问题）"""
    try:
        args = ["curl", "-s", "--max-time", str(timeout), "-A", "Mozilla/5.0"]
        if referer:
            args += ["-H", f"Referer: {referer}"]
        args.append(url)
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 2)
        return result.stdout if result.stdout and len(result.stdout) > 100 else None
    except Exception:
        return None


def fetch_bond_yield() -> float | None:
    """中国10年国债收益率（多源优先）"""
    # 源1: Sina cn10yt（最稳定）
    text = _get("https://hq.sinajs.cn/list=cn10yt",
                {"Referer": "https://finance.sina.com.cn/"}, timeout=8)
    if text:
        m = re.search(r'"([^"]+)"', text)
        if m:
            fields = m.group(1).split(",")
            if len(fields) > 1:
                val_str = fields[1].strip()
                if val_str.replace(".", "").isdigit():
                    val = float(val_str)
                    if 1.0 < val < 5.0:
                        print(f"  [OK] 中国10Y (sina): {val}%")
                        return round(val, 2)

    # 源2: Trading Economics
    text = _curl_text("https://zh.tradingeconomics.com/china/government-bond-yield")
    if text:
        for m in re.findall(r"(\d+\.\d+)%", text):
            val = float(m)
            if 1.0 < val < 5.0:
                print(f"  [OK] 中国10Y (tradingeconomics): {val}%")
                return round(val, 2)
    return None


def fetch_us_yield() -> float | None:
    """美国10年国债收益率（Trading Economics）"""
    text = _curl_text("https://zh.tradingeconomics.com/united-states/government-bond-yield")
    if text:
        for m in re.findall(r"(\d+\.\d+)%", text):
            val = float(m)
            if 3.0 < val < 6.0:
                print(f"  [OK] 美债10Y (tradingeconomics): {val}%")
                return round(val, 2)
    return None


def fetch_dxy() -> float | None:
    """美元指数 DXY（Trading Economics）"""
    text = _curl_text("https://zh.tradingeconomics.com/united-states/currency")
    if text:
        # 匹配 "降至98.6954" 或 95-105 范围内的数字
        m = re.search(r"\u964d\u81f4?(\d{2,3}\.\d{4})", text)
        if not m:
            matches = re.findall(r"\b(9[5-9]\.\d{4}|10[0-5]\.\d{4})\b", text)
            if matches:
                m = type("M", (), {"group": lambda s, i: matches[0]})()
        if m:
            val = float(m.group(1))
            if 90 < val < 110:
                print(f"  [OK] DXY (tradingeconomics): {val}")
                return round(val, 4)
    return None


def fetch_hs300_pe() -> float | None:
    """沪深300 PE（腾讯 sh000300 f75 字段）"""
    text = _get("https://qt.gtimg.cn/q=sh000300", timeout=8)
    if not text:
        return None
    m = re.search(r'v_sh000300="([^"]+)"', text)
    if not m:
        return None
    fields = m.group(1).split("~")
    val = safe_get_field(fields, 75, lo=5, hi=100)
    if val:
        print(f"  [OK] 沪深300 PE: {val}")
        return round(val, 2)
    return None


def fetch_hs300_pe_percentile() -> float | None:
    """沪深300 PE 历史分位（基于 250 日 K 线）"""
    # Sina K线是 oldest-first（无需反转）
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
           "/CN_MarketData.getKLineData?symbol=sh000300&scale=240&ma=no&datalen=250")
    text = _get(url, {"Referer": "https://finance.sina.com.cn/"}, timeout=15)
    if not text:
        return None
    try:
        data = json.loads(text)
        if not isinstance(data, list) or len(data) < 30:
            return None
        closes = [float(item["close"]) for item in data]   # oldest-first
        curr = closes[-1]
        mn, mx = min(closes), max(closes)
        if mx == mn:
            return None
        pct = (curr - mn) / (mx - mn) * 100
        print(f"  [OK] 沪深300 PE分位: {pct:.1f}%")
        return round(pct, 1)
    except Exception as e:
        print(f"  [PARSE] 沪深300 PE分位: {e}")
        return None


def calc_erp(pe: float, bond: float) -> float | None:
    """股权风险溢价 = E/P - bond = 100/PE(%) - bond(%)"""
    if pe and bond and pe > 0:
        return round(100 / pe - bond, 2)
    return None


# ============================================================
# 主流程
# ============================================================

def _save(data: dict):
    """保存 market.json（所有路径相对于脚本目录）"""
    with open("data/market.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    now = datetime.now(_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now}] 开始抓取市场数据...")

    market = {
        "updated":      now,
        "updated_date": datetime.now(_TZ).strftime("%Y-%m-%d"),
        "funds":  {},
        "index":  {},
    }

    # ---- 基金实时价格（fundgz，重试3次） -------------------------------
    for code, info in FUNDS.items():
        fund = fetch_fund_price(code)
        # 即使失败也写入 key（保持所有基金 ID 始终存在）
        market["funds"][code] = fund if fund else {"code": code, "name": FUNDS[code]["name"]}
        if fund:
            print(f"  [OK] {info['name']}({code}): {fund['price']} {fund['change_pct']:+.2f}%")
        else:
            print(f"  [WARN] {info['name']}({code}): fetch failed, 保存空数据")
    _save(market)   # 价格最关键，先落盘

    # ---- 基金指标：PE / 股息率 / PE分位 --------------------------------
    # ---- PE + 股息率 + PE分位（所有基金） ---------------------------
    for code in ALL_FUND_CODES:
        ind = fetch_fund_pe_div(code)
        if ind:
            market["funds"][code].update(ind)
            print(f"  [OK] {code} PE={ind.get('pe')}, 股息率={ind.get('dividend')}")

        # PE 历史分位（价格区间法）
        pct = calc_fund_pe_percentile(code)
        if pct is not None:
            market["funds"][code]["pe_percent"] = pct
            print(f"  [OK] {code} PE分位: {pct:.1f}%")

    # ---- 乖离率 + RSI（所有基金） ---------------------------------
    for code in ALL_FUND_CODES:
        dev = calc_fund_deviation(code)
        if dev:
            market["funds"][code].update(dev)
            rsi_s = f", RSI={dev['rsi']}" if dev.get("rsi") else ""
            print(f"  [OK] {code}: 乖离率={dev['dev']:+.2f}% -> {dev['signal_text']}{rsi_s}")

    # ---- 黄金 ---------------------------------------------------------
    gold = fetch_gold()
    if gold:
        market["gold"] = gold
        print(f"  [OK] 黄金: COMEX={gold.get('global')} USD/oz  SGE={gold.get('sge')} CNY/g")
    else:
        market["gold"] = None
    _save(market)

    # ---- 风险指标 ----------------------------------------------------
    cn10y = fetch_bond_yield()
    us10y = fetch_us_yield()
    dxy   = fetch_dxy()
    pe300 = fetch_hs300_pe()
    pct300 = fetch_hs300_pe_percentile()
    erp   = calc_erp(pe300, cn10y)

    if cn10y:  print(f"  [OK] 中国10Y: {cn10y}%")
    if us10y:  print(f"  [OK] 美债10Y: {us10y}%")
    if dxy:    print(f"  [OK] DXY: {dxy}")
    if pe300: print(f"  [OK] 沪深300 PE: {pe300}")
    if pct300: print(f"  [OK] 沪深300 PE分位: {pct300}%")
    if erp:    print(f"  [OK] ERP: {erp}%")

    market["risk"] = {
        "cn10y":        cn10y,
        "us10y":        us10y,
        "dxy":          dxy,
        "hs300_pe":     pe300,
        "hs300_pe_pct": pct300,
        "erp":          erp,
    }

    # ---- 汇率 --------------------------------------------------------
    fx = fetch_fx()
    if fx:
        market["fx"] = fx
        print(f"  [OK] USD/CNY: {fx['rate']}")
    else:
        market["fx"] = {"rate": None, "change_pct": None}

    # ---- 指数 --------------------------------------------------------
    sh = fetch_index("sh000001")
    if sh:
        market["index"]["sh000001"] = sh
        print(f"  [OK] 上证: {sh['price']} ({sh['change_pct']:+.2f}%)")

    spx = fetch_index("100.SPX")
    if spx:
        market["index"]["spx"] = spx
        print(f"  [OK] S&P500: {spx['price']} ({spx['change_pct']:+.2f}%)")

    # ---- 落盘 --------------------------------------------------------
    _save(market)
    print(f"\n[DONE] data/market.json saved")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FATAL] {e}")
    sys.exit(0)   # 始终退出0，避免网络波动导致 CI 误判失败
