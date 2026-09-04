import { health, listClients, getOverview, getAssets, getPrefill, getIndustries, toClients, toSections, toRuns, toItems, toPrefill } from '@/lib/api';

export const dynamic = 'force-dynamic';

// A live connection check against the hub backend. Server component, so the
// API key stays on the server.
export default async function Page() {
  const h = await health();
  let report = null;

  if (h.ok) {
    const clients = toClients(await listClients());
    const busiest = clients.filter(c => c.assetCount > 0).sort((a, b) => b.assetCount - a.assetCount)[0];
    const overview = busiest ? await getOverview(busiest.id) : null;
    const sections = overview ? toSections(overview.content_types) : [];
    const runs = overview ? toRuns(overview.runs) : [];
    const withAssets = sections.find(s => s.count > 0);
    const items = withAssets ? toItems(await getAssets(busiest.id, { content_type: withAssets.apiId })) : [];
    const prefill = busiest ? toPrefill(await getPrefill(busiest.id)) : {};
    const industries = await getIndustries();
    report = { clients, busiest, sections, runs, items, prefill, industries };
  }

  const mono = { fontFamily: "'IBM Plex Mono', ui-monospace, monospace", fontSize: 12.5 };
  return (
    <main style={{ padding: 28, fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif", color: '#16181c', background: '#f6f5f2', minHeight: '100vh' }}>
      <h1 style={{ margin: '0 0 4px', fontSize: 24, fontWeight: 800, color: '#0f2f2b' }}>Hub API connection</h1>
      <p style={{ margin: '0 0 20px', fontSize: 13.5, color: '#6c6862' }}>{h.base} · key {h.keySet ? 'set' : 'MISSING'}</p>

      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 9, padding: '9px 15px', borderRadius: 999, background: h.ok ? '#eef8f2' : '#fdecec', border: `1px solid ${h.ok ? '#c9e6d6' : '#f6cccc'}`, color: h.ok ? '#1f6b46' : '#c04141', fontWeight: 700, fontSize: 13.5 }}>
        {h.ok ? `connected · ${h.clients} clients · ${h.ms}ms` : `failed · ${h.error}${h.status ? ' (' + h.status + ')' : ''}`}
      </div>

      {report && (
        <div style={{ display: 'grid', gap: 16, marginTop: 22 }}>
          <Card title={`Clients — ${report.clients.length} live`}>
            <p style={mono}>with a run: {report.clients.filter(c => c.lastRunAt).length} · with assets: {report.clients.filter(c => c.assetCount > 0).length}</p>
            <ul style={{ ...mono, margin: 0, paddingLeft: 18 }}>
              {report.clients.filter(c => c.assetCount > 0).slice(0, 8).map(c => (
                <li key={c.id}>{c.name} — {c.assetCount} assets{c.lastRunAt ? ` · ${c.lastRunAt.slice(0, 10)}` : ''}</li>
              ))}
            </ul>
          </Card>

          <Card title={`Overview — ${report.busiest.name}`}>
            <ul style={{ ...mono, margin: 0, paddingLeft: 18 }}>
              {report.sections.map(s => (
                <li key={s.id}>{s.id} “{s.label}” count={s.count} unit={s.unit} subs=[{s.subs.map(x => `${x.id}:${x.count}`).join(' ')}]</li>
              ))}
            </ul>
            <p style={{ ...mono, marginTop: 10 }}>runs: {report.runs.map(r => `${r.version} ${r.contentType} ${r.status} (${r.approved})`).join(' · ') || 'none'}</p>
          </Card>

          <Card title={`Assets — ${report.items.length} returned`}>
            <ul style={{ ...mono, margin: 0, paddingLeft: 18 }}>
              {report.items.slice(0, 6).map(it => (
                <li key={it.id} style={{ marginBottom: 6 }}>
                  [{it.section}/{it.kind}] {it.status} — <strong>{it.title || '(untitled)'}</strong>
                  <br /><span style={{ color: '#8a857f' }}>{(it.caption || '').replace(/\n+/g, ' ').slice(0, 110)}…</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Prefill + industries">
            <ul style={{ ...mono, margin: 0, paddingLeft: 18 }}>
              {['business_name', 'phone', 'email', 'address', 'region', 'zip', 'website_url', 'industry'].map(k => (
                <li key={k}>{k}: {String(report.prefill[k] ?? '—')}</li>
              ))}
              <li>industries: {(report.prefill.industries || []).join(', ') || '—'} · sitemap: {report.prefill._sitemap_status}</li>
              <li>industry vocabulary: {report.industries.length} options</li>
            </ul>
          </Card>
        </div>
      )}
    </main>
  );
}

function Card({ title, children }) {
  return (
    <section style={{ background: '#fff', border: '1px solid #e6e4de', borderRadius: 16, padding: 18 }}>
      <h2 style={{ margin: '0 0 10px', fontSize: 14, fontWeight: 800, letterSpacing: '-.01em' }}>{title}</h2>
      {children}
    </section>
  );
}
