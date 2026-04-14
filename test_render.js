const fs = require('fs');
const html = fs.readFileSync('/home/node/.openclaw/workspace/permanent-portfolio/index.html', 'utf8');
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
  addEventListener: () => {}, appendChild: () => {}, removeChild: () => {},
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
  body: { appendChild: () => {}, style: {} },
  documentElement: { style: {} },
};

global.Chart = class { constructor() {} update() {} destroy() {} };
global.window = global;

const data = JSON.parse(fs.readFileSync('/home/node/.openclaw/workspace/permanent-portfolio/data/market.json', 'utf8'));

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
  check('gold-cny-price', el('gold-cny-price').textContent.length > 0, el('gold-cny-price').textContent);
  check('fx-price', el('fx-price').textContent.length > 0, el('fx-price').textContent);

  if (!pass) process.exit(1);
} catch(e) {
  console.error('❌ ERROR:', e.message);
  console.error(e.stack.split('\n').slice(0,6).join('\n'));
  process.exit(1);
}
