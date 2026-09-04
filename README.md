# WBT Content Hub — frontend

The client-first content hub: pick a client, then review, edit, approve and
export every generated asset in one place.

Next.js App Router, talking to the FastAPI backend in
[WBT-Content-Generation](https://github.com/Metavviz/WBT-Content-Generation)
(branch `wbt-web`), which owns the agents, the prompts and the Supabase database.

## Running it

```bash
npm install
cp .env.example .env.local     # then fill in the two values
npm run dev                    # http://localhost:3000
```

The backend must be up:

```bash
cd ../Paid_Ads_Generation/backend
./venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8001 --host 127.0.0.1
```

`/api-check` reports whether the connection and the key are good, and prints a
sample of what each endpoint returned. Start there when something looks empty.

## How data flows

Nothing is hard-coded. The catch-all route fetches clients, the overview, the
section's assets, the industry list and the client's onboarding record, then
hands them to one component.

```
app/content/[[...slug]]/page.js   server: fetch + canonicalise the URL
  └ components/ContentRoute.jsx   client: URL <-> state, run requests
      └ components/ContentGeneration.jsx   the panel
```

The API key lives in `HUB_API_KEY` and is read **only** on the server, so it
never reaches the browser.

## URLs

Every level is addressable, and short forms redirect up to the canonical path.

```
/content/{client}/{section}/{run}/{sub}/{id}/{slug}
/content/{client}/website/{run}/page/{slug}          website has no id segment

/content/cafgas-cic/social-media/run-2026-09-01/posts/01/why-your-boilers-age-matters
/content/cafgas-cic/website/run-2026-09-01/page/home-page
/content/cafgas-cic/blogs/run-2026-09-01/2026-09
```

Segments are names, never internal ids: client slugs come from client names,
run slugs from run dates. `lib/routes.js` builds that mapping from live data
rather than a fixture, so it works across all 360 clients.

## Layout

```
app/
  content/[[...slug]]/   the hub
  api-check/             live connection diagnostics
  actions.js             server actions (requesting a run)
lib/
  api.js                 the hub API client + adapters      (server-only)
  routes.js              URL model, directory-driven
  forms.js               generation form specs, per section
  ui.js                  accent, stripe, view sets
  markdown.jsx           the small renderer page bodies use
  export-pages.js        Word / Markdown / text / JSON export
  blog-sections.js       blog export, incl. PDF via jspdf
supabase/migrations/     schema v2 (see PARALLEL-AGENT-PLAN.md)
```

## Documents

- `CONTENT-HUB-SCHEMA.md` — the backend schema and API as it stands today
- `PARALLEL-AGENT-PLAN.md` — plan for per-asset, parallel generation
- `supabase/migrations/` — the v2 schema those two describe
