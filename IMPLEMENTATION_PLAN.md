# Implementation plan

Outcomes and exit gates are defined in `docs/MASTER_PROMPT.md` section 33. This file sets the order and pacing.
Sessions run at ~01:43 and ~13:43 IST daily.

| Date (IST) | Target |
|---|---|
| Nov 24 | **Outcome 0** — monorepo, Next.js + FastAPI booting, env examples, Alembic migrations, local auth/storage/SQLite, docs, CI |
| Nov 25 | **Outcome 1** — private reference intake, FFprobe validation, no-residue rejection tests, READY/LIMITED/OFFLINE shell, landing page in the design system |
| Nov 26 | ~~Outcome 2~~ (done Nov 25 pm) → **Outcome 3** segmentation + editable timeline; start avatar retargeting maths (`lib/avatar`, unit tests) |
| Nov 27 | **Outcome 4** Teacher Mode with the **3D AI avatar** (docs/SPEC_AMENDMENTS.md A1): three.js stage, procedural mannequin driven by measured world landmarks, ghosted untracked limbs, section play/loop/speed/mirror, camera views, PiP reference video |
| Nov 28 | Finish **Outcome 4**: spoken + captioned cues (Web Speech API, measured facts only), mark complete/next section, mobile layout, WebGL fallback, Playwright avatar checks; start **Outcome 5** learner capture |
| Nov 29 | Finish **Outcome 5** (webcam/upload learner capture + real learner pose); **Outcome 6** normalization, mirroring, bounded DTW, invariance tests |
| Nov 30 | **Outcome 7** versioned scoring, confidence/coverage rules, golden-fixture relationship tests |
| Dec 1 | **Outcome 8** timestamp feedback + overlay + replay; **Outcome 9** report, weakest-section loop, dashboard |
| Dec 2 | **Outcome 10** Postgres + durable worker (`FOR UPDATE SKIP LOCKED`), private storage adapter, multi-user isolation, rate limits, observability. Supabase adapters written and tested against local Postgres/S3-compatible storage (MinIO) in CI. |
| Dec 3 | **Outcome 11 (adapted)** one-click owner testing: `.devcontainer/` for GitHub Codespaces + `docker compose up`; GitHub Actions CI running unit, API, golden-fixture and Playwright E2E tests (fake-webcam from fixtures). Vercel/Railway/Supabase configs + `deployment/RUNBOOK.md` prepared but not deployed. |
| Dec 4 | Final acceptance test (section 34) run in CI and in a Codespaces-equivalent container, desktop/mobile visual QA, docs, handover |

## Owner constraint (2026-11-24)
The owner will only test. No owner-supplied videos, accounts or credentials.
- Assets: sourced by sessions per `docs/SOURCING.md`.
- "Stable deployed URL" in the spec is replaced by a one-click GitHub Codespaces environment (owner already has GitHub)
  plus green CI. A public Vercel/Railway URL needs accounts the owner hasn't set up; keep those configs ready so it's a 10-minute step later.

## Owner amendment (2026-11-25)
A 3D AI avatar teacher with voice is now MVP scope (docs/SPEC_AMENDMENTS.md A1). It is absorbed by the session gained on
Outcome 2. If still behind, cut avatar polish (skinned v2 model, extra camera presets) before scoring/feedback outcomes.

If behind schedule: keep the order. Correctness, tests and honest-state rules come before visual expansion.
Never skip an exit gate; record any slip in PROJECT_STATUS.md.
