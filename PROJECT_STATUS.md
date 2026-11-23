# Project status

_Last updated: 2026-11-24 00:50 IST (repo seeded; no build session has run yet)_

## Outcomes

| # | Outcome | State |
|---|---|---|
| 0 | Engineering foundation | planned |
| 1 | Robust private reference intake | planned |
| 2 | Real reference pose + debugger | planned |
| 3 | Teachable sections | planned |
| 4 | Teacher Mode | planned |
| 5 | Learner capture + real learner pose | planned |
| 6 | Normalized alignment | planned |
| 7 | Versioned scoring | planned |
| 8 | Actionable feedback | planned |
| 9 | Report, repeat, dashboard | planned |
| 10 | Production identity + durable infra | planned |
| 11 | Stable deployment + full acceptance | planned |

States: planned → implemented → tested → deployed.

## Verified claims
_None yet._

## Owner action needed
- **Fixture videos** (needed by ~Nov 26 for real pose checks, required by Nov 30 for scoring calibration):
  - `fixtures/references/`: 1–3 short (15–30 s) single-dancer, full-body clips you own or have a license for.
  - `fixtures/attempts/`: your own attempts at those dances — ideally one good, one slightly late, one wrong arm, one partly out of frame.
  - Note the source/license of each clip in `fixtures/fixture_manifest.json` (or tell Claude and it will write it).
- **Deployment accounts** (by ~Dec 2): a Supabase project, and Vercel + Railway accounts linked to this GitHub repo. Exact steps will be in `deployment/RUNBOOK.md`.
