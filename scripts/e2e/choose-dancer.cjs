// "Who should we follow?" browser check (spec amendment A2 exit gate, browser half).
//  - a real two-dancer video (fixtures/multi/duo_girl_left.mp4: girl left, boy right) is uploaded
//    and analysed by the real worker → the dance stops at the picker (no failure);
//  - desktop 1440x900: the picker shows the real frame with both detections outlined, the user
//    picks person 1 (left) → analysis re-runs → Learn Mode opens, "Following person 1 (left)",
//    and every measured frame's hips are on the left half;
//  - iPhone 13: "Follow someone else" → person 2 (right) → every measured frame on the right half;
//  - no console errors and no horizontal overflow anywhere.
// Needs a READY stack on :3000 and Playwright. Usage: node scripts/e2e/choose-dancer.cjs [outdir]
const fs = require('fs');
const path = require('path');
const { chromium, devices } = require('playwright');

const WEB = process.env.WEB || 'http://localhost:3000';
const OUT = path.resolve(process.argv[2] || '.');
const ROOT = path.resolve(__dirname, '..', '..');
const DUO = path.join(ROOT, 'fixtures', 'multi', 'duo_girl_left.mp4');

const check = (ok, msg) => {
  if (!ok) throw new Error('FAILED: ' + msg);
  console.log('ok -', msg);
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const j = async (r) => { if (!r.ok) throw new Error(r.status + ' ' + await r.text()); return r.json(); };
  const tok = (await j(await fetch(WEB + '/api/session', { method: 'POST' }))).token;
  const H = { Authorization: 'Bearer ' + tok };
  const waitStatus = async (id, wanted) => {
    for (let i = 0; i < 180; i++) {
      const p = await j(await fetch(WEB + '/api/projects/' + id, { headers: H }));
      if (wanted.includes(p.status)) return p;
      await new Promise((r) => setTimeout(r, 1000));
    }
    throw new Error('timed out waiting for ' + wanted.join('/'));
  };
  const sideOfFrames = async (id) => {
    const poses = await j(await fetch(WEB + `/api/projects/${id}/poses`, { headers: H }));
    const xs = poses.frames.filter((f) => f.valid).map((f) => {
      const lm = f.data.landmarks;
      return (lm[23][0] + lm[24][0]) / 2;
    });
    return { n: xs.length, left: xs.filter((x) => x < 0.5).length, right: xs.filter((x) => x >= 0.5).length };
  };

  // Upload + first analysis (real worker, real MediaPipe).
  const form = new FormData();
  form.append('file', new Blob([fs.readFileSync(DUO)], { type: 'video/mp4' }), 'duo_girl_left.mp4');
  form.append('title', 'Two dancers');
  const created = await j(await fetch(WEB + '/api/projects', { method: 'POST', headers: H, body: form }));
  const id = created.id;
  await j(await fetch(WEB + `/api/projects/${id}/analysis`, { method: 'POST', headers: H }));
  const stopped = await waitStatus(id, ['needs_subject', 'analyzed', 'failed']);
  check(stopped.status === 'needs_subject' && stopped.error_code === 'choose_dancer', `two dancers → "Who should we follow?" (status ${stopped.status})`);
  check(stopped.reference.subject.candidates.length === 2, '2 real candidates offered');

  const browser = await chromium.launch();
  const errors = [];
  async function open(ctxOpts, name) {
    const ctx = await browser.newContext(ctxOpts);
    await ctx.addInitScript((t) => localStorage.setItem('adt.session.v1', t), tok);
    const page = await ctx.newPage();
    page.on('console', (m) => m.type() === 'error' && errors.push(name + ': ' + m.text()));
    page.on('pageerror', (e) => errors.push(name + ': ' + e.message));
    await page.goto(`${WEB}/studio/projects/${id}`);
    return { ctx, page };
  }
  const noOverflow = async (page, label) => {
    const o = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(o <= 1, `${label}: no horizontal overflow (${o}px)`);
  };

  // ---- Desktop: pick the left dancer -----------------------------------------------------------
  {
    const { ctx, page } = await open({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 }, 'desktop');
    await page.waitForSelector('[data-testid=subject-picker]');
    await page.waitForFunction(() => {
      const img = document.querySelector('[data-testid=subject-picker] img');
      return img && img.complete && img.naturalWidth > 0;
    });
    check(await page.getByRole('heading', { name: 'Who should we follow?' }).isVisible(), 'picker heading visible');
    check((await page.locator('[data-testid^=subject-person-]').count()) === 2, 'two person buttons');
    await noOverflow(page, 'desktop picker');
    await page.screenshot({ path: path.join(OUT, 'desktop-picker.png'), fullPage: true });
    await page.getByTestId('subject-person-1').click();
    const p = await waitStatus(id, ['analyzed', 'failed']);
    check(p.status === 'analyzed', `left dancer analysed (${p.status} ${p.error_code || ''})`);
    check(p.reference.subject.choice.person === 1, 'choice stored: person 1');
    const side = await sideOfFrames(id);
    check(side.n > 40 && side.right === 0, `every measured frame follows the left dancer (${side.left} left / ${side.right} right)`);
    await page.reload();
    await page.waitForSelector('[data-testid=section-chip]');
    const following = await page.getByTestId('subject-following').textContent();
    check(/person 1 \(left\)/.test(following), `page says whom it follows: "${following.trim().slice(0, 80)}"`);
    await page.waitForTimeout(800);
    await noOverflow(page, 'desktop learn');
    await page.screenshot({ path: path.join(OUT, 'desktop-following-left.png'), fullPage: true });
    await ctx.close();
  }

  // ---- iPhone 13: follow someone else (the right dancer) ---------------------------------------
  {
    const { ctx, page } = await open({ ...devices['iPhone 13'] }, 'mobile');
    await page.waitForSelector('[data-testid=section-chip]');
    await page.getByTestId('follow-someone-else').click();
    await page.waitForSelector('[data-testid=subject-picker]');
    await page.waitForFunction(() => {
      const img = document.querySelector('[data-testid=subject-picker] img');
      return img && img.complete && img.naturalWidth > 0;
    });
    check((await page.getByTestId('subject-person-1').getAttribute('aria-pressed')) === 'true', 'current choice marked');
    await noOverflow(page, 'mobile picker');
    await page.getByTestId('subject-picker').screenshot({ path: path.join(OUT, 'mobile-picker.png') });
    await page.getByTestId('subject-person-2').click();
    const p = await waitStatus(id, ['analyzed', 'failed']);
    // waitStatus may see the previous "analyzed" before the new job is queued: wait for person 2.
    let fresh = p;
    for (let i = 0; i < 120 && !(fresh.status === 'analyzed' && fresh.reference.subject.choice.person === 2 && fresh.reference.subject.followed); i++) {
      await new Promise((r) => setTimeout(r, 1000));
      fresh = await j(await fetch(WEB + '/api/projects/' + id, { headers: H }));
    }
    check(fresh.status === 'analyzed' && fresh.reference.subject.choice.person === 2, 'right dancer analysed');
    const side = await sideOfFrames(id);
    check(side.n > 40 && side.left === 0, `every measured frame follows the right dancer (${side.left} left / ${side.right} right)`);
    await page.reload();
    await page.waitForSelector('[data-testid=section-chip]');
    const following = await page.getByTestId('subject-following').textContent();
    check(/person 2 \(right\)/.test(following), 'mobile page follows person 2 (right)');
    await noOverflow(page, 'mobile learn');
    await page.screenshot({ path: path.join(OUT, 'mobile-following-right.png'), fullPage: true });
    await ctx.close();
  }

  await browser.close();
  check(errors.length === 0, 'no console errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log('CHOOSE DANCER CHECK OK');
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
