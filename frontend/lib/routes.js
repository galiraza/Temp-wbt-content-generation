// ============================================================================
// URL model for the content hub — driven by live data.
//
//   /content/{client}/{section}/{run}/{sub}/{id}/{slug}
//   /content/{client}/website/{run}/page/{slug}          <- website has no id
//
// Every segment is a readable name, never an internal code. The API deals in
// UUIDs (client 37461550-…, run 9f2c…); those are mapped to names here.
//
//   client  37461550-e2d1-…  -> cafgas-cic          (from client_name)
//   run     9f2c8a41-…       -> run-2026-09-01      (from created_at, + -v2 on a clash)
//   section ads              -> meta-ads
//   sub     stories          -> stories
//   item    position 1       -> 01 + the API's own slug
//
// The item slug is the API's `cg_assets.slug`, which is unique per CLIENT and
// backs GET /clients/{id}/assets/by-slug/{slug} — so a link resolves with one
// request instead of scanning a section.
//
// Nothing is imported from a data file: every function takes a `directory`,
// built server-side from the API and handed to the client component. That is
// what makes these routes work against 360 real clients rather than a fixture.
// ============================================================================

export const ROOT = '/content';
export const DEFAULT_VIEW = 'content';

/** URL-safe slug. Strips accents and punctuation, including curly quotes. */
export function slugify(text) {
  return String(text)
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[’'`]/g, '')
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
    .replace(/-+$/, '');
}

// --- section id <-> url slug -------------------------------------------------
export const SECTION_SLUG = {
  website: 'website',
  posts: 'social-media',
  blog: 'blogs',
  logo: 'logos',
  meta: 'meta-ads',
};
const SECTION_ID = Object.fromEntries(Object.entries(SECTION_SLUG).map(([k, v]) => [v, k]));

// --- sub-tab id <-> url slug, per section -----------------------------------
// Anything unlisted passes through, which is what the Blog months want.
export const SUB_SLUG = {
  website: { pages: 'page' },
  posts: { posts: 'posts', reels: 'reels', reviews: 'reviews', story: 'stories' },
  blog: {},
  logo: { scratch: 'scratch', revamp: 'revamp' },
  meta: { ads: 'ads' },
};

export const sectionSlug = (id) => SECTION_SLUG[id] || id;
export const subSlug = (sectionId, subId) => (SUB_SLUG[sectionId] || {})[subId] || subId;

function subIdFromSlug(section, slug) {
  if (!section || !slug) return null;
  const map = SUB_SLUG[section.id] || {};
  const id = Object.keys(map).find(k => map[k] === slug) || slug;
  return (section.subs || []).some(s => s.id === id) ? id : null;
}

/**
 * Build the slug directory the routes work from.
 *
 * Client slugs are the client's own name. Two clients can share one (HQ has
 * near-duplicates), so a clash gets a numeric suffix rather than silently
 * resolving to whichever row came back first.
 *
 * Run slugs are the run's date. Two runs of the same content type on one day
 * would collide, so those disambiguate on version.
 */
export function buildDirectory({ clients = [], sections = [], runs = [] } = {}) {
  const clientSlugs = new Map();
  const seenClient = new Map();
  for (const c of clients) {
    const base = slugify(c.name) || 'client';
    const n = (seenClient.get(base) || 0) + 1;
    seenClient.set(base, n);
    clientSlugs.set(c.id, n === 1 ? base : `${base}-${n}`);
  }

  const runSlugs = new Map();
  const seenRun = new Map();
  for (const r of runs) {
    const date = (r.createdAt || '').slice(0, 10);
    const base = date ? `run-${date}` : `run-${slugify(r.version || r.id)}`;
    const n = (seenRun.get(base) || 0) + 1;
    seenRun.set(base, n);
    runSlugs.set(r.id, n === 1 ? base : `${base}-${r.version}`);
  }

  return {
    clients,
    sections,
    runs,
    clientSlugs,
    runSlugs,
    clientBySlug: new Map([...clientSlugs].map(([id, s]) => [s, id])),
    runBySlug: new Map([...runSlugs].map(([id, s]) => [s, id])),
  };
}

export const EMPTY_DIRECTORY = buildDirectory();

const clientSlug = (dir, id) => dir.clientSlugs.get(id) || id;
const runSlug = (dir, id) => dir.runSlugs.get(id) || id;
const sectionById = (dir, id) => dir.sections.find(s => s.id === id) || dir.sections[0] || null;

/** Runs that belong to one section — a run is scoped to a content type. */
export function runsForSection(dir, sectionId) {
  return dir.runs.filter(r => r.contentType === sectionId);
}

/** Sections rendered as a table or a logo grid have no view switcher. */
export function showsViews(dir, sectionId) {
  const s = sectionById(dir, sectionId);
  return !!s && !s.logo && !s.table;
}

/** The view switcher's options. Blog swaps the card views for reading modes. */
export function viewsFor(dir, sectionId, subId, viewSets, blogViews, defaultViews) {
  const s = sectionById(dir, sectionId);
  if (s && s.monthly) return blogViews;
  return viewSets[sectionId + ':' + subId] || defaultViews;
}

/** Build a canonical path. Omits the item segments when no item is given. */
export function contentPath(dir, route = {}, opts = {}) {
  const { viewSets = {}, blogViews = [], defaultViews = [] } = opts;
  const section = sectionById(dir, route.section);
  if (!section) return ROOT;

  const client = dir.clients.find(c => c.id === route.clientId) || dir.clients[0];
  if (!client) return ROOT;

  const sectionRuns = runsForSection(dir, section.id);
  const run = sectionRuns.find(r => r.id === route.runId) || sectionRuns[0] || null;
  const subId = (section.subs || []).some(s => s.id === route.sub)
    ? route.sub
    : (section.subs && section.subs[0] ? section.subs[0].id : 'all');

  const parts = [
    ROOT,
    clientSlug(dir, client.id),
    sectionSlug(section.id),
    run ? runSlug(dir, run.id) : 'latest',
    subSlug(section.id, subId),
  ];

  if (route.itemSlug) {
    // Website addresses a page group by slug alone; every other section carries
    // the run-scoped ordinal first.
    if (section.id !== 'website' && route.itemId) parts.push(route.itemId);
    parts.push(route.itemSlug);
  }

  let path = parts.join('/');

  if (showsViews(dir, section.id) && route.view) {
    const allowed = viewsFor(dir, section.id, subId, viewSets, blogViews, defaultViews);
    // The first option is the default, so it never needs to appear in the URL.
    if (allowed.includes(route.view) && route.view !== allowed[0]) path += '?view=' + route.view;
  }
  return path;
}

/**
 * Turn URL segments into a validated route of internal ids.
 *
 * Anything unrecognised falls back to something real rather than 404-ing, so a
 * hand-typed or stale URL still lands on a page; contentPath() then gives the
 * canonical form to redirect to.
 */
export function resolveRoute(dir, segments = [], viewParam, opts = {}) {
  const { viewSets = {}, blogViews = [], defaultViews = [] } = opts;
  const [clientSeg, sectionSeg, runSeg, subSeg, ...rest] = segments;

  const clientId = dir.clientBySlug.get(clientSeg) || (dir.clients[0] && dir.clients[0].id) || null;
  const section = sectionById(dir, SECTION_ID[sectionSeg]);
  if (!section) return { clientId, section: null, runId: null, sub: null, itemId: null, itemSlug: null, view: DEFAULT_VIEW };

  const sectionRuns = runsForSection(dir, section.id);
  const wanted = dir.runBySlug.get(runSeg);
  const run = sectionRuns.find(r => r.id === wanted) || sectionRuns[0] || null;
  const sub = subIdFromSlug(section, subSeg) || (section.subs && section.subs[0] ? section.subs[0].id : null);

  let itemId = null;
  let itemSlug = null;
  if (rest.length) {
    if (section.id === 'website') itemSlug = rest[0];
    else { itemId = rest[0]; itemSlug = rest[1] || null; }
  }

  let view = DEFAULT_VIEW;
  if (showsViews(dir, section.id)) {
    const allowed = viewsFor(dir, section.id, sub, viewSets, blogViews, defaultViews);
    view = allowed[0];
    if (viewParam && allowed.includes(viewParam)) view = viewParam;
  }

  return { clientId, section: section.id, runId: run ? run.id : null, sub, itemId, itemSlug, view };
}

/** Public id for the nth item of a run — "01", "02", matching the card's tag. */
export function itemId(index) {
  return String(index + 1).padStart(2, '0');
}
