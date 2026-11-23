# Decisions

Append new entries at the bottom. Format: date — decision — reason.

- 2026-11-24 — Build runs as scheduled autonomous sessions (twice daily, Nov 24–Dec 4) that push directly to `main`. — Owner's request; the repo is the only state shared between sessions.
- 2026-11-24 — `docs/MASTER_PROMPT.md` is the authoritative spec. — Owner-provided.
- 2026-11-24 — ~~Real end-to-end fixtures come from the owner.~~ Superseded below.
- 2026-11-24 — Owner only tests; sessions source everything. Pose model from GitHub mirrors with SHA-256 pinning; reference clips from openly licensed stock footage committed in public GitHub repos; learner attempts generated from real footage with FFmpeg transforms. — Owner's instruction. See `docs/SOURCING.md`.
- 2026-11-24 — Owner testing via GitHub Codespaces devcontainer + `docker compose`, and CI on GitHub Actions, instead of a Vercel/Railway/Supabase deployment. — No third-party accounts available; GitHub is already connected. Deployment configs still prepared.
