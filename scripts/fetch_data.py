#!/usr/bin/env python3
"""
永久组合数据获取脚本
抓取各ETF最新行情数据，输出 market.json
"""

import json
import urllib.request
import ssl
import os
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
    # 东方财富历史净值接口
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid=1.{code}&fields1=f1,f2,f3,f4,f5,f6"
           f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
           f"&klt=101&fqt=1&end=20500101&lmt={days}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        klines = data.get("data", {}).get("klines", [])
        # 每条格式: "日期,开盘,收盘,最高,最低,成交量,..."
        result = []
        for line in klines:
            parts = line.split(",")
            result.append({
                "date": parts[0],
                "close": float(parts[2]),
            })
        return result
    except Exception as e:
        print(f"获取 {code} 历史净值失败: {e}")
        return []

def calc_annual_avg_deviation(code: str) -> dict:
    """
    计算年线偏离度（年线收益差）
    规则：红利低波年线定投法
    - 年线收益差 < 0%  → 买入（绿）
    - 0% ≤ 年线收益差 ≤ 10% → 持有（黄）
    - 年线收益差 > 10% → 卖出（红）
    """
    history = fetch_nav_history(code, days=250)
    if not history or len(history) < 10:
        return None
    closes = [h["close"] for h in history]
    annual_avg = sum(closes) / len(closes)
    current_price = closes[-1]
    deviation = (current_price / annual_avg - 1) * 100  # 百分比
    if deviation < 0:
        signal, signal_text = "buy", "买入"
        color = "green"
    elif deviation <= 10:
        signal, signal_text = "hold", "持有"
        color = "yellow"
    else:
        signal, signal_text = "sell", "卖出"
        color = "red"
    return {
        "price": round(current_price, 3),
        "annual_avg": round(annual_avg, 3),
        "deviation": round(deviation, 2),
        "signal": signal,
        "signal_text": signal_text,
        "color": color,
        "history_count": len(history),
    }

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

    # 计算 563020 红利低波的年线偏离度（需要历史数据，先单独做）
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

    # 抓取上证指数
    sh = fetch_index_data("000001")
    if sh:
        market["index"]["sh000001"] = sh
        print(f"  ✅ 上证指数: {sh['price']} ({sh['change_pct']:+.2f}%)")

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
