#!/usr/bin/env python3
"""
永久组合数据获取脚本
抓取各ETF最新行情数据，输出 market.json
"""

import json
import urllib.request
import ssl
import os
import re
from datetime import datetime, timezone, timedelta

# 北京时间（UTC+8）
os.environ['TZ'] = 'Asia/Shanghai'
_tz = timezone(timedelta(hours=8))

# 忽略 SSL 证书验证
ssl._create_default_https_context = ssl._create_unverified_context

FUNDS = {
    "159222": {"name": "自由现金流ETF", "target": 0.70},
    "563020": {"name": "红利低波", "target": 0.20},
    "513650": {"name": "标普500ETF", "target": 0.20},
    "518680": {"name": "黄金ETF", "target": 0.10},
}

def fetch_fund_data(code: str) -> dict:
    """从天天基金网获取单个基金数据"""
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
        print(f"获取 {code} 失败: {e}")
        return None

def fetch_sge_gold_price() -> float:
    """获取上海黄金交易所（SGE）现货金价（元/克），通过COMEX国际金价+USD/CNY换算"""
    try:
        # 获取国际金价（COMEX黄金，美元/盎司）
        url_gold = "https://hq.sinajs.cn/list=hf_GC"
        req_gold = urllib.request.Request(url_gold, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn/"
        })
        with urllib.request.urlopen(req_gold, timeout=8) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        m = re.search(r'"([^"]+)"', text)
        if not m:
            return None
        parts = m.group(1).split(",")
        usd_per_oz = float(parts[0])
        # 获取USD/CNY
        url_fx = "https://hq.sinajs.cn/list=fx_susdcny"
        req_fx = urllib.request.Request(url_fx, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn/"
        })
        with urllib.request.urlopen(req_fx, timeout=8) as resp:
            text = resp.read().decode("gbk", errors="ignore")
        m2 = re.search(r'"([^"]+)"', text)
        if not m2:
            return None
        fx_parts = m2.group(1).split(",")
        usd_cny = float(fx_parts[1])
        # 换算：USD/oz → CNY/g（1 troy oz = 31.1035 g）
        cny_per_g = usd_per_oz * usd_cny / 31.1035
        return round(cny_per_g, 2)
    except Exception as e:
        print(f"获取SGE黄金价格失败: {e}")
        return None


def fetch_usd_cny_rate() -> dict:
    """获取美元兑人民币汇率（实时，在岸人民币）"""
    # 新浪财经外汇接口
    url = "https://hq.sinajs.cn/list=fx_susdcny"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn/"
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read().decode("gbk", errors="ignore")
        # 格式: "时间,当前价,昨收,当前,...,在岸人民币,涨跌,涨跌幅,..."
        m = re.search(r'"([^"]+)"', text)
        if m:
            parts = m.group(1).split(",")
            if len(parts) > 1 and parts[1]:
                rate = float(parts[1])
                if 5 < rate < 10:
                    change_pct = None
                    if len(parts) > 2:
                        try:
                            prev = float(parts[2])  # 昨收
                            curr = float(parts[1])  # 当前价
                            change_pct = round((curr - prev) / prev * 100, 2)
                        except (ValueError, IndexError):
                            pass
                    return {"rate": round(rate, 4), "change_pct": change_pct}
    except Exception as e:
        print(f"获取USD/CNY汇率失败: {e}")
    return None


def fetch_fund_nav_and_info(code: str) -> dict:
    """获取场内基金实时行情（从东方财富场内基金接口）"""
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{code}&fields=f43,f170"
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
        return {
            "price": round(float(f43) / 100, 4),
            "change_pct": round(float(f170) / 100, 2),
        }
    except Exception as e:
        print(f"获取 {code} 场内基金数据失败: {e}")
        return None

def fetch_fund_div_yield(code: str) -> float:
    """从天天基金网获取基金股息率"""
    url = f"https://fundgz.1234567.com.cn/js/{code}.js"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8")
        text = text.replace("jsonpgz(", "").rstrip(");")
        data = json.loads(text)
        # 天天基金的股息率字段
        dividend = data.get("dwjz", 0)  # 单位净值，股息率需要额外计算
        # 尝试从基金概况页面获取
        url2 = f"https://fund.10jqka.com.cn/{code}/fundinfo.html"
        req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            html = resp2.read().decode("utf-8")
        m = re.search(r'股息率[^>]*?>([^<]+)%', html)
        if m:
            return float(m.group(1))
    except Exception as e:
        print(f"获取 {code} 股息率失败: {e}")
    return None

def fetch_index_data(code: str, name: str = "上证指数") -> dict:
    """获取指数数据"""
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{code}&fields=f43,f169,f170,f171"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        fields = data.get("data", {})
        return {
            "code": code,
            "name": name,
            "price": fields.get("f43", 0) / 100,
            "change_pct": round(fields.get("f170", 0) / 100, 2),
        }
    except Exception as e:
        print(f"获取指数 {code} 失败: {e}")
        return None

def fetch_us_index_data(secid: str, name: str) -> dict:
    """获取美股指数数据（SPX等）"""
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f169,f170,f171"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        fields = data.get("data", {})
        return {
            "code": secid,
            "name": name,
            "price": fields.get("f43", 0) / 100,
            "change_pct": round(fields.get("f170", 0) / 100, 2),
        }
    except Exception as e:
        print(f"获取 {name}({secid}) 失败: {e}")
        return None

def fetch_nav_history(code: str, days: int = 250) -> list:
    """获取历史净值，用于计算年线"""
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid=1.{code}&fields1=f1,f2,f3,f4,f5,f6"
           f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
           f"&klt=101&fqt=1&end=20500101&lmt={days}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        klines = data.get("data", {}).get("klines", [])
        result = []
        for line in klines:
            parts = line.split(",")
            result.append({"date": parts[0], "close": float(parts[2])})
        return result
    except Exception as e:
        print(f"获取 {code} 历史净值失败: {e}")
        return []

def calc_annual_avg_deviation(code: str) -> dict:
    """计算年线偏离度（年线收益差）"""
    history = fetch_nav_history(code, days=250)
    if not history or len(history) < 10:
        return None
    closes = [h["close"] for h in history]
    annual_avg = sum(closes) / len(closes)
    current_price = closes[-1]
    deviation = (current_price / annual_avg - 1) * 100
    if deviation < 0:
        signal, signal_text, color = "buy", "买入", "green"
    elif deviation <= 10:
        signal, signal_text, color = "hold", "持有", "yellow"
    else:
        signal, signal_text, color = "sell", "卖出", "red"
    return {
        "price": round(current_price, 3),
        "annual_avg": round(annual_avg, 3),
        "deviation": round(deviation, 2),
        "signal": signal,
        "signal_text": signal_text,
        "color": color,
    }

def fetch_10y_china_bond_yield() -> float:
    """获取中国10年期国债收益率（实时）"""
    # 方法1：东方财富债券行情
    # 019547 是10年期国债（代码可能随时间变化，这里用活跃券）
    codes = ["019547", "019547", "T2506", "T2509"]
    for secid in codes:
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{secid}&fields=f43,f170"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            fields = data.get("data", {})
            rate = fields.get("f43", 0)
            if rate and 1 < rate < 10:  # 国债收益率通常在1%-4%之间
                return round(rate / 100, 4)
        except Exception:
            pass
    # 方法2：中债国债收益率曲线（chinamoney）
    try:
        url2 = "https://www.chinamoney.com.cn/ags/ms/cm-u-bond-md/CurveCsv?nameCode=PY1026"
        req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            text = resp2.read().decode("utf-8")
        for line in text.split('\n'):
            if '"value"' in line or "'value'" in line:
                m = re.search(r'["\']?value["\']?\s*[:=]\s*["\']?([0-9.]+)', line)
                if m:
                    val = float(m.group(1))
                    if 1 < val < 10:
                        return round(val, 4)
    except Exception as e:
        print(f"中债曲线获取失败: {e}")
    return None

def fetch_563020_dividend_yield() -> float:
    """获取563020红利低波ETF的股息率"""
    # 从天天基金网基本信息获取
    url = "https://fundgz.1234567.com.cn/js/563020.js"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8")
        text = text.replace("jsonpgz(", "").rstrip(");")
        data = json.loads(text)
        name = data.get("name", "")
        # 尝试从东方财富获取股息率
        url2 = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.563020&fields=f10,f12,f14"
        req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            data2 = json.loads(resp2.read().decode("utf-8"))
        fields2 = data2.get("data", {})
        # f10 通常是股息率
        div = fields2.get("f10", 0)
        if div:
            return round(float(div), 2)
    except Exception as e:
        print(f"获取563020股息率失败: {e}")
    # 备用：直接抓东财基金概况页
    try:
        url3 = "https://fundf10.eastmoney.com/jjjz_563020.html"
        req3 = urllib.request.Request(url3, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req3, timeout=10) as resp3:
            html = resp3.read().decode("utf-8")
        m = re.search(r'股息率[^>]*?>([^<]+)%', html)
        if m:
            return round(float(m.group(1)), 2)
    except Exception as e:
        print(f"备用股息率获取也失败: {e}")
    return None

def main():
    print(f"[{datetime.now(_tz).strftime('%Y-%m-%d %H:%M:%S')}] 开始抓取数据...")

    market = {
        "updated": datetime.now(_tz).strftime("%Y-%m-%d %H:%M:%S"),
        "updated_date": datetime.now(_tz).strftime("%Y-%m-%d"),
        "funds": {},
        "index": {},
    }

    # 抓取基金数据
    for code, info in FUNDS.items():
        fund = fetch_fund_data(code)
        if fund:
            market["funds"][code] = fund
            print(f"  ✅ {info['name']}({code}): {fund['price']} ({fund['change_pct']:+.2f}%)")

    # 抓取场内基金数据（513650 SPX、518680 黄金ETF）
    for code, name in [("513650", "标普500ETF"), ("518680", "黄金ETF")]:
        ind = fetch_fund_nav_and_info(code)
        if ind:
            market["funds"][code] = market["funds"].get(code, {})
            market["funds"][code].update(ind)
            print(f"  ✅ {name}({code}): {ind['price']} ({ind['change_pct']:+.2f}%)")

    # 计算 563020 红利低波的年线偏离度
    print(f"\n[{datetime.now(_tz).strftime('%Y-%m-%d %H:%M:%S')}] 计算 563020 年线偏离度...")
    result = calc_annual_avg_deviation("563020")
    if result:
        market["funds"]["563020"] = market["funds"].get("563020", {})
        market["funds"]["563020"].update({
            "price": result["price"],
            "annual_avg": result["annual_avg"],
            "dev": result["deviation"],
            "signal": result["signal"],
            "signal_text": result["signal_text"],
            "color": result["color"],
            "name": "红利低波",
        })
        print(f"  ✅ 563020 年线偏离度: {result['deviation']:+.2f}% → {result['signal_text']}（{result['color']}）")

    # 获取10年期国债收益率
    print(f"\n[{datetime.now(_tz).strftime('%Y-%m-%d %H:%M:%S')}] 获取10年期国债收益率...")
    bond_yield = fetch_10y_china_bond_yield()

    # 获取563020股息率
    div_yield = fetch_563020_dividend_yield()
    market["risk"] = {
        "rate": bond_yield,
        "dividend": div_yield,
    }
    if bond_yield:
        print(f"  ✅ 10年国债收益率: {bond_yield:.4f}%")
    else:
        print(f"  ⚠️ 10年国债收益率获取失败")
    if div_yield:
        print(f"  ✅ 563020 股息率: {div_yield:.2f}%")
    else:
        print(f"  ⚠️ 563020 股息率获取失败")

    # 抓取上证指数
    sh = fetch_index_data("000001")
    if sh:
        market["index"]["sh000001"] = sh
        print(f"\n  ✅ 上证指数: {sh['price']} ({sh['change_pct']:+.2f}%)")

    # 抓取美元兑人民币汇率
    print(f"\n[{datetime.now(_tz).strftime('%Y-%m-%d %H:%M:%S')}] 获取美元汇率...")
    usd_cny = fetch_usd_cny_rate()
    if usd_cny:
        market["fx"] = usd_cny
        print(f"  ✅ 美元/人民币: {usd_cny['rate']:.4f}")
    else:
        market["fx"] = {"rate": None, "change_pct": None}

    # 抓取国内黄金现货价格
    print(f"\n[{datetime.now(_tz).strftime('%Y-%m-%d %H:%M:%S')}] 获取国内黄金价格...")
    gold_cny = fetch_sge_gold_price()
    if gold_cny:
        market["gold_cny"] = gold_cny
        print(f"  ✅ 国内黄金(SGE): {gold_cny:.2f} 元/克")
    else:
        market["gold_cny"] = None

    # 抓取 S&P 500 指数
    spx = fetch_us_index_data("100.SPX", "S&P 500")
    if spx:
        market["index"]["spx"] = spx
        print(f"  ✅ S&P 500: {spx['price']} ({spx['change_pct']:+.2f}%)")

    # 写入 JSON 文件
    output_path = "data/market.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(market, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 数据已保存至 {output_path}")

if __name__ == "__main__":
    main()
