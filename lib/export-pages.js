// Client-side export of a website content run.
//
// The four formats from Paid_Ads_Generation/frontend/components/website-content/
// exportSections.ts, adapted to this project's data shape. PDF is not here for
// the same reason it is not there: it needs a server route neither project has.
//
// The JSON export deliberately emits the `sections[]` shape the Content
// Generation API documents, so a payload exported here is interchangeable with
// one delivered by the pipeline.

/** Trigger a browser download from in-memory content. Browser-only. */
export function downloadFile(content, filename, type = 'text/plain;charset=utf-8') {
  const blob = typeof content === 'string' ? new Blob([content], { type }) : content;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** "Green Touch Ltd" -> "green-touch-ltd" */
export function slugify(value, fallback = 'export') {
  const slug = String(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
  return slug || fallback;
}

/** Thousands separators. */
export function formatNumber(value) {
  return new Intl.NumberFormat('en-GB').format(value);
}

const escapeHtml = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const withContent = (pages) => pages.filter(p => (p.content || '').trim().length > 0);

const header = (meta) => `${meta.client} — website content (${meta.date}${meta.version ? ', ' + meta.version : ''})`;

export function toMarkdown(meta, pages) {
  const parts = [`# ${header(meta)}`];
  for (const p of withContent(pages)) {
    parts.push(`\n---\n\n## ${p.name}\n\n${(p.content || '').trim()}`);
  }
  return parts.join('\n\n');
}

/**
 * Strip the markdown syntax out of a body.
 *
 * The reference implementation drops the raw source into the .txt, which leaves
 * "## Heading" and "**bold**" in a file whose whole promise is no formatting
 * characters. Headings keep their text, bullets become a bullet character.
 */
function stripMarkdown(src) {
  return String(src || '')
    .split('\n')
    .map(line => line
      .replace(/^#{1,6}\s+/, '')
      .replace(/^[-*]\s+/, '• ')
      .replace(/^(\d+)\.\s+/, '$1. ')
      .replace(/\*\*(.+?)\*\*/g, '$1')
      .replace(/(^|\W)_(.+?)_(\W|$)/g, '$1$2$3'))
    .join('\n');
}

export function toPlainText(meta, pages) {
  const head = header(meta);
  const parts = [head, '='.repeat(head.length)];
  for (const p of withContent(pages)) {
    parts.push(`\n\n${p.name}\n${'-'.repeat(p.name.length)}\n\n${stripMarkdown(p.content).trim()}`);
  }
  return parts.join('\n');
}

/**
 * A .doc that Word, Pages and Google Docs all open with headings intact.
 *
 * `bodyHtml` is what the Markdown component actually rendered, read at click
 * time — re-deriving it here would mean a second renderer that could disagree
 * with what is on screen.
 */
export function toWordDocument(meta, pages, bodyHtml) {
  const blocks = withContent(pages)
    .map(p => `<h2>${escapeHtml(p.name)}</h2>${bodyHtml(p)}`)
    .join('<hr />');
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(header(meta))}</title></head><body><h1>${escapeHtml(header(meta))}</h1>${blocks}</body></html>`;
}

/** The delivered payload, in the shape the Content Generation API documents. */
export function toJson(meta, pages) {
  return JSON.stringify(
    {
      jobId: meta.runId,
      status: 'completed',
      documentName: meta.client,
      version: meta.version,
      sections: withContent(pages).map(p => ({
        section_title: p.name,
        section_content: p.content || '',
      })),
    },
    null,
    2
  );
}

export function exportFilename(meta, ext) {
  return `${slugify(meta.client)}-website-content.${ext}`;
}

export const EXPORT_OPTIONS = [
  { key: 'doc', label: 'Word (.doc)', hint: 'Opens in Word, Pages or Google Docs' },
  { key: 'md', label: 'Markdown (.md)', hint: 'Headings and lists preserved' },
  { key: 'txt', label: 'Plain text (.txt)', hint: 'No formatting characters' },
  { key: 'json', label: 'JSON (.json)', hint: 'The delivered payload shape' },
];
