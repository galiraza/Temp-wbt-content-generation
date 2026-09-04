import { redirect } from 'next/navigation';
import ContentRoute from '@/components/ContentRoute';
import {
  getAssets, getIndustries, getOverview, getPrefill, listClients,
  toApiContentType, toClients, toItems, toPrefill, toRuns, toSections,
} from '@/lib/api';
import {
  ROOT, buildDirectory, contentPath, resolveRoute, runsForSection,
} from '@/lib/routes';
import { BLOG_VIEWS, DEFAULT_VIEWS, VIEW_SETS } from '@/lib/ui';

// Live data, so a stale URL must not be cached into a 200 forever.
export const dynamic = 'force-dynamic';

const VIEW_OPTS = { viewSets: VIEW_SETS, blogViews: BLOG_VIEWS, defaultViews: DEFAULT_VIEWS };

/**
 * Every level is addressable, and a short form redirects up to the canonical
 * path:
 *   /content                                -> default client + section + latest run
 *   /content/{client}                       -> + section, run, sub
 *   /content/{client}/{section}             -> + run, sub
 *   /content/{client}/{section}/{run}       -> + sub
 *   /content/{client}/{section}/{run}/{sub} canonical list
 *   .../{sub}/{id}/{slug}                   canonical item (website: .../page/{slug})
 */
export default async function Page({ params, searchParams }) {
  const { slug = [] } = await params;
  const sp = (await searchParams) || {};
  const viewParam = Array.isArray(sp.view) ? sp.view[0] : sp.view;

  // The switcher lists every client HQ knows; the panel only ever renders one.
  const clients = toClients(await listClients());
  if (!clients.length) {
    return <Empty message="The hub returned no clients." />;
  }

  // Resolve the client first — everything else is scoped to it, and the
  // overview is one request rather than one per tab.
  const dirForClient = buildDirectory({ clients });
  const clientId = dirForClient.clientBySlug.get(slug[0]) || defaultClient(clients).id;

  const overview = await getOverview(clientId);
  const sections = toSections(overview.content_types);
  const runs = toRuns(overview.runs);
  const directory = buildDirectory({ clients, sections, runs });

  // Resolve against the client we actually picked. Without substituting it in,
  // resolveRoute falls back to clients[0] — alphabetical, not the one that was
  // last worked on.
  const segments = slug.length
    ? [directory.clientSlugs.get(clientId) || slug[0], ...slug.slice(1)]
    : [directory.clientSlugs.get(clientId)];

  const route = resolveRoute(directory, segments, viewParam, VIEW_OPTS);
  if (!route.section) return <Empty message="That client has no content types." />;

  const canonical = contentPath(directory, route, VIEW_OPTS);
  const asked = [ROOT, ...segments].join('/') + (viewParam ? '?view=' + viewParam : '');
  if (asked !== canonical) redirect(canonical);

  // Assets for the section on screen. Blog is scoped further by period, which
  // is what its month sub-tabs are.
  const section = sections.find(s => s.id === route.section);
  const run = runsForSection(directory, route.section).find(r => r.id === route.runId);
  const query = { content_type: toApiContentType(section.apiId || section.id) };
  if (section.monthly && route.sub) query.period = route.sub;
  if (run) query.version = run.versionNumber;

  const [items, industries, prefill] = await Promise.all([
    getAssets(clientId, query).then(toItems).catch(() => []),
    getIndustries().catch(() => []),
    getPrefill(clientId).then(toPrefill).catch(() => ({})),
  ]);

  const data = {
    clients,
    sections,
    runs,
    items,
    industries,
    prefill,
    client: clients.find(c => c.id === clientId) || clients[0],
  };

  return (
    <ContentRoute
      route={route}
      routeKey={canonical}
      directory={serialisable(directory)}
      data={data}
    />
  );
}

/** The client the hub opens on: the most recently run, else the first. */
function defaultClient(clients) {
  const withRun = clients.filter(c => c.lastRunAt);
  if (!withRun.length) return clients[0];
  return withRun.sort((a, b) => (a.lastRunAt < b.lastRunAt ? 1 : -1))[0];
}

/** Maps do not survive the server/client boundary; arrays do. */
function serialisable(dir) {
  return {
    clients: dir.clients,
    sections: dir.sections,
    runs: dir.runs,
    clientSlugs: [...dir.clientSlugs],
    runSlugs: [...dir.runSlugs],
  };
}

function Empty({ message }) {
  return (
    <main style={{ padding: 40, fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif", background: '#f6f5f2', minHeight: '100vh' }}>
      <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: '#0f2f2b' }}>Nothing to show</h1>
      <p style={{ marginTop: 8, fontSize: 14, color: '#6c6862' }}>{message}</p>
      <p style={{ marginTop: 16, fontSize: 13 }}><a href="/api-check" style={{ color: '#d9541a' }}>Check the API connection →</a></p>
    </main>
  );
}
