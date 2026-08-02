import { chromium } from 'playwright';

const G = 'file://' + process.argv[2] + '/preview/index.html';
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 950 } });
const p = await ctx.newPage();
const errs = [];
p.on('pageerror', e => errs.push(String(e).slice(0, 160)));
await p.goto(G, { waitUntil: 'load' });

const swatches = await p.$$eval('#pallist [role=option] .sw',
  els => els.map(e => getComputedStyle(e).backgroundColor));
console.log('rows with a swatch colour:', swatches.length, swatches);

await p.click('#palbtn');
console.log('expanded:', await p.getAttribute('#palbtn', 'aria-expanded'));

// Keyboard: Down then Enter must select the second palette.
await p.keyboard.press('ArrowDown');
await p.keyboard.press('Enter');
await p.waitForTimeout(400);
console.log('after Down+Enter:', await p.textContent('#palbtn'));
console.log('collapsed again:', await p.getAttribute('#palbtn', 'aria-expanded'));

// The frame must actually be the new palette, which means the sidecar loaded.
const bg = await p.evaluate(() =>
  getComputedStyle(document.querySelector('iframe').contentDocument.body).backgroundColor);
console.log('frame background:', bg);

await p.click('#palbtn');
await p.keyboard.press('Escape');
console.log('Esc collapsed:', await p.getAttribute('#palbtn', 'aria-expanded'));
console.log('focus returned to button:',
  await p.evaluate(() => document.activeElement.id === 'palbtn'));

// The two axes are independent: nyan pins its own palette, and selecting it
// must NOT drag the palette dropdown onto that pin. The build produces every
// combination precisely so the reviewer chooses, and a control that moves on
// its own is the kind of surprise that makes a toolbar untrustworthy.
const before = await p.textContent('#palbtn');
await p.selectOption('select[data-theme]', 'nyan');
await p.waitForTimeout(400);
const after = await p.textContent('#palbtn');
console.log('palette unmoved by style change:', before === after, `(${before.trim()})`);

console.log('js errors:', errs.length ? errs : 'none');
await b.close();
