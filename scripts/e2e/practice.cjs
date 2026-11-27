// Practice browser check (Outcome 5 exit gate): a learner attempt produces real stored pose data
// and can be reviewed beside the reference.
//  - webcam path: Chromium's fake camera is fed a REAL fixture video (fixtures/attempts/girl_good.mp4
//    → .y4m); the page records it with MediaRecorder, countdown → recording → stop → preview → use;
//    the attempt is analysed by the real pipeline and reviewed side by side (videos stay in step);
//  - upload path: a real FFmpeg attempt variant (mirrored) → analysed, honest tracking note (legs cropped);
//  - permission denied → clear guidance + upload fallback;
//  - desktop 1440x900 + iPhone 13 screenshots, no console errors, no horizontal overflow.
// Needs a READY stack on :3000, ffmpeg and Playwright. Usage: node scripts/e2e/practice.cjs [outdir]
const { chromium, devices } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const OUT = path.resolve(process.argv[2] || '.');
const WEB = process.env.WEB || 'http://localhost:3000';
const ROOT = path.resolve(__dirname, '..', '..');
const ATTEMPTS = path.join(ROOT, 'fixtures', 'attempts');
const Y4M = path.join(OUT, 'fake-camera.y4m');

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  if (!fs.existsSync(Y4M)) {
    // Real footage as the camera: 640x360, 24 fps, 10 s (Chromium loops the file).
    execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', path.join(ATTEMPTS, 'girl_good.mp4'),
      '-t', '10', '-vf', 'fps=24', '-pix_fmt', 'yuv420p', Y4M]);
  }
  const j = async (r) => { if (!r.ok) throw new Error(r.status + ' ' + await r.text()); return r.status === 204 ? null : r.json(); };
  const tok = (await j(await fetch(WEB + '/api/session', { method: 'POST' }))).token;
  const H = { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json' };
  const project = await j(await fetch(WEB + '/api/projects/sample', { method: 'POST', headers: H, body: JSON.stringify({ sample_id: 'mixkit_girl_earphones_28306' }) }));
  const pid = project.id;
  for (let i = 0; i < 180; i++) {
    const p = await j(await fetch(WEB + '/api/projects/' + pid, { headers: H }));
    if (p.status === 'analyzed') break;
    if (p.status === 'failed') throw new Error('reference analysis failed');
    await new Promise((r) => setTimeout(r, 1000));
  }
  const sections = (await j(await fetch(WEB + `/api/projects/${pid}/segments`, { headers: H }))).sections;
  const section = sections[0];

  const failures = [];
  const errors = [];
  const check = (ok, msg) => { console.log((ok ? 'ok   ' : 'FAIL ') + msg); if (!ok) failures.push(msg); };
  const waitAttempt = async (id) => {
    for (let i = 0; i < 180; i++) {
      const a = await j(await fetch(WEB + '/api/practice-sessions/' + id, { headers: H }));
      if (a.status === 'analyzed' || a.status === 'failed') return a;
      await new Promise((r) => setTimeout(r, 1000));
    }
    throw new Error('attempt analysis timed out');
  };
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

  const browser = await chromium.launch({
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${Y4M}`,
      '--autoplay-policy=no-user-gesture-required', '--enable-unsafe-swiftshader', '--use-angle=swiftshader'],
  });
  // Same rule as frontend/lib/alignment.ts referenceTimeAt (kept deliberately simple here).
  function expectedRef(frames, lt) {
    const p = frames.map((f, i) => ({ l: f.learner_t, r: f.ref_src_t, i })).sort((a, b) => a.l - b.l || a.i - b.i);
    if (lt <= p[0].l) return p[0].r;
    if (lt >= p[p.length - 1].l) return p[p.length - 1].r;
    let hi = p.findIndex((q) => q.l >= lt);
    while (hi > 0 && p[hi - 1].l === p[hi].l) hi--;
    const a = p[hi - 1], b = p[hi];
    return b.l === a.l ? b.r : a.r + ((lt - a.l) / (b.l - a.l)) * (b.r - a.r);
  }

  async function open(ctxOpts, name) {
    const ctx = await browser.newContext({ ...ctxOpts, permissions: ['camera'] });
    await ctx.addInitScript((t) => localStorage.setItem('adt.session.v1', t), tok);
    const page = await ctx.newPage();
    page.on('console', (m) => m.type() === 'error' && errors.push(name + ': ' + m.text()));
    page.on('pageerror', (e) => errors.push(name + ': ' + e.message));
    return { ctx, page };
  }

  // ---- 1. Webcam: record a section attempt with the fake camera --------------------------------
  {
    const { ctx, page } = await open({ viewport: { width: 1440, height: 900 } }, 'desktop');
    await page.goto(`${WEB}/studio/projects/${pid}`);
    await page.getByTestId('practice-section').click();
    await page.waitForURL(/\/practice\?section=/);
    await page.getByTestId('practice-target').getByText(section.title).waitFor();
    check(true, `section CTA opens practice for "${section.title}"`);
    await page.screenshot({ path: path.join(OUT, 'practice-intro-desktop.png') });
    await page.getByTestId('camera-on').click();
    await page.locator('[data-phase="live"]').waitFor({ timeout: 15000 });
    await page.waitForFunction(() => (document.querySelector('video[aria-label^="Live camera"]')?.videoWidth ?? 0) > 0, null, { timeout: 15000 });
    const live = await page.locator('video[aria-label^="Live camera"]').evaluate((v) => { const cs = getComputedStyle(v); return { w: v.videoWidth, h: v.videoHeight, mirrored: `${cs.scale} ${cs.transform}` }; });
    check(live.w > 0 && live.h > 0, `live camera preview ${live.w}x${live.h}`);
    check(/^-1 1\b|matrix\(-1/.test(live.mirrored), `preview mirrored (${live.mirrored})`);
    await page.getByTestId('record').click();
    await page.getByText('3', { exact: true }).waitFor({ timeout: 3000 });
    check(true, 'countdown shows 3-2-1');
    await page.locator('[data-phase="recording"]').waitFor({ timeout: 6000 });
    await page.waitForTimeout(800);
    const guidePlaying = await page.getByTestId('reference-guide').evaluate((v) => !v.paused && v.currentTime > 0);
    check(guidePlaying, 'reference guide plays alongside the recording');
    await page.screenshot({ path: path.join(OUT, 'practice-recording-desktop.png') });
    await page.waitForTimeout(4200);
    const clock = await page.getByTestId('rec-clock').innerText();
    check(/REC 0:0[45]/.test(clock), `elapsed clock "${clock}"`);
    await page.getByTestId('stop').click();
    await page.locator('[data-phase="review"]').waitFor({ timeout: 10000 });
    const take = await page.getByTestId('take-preview').evaluate((v) => new Promise((res) => {
      const done = () => res({ ready: v.readyState, w: v.videoWidth });
      if (v.readyState >= 1) done(); else v.addEventListener('loadedmetadata', done, { once: true });
    }));
    check(take.w > 0, `recorded take previews (${take.w}px wide)`);
    // Retry discards the take and returns to the live camera.
    await page.getByTestId('retake').click();
    await page.locator('[data-phase="live"]').waitFor({ timeout: 15000 });
    check(true, 'record again returns to the live camera');
    await page.getByTestId('record').click();
    await page.locator('[data-phase="recording"]').waitFor({ timeout: 6000 });
    await page.waitForTimeout(5000);
    await page.getByTestId('stop').click();
    await page.locator('[data-phase="review"]').waitFor({ timeout: 10000 });
    await page.getByTestId('use-take').click();
    await page.waitForURL(/\/studio\/practice\//, { timeout: 30000 });
    const attemptId = page.url().split('/').pop();
    check(true, 'take uploaded → attempt page');
    const a = await waitAttempt(attemptId);
    check(a.status === 'analyzed', `webcam attempt analysed by the real pipeline (status ${a.status} ${a.error_code || ''})`);
    check(a.capture_source === 'webcam' && a.declared_mirrored === false, 'stored as an unmirrored webcam recording');
    check(a.target.segment_id === section.id, 'attempt is linked to the practised section');
    check(a.duration > 4 && a.duration < 7, `recorded length ${a.duration}s`);
    const refNow = await j(await fetch(WEB + '/api/projects/' + pid, { headers: H }));
    check(a.pipeline_version === 'learner-pose-1' && a.model_version === refNow.reference.model_version, 'same pose model as the reference');
    const poses = await j(await fetch(WEB + `/api/practice-sessions/${attemptId}/poses`, { headers: H }));
    const valid = poses.frames.filter((f) => f.valid).length;
    check(poses.frames.length >= 40 && valid / poses.frames.length > 0.5, `stored learner pose: ${poses.frames.length} frames, ${valid} valid, coverage ${a.tracking_coverage}`);

    await page.getByTestId('side-by-side').waitFor({ timeout: 30000 });
    await page.waitForFunction(() => {
      const r = document.querySelector('[data-testid="review-reference"]');
      const l = document.querySelector('[data-testid="review-learner"]');
      return r && l && r.readyState >= 2 && l.readyState >= 2;
    }, null, { timeout: 30000 });
    // Alignment (Outcome 6): summary loads; "Same time" gives clock playback for this check.
    await page.getByTestId('alignment-summary').waitFor({ timeout: 30000 });
    const alRes = await j(await fetch(WEB + `/api/practice-sessions/${attemptId}/alignment`, { headers: H }));
    const al = alRes.alignment;
    check(al.version === 'align-1' && typeof al.status === 'string', `alignment computed: ${al.status}, mean distance ${al.summary && al.summary.mean_cost}, mirror ${al.mirror && al.mirror.chosen}`);
    const follow = page.getByTestId('review-follow-path');
    const hasFollow = (await follow.count()) > 0;
    check(hasFollow === (al.status === 'aligned'), 'matched-moves toggle offered exactly when moves were paired');
    if (hasFollow) await follow.click();
    await page.getByTestId('review-play').click();
    await page.waitForTimeout(2000);
    const sync = await page.evaluate((start) => {
      const r = document.querySelector('[data-testid="review-reference"]');
      const l = document.querySelector('[data-testid="review-learner"]');
      return { ref: r.currentTime, learner: l.currentTime, drift: (r.currentTime - start) - l.currentTime, playing: !r.paused && !l.paused };
    }, section.start);
    check(sync.playing && sync.learner > 1 && Math.abs(sync.drift) < 0.2, `side-by-side in step: learner ${sync.learner.toFixed(2)}s, reference ${sync.ref.toFixed(2)}s, drift ${sync.drift.toFixed(3)}s`);
    await page.getByTestId('review-play').click();
    if (hasFollow) {
      // Back to matched moves: the reference must follow the alignment path.
      await follow.click();
      await page.getByLabel('Back to the start').click();
      await page.getByTestId('review-play').click();
      await page.waitForTimeout(1500);
      await page.getByTestId('review-play').click();
      await page.waitForTimeout(300);
      const pos = await page.evaluate(() => ({
        ref: document.querySelector('[data-testid="review-reference"]').currentTime,
        learner: document.querySelector('[data-testid="review-learner"]').currentTime,
      }));
      const want = expectedRef(al.frames, pos.learner);
      check(Math.abs(pos.ref - want) < 0.25, `matched moves: learner ${pos.learner.toFixed(2)}s → reference ${pos.ref.toFixed(2)}s (path says ${want.toFixed(2)}s)`);
    }
    const skel = await page.locator('[data-testid="side-by-side"] canvas').count();
    check(skel === 2, 'measured skeletons drawn on both videos');
    await page.screenshot({ path: path.join(OUT, 'attempt-review-desktop.png') });
    check((await overflow(page)) <= 0, 'desktop review: no horizontal overflow');
    // Developer alignment view.
    await page.getByTestId('alignment-link').click();
    await page.waitForURL(/\/alignment$/, { timeout: 15000 });
    await page.getByTestId('alignment-report').waitFor({ timeout: 30000 });
    const shown = await page.getByTestId('alignment-report').getAttribute('data-status');
    check(shown === al.status, `alignment view shows status ${shown}`);
    if (al.status === 'aligned') {
      const dots = await page.locator('[data-testid="alignment-path"] circle').count();
      check(dots === al.frames.length, `alignment path draws every paired reference frame (${dots})`);
    }
    await page.screenshot({ path: path.join(OUT, 'alignment-desktop.png'), fullPage: true });
    check((await overflow(page)) <= 0, 'desktop alignment view: no horizontal overflow');
    await ctx.close();

    // ---- iPhone 13: review page + practice page ----------------------------------------------
    const m = await open({ ...devices['iPhone 13'] }, 'mobile');
    await m.page.goto(`${WEB}/studio/practice/${attemptId}`);
    await m.page.getByTestId('side-by-side').waitFor({ timeout: 30000 });
    await m.page.waitForTimeout(800);
    await m.page.screenshot({ path: path.join(OUT, 'attempt-review-mobile.png'), fullPage: true });
    check((await overflow(m.page)) <= 0, 'mobile review: no horizontal overflow');
    await m.page.goto(`${WEB}/studio/practice/${attemptId}/alignment`);
    await m.page.getByTestId('alignment-report').waitFor({ timeout: 30000 });
    await m.page.screenshot({ path: path.join(OUT, 'alignment-mobile.png'), fullPage: true });
    check((await overflow(m.page)) <= 0, 'mobile alignment view: no horizontal overflow');
    await m.page.goto(`${WEB}/studio/projects/${pid}/practice`);
    await m.page.getByTestId('camera-on').click();
    await m.page.locator('[data-phase="live"]').waitFor({ timeout: 15000 });
    await m.page.waitForTimeout(500);
    await m.page.screenshot({ path: path.join(OUT, 'practice-camera-mobile.png'), fullPage: true });
    check((await overflow(m.page)) <= 0, 'mobile practice: no horizontal overflow');
    await m.ctx.close();
  }

  // ---- 2. Upload path with a real mirrored variant ---------------------------------------------
  {
    const { ctx, page } = await open({ viewport: { width: 1440, height: 900 } }, 'upload');
    await page.goto(`${WEB}/studio/projects/${pid}/practice`);
    await page.getByTestId('mode-upload').click();
    await page.getByTestId('attempt-file').setInputFiles(path.join(ATTEMPTS, 'girl_mirrored.mp4'));
    await page.getByTestId('submit-file').click();
    await page.waitForURL(/\/studio\/practice\//, { timeout: 30000 });
    const id = page.url().split('/').pop();
    const a = await waitAttempt(id);
    check(a.status === 'analyzed' && a.capture_source === 'upload' && a.target.segment_id === null, `uploaded full-dance attempt analysed (coverage ${a.tracking_coverage})`);
    check(a.warnings.includes('cropped_body'), 'cropped legs reported honestly');
    const mal = (await j(await fetch(WEB + `/api/practice-sessions/${id}/alignment`, { headers: H }))).alignment;
    check(mal.status === 'aligned' && mal.mirror.chosen === 'mirrored' && mal.mirror.decision === 'clear',
      `flipped upload compared mirrored (as recorded ${mal.mirror && mal.mirror.mean_cost.direct}, mirrored ${mal.mirror && mal.mirror.mean_cost.mirrored})`);
    await page.getByTestId('side-by-side').waitFor({ timeout: 30000 });
    await page.getByText('Your feet were out of frame').waitFor();
    check(true, 'tracking note shown on the review page');
    // Attempts list + delete
    await page.goto(`${WEB}/studio/projects/${pid}/practice`);
    const rows = page.getByTestId('attempt-list').locator('li');
    await rows.first().waitFor();
    const before = await rows.count();
    check(before === 2, `attempt list shows both attempts (${before})`);
    await page.getByRole('button', { name: /Delete attempt: Full dance/ }).click();
    await page.getByRole('button', { name: 'Delete', exact: true }).click();
    await page.waitForFunction((n) => document.querySelectorAll('[data-testid="attempt-list"] li').length === n - 1, before, { timeout: 10000 });
    const gone = await fetch(WEB + '/api/practice-sessions/' + id, { headers: H });
    check(gone.status === 404, 'deleted attempt is gone (404)');
    await ctx.close();
  }
  await browser.close();

  // ---- 3. Camera permission denied → guidance + upload fallback --------------------------------
  {
    const denied = await chromium.launch({ args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream=deny'] });
    const ctx = await denied.newContext({ viewport: { width: 1280, height: 800 } });
    await ctx.addInitScript((t) => localStorage.setItem('adt.session.v1', t), tok);
    const page = await ctx.newPage();
    page.on('pageerror', (e) => errors.push('denied: ' + e.message));
    await page.goto(`${WEB}/studio/projects/${pid}/practice`);
    await page.getByTestId('camera-on').click();
    const problem = page.getByTestId('camera-problem');
    await problem.waitFor({ timeout: 10000 });
    const text = await problem.innerText();
    check(/blocked/i.test(text) && /allow the camera/i.test(text), `denied camera explained: "${text.split('\n')[0]}"`);
    await page.getByRole('button', { name: 'Upload a video instead' }).click();
    await page.getByTestId('attempt-file').waitFor({ state: 'attached' });
    check(true, 'upload fallback offered');
    await page.screenshot({ path: path.join(OUT, 'practice-camera-denied.png') });
    await denied.close();
  }

  check(errors.length === 0, `no console errors (${errors.join(' | ')})`);
  if (failures.length) {
    console.error(`PRACTICE CHECK FAILED: ${failures.length} problem(s)`);
    process.exit(1);
  }
  console.log('PRACTICE CHECK OK');
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
