'use client';

// A small markdown renderer for page bodies.
//
// The reference project uses react-markdown; this covers the subset the
// generator actually emits — h2/h3, bullet and numbered lists, paragraphs and
// **bold** — without pulling in a dependency, and styles it in the design's own
// type scale rather than a second one.
//
// It renders real elements (never dangerouslySetInnerHTML), which also means the
// Word export can read the rendered innerHTML back out of the DOM and get
// exactly what is on screen.

import { css } from '@/lib/css';

const H2 = 'margin: 0; font-size: 17px; font-weight: 800; letter-spacing: -.015em; color: #0f2f2b; text-wrap: pretty;';
const H3 = 'margin: 0; font-size: 14px; font-weight: 700; letter-spacing: -.01em; color: #16181c; text-wrap: pretty;';
const P = 'margin: 0; font-size: 13.5px; line-height: 1.68; color: #58544e; text-wrap: pretty;';
const UL = 'margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 6px;';
const LI = 'font-size: 13.5px; line-height: 1.6; color: #58544e; text-wrap: pretty;';

/** Split **bold** runs into <strong>, leaving the rest as text. */
function inline(text) {
  const out = [];
  const re = /\*\*(.+?)\*\*/g;
  let last = 0;
  let m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(<strong key={m.index} style={css('font-weight: 700; color: #16181c;')}>{m[1]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** Group the source into blocks: heading, list or paragraph. */
export function parseBlocks(src) {
  const blocks = [];
  let list = null;

  const flush = () => { if (list) { blocks.push(list); list = null; } };

  for (const raw of String(src || '').split('\n')) {
    const line = raw.trimEnd();

    if (!line.trim()) { flush(); continue; }

    const h3 = /^###\s+(.*)$/.exec(line);
    if (h3) { flush(); blocks.push({ type: 'h3', text: h3[1] }); continue; }

    const h2 = /^##\s+(.*)$/.exec(line);
    if (h2) { flush(); blocks.push({ type: 'h2', text: h2[1] }); continue; }

    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (bullet) {
      if (!list || list.ordered) { flush(); list = { type: 'list', ordered: false, items: [] }; }
      list.items.push(bullet[1]);
      continue;
    }

    const numbered = /^\d+\.\s+(.*)$/.exec(line);
    if (numbered) {
      if (!list || !list.ordered) { flush(); list = { type: 'list', ordered: true, items: [] }; }
      list.items.push(numbered[1]);
      continue;
    }

    flush();
    const prev = blocks[blocks.length - 1];
    if (prev && prev.type === 'p') prev.text += ' ' + line.trim();
    else blocks.push({ type: 'p', text: line.trim() });
  }

  flush();
  return blocks;
}

export default function Markdown({ children }) {
  const blocks = parseBlocks(children);
  return (
    <div style={css('display: flex; flex-direction: column; gap: 14px;')}>
      {blocks.map((b, i) => {
        if (b.type === 'h2') return <h2 key={i} style={css(H2)}>{inline(b.text)}</h2>;
        if (b.type === 'h3') return <h3 key={i} style={css(H3)}>{inline(b.text)}</h3>;
        if (b.type === 'list') {
          const Tag = b.ordered ? 'ol' : 'ul';
          return (
            <Tag key={i} style={css(UL)}>
              {b.items.map((it, j) => <li key={j} style={css(LI)}>{inline(it)}</li>)}
            </Tag>
          );
        }
        return <p key={i} style={css(P)}>{inline(b.text)}</p>;
      })}
    </div>
  );
}
