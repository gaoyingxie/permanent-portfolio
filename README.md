# 永久组合 Dashboard

基于规则的 ETF 智能仓位管理 Dashboard，实时监控红利、纳指等核心资产的交易信号与风险状态。

## 功能特性

- 📊 实时行情：510880 红利ETF、512890 红利低波、纳指ETF
- 📈 持仓 vs 目标配置可视化
- 🚦 风险红绿灯：利率、股息率、波动性、信号频率
- 🔄 一键刷新：手动触发 GitHub Actions 重新抓取数据
- ⏰ 自动更新：每天 UTC 1:00（北京时间 9:00）自动抓取

## 数据来源

- 行情数据：[天天基金网](https://fund.eastmoney.com/)
- 无需 API Key，纯爬虫方式获取

## 技术栈

- **前端**：原生 HTML/CSS/JS + Chart.js（CDN）
- **数据脚本**：Python 3
- **CI/CD**：GitHub Actions
- **托管**：GitHub Pages

## 部署

1. Fork 或克隆本仓库
2. 开启 GitHub Pages：`Settings → Pages → Source: main`
3. 等待 Actions 自动运行（或手动触发 `update-data` workflow）

## 手动刷新数据

点击页面右上角「刷新数据」按钮，触发 GitHub Actions 重新抓取最新行情。

## License

MIT
