// Stand-in for the AI behind the AI Edit modal.
//
// There is no model here: `respond()` reads a few intents out of the message
// and returns the edited draft plus a line explaining what it did, so the
// preview on the right visibly tracks the chat on the left. It is deterministic,
// which keeps the prototype predictable to demo and to test.
//
// Replace respond() with the real call when the endpoint exists — the modal
// only needs { draft, reply } back.

const TITLE = /^\s*(?:new\s+)?title\s*[:—–-]\s*(.+)$/im;
const HASHTAG = /#[A-Za-z0-9_]+/g;
const REMOVE = /\b(remove|drop|delete|without|lose)\b/i;
const SHORTER = /\b(short|shorter|shorten|trim|concise|tighten|brief|cut)\b/i;
const LONGER = /\b(long|longer|expand|elaborate|more detail|flesh)\b/i;
const WARMER = /\b(warm|warmer|friendl|casual|softer|human)\b/i;
const STRONGER = /\b(strong|stronger|urgent|punch|direct|bold|firm)\b/i;

const paras = (s) => s.split('\n\n').filter(Boolean);
const sentence = (s) => {
  const t = String(s).trim().replace(/\s+/g, ' ').replace(/[.!?]+$/, '');
  return t ? t[0].toUpperCase() + t.slice(1) + '.' : '';
};

/**
 * @param {{title: string, caption: string, hashtags: string[]}} draft
 * @param {string} message  what the user typed
 * @returns {{draft: object, reply: string}}
 */
export function respond(draft, message) {
  const next = { title: draft.title, caption: draft.caption, hashtags: [...draft.hashtags] };
  const did = [];

  const titled = TITLE.exec(message);
  if (titled) {
    next.title = titled[1].trim();
    did.push('set the title');
  }

  const tags = message.match(HASHTAG) || [];
  if (tags.length && REMOVE.test(message)) {
    const drop = tags.map(t => t.toLowerCase());
    const before = next.hashtags.length;
    next.hashtags = next.hashtags.filter(h => !drop.includes(h.toLowerCase()));
    if (next.hashtags.length !== before) did.push('removed ' + tags.join(', '));
  } else if (tags.length) {
    const add = tags.filter(t => !next.hashtags.some(h => h.toLowerCase() === t.toLowerCase()));
    if (add.length) {
      next.hashtags = next.hashtags.concat(add);
      did.push('added ' + add.join(', '));
    }
  }

  if (SHORTER.test(message)) {
    const p = paras(next.caption);
    if (p.length > 1) {
      next.caption = p.slice(0, Math.max(1, p.length - 1)).join('\n\n');
      did.push('cut it back to ' + (p.length - 1) + ' paragraph' + (p.length - 1 === 1 ? '' : 's'));
    }
  }

  if (LONGER.test(message)) {
    next.caption += '\n\nOur engineers talk you through what they find before any work starts, so there are no surprises on the invoice.';
    did.push('added a paragraph');
  }

  if (WARMER.test(message)) {
    next.caption = 'We know how much a cold home takes out of your week.\n\n' + next.caption;
    did.push('opened on a warmer note');
  }

  if (STRONGER.test(message)) {
    next.caption += '\n\nBook today — the first cold week is when the diary fills up.';
    did.push('sharpened the call to action');
  }

  // Nothing matched: treat the message as direction and work it into the copy,
  // so the preview still responds to what was asked.
  if (!did.length) {
    const s = sentence(message);
    if (s) {
      next.caption += '\n\n' + s;
      return {
        draft: next,
        reply: "I've worked that into the caption. You can also say “make it shorter”, “warmer tone”, “title: …”, or name a #hashtag to add or remove.",
      };
    }
    return { draft: next, reply: 'Tell me what to change and I will update the draft on the right.' };
  }

  const list = did.length === 1 ? did[0] : did.slice(0, -1).join(', ') + ' and ' + did[did.length - 1];
  return { draft: next, reply: 'Done — ' + list + '. Apply changes when it reads right.' };
}

export const GREETING =
  'Tell me how to change this post — try “make it shorter”, “warmer tone”, “title: …”, or name a #hashtag.';
