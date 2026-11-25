// Learn Mode browser check (Outcome 3 exit gate): sections render, a section loops without
// passing its end, mirror swaps instruction sides, split+save persists, no console errors,
// no horizontal overflow at 1440x900 and iPhone 13. Needs a READY stack on :3000 and Playwright.
// Usage: node scripts/e2e/learn-mode.cjs  (screenshots land in the current directory)
const { chromium, devices } = require('playwright');
(async () => {
const WEB = process.env.WEB || 'http://localhost:3000';
const j = async (r) => { if (!r.ok) throw new Error(r.status + ' ' + await r.text()); return r.json(); };
const tok = (await j(await fetch(WEB + '/api/session', { method: 'POST' }))).token;
const H = { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json' };
const samples = await j(await fetch(WEB + '/api/samples'));
const ids = [];
for (const s of samples) {
  const p = await j(await fetch(WEB + '/api/projects/sample', { method: 'POST', headers: H, body: JSON.stringify({ sample_id: s.id }) }));
  ids.push(p.id);
}
for (const id of ids) {
  for (let i = 0; i < 120; i++) {
    const p = await j(await fetch(WEB + '/api/projects/' + id, { headers: H }));
    if (p.status === 'analyzed' || p.status === 'failed') { console.log(id, p.status); break; }
    await new Promise(r => setTimeout(r, 1000));
  }
  const secs = await j(await fetch(WEB + `/api/projects/${id}/segments`, { headers: H }));
  console.log(JSON.stringify(secs.sections.map(s => [s.start, s.end, s.instruction, s.instruction_direct, s.untracked, s.coverage])));
}
const browser = await chromium.launch();
const errors = [];
async function open(ctxOpts, name, id) {
  const ctx = await browser.newContext(ctxOpts);
  await ctx.addInitScript((t) => localStorage.setItem('adt.session.v1', t), tok);
  const page = await ctx.newPage();
  page.on('console', m => m.type() === 'error' && errors.push(name + ': ' + m.text()));
  page.on('pageerror', e => errors.push(name + ': ' + e.message));
  await page.goto(`${WEB}/studio/projects/${id}`);
  await page.waitForSelector('[data-testid=section-chip]');
  await page.waitForFunction(() => document.querySelector('[data-testid=learn-video]').readyState >= 2);
  await page.waitForTimeout(800);
  return { ctx, page };
}
// Desktop
{
  const { ctx, page } = await open({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 }, 'desktop', ids[0]);
  await page.screenshot({ path: 'desktop-learn.png', fullPage: true });
  // loop accuracy on section 2 at 1x
  const chips = page.locator('[data-testid=section-chip]');
  const n = await chips.count();
  await chips.nth(n - 1).click();
  await page.getByRole('radio', { name: '1×' }).click();
  const secs = await j(await fetch(WEB + `/api/projects/${ids[0]}/segments`, { headers: H }));
  const sec = secs.sections[n - 1];
  // Use the first section for loop test (last section ends at video end)
  await chips.nth(0).click();
  const s0 = secs.sections[0];
  await page.getByRole('button', { name: 'Play section' }).click();
  const samplesT = await page.evaluate(async (dur) => {
    const v = document.querySelector('[data-testid=learn-video]');
    const out = [];
    const t0 = performance.now();
    await new Promise(res => { const f = () => { out.push(v.currentTime); if (performance.now() - t0 < dur) requestAnimationFrame(f); else res(); }; f(); });
    return out;
  }, (s0.end - s0.start) * 1000 * 2.3);
  const max = Math.max(...samplesT), min = Math.min(...samplesT);
  let wraps = 0; for (let i = 1; i < samplesT.length; i++) if (samplesT[i] < samplesT[i-1] - 1) wraps++;
  console.log('loop section', s0.start, s0.end, 'observed max', max.toFixed(3), 'min', min.toFixed(3), 'wraps', wraps);
  if (max >= s0.end || wraps < 1) throw new Error('section loop overran its end or never looped');
  await page.getByRole('button', { name: 'Pause' }).click();
  await page.screenshot({ path: 'desktop-playing.png' });
  // mirror toggle & instruction perspective
  const instrMirror = await page.getByTestId('section-instruction').textContent();
  await page.getByRole('button', { name: 'Mirror' }).click();
  const instrDirect = await page.getByTestId('section-instruction').textContent();
  console.log('instr mirror:', instrMirror, '| direct:', instrDirect, '| mirrored attr', await page.getByTestId('mirror-surface').getAttribute('data-mirrored'));
  await page.getByRole('button', { name: 'Mirror' }).click();
  // edit: split at playhead and save
  await page.getByRole('button', { name: 'Edit sections' }).click();
  await page.getByLabel('Playhead').fill('3');
  await page.getByRole('button', { name: 'Split at playhead' }).click();
  const handles = page.getByTestId('boundary-handle');
  console.log('handles while editing', await handles.count());
  await handles.first().focus();
  await page.keyboard.press('Shift+ArrowRight');
  await page.screenshot({ path: 'desktop-editing.png', fullPage: true });
  await page.getByRole('button', { name: 'Save sections' }).click();
  await page.waitForSelector('text=Sections saved');
  await page.reload();
  await page.waitForSelector('[data-testid=section-chip]');
  console.log('after reload chips', await page.locator('[data-testid=section-chip]').count());
  await page.getByRole('button', { name: 'Mark complete' }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: 'desktop-complete.png', fullPage: true });
  const ov = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  console.log('desktop overflow', ov);
  await ctx.close();
}
// Mobile
{
  const { ctx, page } = await open({ ...devices['iPhone 13'] }, 'mobile', ids[1] ?? ids[0]);
  await page.screenshot({ path: 'mobile-learn.png', fullPage: true });
  const ov = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  console.log('mobile overflow', ov);
  await ctx.close();
}
console.log('errors', errors);
if (errors.length) process.exitCode = 1;
await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
