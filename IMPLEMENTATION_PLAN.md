# Implementation plan

Outcomes and exit gates are defined in `docs/MASTER_PROMPT.md` section 33. This file sets the order and pacing.
Sessions run at ~01:43 and ~13:43 IST daily.

| Date (IST) | Target |
|---|---|
| Nov 24 | **Outcome 0** — monorepo, Next.js + FastAPI booting, env examples, Alembic migrations, local auth/storage/SQLite, docs, CI |
| Nov 25 | **Outcome 1** — private reference intake, FFprobe validation, no-residue rejection tests, READY/LIMITED/OFFLINE shell, landing page in the design system |
| Nov 26 | **Outcome 2** — canonical transcode, real MediaPipe pose extraction, quality gates, skeleton viewer/debugger |
| Nov 27 | **Outcome 3** — segmentation + editable timeline; start **Outcome 4** Teacher Mode |
| Nov 28 | Finish **Outcome 4** (desktop + mobile); **Outcome 5** webcam/upload learner capture + real learner pose |
| Nov 29 | Finish **Outcome 5**; **Outcome 6** normalization, mirroring, bounded DTW, invariance tests |
| Nov 30 | **Outcome 7** versioned scoring, confidence/coverage rules, golden-fixture relationship tests |
| Dec 1 | **Outcome 8** timestamp feedback + overlay + replay; **Outcome 9** report, weakest-section loop, dashboard |
| Dec 2 | **Outcome 10** Supabase auth/RLS/Postgres/private storage, durable worker, rate limits, observability |
| Dec 3 | **Outcome 11** deployment configs (Docker, Railway, Vercel) + `deployment/RUNBOOK.md` |
| Dec 4 | Final acceptance test (section 34), desktop/mobile visual QA, docs, handover |

If behind schedule: keep the order. Correctness, tests and honest-state rules come before visual expansion.
Never skip an exit gate; record any slip in PROJECT_STATUS.md.
