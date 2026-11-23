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
_None. The owner only tests. Sessions source every asset themselves (see `docs/SOURCING.md`)._
Only add an item here if it is truly impossible without the owner, and say why.

## Owner testing path (target)
- **GitHub Codespaces:** repo page → Code → Codespaces → Create. The devcontainer installs everything, downloads the model, seeds the demo, and starts the app on a forwarded HTTPS URL (webcam works).
- **Local alternative:** `docker compose up`, then open http://localhost:3000.
