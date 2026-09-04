// Clipboard helpers, browser-only.
// Ported from Paid_Ads_Generation/frontend/lib/clipboard.ts.
//
// Website copy almost always ends up in a Google Doc or a CMS, so handing over
// raw markdown is the wrong thing — it pastes as literal "## Heading". Writing
// text/html AND text/plain together lets the target decide: Docs and Word take
// the formatted HTML, a code editor takes the source.
//
// Everything degrades rather than throws: ClipboardItem is missing on older
// Safari, and the whole API is undefined outside a secure context, which is why
// callers surface a failure instead of assuming success.

/** Copy plain text. Returns false when the clipboard isn't available. */
export async function copyText(text) {
  try {
    if (!navigator.clipboard?.writeText) return false;
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/**
 * Copy rich text with a plain-text alternative. `html` lands in editors that
 * accept formatting; `plain` lands everywhere else.
 */
export async function copyRich(html, plain) {
  try {
    if (typeof ClipboardItem === 'undefined' || !navigator.clipboard?.write) {
      return copyText(plain);
    }
    await navigator.clipboard.write([
      new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }),
        'text/plain': new Blob([plain], { type: 'text/plain' }),
      }),
    ]);
    return true;
  } catch {
    // Firefox rejects text/html in some configurations; plain text still works.
    return copyText(plain);
  }
}
