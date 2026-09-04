// The design builds every style as a raw CSS declaration string — both the
// literals in the markup and the ones returned from renderVals() (secBtn,
// subBtn, viewBtn, iconBtn, stripe, ...). Keeping those strings untouched is
// what makes this port identical to the design, so instead of rewriting them
// as objects we parse them into React style objects at render time.

const cache = new Map();

const camel = (prop) =>
  prop.startsWith('--') ? prop : prop.replace(/-([a-z])/g, (_, c) => c.toUpperCase());

/**
 * Turn a CSS declaration string into a React style object.
 * `css("display: flex; gap: 8px;")` -> `{ display: 'flex', gap: '8px' }`
 *
 * Results are cached and frozen: the same string always yields the same
 * object, so React can skip re-applying styles that did not change.
 */
export function css(str) {
  if (!str) return undefined;

  const hit = cache.get(str);
  if (hit) return hit;

  const out = {};
  for (const decl of str.split(';')) {
    const d = decl.trim();
    if (!d) continue;
    const i = d.indexOf(':');
    if (i === -1) continue;
    const prop = d.slice(0, i).trim();
    if (!prop) continue;
    out[camel(prop)] = d.slice(i + 1).trim();
  }

  const frozen = Object.freeze(out);
  cache.set(str, frozen);
  return frozen;
}
