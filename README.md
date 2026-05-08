# 永久组合 Dashboard

基于规则的 ETF 智能仓位管理 Dashboard，实时监控红利、纳指等核心资产的交易信号与风险状态。

## 功能特性

- 实时行情：打开页面即从浏览器端刷新 ETF、指数、黄金、汇率和风险指标
- 持仓 vs 目标配置可视化
- 风险红绿灯：中国/美国 10 年国债、沪深 300 估值分位、ERP、美元指数
- 一键刷新：页面内直接重新拉取实时数据，不跳转 GitHub Actions
- 严格实时：数据源临时失败时对应字段留空，不用历史数据或缓存补位

## 数据来源

- ETF / 指数行情：东方财富实时行情接口、腾讯行情接口
- 历史 K 线 / 乖离率 / RSI：东方财富 K 线接口
- 中美国债收益率：东方财富数据中心
- 黄金 / 标普500指数 / 美元指数：东方财富实时行情接口
- 标普500估值：US500 的 S&P 500 PE Ratio / Dividend Yield 数据
- 美元人民币：ExchangeRate API（浏览器 CORS 友好）
- 无需 API Key，不依赖 GitHub 定时任务

## 技术栈

- **前端**：原生 HTML/CSS/JS + Chart.js（CDN）
- **数据刷新**：浏览器端 JSONP / script 数据源聚合
- **CI/CD**：GitHub Pages 部署 workflow
- **托管**：GitHub Pages

## 部署

1. Fork 或克隆本仓库
2. 开启 GitHub Pages：`Settings → Pages → Source: GitHub Actions`
3. 推送到 `main` 后由 `deploy-pages` workflow 部署静态页面

## 数据口径

打开页面会自动刷新一次。点击右上角「刷新数据」会在当前页面重新拉取所有数据。

页面不使用 `data/market.json`、localStorage 或 GitHub Actions 产物作为兜底。任一数据源超时或失败时，该源负责的字段保持空值 `--`；所有实时源都失败时，整页行情留空。

## License

MIT
