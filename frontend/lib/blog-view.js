// Blog viewer support.
//
// QC_AREAS is display config — the weighting table the QC prompt itself uses,
// from BlogCard.tsx — so it stays in the frontend.
//
// The per-blog brief and QC results (funnel stage, keywords, meta title, GMB
// post, score breakdown) are NOT yet exposed by the hub API: they live in
// `cg_asset_versions.data`, which the v2 migration adds. Until that ships,
// `blogsFromAssets` returns what the API really has and marks the rest absent
// rather than inventing it.

export const QC_AREAS = [
  { key: 'word_count', label: 'Word count', max: 1 },
  { key: 'uk_grammar', label: 'UK grammar', max: 2 },
  { key: 'structure', label: 'Structure', max: 1 },
  { key: 'keywords', label: 'Keywords', max: 2 },
  { key: 'funnel_stage', label: 'Funnel stage', max: 1 },
  { key: 'brand_alignment', label: 'Brand', max: 1 },
  { key: 'no_emoji', label: 'No emoji', max: 1 },
  { key: 'cta_strength', label: 'CTA', max: 1 },
];

const words = (s) => String(s || '').trim().split(/\s+/).filter(Boolean).length;

/**
 * Live blog assets -> the records the viewer renders.
 * `data` is whatever the API returned alongside the body; everything derived
 * from it is optional, so a field the backend has not started sending yet
 * simply does not render.
 */
export function blogsFromAssets(items) {
  return (items || []).map((it, i) => {
    const d = it.data || {};
    return {
      id: it.id,
      blog_number: i + 1,
      title: it.title || '',
      content: it.caption || '',
      status: it.status,
      word_count: d.word_count ?? words(it.caption),

      // Everything below arrives with cg_asset_versions.data.
      funnel_stage: d.funnel_stage || null,
      service_areas: d.service_areas || [],
      keywords: d.keywords || [],
      general_notes: d.general_notes || null,
      meta_title: d.meta_title || null,
      meta_description: d.meta_description || null,
      gmb_post: d.gmb_post || null,
      gmb_faq: d.gmb_faq || null,
      qc_score: typeof d.qc_score === 'number' ? d.qc_score : null,
      qc_breakdown: d.qc_breakdown || {},
      qc_fixes: d.qc_fixes || [],
      revision_attempts: d.revision_attempts ?? 1,
    };
  });
}
