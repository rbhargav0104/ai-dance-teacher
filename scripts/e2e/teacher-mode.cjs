// Teacher Mode browser check (Outcome 4 exit gate, docs/SPEC_AMENDMENTS.md A1).
// On the real fixture clips analysed by the real pipeline:
//  - the 3D avatar renders (desktop 1440x900 and iPhone 13), screenshots at known timestamps;
//  - the rendered arm bones point where the measured world landmarks point at those timestamps
//    (mirror on and off), and untracked legs are ghosted + labelled, not animated;
//  - count-in, captions, play/loop, camera views, mark complete and next section work;
//  - no console errors, no horizontal overflow.
// Needs a READY stack on :3000 and Playwright. Usage: node scripts/e2e/teacher-mode.cjs [outdir]
const { chromium, devices } = require('playwright');
const path = require('path');
const OUT = process.argv[2] || '.';
const WEB = process.env.WEB || 'http://localhost:3000';
// Rendered bones are One-Euro smoothed; the expectation is the raw, unsmoothed landmark direction
// (incl. MediaPipe's noisy depth). So the typical error must be small, and no bone may be far off.
const MAX_MEDIAN_ERR_DEG = Number(process.env.MAX_MEDIAN_ERR_DEG || 8);
const MAX_ARM_ERR_DEG = Number(process.env.MAX_ARM_ERR_DEG || 30);

const MIRROR = (() => {
  const m = Array.from({ length: 33 }, (_, i) => i);
  for (const [a, b] of [[1, 4], [2, 5], [3, 6], [7, 8], [9, 10], [11, 12], [13, 14], [15, 16], [17, 18], [19, 20], [21, 22], [23, 24], [25, 26], [27, 28], [29, 30], [31, 32]]) { m[a] = b; m[b] = a; }
  return m;
})();
const ARMS = { upperArmL: [11, 13], forearmL: [13, 15], upperArmR: [12, 14], forearmR: [14, 16] };
const angle = (a, b) => {
  const n = (v) => Math.hypot(...v);
  const d = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) / (n(a) * n(b));
  return (Math.acos(Math.max(-1, Math.min(1, d))) * 180) / Math.PI;
};
/** Independent expectation straight from the raw API landmarks (no smoothing, no app code). */
function measuredDir(frame, bone, mirrored) {
  const [a, b] = ARMS[bone];
  const ia = mirrored ? MIRROR[a] : a;
  const ib = mirrored ? MIRROR[b] : b;
  const w = frame.data.world;
  if (!frame.valid || !w || !frame.data.reliable[ia] || !frame.data.reliable[ib]) return null;
  const sx = mirrored ? -1 : 1;
  // MediaPipe world (x right, y down, z away negative) -> avatar (y up, +z to camera), mirrored = negate x.
  return [sx * (w[ib][0] - w[ia][0]), -(w[ib][1] - w[ia][1]), -(w[ib][2] - w[ia][2])];
}

(async () => {
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
    for (let i = 0; i < 180; i++) {
      const p = await j(await fetch(WEB + '/api/projects/' + id, { headers: H }));
      if (p.status === 'analyzed') break;
      if (p.status === 'failed') throw new Error('sample analysis failed: ' + id);
      await new Promise((r) => setTimeout(r, 1000));
    }
  }

  const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--autoplay-policy=no-user-gesture-required'] });
  const errors = [];
  const failures = [];
  const check = (ok, msg) => { console.log((ok ? 'ok   ' : 'FAIL ') + msg); if (!ok) failures.push(msg); };

  async function open(ctxOpts, name, id) {
    const ctx = await browser.newContext(ctxOpts);
    await ctx.addInitScript((t) => localStorage.setItem('adt.session.v1', t), tok);
    const page = await ctx.newPage();
    page.on('console', (m) => m.type() === 'error' && errors.push(name + ': ' + m.text()));
    page.on('pageerror', (e) => errors.push(name + ': ' + e.message));
    await page.goto(`${WEB}/studio/projects/${id}`);
    await page.waitForSelector('[data-testid=avatar-stage] canvas', { timeout: 30000 });
    await page.waitForFunction(() => document.querySelector('[data-testid=learn-video]').readyState >= 2);
    await page.waitForFunction(() => (window.__adtAvatar?.frames ?? 0) > 5, null, { timeout: 30000 });
    return { ctx, page };
  }
  async function seekAndRead(page, t) {
    await page.evaluate(async (t) => {
      const v = document.querySelector('[data-testid=learn-video]');
      v.pause();
      await new Promise((res) => { v.addEventListener('seeked', res, { once: true }); v.currentTime = t; });
      const f0 = window.__adtAvatar?.frames ?? 0;
      await new Promise((res) => { const f = () => ((window.__adtAvatar?.frames ?? 0) > f0 + 2 ? res() : requestAnimationFrame(f)); f(); });
    }, t);
    return page.evaluate(() => window.__adtAvatar);
  }
  async function armCheck(page, poses, times, mirrored, label) {
    const errs = [];
    for (const t of times) {
      const dbg = await seekAndRead(page, t);
      check(dbg.mirrored === mirrored, `${label} t=${t}: stage mirrored=${dbg.mirrored}`);
      // nearest analysed frame to the debug time
      let best = poses.frames[0];
      for (const f of poses.frames) if (Math.abs(f.t - dbg.t) < Math.abs(best.t - dbg.t)) best = f;
      if (dbg.status !== 'tracked') { console.log(`     ${label} t=${t}: status ${dbg.status} (frame valid=${best.valid})`); continue; }
      const row = [];
      for (const bone of Object.keys(ARMS)) {
        const exp = measuredDir(best, bone, mirrored);
        const got = dbg.bones[bone];
        if (!exp) { row.push(`${bone}=untracked(${got.state})`); check(got.state !== 'measured', `${label} t=${t} ${bone}: unmeasured landmark not drawn as measured`); continue; }
        const e = angle(exp, got.dir);
        errs.push(e);
        row.push(`${bone}=${e.toFixed(1)}°`);
      }
      const legs = ['thighL', 'thighR', 'shinL', 'shinR'].map((b) => dbg.bones[b].state);
      console.log(`     ${label} t=${t.toFixed(2)} (frame ${best.t.toFixed(3)}): ${row.join(' ')} legs=${legs.join('/')}`);
      await page.locator('[data-testid=teacher-surface]').screenshot({ path: path.join(OUT, `avatar-${label}-t${t.toFixed(1)}.png`) });
    }
    errs.sort((a, b) => a - b);
    const med = errs[errs.length >> 1];
    const max = errs[errs.length - 1];
    console.log(`     ${label}: ${errs.length} arm bones compared, median ${med?.toFixed(1)}°, max ${max?.toFixed(1)}°`);
    check(errs.length >= 8, `${label}: at least 8 measured arm bones compared (${errs.length})`);
    check(med <= MAX_MEDIAN_ERR_DEG, `${label}: median rendered-vs-measured arm angle ${med?.toFixed(1)}° <= ${MAX_MEDIAN_ERR_DEG}°`);
    check(max <= MAX_ARM_ERR_DEG, `${label}: max rendered-vs-measured arm angle ${max?.toFixed(1)}° <= ${MAX_ARM_ERR_DEG}°`);
    return { med, max };
  }

  const TIMES = [1.0, 3.0, 5.5, 8.0, 10.5, 12.5];
  const results = {};
  for (const [k, id] of ids.entries()) {
    const poses = await j(await fetch(WEB + `/api/projects/${id}/poses`, { headers: H }));
    const { ctx, page } = await open({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 }, 'desktop' + k, id);
    if (k === 0) await page.screenshot({ path: path.join(OUT, 'teacher-desktop.png'), fullPage: true });
    const label = await page.locator('[data-testid=avatar-untracked]').textContent().catch(() => null);
    console.log('     untracked label:', label);
    results[id] = { mirror: await armCheck(page, poses, TIMES, true, `s${k}-mirror`) };
    await page.getByRole('button', { name: 'Mirror' }).click();
    await page.waitForFunction(() => window.__adtAvatar?.mirrored === false);
    results[id].direct = await armCheck(page, poses, TIMES.slice(0, 3), false, `s${k}-direct`);
    const legStates = await page.evaluate(() => ['thighL', 'thighR', 'shinL', 'shinR'].map((b) => window.__adtAvatar.bones[b].state));
    if (label) check(legStates.every((s) => s !== 'measured'), `s${k}: labelled-untracked legs are not animated (${legStates})`);
    await ctx.close();
  }

  // Interaction flow on desktop: camera views, count-in, captions, play loop, complete, next.
  {
    const { ctx, page } = await open({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 }, 'flow', ids[0]);
    for (const v of ['Side', '3/4']) {
      await page.getByRole('radio', { name: v }).click();
      await page.waitForTimeout(1200);
      await page.locator('[data-testid=teacher-surface]').screenshot({ path: path.join(OUT, `avatar-view-${v.replace('/', '-')}.png`) });
    }
    await page.getByRole('radio', { name: 'Front' }).click();
    await page.locator('[data-testid=section-chip]').first().click();
    await page.getByRole('radio', { name: '1×' }).click();
    await page.getByRole('button', { name: 'Play section' }).click();
    const counted = await page.waitForSelector('[data-testid=count-in]', { timeout: 3000 }).then(() => true).catch(() => false);
    check(counted, 'count-in shows before the section plays');
    await page.waitForFunction(() => !document.querySelector('[data-testid=learn-video]').paused, null, { timeout: 8000 });
    const caption = await page.locator('[data-testid=coach-caption]').textContent();
    check(Boolean(caption && caption.length > 5), `caption shown while playing: "${caption}"`);
    const sp = await page.evaluate(() => 'speechSynthesis' in window);
    console.log('     speechSynthesis available in this browser:', sp);
    await page.waitForTimeout(2500);
    const dbg = await page.evaluate(() => window.__adtAvatar);
    check(dbg.frames > 60, `avatar keeps rendering while playing (frames=${dbg.frames})`);
    const fps = await page.evaluate(async () => { const f0 = window.__adtAvatar.frames; const t0 = performance.now(); await new Promise((r) => setTimeout(r, 2000)); return (window.__adtAvatar.frames - f0) / ((performance.now() - t0) / 1000); });
    console.log(`     render rate in headless SwiftShader: ${fps.toFixed(1)} fps (software GL; not a GPU benchmark)`);
    await page.locator('[data-testid=teacher-surface]').screenshot({ path: path.join(OUT, 'avatar-playing.png') });
    await page.getByRole('button', { name: 'Pause' }).click();
    await page.getByRole('button', { name: 'Mark complete' }).click();
    await page.waitForSelector('text=✓ Completed — undo');
    check(true, 'mark complete');
    await page.getByRole('button', { name: 'Next section →' }).click();
    await page.waitForTimeout(500);
    const head = await page.locator('#section-title').textContent();
    check(/02/.test(head || ''), `next section selected (${head})`);
    await page.getByRole('button', { name: '← Previous' }).click();
    await page.getByRole('button', { name: '✓ Completed — undo' }).click();
    // Swap: video becomes the main surface, avatar goes picture-in-picture.
    await page.getByRole('button', { name: 'Video ⤢' }).click();
    check((await page.locator('[data-testid=teacher-surface]').getAttribute('data-primary')) === 'video', 'swap to video-primary with avatar PiP');
    await page.locator('[data-testid=teacher-surface]').screenshot({ path: path.join(OUT, 'avatar-pip.png') });
    await ctx.close();
  }

  // Mobile
  {
    const { ctx, page } = await open({ ...devices['iPhone 13'] }, 'mobile', ids[0]);
    await seekAndRead(page, 3.0);
    await page.screenshot({ path: path.join(OUT, 'teacher-mobile.png'), fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(overflow <= 0, `mobile: no horizontal overflow (${overflow}px)`);
    await ctx.close();
  }
  {
    const { ctx, page } = await open({ viewport: { width: 1440, height: 900 } }, 'desktop-overflow', ids[0]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(overflow <= 0, `desktop: no horizontal overflow (${overflow}px)`);
    await ctx.close();
  }

  await browser.close();
  check(errors.length === 0, `no console errors${errors.length ? ': ' + errors.join(' | ') : ''}`);
  console.log(JSON.stringify(results));
  if (failures.length) { console.log(`TEACHER MODE CHECK FAILED (${failures.length})`); process.exit(1); }
  console.log('TEACHER MODE CHECK OK');
})().catch((e) => { console.error(e); process.exit(1); });
