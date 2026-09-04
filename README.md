# WBT Content Generation

The content pipeline: generate website copy, social content, blogs, logos and
Meta ads for a client, then review, edit, approve and export the results.

Same backend as before. The frontend is a rebuild — a Next.js app replacing the
old one, built from the Claude Design handoff in `design-handoff/`.

```
backend/    FastAPI + the agents. Supabase Postgres, Supabase Storage.
frontend/   Next.js App Router. Talks to the backend, never to the database.
supabase/   schema v2 migrations (see PARALLEL-AGENT-PLAN.md)
```

## Running it with Docker

```bash
cp .env.example .env      # fill in DATABASE_URL, API_KEY, ANTHROPIC_API_KEY, SUPABASE_*
docker compose up --build
```

- frontend → http://localhost:4000
- backend → http://localhost:9001 (docs at `/docs`)

Compose refuses to start if a required value is missing, rather than passing an
empty string that fails later inside SQLAlchemy or the Supabase client.

## Running it without Docker

```bash
# backend  -> http://127.0.0.1:8001
cd backend && ./venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8001 --host 127.0.0.1

# frontend -> http://localhost:3000
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

`http://localhost:3000/api-check` reports whether the connection and the key are
good and prints a sample of what each endpoint returned. Start there when the UI
looks empty.

## The API key

Every backend route needs `X-API-Key` except `/docs`, `/openapi.json`, `/redoc`
and `/health`.

The frontend reads it as **`HUB_API_KEY`, server-side only**. This is the one
deliberate difference from the old frontend, which used `NEXT_PUBLIC_API_KEY`:
Next inlines every `NEXT_PUBLIC_*` value into the browser bundle at build time,
so that key shipped to every visitor and rotating it meant a rebuild. Here every
fetch happens in a server component, so the key stays on the server and rotating
it is a restart.

Set `API_KEY` once in `.env`; compose passes it to the backend as `API_KEY` and
to the frontend as `HUB_API_KEY`.

## URLs

Every level is addressable, and short forms redirect up to the canonical path.

```
/content/{client}/{section}/{run}/{sub}/{id}/{slug}
/content/{client}/website/{run}/page/{slug}          website has no id segment

/content/cafgas-cic/social-media/run-2026-09-01/posts/01/why-your-boilers-age
/content/cafgas-cic/website/run-2026-09-01/page/home-page
```

Segments are names, never internal ids: client slugs come from client names, run
slugs from run dates. `frontend/lib/routes.js` builds that mapping from live data
rather than a fixture, so it holds across all 360 clients.

## Documents

| file | what |
|---|---|
| `CONTENT-HUB-SCHEMA.md` | the backend schema and API as they stand today |
| `PARALLEL-AGENT-PLAN.md` | plan for per-asset, parallel generation |
| `supabase/migrations/` | the v2 schema those two describe |
| `design-handoff/` | the Claude Design source the frontend was built from |
