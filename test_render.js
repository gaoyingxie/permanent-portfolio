const fs = require('fs');
const path = require('path');
const root = __dirname;
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const scripts = html.match(/<script[^>]*>([\s\S]*?)<\/script>/g) || [];
const js = scripts.map(s => s.replace(/<script[^>]*>/, '').replace(/<\/script>/, '')).join('\n\n');

const mkClassList = () => {
  const classes = new Set();
  return {
    add: (...c) => c.forEach(x => classes.add(x)),
    remove: (...c) => c.forEach(x => classes.delete(x)),
    contains: c => classes.has(c),
    toString: () => [...classes].join(' '),
  };
};

const mkEl = () => ({
  textContent: '', style: { color: '', fontSize: '' },
  classList: mkClassList(), className: '',
  value: '', innerHTML: '',
  addEventListener: () => {}, appendChild: () => {}, removeChild: () => {}, remove: () => {},
  getAttribute: () => null, setAttribute: () => {}, getContext: () => null,
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 20 }),
});

const dom = {};
const el = id => { if (!dom[id]) dom[id] = mkEl(); return dom[id]; };
const document = {
  getElementById: el,
  querySelector: () => mkEl(),
  addEventListener: () => {},
  createElement: () => mkEl(),
  head: { appendChild: () => {} },
  body: { appendChild: () => {}, style: {} },
  documentElement: { style: {} },
};

global.Chart = class { constructor() {} update() {} destroy() {} };
global.window = global;
global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };

const data = {
  updated: 'render test',
  funds: {
    '159222': { price: 1.395, change_pct: -0.21, dev: 12.96, rsi: 48.5, pe: 24.3, dividend: 3.69, pe_percent: 79, color: 'red', signal: 'sell', signal_text: '卖出' },
    '563020': { price: 1.185, change_pct: 0.08, dev: -0.42, rsi: 39.1, pe: 8.7, dividend: 2.22, pe_percent: 53.5, annual_avg: 1.19, color: 'green', signal: 'buy', signal_text: '买入' },
    '513650': { price: 1.839, change_pct: -0.11, dev: 8.27, rsi: 83.7, pe: 31.6, dividend: 1.07, pe_percent: 98.6, color: 'yellow', signal: 'hold', signal_text: '持有' },
    '518680': { price: 10.338, change_pct: -0.28, dev: 12.87, rsi: 40.2, color: 'red', signal: 'sell', signal_text: '卖出' },
  },
  index: {
    sh000001: { price: 4179.95, change_pct: 0 },
    spx: { price: 7385.34, change_pct: 0.3 },
  },
  gold: { global: 4733.7, sge: 1037.32 },
  fx: { rate: 6.8159, change_pct: null },
  risk: { hs300_pe_pct: 97.5, hs300_pe: 18.73, cn10y: 1.76, us10y: 4.41, dxy: 98.12, erp: 3.58 },
};

try {
  eval(js);
  console.log('✅ JS loaded without errors');

  renderData(data);
  console.log('✅ renderData completed');

  // Verify key elements
  let pass = true;
  const check = (name, cond, val) => {
    if (!cond) { pass = false; console.log('❌', name, '->', JSON.stringify(val)); }
    else console.log('✅', name);
  };

  check('price-159222', !el('price-159222').textContent.includes('--'), el('price-159222').textContent);
  check('dev-159222', el('dev-159222').textContent.includes('%'), el('dev-159222').textContent);
  check('signal-tag-563020', el('signal-tag-563020').textContent.length > 0, el('signal-tag-563020').textContent);
  check('etf-spx', !el('etf-spx').textContent.includes('--'), el('etf-spx').textContent);
  check('pe-513650', el('pe-513650').textContent === '31.6', el('pe-513650').textContent);
  check('dividend-513650', el('dividend-513650').textContent === '1.07%', el('dividend-513650').textContent);
  check('pe_pct-513650', el('pe_pct-513650').textContent === '98.6%', el('pe_pct-513650').textContent);
  check('gold-cny-price', el('gold-cny-price').textContent.length > 0, el('gold-cny-price').textContent);
  check('fx-price', el('fx-price').textContent.length > 0, el('fx-price').textContent);

  if (!pass) process.exit(1);
} catch(e) {
  console.error('❌ ERROR:', e.message);
  console.error(e.stack.split('\n').slice(0,6).join('\n'));
  process.exit(1);
}
