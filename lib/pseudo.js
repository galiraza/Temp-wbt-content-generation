// GENERATED from the style-hover / style-focus attributes in
// "Content Generation.dc.html". Regenerate rather than hand-edit.
// Each entry maps the design's literal CSS string to the class that
// carries its :hover / :focus rule in globals.css.

const PSEUDO = {
  "background: #eae7e1; color: #16181c;": "scph0",
  "background: #efe7fb;": "scph1",
  "background: #efe7fb; border-color: #d6c7f2;": "scph2",
  "background: #faf8f5;": "scph3",
  "background: #faf9f6;": "scph4",
  "background: #fcfbf9;": "scph5",
  "background: #ffeadb;": "scph6",
  "background: #ffeadb; border-color: #f6cca9;": "scph7",
  "background: rgba(20,18,16,.78);": "scph8",
  "border-color: #aed7c1; background: #f3faf6;": "scph9",
  "border-color: #cbc6bd;": "scph10",
  "border-color: #cbc6bd; background: #faf9f6;": "scph11",
  "border-color: #cbc6bd; box-shadow: 0 6px 20px rgba(20,18,16,.09);": "scph12",
  "border-color: #cbc6bd; color: #4b4741;": "scph13",
  "border-color: #f0bd97; color: #cf5c17;": "scph14",
  "border-color: #f2b98e;": "scph15",
  "border-color: #f6cca9; color: #cf5c17;": "scph16",
  "box-shadow: 0 10px 30px rgba(20,18,16,.08);": "scph17",
  "color: #16181c;": "scph18",
  "transform: translateY(-1px);": "scph19",
  "transform: translateY(-1px); box-shadow: 0 12px 26px rgba(217,84,26,.34);": "scph20",
  "focus:border-color: #f2b98e;": "scpf0"
};

/** Class for a style-hover="..." value from the design. */
export function hv(css) {
  const cls = PSEUDO[css];
  if (!cls && process.env.NODE_ENV !== 'production') {
    console.warn('[pseudo] no hover rule generated for:', css);
  }
  return cls || '';
}

/** Class for a style-focus="..." value from the design. */
export function fc(css) {
  const cls = PSEUDO['focus:' + css];
  if (!cls && process.env.NODE_ENV !== 'production') {
    console.warn('[pseudo] no focus rule generated for:', css);
  }
  return cls || '';
}

/** Join a hover class with an optional focus class. */
export function hf(hoverCss, focusCss) {
  return [hv(hoverCss), focusCss ? fc(focusCss) : ''].filter(Boolean).join(' ');
}
