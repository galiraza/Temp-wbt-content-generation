// Blog run -> display sections, and the five export formats.
//
// Ported from Paid_Ads_Generation/frontend/lib/blog-sections.ts. The section
// assembly (blogMarkdown / blogSections / sectionSummary) and all five export
// builders match the source; PDF is built in the browser with jspdf the same
// way theirs is, loaded on demand so it stays out of the main bundle.

import { downloadFile, formatNumber, slugify } from './export-pages.js';

export { downloadFile, formatNumber, slugify };

const escapeHtml = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export function wordCount(markdown) {
  return String(markdown || '').trim().split(/\s+/).filter(Boolean).length;
}

/**
 * One blog as a single markdown document.
 *
 * Sections the model never returned are skipped rather than left as empty
 * headings, so a blog that lost its GMB FAQ reads as a blog without one instead
 * of a blog with a blank section.
 */
export function blogMarkdown(blog) {
  const parts = [];

  if (blog.general_notes) parts.push('## General Notes', blog.general_notes.trim());

  const meta = [];
  if (blog.meta_title) meta.push(`**Meta Title:** ${blog.meta_title}`);
  if (blog.meta_description) meta.push(`**Meta Description:** ${blog.meta_description}`);
  if (meta.length) parts.push(meta.join('\n\n'));

  if (blog.content) parts.push(blog.content.trim());

  if (blog.gmb_post) parts.push('---', '## Google My Business Post', blog.gmb_post.trim());
  if (blog.gmb_faq) parts.push('---', '## GMB FAQ', blog.gmb_faq.trim());

  return parts.join('\n\n').trim();
}

/** Every blog in a job, in order, as display sections. */
export function blogSections(blogs) {
  return blogs.map((blog) => {
    const body = blogMarkdown(blog);
    return {
      title: 'Blog ' + blog.blog_number,
      // Optional on purpose: a blog whose brief never parsed has no title, and
      // the row should read "Blog 3" rather than "Blog 3 —".
      subtitle: (blog.title || '').trim() || undefined,
      body,
      badge: typeof blog.qc_score === 'number' ? `Score ${blog.qc_score}/10` : undefined,
      words: wordCount(body),
    };
  });
}

export function totalWords(sections) {
  return sections.reduce((sum, s) => sum + s.words, 0);
}

/** The header line the viewer shows above the sections. */
export function sectionSummary(sections) {
  const count = sections.length;
  return `Content · ${count} ${count === 1 ? 'section' : 'sections'} · ${formatNumber(totalWords(sections))} words`;
}

export function exportSubtitle(meta) {
  return `${meta.documentName} — blog content (${meta.date}${meta.version ? ', ' + meta.version : ''})`;
}

// --- Export builders ---------------------------------------------------------

export function toMarkdownBody(sections) {
  return sections
    .map(s => `## ${s.title}${s.subtitle ? ' — ' + s.subtitle : ''}\n\n${s.body}`)
    .join('\n\n---\n\n');
}

export function toMarkdown(sections, meta) {
  return `# ${exportSubtitle(meta)}\n\n${toMarkdownBody(sections)}`;
}

/** Strip markdown syntax, for the plain-text export. */
export function toPlainText(markdown) {
  return String(markdown || '')
    .split('\n')
    .map(line => line
      .replace(/^#{1,6}\s+/, '')
      .replace(/^[-*]\s+/, '• ')
      .replace(/^---$/, '')
      .replace(/\*\*(.+?)\*\*/g, '$1'))
    .join('\n');
}

export function toPlainTextDocument(sections, meta) {
  const head = exportSubtitle(meta);
  const parts = [head, '='.repeat(head.length)];
  for (const s of sections) {
    const title = `${s.title}${s.subtitle ? ' — ' + s.subtitle : ''}`;
    parts.push(`\n\n${title}\n${'-'.repeat(title.length)}\n\n${toPlainText(s.body).trim()}`);
  }
  return parts.join('\n');
}

export function toWordDocument(meta, bodyHtml) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(exportSubtitle(meta))}</title></head><body><h1>${escapeHtml(exportSubtitle(meta))}</h1>${bodyHtml}</body></html>`;
}

export function toJson(blogs, meta) {
  return JSON.stringify(
    {
      jobId: meta.jobId,
      documentName: meta.documentName,
      version: meta.version,
      blogs: blogs.map(b => ({
        blog_number: b.blog_number,
        title: b.title,
        status: b.status,
        funnel_stage: b.funnel_stage,
        service_areas: b.service_areas,
        keywords: b.keywords,
        meta_title: b.meta_title,
        meta_description: b.meta_description,
        general_notes: b.general_notes,
        content: b.content,
        gmb_post: b.gmb_post,
        gmb_faq: b.gmb_faq,
        qc_score: b.qc_score,
        qc_breakdown: b.qc_breakdown,
        qc_fixes: b.qc_fixes,
        revision_attempts: b.revision_attempts,
        word_count: b.word_count,
      })),
    },
    null,
    2
  );
}

export function blogFilename(meta, ext) {
  return `${slugify(meta.documentName)}-blog-content.${ext}`;
}

/**
 * PDF, built in the browser. jspdf is imported on demand so it never lands in
 * the main bundle; it has no HTML renderer, so this is plain text rather than
 * the branded layout a server route would produce.
 */
export async function exportPdf(sections, meta) {
  const { default: JsPDF } = await import('jspdf');
  const doc = new JsPDF({ unit: 'pt', format: 'a4' });
  const marginX = 48;
  const marginY = 56;
  const width = doc.internal.pageSize.getWidth() - marginX * 2;
  const bottom = doc.internal.pageSize.getHeight() - marginY;
  let y = marginY;

  const write = (text, size, bold, gap) => {
    doc.setFont('helvetica', bold ? 'bold' : 'normal');
    doc.setFontSize(size);
    for (const line of doc.splitTextToSize(text, width)) {
      if (y > bottom) { doc.addPage(); y = marginY; }
      doc.text(line, marginX, y);
      y += size * 1.35;
    }
    y += gap;
  };

  write(meta.documentName, 18, true, 4);
  write(`Blog Content · job ${meta.jobId}`, 9, false, 14);

  sections.forEach((s, i) => {
    if (i > 0) { doc.addPage(); y = marginY; }
    write(`${s.title}${s.badge ? ' — ' + s.badge : ''}`, 14, true, 6);
    write(toPlainText(s.body), 10.5, false, 0);
  });

  doc.save(blogFilename(meta, 'pdf'));
}

export const BLOG_EXPORT_OPTIONS = [
  { key: 'pdf', label: 'PDF (.pdf)', hint: 'Send to a client' },
  { key: 'doc', label: 'Word (.doc)', hint: 'Opens in Word, Pages or Google Docs' },
  { key: 'md', label: 'Markdown (.md)', hint: 'Headings and lists preserved' },
  { key: 'txt', label: 'Plain text (.txt)', hint: 'No formatting characters' },
  { key: 'json', label: 'JSON (.json)', hint: 'The raw delivered payload' },
];
