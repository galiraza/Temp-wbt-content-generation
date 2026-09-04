// Pure UI configuration — the parts of the old lib/data.js that were never
// data. Everything else (clients, sections, runs, assets, industries) now comes
// from the hub API via lib/api.js.

export const ACCENT = '#d9541a';

/** The diagonal-stripe placeholder used wherever an image has not been generated. */
export function stripe(h) {
  return 'repeating-linear-gradient(135deg, hsl(' + h + ' 14% 94%) 0 7px, hsl(' + h + ' 14% 90%) 7px 14px)';
}

export const VIEW_LABELS = {
  content: 'Content',
  images: 'Images',
  videos: 'Videos',
  preview: 'Preview',
  sections: 'Sections',
  briefs: 'Briefs & QC',
};

/**
 * Which view switcher a sub-tab gets.
 *
 * Reels carry video rather than stills, and Blog uses the reference repo's two
 * reading modes instead of the card views.
 */
export const VIEW_SETS = {
  'posts:reels': ['content', 'videos', 'preview'],
  'posts:story': ['content', 'images', 'preview'],
  'meta:ads': ['content', 'images', 'preview'],
};

export const DEFAULT_VIEWS = ['content', 'images', 'preview'];
export const BLOG_VIEWS = ['sections', 'briefs'];
