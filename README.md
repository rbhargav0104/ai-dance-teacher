# AI Dance Teacher

**Learn any dance. Frame by frame.**

A private computer-vision dance coach: upload choreography, see it broken into teachable sections, practice, and get real pose-based feedback. Scores come only from measured movement — never invented.

> 🚧 Under active construction (Nov 24 – Dec 4, 2026). `PROJECT_STATUS.md` says exactly what works today; `docs/MASTER_PROMPT.md` is the full spec.

## Run it locally

Requirements: **Node.js ≥ 20.9**, **[uv](https://docs.astral.sh/uv/)** (it fetches Python 3.12 for you), **FFmpeg** (needed from Outcome 1 onward), `curl`.

```bash
git clone https://github.com/rbhargav0104/ai-dance-teacher.git
cd ai-dance-teacher
scripts/setup.sh     # backend + frontend deps, pose model (SHA-256 verified), DB migrations, .env from .env.example
scripts/dev.sh       # API on :8000, web on :3000
```

Then open:

- http://localhost:3000 — landing page; the status pill (top right) shows **STUDIO READY / LIMITED / OFFLINE**
- http://localhost:3000/studio — private studio shell + live system check
- http://localhost:8000/api/health — capability JSON
- http://localhost:8000/api/docs — OpenAPI docs

Check a running stack: `scripts/smoke.sh`.

The browser calls the API **same-origin** (`/api/*`), and Next.js proxies to `API_INTERNAL_URL` — so only port 3000 needs to be exposed.

### Running pieces by hand

```bash
# backend
cd backend
uv sync --extra vision            # drop --extra vision to run without MediaPipe (LIMITED mode)
uv run alembic upgrade head       # SQLite at ./data/app.db by default
uv run uvicorn app.main:app --port 8000
uv run pytest                     # tests
uv run ruff check . && uv run mypy
uv run python -m app.pose.verify  # load the real model and run one inference

# frontend
cd frontend
npm ci
npm run dev                       # http://localhost:3000
npm test && npm run lint && npm run typecheck && npm run build
```

## Honest capability states

| State | Meaning |
|---|---|
| **STUDIO READY** | API, database, private storage, verified pose model, runtime and analysis pipeline all available |
| **LIMITED** | Private studio works, but movement analysis is unavailable (model missing/corrupt, runtime absent, or pipeline not built yet). Analysis is refused server-side, not faked |
| **OFFLINE** | The API can't be reached or persistence is broken. Retry is offered |

## Layout

```
backend/    FastAPI + SQLAlchemy + Alembic (Python 3.12). Pure movement math lives in isolated modules.
frontend/   Next.js (App Router, TypeScript strict, Tailwind v4)
scripts/    setup.sh, dev.sh, smoke.sh, download_model.sh
fixtures/   licensed reference clips + generated learner attempts (see docs/SOURCING.md)
docs/       spec, sourcing plan, run log
```

See `ARCHITECTURE.md` for how the pieces fit, and `DECISIONS.md` for why.

## Troubleshooting

- **`scripts/download_model.sh` fails** — the app still runs in LIMITED mode. The script tries the official URL, then GitHub mirrors, and only accepts the pinned SHA-256.
- **OpenCV/MediaPipe import errors on Linux** — install `libgl1 libglib2.0-0` (Debian/Ubuntu).
- **Status pill says OFFLINE** — the API isn't running on `API_INTERNAL_URL` (default `http://127.0.0.1:8000`), or migrations haven't run (`cd backend && uv run alembic upgrade head`).

## Privacy

Videos are private to the session that uploaded them, stored outside any public path, and deletable. Nothing is used for model training.
