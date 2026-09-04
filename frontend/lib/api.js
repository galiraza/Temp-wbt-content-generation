// The WBT Content Hub API, server-side.
//
// Backend: Paid_Ads_Generation (branch wbt-web), FastAPI on HUB_API_URL.
// Every route needs `X-API-Key` except /docs, /openapi.json, /redoc, /health.
//
// Deliberately server-only. The old frontend reads NEXT_PUBLIC_API_KEY, which
// ships the key to the browser; this repo's catch-all route is a server
// component, so the key stays on the server and never reaches the client.
//
// Adapters at the bottom convert the API's shapes into the ones the design
// renders, so the component keeps one vocabulary whether data comes from the
// API or not.

import 'server-only';

const BASE = (process.env.HUB_API_URL || 'http://127.0.0.1:8001').replace(/\/$/, '');
const KEY = process.env.HUB_API_KEY || '';
const ROOT = BASE + '/api/content-generation';

export class HubError extends Error {
  constructor(message, status, url) {
    super(message);
    this.name = 'HubError';
    this.status = status;
    this.url = url;
  }
}

async function get(path, { timeout = 20000, revalidate = 30 } = {}) {
  const url = path.startsWith('http') ? path : ROOT + path;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetch(url, {
      headers: { 'X-API-Key': KEY },
      signal: controller.signal,
      next: { revalidate },
    });
    if (!res.ok) {
      throw new HubError(`${res.status} ${res.statusText}`, res.status, url);
    }
    return await res.json();
  } catch (err) {
    if (err instanceof HubError) throw err;
    throw new HubError(err.name === 'AbortError' ? `timed out after ${timeout}ms` : err.message, 0, url);
  } finally {
    clearTimeout(timer);
  }
}

// --- raw endpoints ----------------------------------------------------------

export const listClients = () => get('/clients', { revalidate: 300 });
export const getOverview = (clientId) => get(`/clients/${clientId}/overview`);
export const getAssets = (clientId, params) =>
  get(`/clients/${clientId}/assets?${new URLSearchParams(params)}`);
export const getAssetBySlug = (clientId, slug) => get(`/clients/${clientId}/assets/by-slug/${slug}`);
export const getAsset = (assetId) => get(`/assets/${assetId}`);
export const getChat = (assetId) => get(`/assets/${assetId}/chat`);
export const getDraft = (clientId, contentType) =>
  get(`/clients/${clientId}/draft?content_type=${contentType}`);
export const getSettings = () => get('/settings');

/** Onboarding data the forms prefill from. Different router prefix. */
export const getPrefill = (clientId) =>
  get(`${BASE}/api/client-export/${clientId}/prefill`, { revalidate: 300 });

/** The website-content industry vocabulary (many-select). */
export const getIndustries = () =>
  get(`${BASE}/api/website-content/industries`, { revalidate: 3600 });

/** Is the backend reachable and is the key accepted? */
export async function health() {
  const started = Date.now();
  try {
    await get(`${BASE}/health`, { timeout: 5000, revalidate: 0 });
    const clients = await listClients();
    return { ok: true, ms: Date.now() - started, clients: clients.length, base: BASE, keySet: !!KEY };
  } catch (err) {
    return { ok: false, ms: Date.now() - started, error: err.message, status: err.status, base: BASE, keySet: !!KEY };
  }
}

// --- adapters ---------------------------------------------------------------

/** HubClientOut[] -> the client list the switcher renders. */
export function toClients(rows) {
  return (rows || []).map(c => ({
    id: c.client_id,
    name: c.client_name,
    meta: c.meta || `${c.asset_count ?? 0} assets`,
    assetCount: c.asset_count ?? 0,
    lastRunAt: c.last_run_at || null,
  }));
}

//: The API returns `ads`; the design's tab is `meta`. One rename, kept here so
//: nothing downstream has to know the two vocabularies differ.
const SECTION_ID = { website: 'website', social: 'posts', blog: 'blog', logo: 'logo', ads: 'meta' };
export const toContentTypeId = (apiId) => SECTION_ID[apiId] || apiId;
export const toApiContentType = (id) =>
  Object.keys(SECTION_ID).find(k => SECTION_ID[k] === id) || id;

//: The API says `stories`; the design's sub is `story`.
const SUB_ID = { stories: 'story' };
export const toSubId = (apiSub) => SUB_ID[apiSub] || apiSub;

/** HubContentTypeOut[] -> the section tabs, in the design's shape. */
export function toSections(contentTypes) {
  return (contentTypes || []).map(t => ({
    id: toContentTypeId(t.id),
    apiId: t.id,
    label: t.label,
    count: t.count ?? 0,
    unit: t.unit || 'items',
    newLabel: t.unit || 'items',
    single: !!t.single,
    table: !!t.table,
    monthly: !!t.monthly,
    logo: !!t.logo,
    subs: (t.sections || []).map(s => ({
      id: toSubId(s.id),
      apiId: s.id,
      label: s.label,
      count: s.count ?? 0,
    })),
  }));
}

/** HubRunOut[] -> the run-history drawer's rows. */
export function toRuns(rows) {
  return (rows || []).map(r => ({
    id: r.run_id,
    contentType: toContentTypeId(r.content_type),
    version: 'v' + r.version,
    versionNumber: r.version,
    status: r.status,
    period: r.period || null,
    date: r.created_at ? new Date(r.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '',
    createdAt: r.created_at || null,
    summary: r.summary || '',
    approved: r.approved_label || '',
    author: r.requested_by || '',
  }));
}

/**
 * HubAssetOut[] -> the cards the grid renders.
 *
 * The API's `body` already carries the contact block the generator wrote into
 * it, and no hashtags — so unlike the prototype's dummy rows there is nothing
 * to append. Whatever the generator produced is what shows.
 */
export function toItems(rows) {
  return (rows || [])
    .slice()
    .sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
    .map((a, i) => ({
      id: a.asset_id,
      assetId: a.asset_id,
      runId: a.run_id,
      section: toSubId(a.section),
      kind: a.type,
      index: String(i + 1).padStart(2, '0'),
      position: a.position ?? i,
      title: a.title || '',
      caption: a.body || '',
      hashtags: [],
      slug: a.slug || null,
      status: a.status,
      activeVersion: a.active_version ?? 1,
      filePath: a.file_path || null,
      approvedAt: a.approved_at || null,
      updatedAt: a.updated_at || null,
    }));
}

/** HubVersionOut[] -> the version-history rows. */
export function toVersions(rows) {
  return (rows || []).map(v => ({
    version: v.version,
    body: v.body || '',
    filePath: v.file_path || null,
    isActive: !!v.is_active,
    createdAt: v.created_at || null,
  }));
}

/** HubChatMessageOut[] -> the AI Edit transcript. */
export function toMessages(rows) {
  return (rows || []).map(m => ({
    id: m.message_id,
    version: m.version,
    role: m.role || 'user',
    content: m.body || '',
    createdAt: m.created_at || null,
  }));
}

/** ClientPrefill -> the form field values, keyed by form-spec field key. */
export function toPrefill(p) {
  if (!p) return {};
  return {
    business_name: p.company_name,
    company_name: p.company_name,
    client_name: p.company_name,
    phone: p.phone,
    email: p.email,
    address: p.address,
    country: p.country,
    region: p.region,
    zip: p.postcode,
    website_url: p.website_url,
    industry: p.industry,
    industries: p.industries || [],
    other_industry: p.other_industries,
    sitemap_text: p.sitemap_text,
    unique_selling_points: p.usps,
    usps: p.usps,
    _sitemap_status: p.sitemap_status || 'none',
    _sitemap_page_count: p.sitemap_page_count ?? 0,
  };
}

/**
 * Request a run. Returns 202, not 201: the run exists, the work it describes
 * has not happened yet — a website run is up to seventeen agent calls, so the
 * backend puts it behind BackgroundTasks rather than holding the connection.
 */
export async function createRun(clientId, { contentType, source = {}, period, requestedBy }) {
  const url = `${ROOT}/clients/${clientId}/runs`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'X-API-Key': KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content_type: contentType,
      source,
      ...(period ? { period } : {}),
      ...(requestedBy ? { requested_by: requestedBy } : {}),
    }),
    cache: 'no-store',
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new HubError(detail, res.status, url);
  }
  return res.json();
}
