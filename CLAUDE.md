# AI Dance Teacher — instructions for every build session

This repo is built by scheduled, autonomous Claude sessions (twice daily, 2026-11-24 → 2026-12-04, IST).
Each session starts fresh: this repo is the only memory between runs.

## Source of truth
- `docs/MASTER_PROMPT.md` — the full product + engineering spec. Its non-negotiable rules (section 3) always win.
- `docs/SPEC_AMENDMENTS.md` — owner decisions that override parts of the spec (A1: **3D AI avatar teacher with voice**
  is MVP scope, centrepiece of Outcome 4). Read it every session.
- `IMPLEMENTATION_PLAN.md` — outcome order and daily pacing targets.
- `PROJECT_STATUS.md` — what is implemented / tested / deployed / planned, and "Owner action needed".
- `DECISIONS.md` — material decisions (append, never rewrite history).
- `docs/RUN_LOG.md` — one entry per session.

- `docs/SOURCING.md` — where the pose model, reference videos and attempt fixtures come from. **The owner supplies nothing and only tests.** Never block on the owner for assets or accounts; find a way, and only escalate something that is truly impossible.

## Start of every session
1. Read PROJECT_STATUS.md, the latest docs/RUN_LOG.md entries, and `git log --oneline -20`.
2. Re-run the previous outcome's exit-gate checks before building further.
3. Finish any partial outcome before starting the next one.

## Hard rules
- No fake AI: no random, hard-coded or invented scores, poses or feedback. Synthetic landmark sequences are for pure-math unit tests only.
- Unavailable inference → explicit LIMITED state, never a simulated result.
- Never commit secrets, real credentials, or `.env` files. Only `.env.example`.
- Never commit large binaries except trimmed, licensed fixture videos under `fixtures/` (≤720p, ≤30 s each; provenance in `fixtures/fixture_manifest.json`). The pose model is downloaded, never committed.
- Keep the app runnable at every push. Run tests before committing; record exact commands + results in the run log.
- Report progress by outcomes and exit gates, never percentages.

## End of every session
Update PROJECT_STATUS.md, append docs/RUN_LOG.md, update DECISIONS.md if needed, commit.

## Shipping: `main` only ever receives green code (owner decision 2026-11-27)
The owner gets a GitHub email for every red CI run on `main`, so never push untested work to `main`.
1. Push work to the `build` branch (`git push origin HEAD:build`, force-with-lease is fine — `build` is scratch).
2. Wait for the CI run on `build` (backend, frontend, smoke) and fix it there until it is green.
3. Only then fast-forward `main`: `git push origin HEAD:main`. No merge commits, no PRs.
4. If it can't be made green before the session ends, leave `main` untouched, record the state in
   PROJECT_STATUS.md on `build`, and say so in the owner update.
