# Decisions

Append new entries at the bottom. Format: date — decision — reason.

- 2026-11-24 — Build runs as scheduled autonomous sessions (twice daily, Nov 24–Dec 4) that push directly to `main`. — Owner's request; the repo is the only state shared between sessions.
- 2026-11-24 — `docs/MASTER_PROMPT.md` is the authoritative spec. — Owner-provided.
- 2026-11-24 — ~~Real end-to-end fixtures come from the owner.~~ Superseded below.
- 2026-11-24 — Owner only tests; sessions source everything. Pose model from GitHub mirrors with SHA-256 pinning; reference clips from openly licensed stock footage committed in public GitHub repos; learner attempts generated from real footage with FFmpeg transforms. — Owner's instruction. See `docs/SOURCING.md`.
- 2026-11-24 — Owner testing via GitHub Codespaces devcontainer + `docker compose`, and CI on GitHub Actions, instead of a Vercel/Railway/Supabase deployment. — No third-party accounts available; GitHub is already connected. Deployment configs still prepared.
- 2026-11-24 — Browser calls the API same-origin (`/api/*`) and Next.js rewrites to `API_INTERNAL_URL`. — One forwarded port in Codespaces, no CORS in dev. Large uploads may need a direct API URL (`NEXT_PUBLIC_API_URL`) because proxied bodies are size-limited; revisit in Outcome 1.
- 2026-11-24 — `/api/health` reports LIMITED until the analysis pipeline is actually implemented, even with a verified model. — Spec §3.4/§25: never advertise capability that doesn't exist.
- 2026-11-24 — Local sessions: itsdangerous-signed, salted, expiring bearer tokens bound to a `users` row; refused (503/404) in any non-local auth mode. — Dev/demo only per spec §23; Supabase JWT in Outcome 10.
- 2026-11-24 — Python deps via `uv` (lockfile committed); MediaPipe/OpenCV/NumPy/SciPy in the `vision` extra. — Lets the API boot in LIMITED mode without the vision stack, and keeps installs reproducible.
- 2026-11-24 — Next.js 16 + Tailwind v4 + vitest; fonts self-hosted via npm (`geist`, `@fontsource-variable/unbounded`). — No build-time Google Fonts fetch (blocked in sandboxes, flaky in CI).
- 2026-11-24 — MediaPipe 1.2.x needs `libegl1 libgles2 libgl1` on Linux even for CPU inference. — Found via CI failure; added to CI and README, to be baked into the Docker image.
