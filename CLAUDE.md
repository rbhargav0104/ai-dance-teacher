# AI Dance Teacher — instructions for every build session

This repo is built by scheduled, autonomous Claude sessions (twice daily, 2026-11-24 → 2026-12-04, IST).
Each session starts fresh: this repo is the only memory between runs.

## Source of truth
- `docs/MASTER_PROMPT.md` — the full product + engineering spec. Its non-negotiable rules (section 3) always win.
- `IMPLEMENTATION_PLAN.md` — outcome order and daily pacing targets.
- `PROJECT_STATUS.md` — what is implemented / tested / deployed / planned, and "Owner action needed".
- `DECISIONS.md` — material decisions (append, never rewrite history).
- `docs/RUN_LOG.md` — one entry per session.

## Start of every session
1. Read PROJECT_STATUS.md, the latest docs/RUN_LOG.md entries, and `git log --oneline -20`.
2. Re-run the previous outcome's exit-gate checks before building further.
3. Finish any partial outcome before starting the next one.

## Hard rules
- No fake AI: no random, hard-coded or invented scores, poses or feedback. Synthetic landmark sequences are for pure-math unit tests only.
- Unavailable inference → explicit LIMITED state, never a simulated result.
- Never commit secrets, real credentials, or `.env` files. Only `.env.example`.
- Never commit large binaries except owner-supplied fixtures under `fixtures/` (keep provenance in `fixtures/fixture_manifest.json`).
- Keep the app runnable at every push. Run tests before committing; record exact commands + results in the run log.
- Report progress by outcomes and exit gates, never percentages.

## End of every session
Update PROJECT_STATUS.md, append docs/RUN_LOG.md, update DECISIONS.md if needed, commit, and push to `main`
(the owner has asked for direct pushes to main for this project).
