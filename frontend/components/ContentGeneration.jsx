'use client';

// ============================================================================
// Direct port of the Claude Design prototype "Content Generation.dc.html".
//
// The design's logic class is reproduced method-for-method below, and the
// markup is transcribed one-to-one:
//
//   <sc-if value="{{ x }}">      ->  {v.x && (<>...</>)}
//   <sc-for list="{{ xs }}" as="y"> ->  {v.xs.map((y, i) => ...)}
//   style="{{ y.style }}"        ->  style={css(y.style)}
//   style-hover="..."            ->  className={hv('...')}   (see lib/pseudo.js)
//
// DOM structure is preserved exactly, because the responsive rules in
// globals.css target it structurally (e.g. `[data-panel] > div:not([data-approve])`).
// ============================================================================

import React from 'react';
import { css } from '@/lib/css';
import { hv, fc } from '@/lib/pseudo';
import { ACCENT, BLOG_VIEWS, DEFAULT_VIEWS, VIEW_LABELS, VIEW_SETS, stripe } from '@/lib/ui';
import { itemId, slugify } from '@/lib/routes';
import { GREETING, respond } from '@/lib/ai-edit';
import { FORM_SPECS, formSections } from '@/lib/forms';
import { EMOJIS } from '@/lib/emoji';
import { QC_AREAS, blogsFromAssets } from '@/lib/blog-view';
import {
  BLOG_EXPORT_OPTIONS, blogFilename, blogSections, exportPdf, sectionSummary,
  toJson as blogToJson, toMarkdown as blogToMarkdown, toMarkdownBody,
  toPlainTextDocument, toWordDocument as blogToWord,
} from '@/lib/blog-sections';
import { copyRich } from '@/lib/clipboard';
import Markdown from '@/lib/markdown';
import {
  EXPORT_OPTIONS, downloadFile, exportFilename, formatNumber,
  toJson, toMarkdown, toPlainText, toWordDocument,
} from '@/lib/export-pages';

// Sections whose cards carry AI Edit in the header rather than the footer.
const AI_EDIT_ON_TOP = ['posts'];

// Sections whose cards carry no AI Edit control at all.
const AI_EDIT_HIDDEN = ['blog'];

// Blog swaps the Content / Images / Preview switcher for the reference repo's
// two reading modes.
const BLOG_VIEW_LABELS = { sections: 'Sections', briefs: 'Briefs & QC' };

// Section-heading icon tints used by the generation forms.
const ICON_TONE = {
  business: { bg: '#fff4ec', bd: '#fadfc9', fg: '#cf5c17' },
  doc: { bg: '#f2f6fd', bd: '#e1eaf8', fg: '#3b7fbf' },
  video: { bg: '#f4f2ee', bd: '#e8e5df', fg: '#6c6862' },
  image: { bg: '#f6f2fd', bd: '#e6dcf8', fg: '#6a4bbd' },
};

// State that the URL owns. Everything else (approvals, open modals, form
// drafts) stays local to the component, exactly as the design has it.
const ROUTE_KEYS = ['clientId', 'runId', 'section', 'sub', 'view'];

// A client with no runs yet still has to render a panel.
const EMPTY_RUN = { id: null, version: 'v1', versionNumber: 1, date: '', summary: '', approved: '', author: '', contentType: null };

const EMPTY_DATA = { clients: [], sections: [], runs: [], items: [], industries: [], prefill: {}, client: null };

//: The tag printed on a card, by sub-tab.
const TAG_PREFIX = {
  posts: 'POST', reels: 'REEL', reviews: 'REVIEW', story: 'STORY', stories: 'STORY',
  pages: 'PAGE', ads: 'AD', blogs: 'BLOG', scratch: 'LOGO', revamp: 'LOGO',
};

/**
 * How long ago a client last had a run.
 * Coarse on purpose: the tab exists so someone can find the client they were
 * working on, and "2 days ago" answers that better than a timestamp does.
 */
function agoOf(iso) {
  if (!iso) return '';
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return days + ' days ago';
  if (days < 14) return 'last week';
  if (days < 60) return Math.floor(days / 7) + ' weeks ago';
  return Math.floor(days / 30) + ' months ago';
}

const wordsIn = (text) => String(text || '').trim().split(/\s+/).filter(Boolean).length;

// Generated page bodies open with a top-level '# <SEO title>' line. The card
// header already names the page, so that line is dropped from the body copy on
// screen, in the editor and in every export.
const stripPageTitle = (text) => String(text || '').replace(/^\s*#(?!#)[^\n]*\n*/, '');

export default class ContentGeneration extends React.Component {
  /** Everything on screen comes from the hub API, handed down by the route. */
  get data() {
    return this.props.data || EMPTY_DATA;
  }
  constructor(props) {
    super(props);
    const sec = this.data.sections.find(s => s.id === (props.defaultSection || 'posts')) || this.data.sections[1];
    this.state = {
      clientId: 'cafgas',
      runId: 'r1',
      historyOpen: false,
      cardHistory: null,
      versions: {},
      cardView: {},
      generated: {},
      logo: { name: '', url: '', industry: '', direction: '', usp: '', notes: '' },
      pages: {},
      pageIndustries: ['Bathroom Installation', 'Boiler', 'Driveway and Patio', 'Electrical', 'Insulation', 'Property Maintenance', 'Roofing', 'Solar'],
      formOpen: null,      // section id whose generation form is open
      formValues: {},      // { [sectionId]: { [fieldKey]: value } }
      formSections: {},    // collapsed/expanded state for collapsible cards
      submitting: false,   // a run request is in flight
      formError: '',       // why the last request failed, shown in the form
      modalOpen: false,
      query: '',
      clientTab: 'recent',   // Recent | All in the client picker
      section: sec.id,
      sub: sec.subs[0].id,
      view: props.defaultView || 'content',
      approved: { 'posts:posts:0': true },
      aiEdit: null,   // open modal: { id, tag, title, draft, messages }
      aiInput: '',
      aiSending: false,
      emojiOpen: false,
      cardEditId: null,   // card whose inline editor is open
      cardDraft: null,    // { title, caption, hashtags } while editing
      edits: {},      // per-item content applied from the AI Edit modal
      blogsOpen: {},     // which blog sections are expanded
      blogBriefTab: {},  // per-blog tab in the Briefs & QC view
      blogExportOpen: false,
      blogExporting: false,
      blogExportError: '',
      pagesOpen: {},  // which website page groups are expanded
      pageEditId: null,
      pageDraft: '',
      pageEdits: {},  // per-page body copy saved from the inline editor
      exportOpen: false,
      copied: null    // id of the page whose Copy just succeeded
    };

    // Route-driven seed. Additive: with no `route` prop the component behaves
    // exactly as the design does, off defaultSection / defaultView.
    const r = props.route;
    if (r) {
      const routed = this.data.sections.find(s => s.id === r.section);
      if (routed) {
        this.state.section = routed.id;
        this.state.sub = routed.subs.some(x => x.id === r.sub) ? r.sub : routed.subs[0].id;
      }
      if (this.data.clients.some(c => c.id === r.clientId)) this.state.clientId = r.clientId;
      if (this.data.runs.some(x => x.id === r.runId)) this.state.runId = r.runId;
      if (r.view) this.state.view = r.view;
    }

    this.searchRef = React.createRef();
    this.aiScrollRef = React.createRef();
  }

  componentDidUpdate(prevProps, prevState) {
    // Follow the conversation, the way AngleChatView does.
    const before = prevState.aiEdit ? prevState.aiEdit.messages.length : 0;
    const now = this.state.aiEdit ? this.state.aiEdit.messages.length : 0;
    if (now !== before && this.aiScrollRef.current) {
      this.aiScrollRef.current.scrollTo({ top: this.aiScrollRef.current.scrollHeight });
    }

    // state -> URL: the user clicked a tab, a client, a run or a view.
    if (this.props.onRouteChange && ROUTE_KEYS.some(k => prevState[k] !== this.state[k])) {
      const next = {};
      ROUTE_KEYS.forEach(k => { next[k] = this.state[k]; });
      this.props.onRouteChange(next);
    }

    // URL -> state: back/forward, or a link into a different route. Guarded on
    // routeKey so a round-trip from our own push does not loop.
    if (this.props.routeKey && this.props.routeKey !== prevProps.routeKey) {
      const r = this.props.route || {};
      const patch = {};
      ROUTE_KEYS.forEach(k => {
        // `view` is not addressable for table/logo sections; leave it alone
        // there so it survives a trip through those tabs, as in the design.
        if (k === 'view' && !this.props.routeOwnsView) return;
        if (r[k] !== undefined && r[k] !== this.state[k]) patch[k] = r[k];
      });
      if (Object.keys(patch).length) this.setState(patch);
    }
  }

  componentDidMount() {
    this._keys = e => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); this.open(); }
      if (e.key === 'Escape') this.setState({ modalOpen: false, historyOpen: false, cardHistory: null, formOpen: null, aiEdit: null });
    };
    window.addEventListener('keydown', this._keys);
  }

  componentWillUnmount() { window.removeEventListener('keydown', this._keys); }

  open() {
    this.setState({ modalOpen: true, query: '' });
    setTimeout(() => { if (this.searchRef.current) this.searchRef.current.focus(); }, 30);
  }

  key() { return this.state.section + ':' + this.state.sub; }

  /**
   * Copy one page or all of them. The rendered HTML goes on the clipboard
   * alongside the markdown, so Docs and Word receive real headings while a code
   * editor still gets the source.
   */
  async copyPages(pages, token) {
    const html = pages
      .map(p => `<h2>${p.name}</h2>${(typeof document !== 'undefined' && document.getElementById(p.bodyId)?.innerHTML) || ''}`)
      .join('<hr />');
    const text = pages.map(p => `## ${p.name}\n\n${(p.content || '').trim()}`).join('\n\n---\n\n');
    const ok = await copyRich(html, text);
    if (!ok) return;
    this.setState({ copied: token });
    clearTimeout(this._copyTimer);
    this._copyTimer = setTimeout(
      () => this.setState(s => (s.copied === token ? { copied: null } : null)),
      1600
    );
  }

  setBriefTab(id, tab) {
    this.setState(s => ({ blogBriefTab: Object.assign({}, s.blogBriefTab, { [id]: tab }) }));
  }

  /** Copy one blog section or all of them, rich + plain. */
  async copyBlogs(sections, token) {
    const html = sections
      .map((s, i) => `<h2>${s.title}${s.subtitle ? ' — ' + s.subtitle : ''}</h2>` +
        ((typeof document !== 'undefined' && document.getElementById('blog-body-' + (s.index ?? i))?.innerHTML) || ''))
      .join('<hr />');
    const ok = await copyRich(html, toMarkdownBody(sections));
    if (!ok) return;
    this.setState({ copied: token });
    clearTimeout(this._copyTimer);
    this._copyTimer = setTimeout(
      () => this.setState(s => (s.copied === token ? { copied: null } : null)),
      1600
    );
  }

  /** Download a blog run in one of the five export formats. */
  async exportBlogs(kind, sections, blogs, meta) {
    this.setState({ blogExportOpen: false, blogExportError: '' });
    if (kind === 'pdf') {
      this.setState({ blogExporting: true });
      try {
        await exportPdf(sections, meta);
      } catch {
        this.setState({ blogExportError: "Couldn't build the PDF. Try Word or Markdown instead." });
      } finally {
        this.setState({ blogExporting: false });
      }
      return;
    }
    if (kind === 'doc') {
      const html = sections
        .map((s, i) => `<h2>${s.title}${s.subtitle ? ' — ' + s.subtitle : ''}</h2>` +
          (document.getElementById('blog-body-' + i)?.innerHTML || ''))
        .join('<hr />');
      downloadFile(blogToWord(meta, html), blogFilename(meta, 'doc'), 'application/msword');
    } else if (kind === 'md') {
      downloadFile(blogToMarkdown(sections, meta), blogFilename(meta, 'md'), 'text/markdown;charset=utf-8');
    } else if (kind === 'txt') {
      downloadFile(toPlainTextDocument(sections, meta), blogFilename(meta, 'txt'));
    } else {
      downloadFile(blogToJson(blogs, meta), blogFilename(meta, 'json'), 'application/json');
    }
  }

  /** Download the run in one of the four export formats. */
  exportPages(kind, pages, meta) {
    this.setState({ exportOpen: false });
    const bodyHtml = p => document.getElementById(p.bodyId)?.innerHTML ?? '';
    if (kind === 'doc') {
      downloadFile(toWordDocument(meta, pages, bodyHtml), exportFilename(meta, 'doc'), 'application/msword');
    } else if (kind === 'md') {
      downloadFile(toMarkdown(meta, pages), exportFilename(meta, 'md'), 'text/markdown;charset=utf-8');
    } else if (kind === 'txt') {
      downloadFile(toPlainText(meta, pages), exportFilename(meta, 'txt'));
    } else {
      downloadFile(toJson(meta, pages), exportFilename(meta, 'json'), 'application/json');
    }
  }

  /**
   * Send the composer's text. The user's turn appears immediately and the
   * assistant answers with a proposed version, which stays selectable in the
   * transcript rather than being applied straight away.
   */
  sendAi() {
    const text = this.state.aiInput.trim();
    if (!text || this.state.aiSending) return;

    this.setState(s => ({
      aiInput: '',
      aiSending: true,
      emojiOpen: false,
      aiEdit: Object.assign({}, s.aiEdit, {
        messages: s.aiEdit.messages.concat([{ role: 'user', content: text }]),
      }),
    }));

    this.setState(s => {
      if (!s.aiEdit) return null;
      const { draft, reply } = respond(s.aiEdit.current, text);
      return {
        aiSending: false,
        aiEdit: Object.assign({}, s.aiEdit, {
          current: draft,
          messages: s.aiEdit.messages.concat([{ role: 'assistant', content: reply, draft }]),
        }),
      };
    });
  }

  setCardDraft(key, value) {
    this.setState(s => ({ cardDraft: Object.assign({}, s.cardDraft, { [key]: value }) }));
  }

  /** Put an earlier proposal back in use. */
  useAiVersion(draft) {
    this.setState(s => (s.aiEdit ? { aiEdit: Object.assign({}, s.aiEdit, { current: draft }) } : null));
  }

  setLogo(k, v) {
    this.setState(s => ({ logo: Object.assign({}, s.logo, { [k]: v }) }));
  }

  setPages(k, v) {
    this.setState(s => ({ pages: Object.assign({}, s.pages, { [k]: v }) }));
  }

  /**
   * Current value for a form field.
   *
   * Anything typed wins. Otherwise the active client's onboarding record fills
   * it, so a form opens with what HQ already knows rather than an empty sheet.
   */
  formValue(sectionId, field) {
    const bag = this.state.formValues[sectionId] || {};
    if (bag[field.key] !== undefined) return bag[field.key];

    const prefilled = this.data.prefill[field.key];
    if (prefilled !== undefined) return prefilled;

    if (field.type === 'industries') return [];
    if (field.type === 'industry') return '';
    return '';
  }

  /**
   * Send the form to the backend, which queues the run and generates behind it.
   *
   * Every value the form collected goes into the run's `source` — the frozen
   * brief the agents read — plus the client's name, which the API stores as a
   * generated column.
   */
  async submitForm() {
    const sectionId = this.state.formOpen;
    if (!sectionId || this.state.submitting) return;

    const section = this.data.sections.find(x => x.id === sectionId);
    const client = this.data.client || this.data.clients.find(c => c.id === this.state.clientId);
    if (!section || !client) return;

    // Read every field through formValue so prefilled answers are sent too,
    // not just the ones that were typed over.
    const source = { client_name: client.name };
    for (const card of formSections(sectionId, this.state.sub)) {
      for (const field of card.fields) source[field.key] = this.formValue(sectionId, field);
    }

    this.setState({ submitting: true, formError: '' });
    const result = await this.props.onRequestRun({
      clientId: client.id,
      section: sectionId,
      values: source,
      period: section.monthly ? this.state.sub : undefined,
    });

    if (result && result.ok) {
      this.setState({ submitting: false, formOpen: null, formError: '' });
    } else {
      this.setState({ submitting: false, formError: (result && result.error) || 'Could not start the run.' });
    }
  }

  setFormValue(key, value) {
    this.setState(s => ({
      formValues: Object.assign({}, s.formValues, {
        [s.formOpen]: Object.assign({}, s.formValues[s.formOpen], { [key]: value }),
      }),
    }));
  }

  /** Overlay anything the AI Edit modal has applied to an item. */
  withEdits(list) {
    const edits = this.state.edits;
    return list.map(it => (edits[it.id] ? Object.assign({}, it, edits[it.id]) : it));
  }

  /**
   * The assets on screen, in position order.
   *
   * One shape for every section, because the API returns one shape: the run's
   * items, already scoped to this client, content type and period by the route.
   */
  itemsFor() {
    const section = this.data.sections.find(x => x.id === this.state.section);
    // Blog's sub-tabs are months, not sections — its assets all sit under
    // 'blogs' and the period was applied when they were fetched.
    const wanted = section && section.monthly ? 'blogs' : this.state.sub;
    const prefix = TAG_PREFIX[wanted] || 'ITEM';

    const rows = this.data.items.filter(it => it.section === wanted);
    return this.withEdits(rows.map((it, i) => {
      const n = String(i + 1).padStart(2, '0');
      return {
        id: it.id,
        assetId: it.assetId,
        index: n,
        tag: prefix + ' ' + n,
        title: it.title,
        caption: it.caption,
        hashtags: it.hashtags || [],
        slug: it.slug,
        status: it.status,
        activeVersion: it.activeVersion,
        filePath: it.filePath,
        isVideoAsset: it.kind === 'video',
        slots: [],
      };
    }));
  }

  renderVals() {
    const st = this.state;
    const showCounts = this.props.showCounts !== false;
    const client = this.data.clients.find(c => c.id === st.clientId) || this.data.clients[0];
    const section = this.data.sections.find(s => s.id === st.section) || this.data.sections[1];
    const subMeta = section.subs.find(x => x.id === st.sub) || section.subs[0];
    const run = this.data.runs.find(r => r.id === st.runId) || this.data.runs[0] || EMPTY_RUN;
    // Website content is version-scoped: the run selected in Run history
    // decides which snapshot of the six page groups the table shows.
    const baseVersion = 1;
    // Each page group plus the body copy behind it, so the panel can show the
    // page rather than only its row of numbers.
    // Website page groups are assets like any other; the body is the page.
    const pages = this.data.items
      .filter(it => it.section === 'pages')
      .map((it, i) => ({
        id: it.id,
        name: it.title || '(untitled page)',
        desc: '',
        status: it.status,
        words: wordsIn(stripPageTitle(it.caption)),
        passes: it.activeVersion,
        versions: it.activeVersion,
        time: it.updatedAt ? new Date(it.updatedAt).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '',
        slug: it.slug,
        bodyId: 'wc-body-' + i,
        content: st.pageEdits[it.id] !== undefined ? st.pageEdits[it.id] : stripPageTitle(it.caption),
      }));
    const allPagesOpen = pages.length > 0 && pages.every(p => st.pagesOpen[p.id]);
    // The open generation form, if any. Logo picks its field set from the
    // section's own scratch / revamp sub-tab.
    const formSpec = st.formOpen ? FORM_SPECS[st.formOpen] : null;
    const formCards = st.formOpen ? formSections(st.formOpen, st.sub) : [];
    const formValue = f => this.formValue(st.formOpen, f);
    // Why the Sitemap box is or is not filled, so an empty one is explained
    // rather than mysterious.
    const sitemapHint = (() => {
      const status = this.data.prefill._sitemap_status || 'none';
      if (status === 'agreed') {
        return { tone: 'ok', text: 'Filled from the agreed sitemap — ' + (this.data.prefill._sitemap_page_count || 0) + ' pages.' };
      }
      if (status === 'crawl_only') {
        return { tone: 'warn', text: 'No agreed sitemap on file — HQ only has pages crawled off their existing site. Paste the agreed list.' };
      }
      return { tone: 'warn', text: 'No sitemap on file for this client. Paste the agreed list.' };
    })();
    // Blog runs render through the reference repo's viewer: a Sections reading
    // list and a Briefs & QC list, instead of the social-style card grid.
    const blogs = section.monthly ? blogsFromAssets(items) : [];
    const blogSecs = section.monthly ? blogSections(blogs) : [];
    const blogView = st.view === 'briefs' ? 'briefs' : 'sections';
    const blogAllOpen = blogSecs.length > 0 && blogSecs.every((_, i) => st.blogsOpen[i]);
    const canSaveCard = !!st.cardDraft && !!st.cardDraft.title.trim() && !!st.cardDraft.caption.trim();
    const items = this.itemsFor(client);
    const approvedCount = items.filter(it => st.approved[it.id]).length;
    const pct = items.length ? Math.round((approvedCount / items.length) * 100) : 0;
    const labels = { posts: ['Post title', 'Post caption'], reviews: ['Review', 'Detail'], reels: ['Concept', 'Script'], story: ['Concept', 'Frames'], pages: ['Page title', 'Outline'], services: ['Service', 'Outline'], landing: ['Landing page', 'Structure'], feed: ['Post', 'Caption'], carousel: ['Concept', 'Slides'], shorts: ['Concept', 'Script'], ads: ['Ad name', 'Ad copy'] };
    const lbl = section.monthly ? ['Blog title', 'Blog content'] : (labels[st.sub] || ['Title', 'Body']);
    const unitSingular = section.monthly ? 'blog' : subMeta.label.replace(/s$/, '').toLowerCase();
    const viewSet = section.monthly
      ? ['sections', 'briefs']
      : (VIEW_SETS[st.section + ':' + st.sub] || ['content', 'images', 'preview']);
    const view = viewSet.indexOf(st.view) === -1 ? viewSet[0] : st.view;
    const mediaView = viewSet.indexOf('videos') !== -1 ? 'videos' : 'images';
    const allowPreview = viewSet.indexOf('preview') !== -1;
    const contacts = [
      { kind: 'WEB', value: client.site },
      { kind: 'PHONE', value: client.tel },
      { kind: 'EMAIL', value: client.email }
    ];

    const secBtn = a => 'display: flex; align-items: center; justify-content: center; gap: 8px; flex: 1 1 132px; padding: 11px 14px; border-radius: 11px; font-family: inherit; font-size: 13.5px; font-weight: 700; cursor: pointer; white-space: nowrap; transition: all .16s ease; border: 1px solid ' + (a ? '#f2b98e' : '#e6e4de') + '; background: ' + (a ? 'linear-gradient(180deg, #fff8f3, #fff2e8)' : '#fff') + '; color: ' + (a ? '#a8410a' : '#5b5750') + '; box-shadow: ' + (a ? '0 2px 8px rgba(217,84,26,.14)' : '0 1px 2px rgba(20,18,16,.04)') + ';';
    const secBadge = a => 'font-family: \'IBM Plex Mono\', monospace; font-size: 10.5px; padding: 2px 6px; border-radius: 6px; display: ' + (showCounts ? 'inline' : 'none') + '; background: ' + (a ? '#fadcc4' : '#f1eee9') + '; color: ' + (a ? '#a8410a' : '#8a857f') + ';';

    const subBtn = a => 'display: flex; align-items: center; gap: 8px; padding: 10px 15px; border-radius: 11px; font-family: inherit; font-size: 13px; font-weight: 700; cursor: pointer; white-space: nowrap; transition: all .16s ease; border: 1px solid ' + (a ? '#f2b98e' : '#e6e4de') + '; background: ' + (a ? 'linear-gradient(180deg, #fff8f3, #fff2e8)' : '#fff') + '; color: ' + (a ? '#a8410a' : '#5b5750') + '; box-shadow: ' + (a ? '0 2px 8px rgba(217,84,26,.12)' : 'none') + ';';
    const subBadge = a => 'font-family: \'IBM Plex Mono\', monospace; font-size: 10.5px; padding: 2px 6px; border-radius: 6px; display: ' + (showCounts ? 'inline' : 'none') + '; background: ' + (a ? '#fadcc4' : '#f2efea') + '; color: ' + (a ? '#a8410a' : '#8a857f') + ';';

    const viewBtn = a => 'display: flex; align-items: center; gap: 7px; padding: 8px 15px; border: none; border-radius: 9px; font-family: inherit; font-size: 12.5px; font-weight: 700; cursor: pointer; transition: all .16s ease; background: ' + (a ? '#fff' : 'transparent') + '; color: ' + (a ? '#0f2f2b' : '#847f78') + '; box-shadow: ' + (a ? '0 1px 3px rgba(20,18,16,.14)' : 'none') + ';';
    const viewDot = a => 'width: 6px; height: 6px; border-radius: 999px; background: ' + (a ? ACCENT : '#c8c3bb') + ';';
    const iconBtn = a => 'display: flex; align-items: center; justify-content: center; width: 38px; height: 38px; border-radius: 10px; cursor: pointer; transition: all .16s ease; border: 1px solid ' + (a ? '#f2b98e' : '#e3e1dc') + '; background: ' + (a ? '#fff4ec' : '#fff') + '; color: ' + (a ? '#cf5c17' : '#6c6862') + ';';

    const initials = n => n.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
    const q = st.query.trim().toLowerCase();
    const filtered = this.data.clients.filter(c => !q || c.name.toLowerCase().includes(q) || c.meta.toLowerCase().includes(q));
    const clientSearching = !!q;
    // Recent is clients that have actually had a run, newest first. String
    // compare is safe and cheap: these are ISO 8601 in UTC, so lexical order is
    // chronological order.
    const recentClients = this.data.clients.filter(c => c.lastRunAt)
      .sort((a, b) => (a.lastRunAt < b.lastRunAt ? 1 : -1));
    // A search overrides the tabs: typing a name is an unambiguous request for
    // that client, so it looks across both lists.
    const clientRows = clientSearching
      ? filtered
      : (st.clientTab === 'recent' ? recentClients : this.data.clients);

    return {
      clientName: client.name,
      clientInitials: initials(client.name),
      generateLabel: { website: 'Generate Pages', posts: 'Generate Social Content', blog: 'Generate Blogs', logo: 'Generate Logo', meta: 'Generate Ads' }[section.id] || 'Generate',
      // Every section has a generation form now, not just Logo and Website.
      onGenerate: () => this.setState({ formOpen: section.id, logoPicker: false }),
      // --- Generation form (spec-driven, one per section) ------------------
      formOpen: !!st.formOpen,
      formSubmit: formSpec ? formSpec.submit : 'Generate',
      formMeta: formSpec ? formSpec.meta : '',
      formFootnote: formSpec ? formSpec.footnote : '',
      closeForm: () => this.setState({ formOpen: null, logoPicker: false, formError: '' }),
      submitForm: () => this.submitForm(),
      submitting: !!st.submitting,
      formError: st.formError || '',
      formSubmitStyle: 'flex: 2 1 auto; display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px 18px; background: linear-gradient(140deg, #ef7326, #d9541a); color: #fff; border: none; border-radius: 12px; font-family: inherit; font-size: 13.5px; font-weight: 700; cursor: ' + (st.submitting ? 'default' : 'pointer') + '; opacity: ' + (st.submitting ? '.6' : '1') + '; box-shadow: 0 6px 18px rgba(217,84,26,.24);',
      cancelForm: () => this.setState(s => ({
        formOpen: null,
        logoPicker: false,
        formValues: Object.assign({}, s.formValues, { [s.formOpen]: undefined }),
      })),
      // The logo form's approach toggle drives which mode's fields are shown,
      // and is the section's own scratch / revamp sub-tab.
      formHasModes: !!(formSpec && formSpec.modes),
      formModes: (formSpec && formSpec.modes ? section.subs : []).map(t => ({
        label: t.label,
        style: 'padding: 8px 14px; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 700; cursor: pointer; border: 1px solid ' + (t.id === st.sub ? '#f2b98e' : '#e3e1dc') + '; background: ' + (t.id === st.sub ? '#fff4ec' : '#fff') + '; color: ' + (t.id === st.sub ? '#a8410a' : '#5b5750') + ';',
        select: () => this.setState({ sub: t.id }),
      })),
      formCards: formCards.map(sec => {
        const collapsed = sec.collapsible && !st.formSections[sec.heading];
        return {
          heading: sec.heading,
          subtext: sec.subtext,
          note: sec.note || '',
          optional: !!sec.optional,
          requiredMark: !!sec.requiredMark,
          collapsible: !!sec.collapsible,
          open: !collapsed,
          toggle: () => this.setState(s => ({
            formSections: Object.assign({}, s.formSections, { [sec.heading]: !s.formSections[sec.heading] }),
          })),
          caretStyle: 'flex: none; color: #a3a09a; font-size: 13px; transition: transform .16s ease; transform: rotate(' + (collapsed ? '0deg' : '180deg') + ');',
          iconWrapStyle: 'width: 38px; height: 38px; border-radius: 11px; display: flex; align-items: center; justify-content: center; flex: none; background: ' + ICON_TONE[sec.icon || 'doc'].bg + '; border: 1px solid ' + ICON_TONE[sec.icon || 'doc'].bd + ';',
          iconStroke: ICON_TONE[sec.icon || 'doc'].fg,
          isBusiness: (sec.icon || 'doc') === 'business',
          isDoc: (sec.icon || 'doc') === 'doc',
          isVideo: (sec.icon || 'doc') === 'video',
          isImage: (sec.icon || 'doc') === 'image',
          gridStyle: 'display: grid; grid-template-columns: repeat(auto-fit, minmax(' + (sec.min || 240) + 'px, 1fr)); gap: 14px;',
          bodyStyle: collapsed ? 'display: none;' : 'display: flex; flex-direction: column; gap: 16px;',
          fields: sec.fields.map(f => {
            const value = formValue(f);
            const base = 'padding: 11px 13px; border: 1px solid #e3e1dc; border-radius: 11px; font-family: ' + (f.mono ? "'IBM Plex Mono', monospace" : 'inherit') + '; font-size: ' + (f.mono ? '12.5px' : '13.5px') + '; line-height: 1.55; color: #16181c; background: #fff; outline: none; width: 100%;';
            return {
              key: f.key,
              label: f.label,
              hideLabel: !!f.hideLabel,
              required: !!f.required,
              hint: f.key === 'sitemap_text' ? sitemapHint.text : (f.hint || ''),
              hintTone: f.key === 'sitemap_text' ? sitemapHint.tone : '',
              placeholder: f.placeholder || '',
              rows: f.rows || 3,
              accept: f.accept || '',
              min: f.min,
              max: f.max,
              inputType: f.type === 'number' ? 'number' : f.type === 'email' ? 'email' : f.type === 'url' ? 'url' : 'text',
              isInput: ['text', 'email', 'url', 'number'].includes(f.type),
              isTextarea: f.type === 'textarea',
              isIndustries: f.type === 'industries',
              isIndustry: f.type === 'industry',
              isFile: f.type === 'file',
              wrapStyle: 'display: flex; flex-direction: column; gap: 6px;' + (f.full ? ' grid-column: 1 / -1;' : ''),
              inputStyle: base,
              textareaStyle: base + ' resize: vertical;',
              value: typeof value === 'string' ? value : '',
              onChange: e => this.setFormValue(f.key, e.target.value),
              fileName: typeof value === 'string' && value ? value : '',
              pickFile: () => this.setFormValue(f.key, value ? '' : 'logo-' + slugify(client.name) + '.png'),
              countLabel: (Array.isArray(value) ? value.length : 0) + ' selected',
              chips: this.data.industries.map(name => {
                const on = f.type === 'industry'
                  ? value === name
                  : Array.isArray(value) && value.indexOf(name) !== -1;
                return {
                  label: name,
                  style: 'display: flex; align-items: center; gap: 6px; padding: 9px 10px; border-radius: 10px; cursor: pointer; font-family: inherit; font-size: 12px; font-weight: 600; transition: all .14s ease; border: 1px solid ' + (on ? '#f2b98e' : '#e6e4de') + '; background: ' + (on ? '#fff4ec' : '#fff') + '; color: ' + (on ? '#a8410a' : '#5b5750') + ';',
                  checkStyle: 'flex: none; width: 18px; height: 18px; border-radius: 999px; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; background: ' + (on ? ACCENT : 'transparent') + '; color: ' + (on ? '#fff' : 'transparent') + ';',
                  toggle: () => {
                    if (f.type === 'industry') this.setFormValue(f.key, on ? '' : name);
                    else {
                      const cur = Array.isArray(value) ? value : [];
                      this.setFormValue(f.key, cur.indexOf(name) === -1 ? cur.concat([name]) : cur.filter(x => x !== name));
                    }
                  },
                };
              }),
            };
          }),
        };
      }),
      unitPlural: section.unit,
      panelMeta: section.logo
        ? 'Logo studio · 4 concepts · last run ' + run.date
        : section.monthly
        ? 'Saved ' + run.date + ' (' + run.version + ') · Blog · ' + subMeta.label + ' · 12 blogs'
        : 'Saved ' + run.date + ' (' + run.version + ') · ' + section.label + ' · ' + subMeta.label + ' (' + subMeta.count + ')',
      approvedLabel: approvedCount + ' of ' + items.length + ' approved',
      progressStyle: 'height: 100%; width: ' + pct + '%; border-radius: 999px; background: linear-gradient(90deg, #2f9c66, #1f6b46); transition: width .3s ease;',

      sectionValue: st.section,
      onSectionChange: e => {
        const sec = this.data.sections.find(x => x.id === e.target.value);
        if (sec) this.setState({ section: sec.id, sub: sec.subs.length ? sec.subs[0].id : null, mobMenuOpen: false });
      },
      sections: this.data.sections.map((s, i) => ({
        id: s.id, optLabel: s.label + ' (' + s.count + ')',
        label: s.label, count: s.count,
        wide: (this.data.sections.length % 2 === 1 && i === 0) ? '1' : null,
        style: secBtn(s.id === st.section), badgeStyle: secBadge(s.id === st.section),
        select: () => this.setState({ section: s.id, sub: s.subs[0].id, cardView: {} })
      })),
      subTabs: section.subs.map(t => ({
        label: t.label, count: t.count,
        style: subBtn(t.id === st.sub),
        badgeStyle: (section.monthly || section.logo) ? 'display: none;' : subBadge(t.id === st.sub),
        select: () => this.setState({ sub: t.id, cardView: {} })
      })),
      views: viewSet.map(v => ({
        label: BLOG_VIEW_LABELS[v] || VIEW_LABELS[v], style: viewBtn(v === view), dotStyle: viewDot(v === view),
        select: () => this.setState({ view: v, cardView: {} })
      })),
      isMonthly: !!section.monthly,
      notMonthly: !section.monthly && !section.single && !section.logo,
      monthLabel: subMeta.label,
      monthsOpen: !!st.monthsOpen,
      toggleMonths: () => this.setState(s => ({ monthsOpen: !s.monthsOpen })),
      closeMonths: e => { e.stopPropagation(); this.setState({ monthsOpen: false }); },
      monthBtnStyle: 'display: flex; align-items: center; gap: 10px; padding: 8px 14px 8px 12px; border-radius: 12px; cursor: pointer; font-family: inherit; transition: all .16s ease; border: 1px solid ' + (st.monthsOpen ? '#f2b98e' : '#e3e1dc') + '; background: ' + (st.monthsOpen ? '#fff8f3' : '#fff') + '; box-shadow: 0 1px 2px rgba(20,18,16,.05);',
      monthCaretStyle: 'color: #a3a09a; font-size: 11px; transition: transform .16s ease; transform: rotate(' + (st.monthsOpen ? '180deg' : '0deg') + ');',
      monthOptions: section.subs.map(t => {
        const sel = t.id === st.sub;
        return {
          id: t.id, label: t.label,
          style: 'display: flex; align-items: center; gap: 10px; padding: 9px 11px; border: none; border-radius: 10px; cursor: pointer; font-family: inherit; font-size: 13px; font-weight: ' + (sel ? '700' : '500') + '; color: ' + (sel ? '#a8410a' : '#4b4741') + '; background: ' + (sel ? '#fff4ec' : 'transparent') + ';',
          checkStyle: 'font-size: 11px; font-weight: 700; color: ' + (sel ? '#cf5c17' : 'transparent') + ';',
          select: () => this.setState({ sub: t.id, monthsOpen: false, cardView: {} })
        };
      }),
      isLogo: !!section.logo,
      isTable: !!section.table,
      tableCount: pages.length + ' of ' + pages.length + ' pages',
      pagesAllOpen: allPagesOpen,
      toggleAllPages: () => this.setState(s => ({
        pagesOpen: allPagesOpen ? {} : pages.reduce((acc, p) => { acc[p.id] = true; return acc; }, {}),
      })),
      copyAllPages: () => this.copyPages(pages, 'all'),
      copiedAll: st.copied === 'all',
      exportOpen: !!st.exportOpen,
      toggleExport: () => this.setState(s => ({ exportOpen: !s.exportOpen })),
      closeExport: () => this.setState({ exportOpen: false }),
      exportOptions: EXPORT_OPTIONS.map(o => Object.assign({}, o, {
        run: () => this.exportPages(o.key, pages, {
          client: client.name, date: run.date, version: run.version, runId: run.id,
        }),
      })),
      pageCards: pages.map((p, i) => {
        const editing = st.pageEditId === p.id;
        // Editing forces the group open: the inline editor lives inside the
        // collapsible body, so an edit on a collapsed card would be invisible.
        const open = !!st.pagesOpen[p.id] || editing;
        const tone = p.status === 'approved'
          ? { bg: '#eef8f2', bd: '#c9e6d6', fg: '#1f6b46', dot: '#2f9c66', label: 'Approved' }
          : p.status === 'generating'
          ? { bg: '#eef4fd', bd: '#d3e2f7', fg: '#2f6ab5', dot: '#3b7fbf', label: 'Generating' }
          : { bg: '#fff4ec', bd: '#fadfc9', fg: '#a8410a', dot: '#e07422', label: 'Needs review' };
        const vs = st.versions[p.id] || { cur: p.versions, act: p.versions };
        return {
          name: p.name, desc: p.desc, words: formatNumber(p.words), content: p.content,
          bodyId: p.bodyId,
          routeId: itemId(i), routeSlug: slugify(p.name),
          meta: p.passes + ' passes · v' + vs.cur + ' · ' + run.date + ' ' + p.time,
          statusStyle: 'display: inline-flex; align-items: center; gap: 7px; padding: 5px 11px; border-radius: 999px; font-size: 11.5px; font-weight: 700; flex: none; background: ' + tone.bg + '; border: 1px solid ' + tone.bd + '; color: ' + tone.fg + ';',
          statusDotStyle: 'width: 6px; height: 6px; border-radius: 999px; background: ' + tone.dot + ';',
          statusLabel: tone.label,
          open,
          editing,
          toggle: () => this.setState(s => ({
            pagesOpen: Object.assign({}, s.pagesOpen, { [p.id]: !s.pagesOpen[p.id] }),
            // Collapsing the card from the header drops the open editor with it.
            pageEditId: s.pageEditId === p.id && s.pagesOpen[p.id] ? null : s.pageEditId,
            pageDraft: s.pageEditId === p.id && s.pagesOpen[p.id] ? '' : s.pageDraft,
          })),
          chevronStyle: 'flex: none; color: #a3a09a; transition: transform .16s ease; transform: rotate(' + (open ? '0deg' : '-90deg') + ');',
          // The body stays mounted when collapsed, just hidden: the Word export
          // reads the rendered innerHTML, and it cannot read a body that was
          // never rendered.
          bodyStyle: open ? 'border-top: 1px solid #f1eee9; padding: 18px clamp(16px, 2.4vw, 22px) 22px;' : 'display: none;',
          copied: st.copied === p.id,
          copy: () => this.copyPages([p], p.id),
          // Pressed state, so the toggle reads as on rather than inert.
          editStyle: 'display: flex; align-items: center; gap: 6px; padding: 8px 12px; border-radius: 9px; font-family: inherit; font-size: 12px; font-weight: 600; cursor: pointer; background: ' + (editing ? '#fff4ec' : '#fff') + '; border: 1px solid ' + (editing ? '#f2b98e' : '#e3e1dc') + '; color: ' + (editing ? '#a8410a' : '#4b4741') + ';',
          // Edit is a toggle: a second click leaves the editor and collapses
          // the card back down, the same as clicking the header chevron.
          startEdit: () => this.setState(s => (s.pageEditId === p.id
            ? {
              pageEditId: null,
              pageDraft: '',
              pagesOpen: Object.assign({}, s.pagesOpen, { [p.id]: false }),
            }
            : {
              pageEditId: p.id,
              pageDraft: p.content,
              pagesOpen: Object.assign({}, s.pagesOpen, { [p.id]: true }),
            })),
          cancelEdit: () => this.setState({ pageEditId: null, pageDraft: '' }),
          saveEdit: () => this.setState(s => ({
            pageEdits: Object.assign({}, s.pageEdits, { [p.id]: s.pageDraft }),
            pageEditId: null,
            pageDraft: '',
          })),
        };
      }),
      cardDraftTitle: st.cardDraft ? st.cardDraft.title : '',
      cardDraftCaption: st.cardDraft ? st.cardDraft.caption : '',
      cardDraftHashtags: st.cardDraft ? st.cardDraft.hashtags : '',
      onCardTitle: e => this.setCardDraft('title', e.target.value),
      onCardCaption: e => this.setCardDraft('caption', e.target.value),
      onCardHashtags: e => this.setCardDraft('hashtags', e.target.value),
      pageDraft: st.pageDraft,
      onPageDraft: e => this.setState({ pageDraft: e.target.value }),
      cardsWrapStyle: 'padding: clamp(14px, 2vw, 20px) clamp(14px, 2.4vw, 26px) 30px; display: ' + (section.logo || section.table || section.monthly ? 'none' : 'block') + ';',
      notLogo: !section.logo,
      showViews: !section.logo && !section.table,
      logoPickerOpen: !!st.logoPicker,
      toggleLogoPicker: () => this.setState(s => ({ logoPicker: !s.logoPicker, query: '' })),
      closePicker: e => { e.stopPropagation(); this.setState({ logoPicker: false, query: '' }); },
      logoClientBtnStyle: 'display: flex; align-items: center; gap: 14px; width: 100%; padding: clamp(14px, 2.4vw, 18px) clamp(14px, 2.4vw, 22px); border: none; cursor: pointer; font-family: inherit; transition: background .16s ease; background: ' + (st.logoPicker ? '#faf9f6' : 'linear-gradient(180deg, #fcfbf9, #ffffff)') + ';',
      newClient: () => this.setState({ logoPicker: false }),
      logoClients: filtered.map(c => {
        const sel = c.id === st.clientId;
        return {
          name: c.name, meta: c.meta, initials: initials(c.name),
          style: 'display: flex; align-items: center; gap: 10px; padding: 9px 11px; border-radius: 12px; cursor: pointer; font-family: inherit; transition: border-color .16s ease; border: 1px solid ' + (sel ? '#f2b98e' : '#e6e4de') + '; background: ' + (sel ? '#fff4ec' : '#fff') + ';',
          avatarStyle: 'width: 30px; height: 30px; border-radius: 9px; flex: none; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; background: ' + (sel ? 'linear-gradient(140deg, #0f3a34, #185349)' : '#f4f2ee') + '; color: ' + (sel ? '#eafdf6' : '#6c6862') + ';',
          checkStyle: 'flex: none; width: 20px; height: 20px; border-radius: 999px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; background: ' + (sel ? ACCENT : 'transparent') + '; color: ' + (sel ? '#fff' : 'transparent') + ';',
          select: () => this.setState(s => ({ clientId: c.id, logoPicker: false, query: '', formValues: Object.assign({}, s.formValues, { [s.formOpen]: undefined }) }))
        };
      }),
      logoCards: ['A', 'B', 'C', 'D'].map((letter, i) => {
        const id = 'logo:concept:' + letter;
        const vs = st.versions[id] || { cur: baseVersion, act: baseVersion };
        return {
          tag: 'LOGO 0' + (i + 1),
          label: 'logo concept ' + letter,
          version: 'v' + vs.act,
          routeId: itemId(i), routeSlug: slugify('logo concept ' + letter),
          canvasStyle: 'aspect-ratio: 1/1; background: ' + stripe(24 + i * 52) + '; display: flex; align-items: center; justify-content: center;',
          openVersions: () => this.setState({ cardHistory: { id: id, kind: 'image', tag: 'LOGO 0' + (i + 1), title: 'Logo concept ' + letter + ' — ' + client.name, slot: 'logo concept ' + letter, snippet: ['logo concept ' + letter] } })
        };
      }),
      isContent: view === 'content',
      showApprove: view === 'content' && !section.logo && !section.table && !section.monthly,
      isImages: view === 'images' || view === 'videos',
      isPreview: view === 'preview',

      cards: items.map((it, i) => {
        const ok = !!st.approved[it.id];
        const cv = st.cardView[it.id];
        const mode = (cv && viewSet.indexOf(cv) !== -1) ? cv : view;
        const isC = mode === 'content';
        const hasImage = (i % 3 !== 1) || !!st.generated[it.id];
        const vs = st.versions[it.id] || { cur: baseVersion, act: baseVersion };
        const drifted = vs.act !== vs.cur;
        const short = it.caption.split('\n\n').slice(0, 2).join('\n\n');
        return {
          index: it.index, tag: it.tag, title: it.title, caption: it.caption,
          titleLabel: lbl[0], captionLabel: lbl[1], unitSingular,
          routeId: itemId(i), routeSlug: slugify(it.title),
          siteUrl: 'http://' + client.site + '/', tel: client.tel, email: client.email,
          hashtags: it.hashtags.map(h => ({ text: h })),
          hashLine: it.hashtags.slice(0, 6).join('  '),
          previewCaption: short,
          showContent: isC,
          showImage: mode === 'images' || mode === 'videos',
          showPreview: mode === 'preview',
          hasImage,
          noImage: !hasImage,
          imageLabel: mediaView === 'videos' ? 'video · ' + it.slots[0] : it.slots[0],
          ratioLabel: mediaView === 'videos' ? '9:16 · 1080×1920' : '4:5 · 1080×1350',
          isVideo: mediaView === 'videos',
          isImageMedia: mediaView !== 'videos',
          mediaTitle: mediaView === 'videos' ? 'Video' : 'Image',
          noMediaLabel: mediaView === 'videos' ? 'NO VIDEO YET' : 'NO IMAGE YET',
          textOnlyLabel: 'Text only — no ' + (mediaView === 'videos' ? 'video' : 'image') + ' generated yet.',
          generateMediaLabel: mediaView === 'videos' ? '✦ Generate video' : '✦ Generate image',
          duration: '0:' + String(18 + i * 4).padStart(2, '0'),
          durationStyle: mediaView === 'videos' ? 'color: #4b4741; font-weight: 600;' : 'display: none;',
          versionLabel: 'v' + vs.act,
          versionStyle: 'font-family: \'IBM Plex Mono\', monospace; font-size: 10px; font-weight: 500; padding: 2px 7px; border-radius: 6px; background: ' + (drifted ? '#fdeadd' : '#f4f2ee') + '; color: ' + (drifted ? '#a8410a' : '#8a857f') + ';',
          cardStyle: 'position: relative; display: flex; flex-direction: column; height: 100%; border-radius: 20px; overflow: hidden; background: #fff; border: 1px solid ' + (ok && isC ? '#c9e5d6' : '#e6e4de') + '; box-shadow: 0 2px 6px rgba(20,18,16,.04); transition: box-shadow .2s ease; animation: dcFade .3s ease both;',
          railStyle: 'position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: ' + (ok && isC ? 'linear-gradient(180deg, #2f9c66, #1f6b46)' : 'linear-gradient(180deg, #f2b98e, #e2ded7)') + ';',
          indexStyle: 'width: 34px; height: 34px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-family: \'IBM Plex Mono\', monospace; font-size: 13px; font-weight: 500; flex: none; background: ' + (ok && isC ? '#eaf5ef' : '#f4f2ee') + '; color: ' + (ok && isC ? '#1f6b46' : '#7a756e') + ';',
          statusLabel: ok ? 'Approved' : 'Needs review',
          statusStyle: 'font-size: 11px; font-weight: 700; letter-spacing: .01em; padding: 3px 9px; border-radius: 999px; width: fit-content; display: ' + (isC ? 'block' : 'none') + '; background: ' + (ok ? '#eaf5ef' : '#f4f2ee') + '; color: ' + (ok ? '#1f6b46' : '#8a857f') + ';',
          approveStyle: 'width: 30px; height: 30px; border-radius: 9px; cursor: pointer; font-size: 13px; font-weight: 700; transition: all .16s ease; display: ' + (isC ? 'block' : 'none') + '; border: 1px solid ' + (ok ? '#1f6b46' : '#e3e1dc') + '; background: ' + (ok ? 'linear-gradient(180deg, #2f9c66, #1f6b46)' : '#fff') + '; color: ' + (ok ? '#fff' : '#b8b3ab') + ';',
          downloadStyle: 'display: ' + (isC ? 'none' : 'flex') + '; align-items: center; justify-content: center; width: 30px; height: 30px; background: #fff; border: 1px solid #e3e1dc; border-radius: 9px; color: #6c6862; cursor: pointer;',
          // Inline edit, as PostItemCard does it: every field is a textarea,
          // including the title and the hashtags, because a single-line input
          // clipped long values out of sight.
          editing: st.cardEditId === it.id,
          startEdit: () => this.setState({
            cardEditId: it.id,
            cardDraft: { title: it.title, caption: it.caption, hashtags: it.hashtags.join(' ') },
          }),
          cancelEdit: () => this.setState({ cardEditId: null, cardDraft: null }),
          saveEdit: () => this.setState(s => {
            const d = s.cardDraft;
            if (!d) return null;
            return {
              edits: Object.assign({}, s.edits, {
                [it.id]: {
                  title: d.title.trim(),
                  caption: d.caption,
                  hashtags: d.hashtags.split(/\s+/).map(h => h.trim()).filter(Boolean)
                    .map(h => (h.startsWith('#') ? h : '#' + h)),
                },
              }),
              cardEditId: null,
              cardDraft: null,
            };
          }),
          saveStyle: 'padding: 7px 13px; border: none; border-radius: 9px; font-family: inherit; font-size: 12px; font-weight: 700; color: #fff; background: linear-gradient(140deg, #ef7326, #d9541a); box-shadow: 0 4px 12px rgba(217,84,26,.22); cursor: ' + (canSaveCard ? 'pointer' : 'default') + '; opacity: ' + (canSaveCard ? '1' : '.5') + ';',
          openAiEdit: () => this.setState({
            aiEdit: {
              id: it.id,
              tag: it.tag,
              title: it.title,
              original: { title: it.title, caption: it.caption, hashtags: it.hashtags.slice() },
              current: { title: it.title, caption: it.caption, hashtags: it.hashtags.slice() },
              messages: [],
            },
            aiInput: '',
            aiSending: false,
            emojiOpen: false,
          }),
          toggle: () => this.setState(s => ({ approved: Object.assign({}, s.approved, { [it.id]: !s.approved[it.id] }) })),
          generate: () => this.setState(s => ({ generated: Object.assign({}, s.generated, { [it.id]: true }) })),
          viewContent: () => this.setState(s => ({ cardView: Object.assign({}, s.cardView, { [it.id]: 'content' }) })),
          viewImage: () => this.setState(s => ({ cardView: Object.assign({}, s.cardView, { [it.id]: mediaView }) })),
          viewPreview: () => this.setState(s => ({ cardView: Object.assign({}, s.cardView, { [it.id]: 'preview' }) })),
          contentBtnStyle: iconBtn(isC),
          imageBtnStyle: iconBtn(mode === 'images' || mode === 'videos'),
          previewBtnStyle: allowPreview ? iconBtn(mode === 'preview') : 'display: none;',
          actionsStyle: 'flex: 1; gap: 8px; display: ' + (mode === 'preview' ? 'none' : 'flex') + ';',
          historyBtnStyle: 'display: ' + (mode === 'preview' ? 'none' : 'flex') + '; align-items: center; justify-content: center; width: 38px; height: 38px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; color: #6c6862; cursor: pointer;',
          dividerStyle: 'width: 1px; height: 24px; background: #eae7e1; display: ' + (mode === 'preview' ? 'none' : 'block') + ';',
          iconGroupStyle: 'display: flex; align-items: center; gap: 6px; ' + (mode === 'preview' ? 'flex: 1; justify-content: flex-end;' : 'margin-left: auto;'),
          openVersions: () => this.setState({ cardHistory: { id: it.id, kind: mode === 'images' ? 'image' : 'content', tag: it.tag, title: it.title, slot: it.slots[0], snippet: it.caption.split('\n\n') } }),
          canvasStyle: 'flex: 1; aspect-ratio: 4/5; background: ' + stripe(20 + i * 44) + '; display: flex; flex-direction: column; align-items: center; justify-content: space-between; padding: 12px;',
          mosaicStyle: 'display: grid; grid-template-columns: 2.1fr 1fr; gap: 3px; background: #eeebe5;',
          heroStyle: 'aspect-ratio: 4/3; background: ' + stripe(28 + i * 46) + '; display: flex; align-items: flex-end; justify-content: flex-start; padding: 10px;',
          sideThumbs: it.slots.slice(1, 4).map((s, j) => ({ style: 'height: 100%; min-height: 40px; background: ' + stripe(18 + (i * 3 + j) * 37) + ';' })),
          thumbs: it.slots.map((s, j) => ({ style: 'flex: 1; height: 52px; border-radius: 9px; border: 1px solid #e8e5df; background: ' + stripe(18 + (i * 4 + j) * 33) + ';' }))
        };
      }),

      // Social Media carries AI Edit in the card header; the other card
      // sections keep it in the footer where the design put it.
      aiEditOnTop: AI_EDIT_ON_TOP.includes(section.id),
      showAiEdit: !AI_EDIT_HIDDEN.includes(section.id),

      // --- Blog viewer (Sections / Briefs & QC) ----------------------------
      isBlog: !!section.monthly,
      blogSummary: sectionSummary(blogSecs),
      blogIsSections: blogView === 'sections',
      blogIsBriefs: blogView === 'briefs',
      blogAllOpen: blogAllOpen,
      toggleAllBlogs: () => this.setState(() => ({
        blogsOpen: blogAllOpen ? {} : blogSecs.reduce((a, s, i) => { a[i] = true; return a; }, {}),
      })),
      copyAllBlogs: () => this.copyBlogs(blogSecs, 'blogs-all'),
      copiedAllBlogs: st.copied === 'blogs-all',
      blogExportOpen: !!st.blogExportOpen,
      toggleBlogExport: () => this.setState(s => ({ blogExportOpen: !s.blogExportOpen })),
      closeBlogExport: () => this.setState({ blogExportOpen: false }),
      blogExporting: !!st.blogExporting,
      blogExportError: st.blogExportError || '',
      blogExportOptions: BLOG_EXPORT_OPTIONS.map(o => Object.assign({}, o, {
        run: () => this.exportBlogs(o.key, blogSecs, blogs, {
          documentName: client.name, date: run.date, version: run.version, jobId: run.id,
        }),
      })),
      blogSections: blogSecs.map((s, i) => {
        const open = !!st.blogsOpen[i];
        return {
          title: s.title,
          subtitle: s.subtitle || '',
          badge: s.badge || '',
          words: formatNumber(s.words),
          body: s.body,
          bodyId: 'blog-body-' + i,
          routeId: itemId(i),
          routeSlug: slugify(s.subtitle || s.title),
          open,
          toggle: () => this.setState(x => ({ blogsOpen: Object.assign({}, x.blogsOpen, { [i]: !x.blogsOpen[i] }) })),
          chevronStyle: 'flex: none; color: #a3a09a; transition: transform .16s ease; transform: rotate(' + (open ? '0deg' : '-90deg') + ');',
          badgeStyle: 'flex: none; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 600; border: 1px solid #e3e1dc; background: #f4f2ee; color: #6c6862;',
          // Kept mounted when collapsed so the Word export can read the
          // rendered HTML back out of the DOM.
          bodyStyle: open ? 'border-top: 1px solid #f1eee9; padding: 16px clamp(14px, 2.4vw, 20px) 20px;' : 'display: none;',
          copied: st.copied === 'blog-' + i,
          copy: () => this.copyBlogs([s], 'blog-' + i),
        };
      }),
      blogBriefs: blogs.map((b, i) => {
        const tone = b.status === 'passed'
          ? { bg: '#eef8f2', bd: '#c9e6d6', fg: '#1f6b46', label: 'passed' }
          : b.status === 'failed_qc'
          ? { bg: '#fff4ec', bd: '#fadfc9', fg: '#a8410a', label: 'below threshold' }
          : { bg: '#fdecec', bd: '#f6cccc', fg: '#c04141', label: 'failed' };
        const tab = st.blogBriefTab[b.id] || 'blog';
        const tabStyle = a => 'padding: 7px 13px; border: none; border-radius: 9px; font-family: inherit; font-size: 12.5px; font-weight: 700; cursor: pointer; transition: all .16s ease; background: ' + (a ? '#fff4ec' : 'transparent') + '; color: ' + (a ? '#d95c15' : '#847f78') + ';';
        return {
          number: 'Blog ' + b.blog_number,
          title: b.title,
          statusLabel: tone.label,
          statusStyle: 'flex: none; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; background: ' + tone.bg + '; border: 1px solid ' + tone.bd + '; color: ' + tone.fg + ';',
          funnel: b.funnel_stage,
          areas: b.service_areas.join(', '),
          score: b.qc_score,
          rounds: b.revision_attempts > 1 ? b.revision_attempts + ' QC rounds' : '',
          words: formatNumber(b.word_count) + ' words',
          keywords: b.keywords.map(k => ({ text: k })),
          isBlogTab: tab === 'blog',
          isGmbTab: tab === 'gmb',
          isQcTab: tab === 'qc',
          tabs: [
            { key: 'blog', label: 'Blog', style: tabStyle(tab === 'blog'), select: () => this.setBriefTab(b.id, 'blog') },
            { key: 'gmb', label: 'GMB', style: tabStyle(tab === 'gmb'), select: () => this.setBriefTab(b.id, 'gmb') },
            { key: 'qc', label: 'QC', style: tabStyle(tab === 'qc'), select: () => this.setBriefTab(b.id, 'qc') },
          ],
          generalNotes: b.general_notes,
          metaTitle: b.meta_title,
          metaTitleChars: b.meta_title.length + ' chars',
          metaDescription: b.meta_description,
          metaDescriptionChars: b.meta_description.length + ' chars',
          content: b.content,
          gmbPost: b.gmb_post,
          gmbFaq: b.gmb_faq,
          gmbFaqWords: b.gmb_faq.split(/\s+/).length + '/70 words',
          scoreLabel: (b.qc_score == null ? '—' : b.qc_score) + '/10',
          qcAreas: QC_AREAS.map(area => {
            const v = b.qc_breakdown[area.key] ?? 0;
            const full = v >= area.max;
            return {
              label: area.label,
              value: v + '/' + area.max,
              style: 'display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 11px; border-radius: 10px; font-size: 12px; border: 1px solid ' + (full ? '#c9e6d6' : '#fadfc9') + '; background: ' + (full ? '#f3faf6' : '#fff8f3') + '; color: ' + (full ? '#1f6b46' : '#a8410a') + ';',
            };
          }),
          fixes: b.qc_fixes.map(f => ({ text: f })),
          hasFixes: b.qc_fixes.length > 0,
        };
      }),

      // --- AI Edit chat ----------------------------------------------------
      // Modelled on AngleChatView: every assistant turn carries a proposed
      // version with "Use this version", and the right pane shows whichever
      // version is currently in use.
      aiEditOpen: !!st.aiEdit,
      aiEditTag: st.aiEdit ? st.aiEdit.tag + ' · AI edit' : '',
      aiEditTitle: st.aiEdit ? st.aiEdit.title : '',
      closeAiEdit: () => this.setState({ aiEdit: null, aiInput: '', emojiOpen: false }),
      aiInput: st.aiInput,
      onAiInput: e => this.setState({ aiInput: e.target.value }),
      aiInputKey: e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendAi(); } },
      sendAi: () => this.sendAi(),
      aiSending: !!st.aiSending,
      aiNoMessages: !!st.aiEdit && st.aiEdit.messages.length === 0,
      aiScrollRef: this.aiScrollRef,
      aiSendStyle: 'display: flex; align-items: center; justify-content: center; gap: 7px; flex: none; padding: 11px 16px; border: none; border-radius: 11px; font-family: inherit; font-size: 13px; font-weight: 700; color: #fff; cursor: ' + (st.aiInput.trim() && !st.aiSending ? 'pointer' : 'default') + '; opacity: ' + (st.aiInput.trim() && !st.aiSending ? '1' : '.45') + '; background: linear-gradient(140deg, #ef7326, #d9541a); box-shadow: 0 6px 16px rgba(217,84,26,.22);',
      emojiOpen: !!st.emojiOpen,
      toggleEmoji: () => this.setState(s => ({ emojiOpen: !s.emojiOpen })),
      closeEmoji: () => this.setState({ emojiOpen: false }),
      emojis: EMOJIS.map((e, i) => ({
        char: e,
        pick: () => this.setState(s => ({ aiInput: s.aiInput + e, emojiOpen: false })),
      })),
      aiMessages: (st.aiEdit ? st.aiEdit.messages : []).map((m, i) => {
        const isUser = m.role === 'user';
        const cur = st.aiEdit.current;
        const inUse = !isUser && !!m.draft && m.draft.title === cur.title && m.draft.caption === cur.caption;
        return {
          text: m.content,
          isUser,
          headline: !isUser && m.draft ? m.draft.title : '',
          hasDraft: !isUser && !!m.draft,
          body: !isUser && m.draft ? m.draft.caption : m.content,
          rowStyle: 'flex: none; display: flex; flex-direction: column; gap: 6px; align-items: ' + (isUser ? 'flex-end' : 'flex-start') + '; animation: dcFade .24s ease both;',
          bubbleStyle: 'max-width: 85%; padding: 10px 13px; border-radius: 16px; font-size: 12.5px; line-height: 1.55; text-wrap: pretty; box-shadow: 0 1px 2px rgba(20,18,16,.06); ' + (isUser
            ? 'background: linear-gradient(140deg, #ef7326, #d9541a); color: #fff; border: none;'
            : 'background: #f4f2ee; color: #16181c; border: 1px solid #eae7e1;'),
          headlineStyle: 'margin: 0 0 5px; font-size: 13px; font-weight: 800; color: #0f2f2b;',
          inUse,
          useStyle: 'display: inline-flex; align-items: center; gap: 6px; padding: 3px 11px; border-radius: 999px; font-family: inherit; font-size: 11.5px; font-weight: 600; cursor: ' + (inUse ? 'default' : 'pointer') + '; border: 1px solid ' + (inUse ? '#d8ecdf' : '#c9e5d6') + '; background: ' + (inUse ? '#f6fbf8' : '#eef8f2') + '; color: ' + (inUse ? '#7bb497' : '#1f6b46') + ';',
          useLabel: inUse ? 'Currently in use' : 'Use this version',
          use: () => { if (!inUse) this.useAiVersion(m.draft); },
        };
      }),
      aiDraftTitle: st.aiEdit ? st.aiEdit.current.title : '',
      aiDraftCaption: st.aiEdit ? st.aiEdit.current.caption : '',
      aiDraftHashtags: (st.aiEdit ? st.aiEdit.current.hashtags : []).map(h => ({ text: h })),
      aiSiteUrl: 'http://' + client.site + '/',
      aiTel: client.tel,
      aiEmail: client.email,
      aiTitleLabel: lbl[0],
      aiCaptionLabel: lbl[1],
      aiDirty: !!st.aiEdit && (st.aiEdit.current.title !== st.aiEdit.original.title
        || st.aiEdit.current.caption !== st.aiEdit.original.caption
        || st.aiEdit.current.hashtags.join('|') !== st.aiEdit.original.hashtags.join('|')),
      aiApplyStyle: 'flex: 1 1 auto; display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px 18px; border: none; border-radius: 12px; font-family: inherit; font-size: 13.5px; font-weight: 700; color: #fff; background: linear-gradient(140deg, #ef7326, #d9541a); box-shadow: 0 6px 18px rgba(217,84,26,.24); cursor: pointer;',
      applyAiEdit: () => this.setState(s => {
        if (!s.aiEdit) return null;
        const d = s.aiEdit.current;
        return {
          edits: Object.assign({}, s.edits, {
            [s.aiEdit.id]: { title: d.title, caption: d.caption, hashtags: d.hashtags },
          }),
          aiEdit: null,
          aiInput: '',
          emojiOpen: false,
        };
      }),

      approveAll: () => this.setState(s => {
        const next = Object.assign({}, s.approved);
        items.forEach(it => { next[it.id] = true; });
        return { approved: next };
      }),

      cardHistoryOpen: !!st.cardHistory,
      closeCardHistory: () => this.setState({ cardHistory: null }),
      cardHistoryTag: st.cardHistory ? st.cardHistory.tag + ' · versions' : '',
      cardHistoryTitle: st.cardHistory ? st.cardHistory.title : '',
      cardVersions: (st.cardHistory ? [0, 1, 2, 3] : []).map(j => {
        const ch = st.cardHistory;
        const vnum = 4 - j;
        const vs = st.versions[ch.id] || { cur: baseVersion, act: baseVersion };
        const isCur = vnum === vs.cur;
        const isAct = vnum === vs.act;
        const img = ch.kind === 'image';
        const badge = (on, bg, fg) => 'font-size: 9.5px; font-weight: 700; padding: 2px 7px; border-radius: 999px; display: ' + (on ? 'inline' : 'none') + '; background: ' + bg + '; color: ' + fg + ';';
        return {
          version: 'v' + vnum,
          currentStyle: badge(isCur, '#eaf5ef', '#1f6b46'),
          activeStyle: badge(isAct, '#fdeadd', '#a8410a'),
          restoreStyle: 'flex: none; align-self: center; padding: 6px 11px; border-radius: 9px; font-family: inherit; font-size: 11.5px; font-weight: 600; cursor: pointer; border: 1px solid #e3e1dc; background: #fff; color: #6c6862; display: ' + (isCur ? 'none' : 'block') + ';',
          restore: e => { e.stopPropagation(); this.setState(s => ({ versions: Object.assign({}, s.versions, { [ch.id]: { cur: vnum, act: vnum } }) })); },
          snippet: img ? ch.slot + ' · ' + ['latest crop', 'tighter crop', 'first pass', 'original brief'][j] : ch.snippet[j % ch.snippet.length],
          meta: ['Sep 1, 2026 · James', 'Aug 28, 2026 · Dillon', 'Aug 21, 2026 · James', 'Aug 14, 2026 · auto-run'][j],
          thumbStyle: img
            ? 'width: 44px; height: 56px; border-radius: 8px; flex: none; border: 1px solid #e8e5df; background: ' + stripe(20 + j * 47) + ';'
            : 'width: 44px; height: 56px; border-radius: 8px; flex: none; display: flex; align-items: center; justify-content: center; font-family: \'IBM Plex Mono\', monospace; font-size: 10px; color: #8a857f; background: #f4f2ee; border: 1px solid #e8e5df;',
          thumbLabel: img ? '' : 'TXT',
          style: 'flex: none; display: flex; align-items: flex-start; gap: 11px; width: 100%; padding: 11px; border-radius: 13px; cursor: pointer; font-family: inherit; transition: border-color .16s ease; border: 1px solid ' + (isAct ? '#f2b98e' : (isCur ? '#c9e5d6' : '#e6e4de')) + '; background: ' + (isAct ? 'linear-gradient(180deg, #fff8f3, #fff2e8)' : '#fff') + ';',
          select: () => this.setState(s => ({ versions: Object.assign({}, s.versions, { [ch.id]: { cur: vs.cur, act: vnum } }) }))
        };
      }),

      historyOpen: st.historyOpen,
      openHistory: () => this.setState({ historyOpen: true }),
      // Every section is version-scoped, so the Run history control always
      // carries the version that is currently on screen.
      showHistoryVersion: true,
      historyVersion: run.version,
      runHistoryBtnStyle: 'display: flex; align-items: center; gap: 8px; height: 40px; padding: 0 12px; background: #fff; border: 1px solid #e3e1dc; border-radius: 11px; color: #4b4741; cursor: pointer; font-family: inherit;',
      historyVersionStyle: "font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 500; padding: 2px 7px; border-radius: 6px; background: #fff4ec; color: #a8410a;",
      mobMenuOpen: !!st.mobMenuOpen,
      toggleMobMenu: () => this.setState(x => ({ mobMenuOpen: !x.mobMenuOpen })),
      closeMobMenu: () => this.setState({ mobMenuOpen: false }),
      mobHistory: () => this.setState({ mobMenuOpen: false, historyOpen: true }),
      closeHistory: () => this.setState({ historyOpen: false }),
      historySubtitle: client.name + ' · ' + this.data.runs.length + ' saved runs',
      runs: this.data.runs.map(r => {
        const sel = r.id === st.runId;
        return {
          date: r.date, summary: r.summary, author: r.author, approved: r.approved, version: r.version,
          tag: sel ? 'Viewing' : (r.id === 'r1' ? 'Latest' : ''),
          tagStyle: 'font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 999px; display: ' + (sel || r.id === 'r1' ? 'inline' : 'none') + '; background: ' + (sel ? '#fdeadd' : '#eaf5ef') + '; color: ' + (sel ? '#a8410a' : '#1f6b46') + ';',
          dotStyle: 'width: 8px; height: 8px; border-radius: 999px; background: ' + (sel ? ACCENT : '#d6d1c9') + ';',
          style: 'flex: none; display: flex; flex-direction: column; gap: 8px; width: 100%; padding: 13px 14px; border-radius: 14px; cursor: pointer; font-family: inherit; text-align: left; transition: border-color .16s ease; border: 1px solid ' + (sel ? '#f2b98e' : '#e6e4de') + '; background: ' + (sel ? 'linear-gradient(180deg, #fff8f3, #fff2e8)' : '#fff') + ';',
          select: () => this.setState({ runId: r.id, historyOpen: false })
        };
      }),

      modalOpen: st.modalOpen,
      openModal: () => this.open(),
      closeModal: () => this.setState({ modalOpen: false }),
      stop: e => e.stopPropagation(),
      searchRef: this.searchRef,
      query: st.query,
      onQuery: e => this.setState({ query: e.target.value }),
      noResults: filtered.length === 0,
      clientCountLabel: filtered.length + ' / ' + this.data.clients.length,
      // Recent / All, ported from the reference picker. Recent is the default
      // because the list is long and the client you want is nearly always one
      // you were just working on. A search overrides both tabs: typing a name
      // is an unambiguous request for that client, so it looks everywhere.
      clientSearching: clientSearching,
      clientTabs: [
        { id: 'recent', label: 'Recent', count: recentClients.length },
        { id: 'all', label: 'All clients', count: this.data.clients.length },
      ].map(t => {
        const on = st.clientTab === t.id && !clientSearching;
        return {
          label: t.label,
          count: t.count,
          style: 'display: flex; align-items: center; gap: 7px; padding: 7px 13px; border-radius: 999px; cursor: pointer; font-family: inherit; font-size: 12.5px; font-weight: 600; border: 1px solid ' + (on ? '#f2b98e' : '#e6e4de') + '; background: ' + (on ? '#fff8f3' : '#fff') + '; color: ' + (on ? '#0f2f2b' : '#8a857f') + ';',
          countStyle: "font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; padding: 1px 6px; border-radius: 999px; background: " + (on ? '#f6dcc4' : '#f4f2ee') + '; color: ' + (on ? '#8a5a2b' : '#a3a09a') + ';',
          select: () => this.setState({ clientTab: t.id }),
        };
      }),
      filteredClients: clientRows.map(c => {
        const sel = c.id === st.clientId;
        return {
          name: c.name, meta: c.meta, initials: initials(c.name),
          ago: agoOf(c.lastRunAt),
          style: 'width: 100%; display: flex; align-items: center; gap: 12px; padding: 10px 12px; border: none; border-radius: 12px; cursor: pointer; font-family: inherit; background: ' + (sel ? '#fff6f0' : 'transparent') + ';',
          avatarStyle: 'width: 34px; height: 34px; border-radius: 10px; flex: none; display: flex; align-items: center; justify-content: center; font-size: 12.5px; font-weight: 700; background: ' + (sel ? 'linear-gradient(140deg, #0f3a34, #185349)' : '#f4f2ee') + '; color: ' + (sel ? '#eafdf6' : '#6c6862') + ';',
          checkStyle: 'flex: none; width: 22px; height: 22px; border-radius: 999px; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; background: ' + (sel ? ACCENT : 'transparent') + '; color: ' + (sel ? '#fff' : 'transparent') + ';',
          select: () => this.setState({ clientId: c.id, modalOpen: false, query: '' })
        };
      })
    };
  }

  render() {
    const v = this.renderVals();

    return (
      <div data-page="1" style={css("font-family: 'Plus Jakarta Sans', system-ui, sans-serif; color: #16181c; background: #f6f5f2; min-height: 100vh; padding: clamp(18px, 3vw, 28px) clamp(14px, 3vw, 32px) 72px; display: flex; flex-direction: column; gap: 20px;")}>

        <div style={css('display: flex; align-items: flex-start; justify-content: space-between; gap: 32px; flex-wrap: wrap;')}>
          <div style={css('display: flex; flex-direction: column; gap: 6px; max-width: 560px;')}>
            <div style={css("font-size: 11.5px; font-weight: 500; letter-spacing: .16em; text-transform: uppercase; color: #a3a09a; font-family: 'IBM Plex Mono', monospace;")}>WBT content pipeline</div>
            <h1 style={css('margin: 0; font-size: 30px; font-weight: 800; letter-spacing: -.025em; color: #0f2f2b;')}>Content Generation</h1>
            <p style={css('margin: 0; font-size: 14px; line-height: 1.55; color: #6c6862; text-wrap: pretty;')}>Pick a client, then review every generated asset in one place. Results land here automatically as runs complete.</p>
          </div>
        </div>

        <div data-mobbar="1" style={css('display: none; position: relative; align-items: center; gap: 8px;')}>
          <div style={css('position: relative; flex: 1 1 auto; min-width: 0;')}>
            <select value={v.sectionValue} onChange={v.onSectionChange} aria-label="Section" style={css('appearance: none; width: 100%; padding: 12px 34px 12px 14px; background: #fff; border: 1px solid #e3e1dc; border-radius: 14px; font-family: inherit; font-size: 14px; font-weight: 700; color: #16181c; box-shadow: 0 3px 12px rgba(20,18,16,.05); cursor: pointer;')}>
              {v.sections.map(s => (
                <option key={s.id} value={s.id}>{s.optLabel}</option>
              ))}
            </select>
            <span style={css('position: absolute; right: 13px; top: 50%; transform: translateY(-50%); pointer-events: none; color: #a3a09a; font-size: 11px;')}>▾</span>
          </div>
          <button type="button" onClick={v.openModal} title="Switch client" aria-label="Switch client" style={css('display: flex; align-items: center; justify-content: center; width: 46px; height: 46px; flex: none; padding: 0; background: linear-gradient(140deg, #0f3a34, #185349); color: #eafdf6; border: none; border-radius: 14px; font-family: inherit; font-size: 13px; font-weight: 700; cursor: pointer; box-shadow: 0 4px 14px rgba(15,58,52,.24);')}>{v.clientInitials}</button>
          <button type="button" data-mobmenu="1" onClick={v.toggleMobMenu} title="More actions" aria-label="More actions" style={css('display: flex; align-items: center; justify-content: center; width: 46px; height: 46px; flex: none; background: #fff; border: 1px solid #e3e1dc; border-radius: 14px; color: #4b4741; cursor: pointer;')}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="12" cy="5" r="1.4" fill="currentColor" stroke="none"></circle>
              <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"></circle>
              <circle cx="12" cy="19" r="1.4" fill="currentColor" stroke="none"></circle>
            </svg>
          </button>
          {v.mobMenuOpen && (
            <>
              <div onClick={v.closeMobMenu} style={css('position: fixed; inset: 0; z-index: 19;')}></div>
              <div style={css('position: absolute; top: 100%; right: 0; z-index: 20; margin-top: 6px; min-width: 190px; padding: 7px; background: #fff; border: 1px solid #e6e4de; border-radius: 14px; box-shadow: 0 22px 44px rgba(20,18,16,.18); display: flex; flex-direction: column; gap: 2px; animation: dcPop .14s ease both;')}>
                <button type="button" onClick={v.mobHistory} className={hv('background: #faf8f5;')} style={css('display: flex; align-items: center; gap: 10px; padding: 11px 12px; background: transparent; border: none; border-radius: 10px; font-family: inherit; font-size: 13.5px; font-weight: 600; color: #4b4741; cursor: pointer; text-align: left;')}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"></path><path d="M3 4v4h4"></path><path d="M12 8v4.5l3 2"></path></svg>
                  Run history{v.showHistoryVersion ? ' · ' + v.historyVersion : ''}
                </button>
                <button type="button" onClick={v.closeMobMenu} className={hv('background: #faf8f5;')} style={css('display: flex; align-items: center; gap: 10px; padding: 11px 12px; background: transparent; border: none; border-radius: 10px; font-family: inherit; font-size: 13.5px; font-weight: 600; color: #4b4741; cursor: pointer; text-align: left;')}>↻ Run again</button>
                <button type="button" onClick={v.closeMobMenu} className={hv('background: #faf8f5;')} style={css('display: flex; align-items: center; gap: 10px; padding: 11px 12px; background: transparent; border: none; border-radius: 10px; font-family: inherit; font-size: 13.5px; font-weight: 600; color: #4b4741; cursor: pointer; text-align: left;')}>↓ Export</button>
              </div>
            </>
          )}
        </div>

        <div style={css('display: flex; align-items: center; justify-content: space-between; gap: 20px; flex-wrap: wrap;')}>
          <div data-sectabs="1" style={css('display: flex; flex-wrap: wrap; justify-content: center; gap: 4px; padding: 5px; background: #eae7e1; border-radius: 15px; flex: 0 1 auto; min-width: 0;')}>
            {v.sections.map(s => (
              <button key={s.id} type="button" data-wide={s.wide} onClick={s.select} style={css(s.style)} className={hv('color: #16181c;')}>
                {s.label}
                <span style={css(s.badgeStyle)}>{s.count}</span>
              </button>
            ))}
          </div>
          <button type="button" data-genbtn="1" onClick={v.onGenerate} className={hv('transform: translateY(-1px); box-shadow: 0 12px 26px rgba(217,84,26,.34);')} style={css('display: flex; align-items: center; justify-content: center; gap: 9px; flex: 1 1 220px; max-width: 420px; margin-left: auto; white-space: nowrap; padding: 13px 19px; background: linear-gradient(140deg, #ef7326, #d9541a); color: #fff; border: none; border-radius: 13px; font-family: inherit; font-size: 14px; font-weight: 700; cursor: pointer; box-shadow: 0 8px 22px rgba(217,84,26,.28); transition: transform .16s ease, box-shadow .16s ease;')}>
            <span style={css('font-size: 15px; line-height: 1;')}>✦</span><span>{v.generateLabel}</span>
          </button>
        </div>

        <div data-panel="1" style={css('background: #ffffff; border: 1px solid #e6e4de; border-radius: 22px; box-shadow: 0 1px 3px rgba(20,18,16,.04); overflow: hidden;')}>

          <div data-panelhead="1" style={css('display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: clamp(16px, 2.2vw, 22px) clamp(14px, 2.4vw, 26px); border-bottom: 1px solid #efece7; background: linear-gradient(180deg, #fcfbf9, #ffffff); flex-wrap: wrap;')}>
            <button type="button" data-clientbtn="1" onClick={v.openModal} className={hv('border-color: #cbc6bd; box-shadow: 0 6px 20px rgba(20,18,16,.09);')} style={css('display: flex; align-items: center; gap: 13px; flex: 1 1 300px; min-width: 0; padding: 10px 14px 10px 12px; background: #ffffff; border: 1px solid #e3e1dc; border-radius: 14px; cursor: pointer; text-align: left; font-family: inherit; box-shadow: 0 1px 2px rgba(20,18,16,.05); transition: box-shadow .18s ease, border-color .18s ease;')}>
              <span style={css('width: 40px; height: 40px; border-radius: 11px; background: linear-gradient(140deg, #0f3a34, #185349); color: #eafdf6; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex: none;')}>{v.clientInitials}</span>
              <span style={css('display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0;')}>
                <span style={css('display: flex; align-items: center; gap: 8px;')}>
                  <span style={css('font-size: 9.5px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: #a3a09a;')}>Active client</span>
                  <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #a3a09a; padding: 2px 6px; background: #f4f2ee; border-radius: 5px;")}>⌘K</span>
                </span>
                <span style={css('font-size: 17px; font-weight: 800; letter-spacing: -.02em; color: #0f2f2b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;')}>{v.clientName}</span>
                <span data-clientmeta="1" style={css('font-size: 11.5px; color: #8a857f;')}>{v.panelMeta}</span>
              </span>
              <span style={css('color: #a3a09a; font-size: 12px; flex: none;')}>▾</span>
            </button>
            <div data-toolbar="1" style={css('display: flex; align-items: center; gap: 8px; flex: 0 0 auto; flex-wrap: nowrap; justify-content: flex-end;')}>
              <button type="button" onClick={v.openHistory} title="Run history" className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css(v.runHistoryBtnStyle)}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"></path>
                  <path d="M3 4v4h4"></path>
                  <path d="M12 8v4.5l3 2"></path>
                </svg>
                {v.showHistoryVersion && (
                  <span style={css(v.historyVersionStyle)}>{v.historyVersion}</span>
                )}
              </button>
              <button type="button" className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('display: flex; align-items: center; gap: 7px; padding: 10px 15px; background: #fff; border: 1px solid #e3e1dc; border-radius: 11px; font-family: inherit; font-size: 13px; font-weight: 600; color: #4b4741; cursor: pointer;')}>↻ Run again</button>
              <button type="button" className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('display: flex; align-items: center; gap: 7px; padding: 10px 15px; background: #fff; border: 1px solid #e3e1dc; border-radius: 11px; font-family: inherit; font-size: 13px; font-weight: 600; color: #4b4741; cursor: pointer;')}>↓ Export</button>
            </div>
          </div>

          <div data-tabrow="1" style={css('display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: clamp(14px, 2vw, 18px) clamp(14px, 2.4vw, 26px) 0; flex-wrap: wrap;')}>
            <div data-tabrowleft="1" style={css('display: flex; align-items: center; gap: 10px; flex-wrap: wrap;')}>
              {v.isMonthly && (
                <div style={css('position: relative; display: flex; align-items: center; gap: 10px;')}>
                  <button type="button" onClick={v.toggleMonths} style={css(v.monthBtnStyle)} className={hv('border-color: #cbc6bd;')}>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#a8410a" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" style={css('flex: none;')}>
                      <rect x="3.5" y="5" width="17" height="16" rx="3"></rect>
                      <path d="M3.5 10h17"></path>
                      <path d="M8 3v3.5"></path>
                      <path d="M16 3v3.5"></path>
                    </svg>
                    <span style={css('display: flex; flex-direction: column; gap: 1px; text-align: left;')}>
                      <span style={css('font-size: 8.5px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: #a3a09a;')}>Month</span>
                      <span style={css('font-size: 13.5px; font-weight: 700; color: #16181c;')}>{v.monthLabel}</span>
                    </span>
                    <span style={css(v.monthCaretStyle)}>▾</span>
                  </button>
                  <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #a3a09a;")}>12 blogs</span>
                  {v.monthsOpen && (
                    <>
                      <div onClick={v.closeMonths} style={css('position: fixed; inset: 0; z-index: 19;')}></div>
                      <div style={css('position: absolute; top: 100%; left: 0; z-index: 20; margin-top: 8px; min-width: 230px; padding: 7px; background: #fff; border: 1px solid #e6e4de; border-radius: 14px; box-shadow: 0 22px 44px rgba(20,18,16,.18); display: flex; flex-direction: column; gap: 2px; animation: dcPop .14s ease both;')}>
                        {v.monthOptions.map(m => (
                          <button key={m.id} type="button" onClick={m.select} style={css(m.style)} className={hv('background: #faf8f5;')}>
                            <span style={css('flex: 1; text-align: left;')}>{m.label}</span>
                            <span style={css(m.checkStyle)}>✓</span>
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}
              {v.notMonthly && (
                <div data-subtabs="1" style={css('display: flex; align-items: center; gap: 8px; flex-wrap: wrap;')}>
                  {v.subTabs.map((t, ti) => (
                    <button key={ti} type="button" onClick={t.select} style={css(t.style)} className={hv('border-color: #cbc6bd;')}>
                      {t.label}
                      <span style={css(t.badgeStyle)}>{t.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {v.showViews && (
              <div data-views="1" style={css('display: flex; padding: 4px; background: #f2efea; border: 1px solid #e8e5df; border-radius: 12px; gap: 3px;')}>
                {v.views.map((vw, vi) => (
                  <button key={vi} type="button" onClick={vw.select} style={css(vw.style)}>
                    <span style={css(vw.dotStyle)}></span>{vw.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {v.showApprove && (
            <div data-approve="1" style={css('display: flex; align-items: center; justify-content: space-between; gap: 20px; margin: 18px clamp(14px, 2.4vw, 26px) 0; padding: 14px 18px; background: #faf9f6; border: 1px solid #eeebe5; border-radius: 14px; flex-wrap: wrap;')}>
              <div style={css('display: flex; align-items: center; gap: 14px;')}>
                <div style={css('width: 132px; height: 6px; border-radius: 999px; background: #e7e3dc; overflow: hidden;')}>
                  <div style={css(v.progressStyle)}></div>
                </div>
                <span style={css("font-size: 12.5px; color: #6c6862; font-family: 'IBM Plex Mono', monospace;")}>{v.approvedLabel}</span>
              </div>
              <button type="button" onClick={v.approveAll} className={hv('border-color: #aed7c1; background: #f3faf6;')} style={css('padding: 9px 15px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; font-family: inherit; font-size: 13px; font-weight: 600; color: #1f6b46; cursor: pointer;')}>✓ Approve all {v.unitPlural}</button>
            </div>
          )}

          {v.isLogo && (
            <div style={css('padding: clamp(14px, 2vw, 22px) clamp(14px, 2.4vw, 26px) 30px; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: 20px;')}>
              {v.logoCards.map((l, li) => (
                <div key={li} data-item-id={l.routeId} data-item-slug={l.routeSlug} className={hv('box-shadow: 0 10px 30px rgba(20,18,16,.08);')} style={css('display: flex; flex-direction: column; border: 1px solid #e6e4de; border-radius: 20px; overflow: hidden; background: #fff; box-shadow: 0 2px 6px rgba(20,18,16,.04); animation: dcFade .3s ease both;')}>
                  <div style={css('display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 14px 16px; border-bottom: 1px solid #f1eee9; background: linear-gradient(180deg, #fcfbf9, #ffffff);')}>
                    <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: .1em; color: #a3a09a;")}>{l.tag}</span>
                    <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10px; padding: 2px 7px; border-radius: 6px; background: #f4f2ee; color: #8a857f;")}>{l.version}</span>
                  </div>
                  <div style={css(l.canvasStyle)}>
                    <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #6c6862; background: rgba(255,255,255,.9); padding: 6px 10px; border-radius: 7px;")}>{l.label}</span>
                  </div>
                  <div style={css('display: flex; align-items: center; gap: 6px; padding: 12px 14px; border-top: 1px solid #f1eee9; background: #fcfbf9;')}>
                    <button type="button" title="AI Edit" className={hv('background: #efe7fb;')} style={css('flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 9px; background: #f6f2fd; border: 1px solid #e6dcf8; border-radius: 10px; font-family: inherit; font-size: 12px; font-weight: 600; color: #6a4bbd; cursor: pointer;')}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 3l1.7 4.6L18.5 9l-4.8 1.4L12 15l-1.7-4.6L5.5 9l4.8-1.4L12 3z"></path>
                        <path d="M18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8L18 16z"></path>
                      </svg>
                      <span data-lbl="ai">AI<span data-lbl="edit"> Edit</span></span>
                    </button>
                    <button type="button" title="Regenerate" className={hv('background: #ffeadb;')} style={css('display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; background: #fff4ec; border: 1px solid #fadfc9; border-radius: 10px; color: #cf5c17; cursor: pointer;')}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1"></path>
                        <path d="M21 4v4h-4"></path>
                      </svg>
                    </button>
                    <button type="button" title="Download" className={hv('border-color: #cbc6bd;')} style={css('display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; color: #6c6862; cursor: pointer;')}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 4v11"></path>
                        <path d="M7 11l5 5 5-5"></path>
                        <path d="M5 19h14"></path>
                      </svg>
                    </button>
                    <button type="button" onClick={l.openVersions} title="Version history" className={hv('border-color: #cbc6bd;')} style={css('display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; color: #6c6862; cursor: pointer;')}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"></path>
                        <path d="M3 4v4h4"></path>
                        <path d="M12 8v4.5l3 2"></path>
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {v.formOpen && (
            <div onClick={v.closeForm} style={css('position: fixed; inset: 0; background: rgba(18,16,14,.44); backdrop-filter: blur(3px); display: flex; align-items: center; justify-content: center; padding: clamp(0px, calc(6vw - 34px), 40px) clamp(0px, calc(6vw - 34px), 20px); z-index: 60;')}>
              <div onClick={v.stop} style={css('width: min(100%, 1480px); max-height: 100%; display: flex; flex-direction: column; background: #fff; border-radius: clamp(0px, calc(6vw - 34px), 20px); box-shadow: 0 30px 70px rgba(20,18,16,.3); overflow: hidden; animation: dcPop .18s ease both;')}>

                <div style={css('position: relative; border-bottom: 1px solid #efece7;')}>
                  <button type="button" onClick={v.toggleLogoPicker} style={css(v.logoClientBtnStyle)} className={hv('background: #faf9f6;')}>
                    <span style={css('width: 46px; height: 46px; border-radius: 13px; background: linear-gradient(140deg, #0f3a34, #185349); color: #eafdf6; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700; flex: none;')}>{v.clientInitials}</span>
                    <span style={css('display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; text-align: left;')}>
                      <span style={css('font-size: 9.5px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: #a3a09a;')}>Active client</span>
                      <span style={css('font-size: 19px; font-weight: 800; letter-spacing: -.02em; color: #0f2f2b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;')}>{v.clientName}</span>
                      <span style={css('font-size: 12px; color: #8a857f;')}>{v.formMeta}</span>
                    </span>
                    <span style={css('display: flex; align-items: center; gap: 8px; flex: none; font-size: 12px; font-weight: 600; color: #8a857f;')}>Switch client <span style={css('color: #a3a09a;')}>▾</span></span>
                  </button>
                  {v.logoPickerOpen && (
                    <>
                      <div onClick={v.closePicker} style={css('position: fixed; inset: 0; z-index: 7;')}></div>
                      <div style={css('position: absolute; top: 100%; left: 0; right: 0; z-index: 8; margin-top: -1px; padding: 14px clamp(14px, 2.4vw, 22px) 16px; border-bottom: 1px solid #e6e4de; background: #fff; box-shadow: 0 22px 40px rgba(20,18,16,.16); display: flex; flex-direction: column; gap: 10px;')}>
                        <div style={css('display: flex; align-items: center; gap: 10px; padding: 10px 12px; background: #fff; border: 1px solid #e3e1dc; border-radius: 11px;')}>
                          <span style={css('color: #a3a09a; font-size: 14px;')}>⌕</span>
                          <input value={v.query} onChange={v.onQuery} placeholder="Search clients…" style={css('flex: 1; border: none; outline: none; font-family: inherit; font-size: 14px; color: #16181c; background: transparent;')} />
                          <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; color: #a3a09a;")}>{v.clientCountLabel}</span>
                        </div>
                        <div style={css('display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 6px; max-height: 220px; overflow: auto;')}>
                          {v.logoClients.map((lc, lci) => (
                            <button key={lci} type="button" onClick={lc.select} style={css(lc.style)} className={hv('border-color: #cbc6bd;')}>
                              <span style={css(lc.avatarStyle)}>{lc.initials}</span>
                              <span style={css('display: flex; flex-direction: column; gap: 1px; flex: 1; min-width: 0; text-align: left;')}>
                                <span style={css('font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;')}>{lc.name}</span>
                                <span style={css('font-size: 11px; color: #8a857f; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;')}>{lc.meta}</span>
                              </span>
                              <span style={css(lc.checkStyle)}>✓</span>
                            </button>
                          ))}
                          <button type="button" onClick={v.newClient} className={hv('border-color: #f2b98e;')} style={css('display: flex; align-items: center; gap: 10px; padding: 9px 11px; border: 1px dashed #ded9d1; border-radius: 12px; background: #fff; cursor: pointer; font-family: inherit;')}>
                            <span style={css('width: 30px; height: 30px; border-radius: 9px; background: #f4f2ee; color: #cf5c17; display: flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 700; flex: none;')}>+</span>
                            <span style={css('font-size: 13px; font-weight: 600; color: #cf5c17;')}>New client</span>
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </div>

                <div style={css('flex: 1; min-height: 0; overflow: auto; padding: clamp(12px, 2.4vw, 20px) clamp(12px, 2.4vw, 22px) 24px; display: flex; flex-direction: column; gap: 16px; background: #faf9f6;')}>

                  {v.formHasModes && (
                    <div style={css('flex: none; display: flex; flex-direction: column; gap: 8px; padding: clamp(14px, 2.4vw, 20px); background: #fff; border: 1px solid #e8e5df; border-radius: 16px;')}>
                      <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>Approach</span>
                      <div style={css('display: flex; align-items: center; gap: 8px; flex-wrap: wrap;')}>
                        {v.formModes.map((m, mi) => (
                          <button key={mi} type="button" onClick={m.select} style={css(m.style)}>{m.label}</button>
                        ))}
                      </div>
                    </div>
                  )}

                  {v.formCards.map((sec, si) => (
                    <div key={si} style={css('flex: none; background: #fff; border: 1px solid #e8e5df; border-radius: 16px; overflow: hidden;')}>
                      <button type="button" onClick={sec.collapsible ? sec.toggle : undefined} className={sec.collapsible ? hv('background: #fcfbf9;') : ''} style={css('display: flex; align-items: center; gap: 12px; width: 100%; padding: clamp(14px, 2.4vw, 20px) clamp(14px, 2.4vw, 20px) ' + (sec.open ? '0' : 'clamp(14px, 2.4vw, 20px)') + '; background: transparent; border: none; font-family: inherit; text-align: left; cursor: ' + (sec.collapsible ? 'pointer' : 'default') + ';')}>
                        <span style={css(sec.iconWrapStyle)}>
                          {sec.isBusiness && (
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={sec.iconStroke} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                              <rect x="3" y="4" width="18" height="16" rx="3"></rect>
                              <path d="M7 15v-3"></path><path d="M12 15V9"></path><path d="M17 15v-5"></path>
                            </svg>
                          )}
                          {sec.isDoc && (
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={sec.iconStroke} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M6 3h9l4 4v14H6z"></path><path d="M15 3v4h4"></path><path d="M9 12h7"></path><path d="M9 16h7"></path>
                            </svg>
                          )}
                          {sec.isVideo && (
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={sec.iconStroke} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                              <rect x="2.5" y="6" width="13" height="12" rx="3"></rect>
                              <path d="M15.5 11l6-3.2v8.4l-6-3.2z"></path>
                            </svg>
                          )}
                          {sec.isImage && (
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={sec.iconStroke} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                              <rect x="3" y="4" width="18" height="16" rx="3"></rect>
                              <circle cx="8.5" cy="9.5" r="1.6"></circle>
                              <path d="M4 17l5-5 4 4 3-2.5 4 3.5"></path>
                            </svg>
                          )}
                        </span>
                        <span style={css('display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0;')}>
                          <span style={css('display: flex; align-items: center; gap: 8px; flex-wrap: wrap;')}>
                            <span style={css('font-size: 15.5px; font-weight: 800; letter-spacing: -.015em; color: #16181c;')}>{sec.heading}</span>
                            {sec.requiredMark && <span style={css('color: #d95c15; font-weight: 800;')}>*</span>}
                            {sec.optional && <span style={css('font-size: 12px; font-weight: 600; color: #a3a09a;')}>optional</span>}
                          </span>
                          <span style={css('font-size: 12.5px; line-height: 1.5; color: #8a857f; text-wrap: pretty;')}>{sec.subtext}</span>
                        </span>
                        {sec.collapsible && <span style={css(sec.caretStyle)}>▾</span>}
                      </button>

                      <div style={css(sec.bodyStyle)}>
                        <div style={css('padding: 16px clamp(14px, 2.4vw, 20px) clamp(14px, 2.4vw, 20px); display: flex; flex-direction: column; gap: 14px;')}>
                          {sec.note && (
                            <span style={css('font-size: 11.5px; line-height: 1.5; color: #a3a09a;')}>{sec.note}</span>
                          )}
                          <div style={css(sec.gridStyle)}>
                            {sec.fields.map((f, fi) => (
                              <label key={fi} style={css(f.wrapStyle)}>
                                {!f.hideLabel && (
                                  <span style={css("display: flex; align-items: center; gap: 5px; font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>
                                    {f.label}
                                    {f.required && <span style={css('color: #d95c15;')}>*</span>}
                                    {f.isIndustries && <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; padding: 2px 7px; border-radius: 6px; background: #fff4ec; color: #a8410a; letter-spacing: 0;")}>{f.countLabel}</span>}
                                  </span>
                                )}

                                {f.isInput && (
                                  <input type={f.inputType} value={f.value} onChange={f.onChange} placeholder={f.placeholder} min={f.min} max={f.max} className={fc('border-color: #f2b98e;')} style={css(f.inputStyle)} />
                                )}
                                {f.isTextarea && (
                                  <textarea value={f.value} onChange={f.onChange} rows={f.rows} placeholder={f.placeholder} className={fc('border-color: #f2b98e;')} style={css(f.textareaStyle)}></textarea>
                                )}
                                {(f.isIndustries || f.isIndustry) && (
                                  <div style={css('display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 150px), 1fr)); gap: 8px;')}>
                                    {f.chips.map((c, ci) => (
                                      <button key={ci} type="button" onClick={c.toggle} style={css(c.style)} className={hv('border-color: #cbc6bd;')}>
                                        <span style={css('flex: 1; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;')}>{c.label}</span>
                                        <span style={css(c.checkStyle)}>✓</span>
                                      </button>
                                    ))}
                                  </div>
                                )}
                                {f.isFile && (
                                  <div style={css('display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 26px 18px; border: 1px dashed #ded9d1; border-radius: 14px; background: #faf9f6; text-align: center;')}>
                                    <span style={css('font-size: 13px; font-weight: 600; color: #4b4741;')}>{f.fileName || 'Drop the file here'}</span>
                                    <span style={css('font-size: 11.5px; color: #8a857f;')}>{f.accept}</span>
                                    <button type="button" onClick={f.pickFile} className={hv('border-color: #cbc6bd;')} style={css('margin-top: 4px; padding: 8px 14px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 600; color: #4b4741; cursor: pointer;')}>{f.fileName ? 'Remove' : 'Browse files'}</button>
                                  </div>
                                )}

                                {f.hint && (
                                  <span style={css(f.hintTone === 'ok'
                                    ? 'font-size: 11.5px; line-height: 1.5; color: #1f6b46;'
                                    : f.hintTone === 'warn'
                                    ? 'font-size: 11.5px; line-height: 1.5; color: #a8410a;'
                                    : 'font-size: 11.5px; line-height: 1.5; color: #a3a09a;')}>{f.hint}</span>
                                )}
                              </label>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {v.formError && (
                  <div style={css('padding: 10px clamp(14px, 2.4vw, 22px); border-top: 1px solid #f6cccc; background: #fdecec; font-size: 12.5px; color: #c04141;')}>{v.formError}</div>
                )}

                <div style={css('display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px clamp(14px, 2.4vw, 22px); border-top: 1px solid #efece7; background: #fff; flex-wrap: wrap;')}>
                  <span style={css('display: flex; align-items: center; gap: 9px;')}>
                    <span style={css('width: 22px; height: 22px; border-radius: 999px; background: #eef8f2; border: 1px solid #c9e6d6; color: #1f6b46; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700;')}>✓</span>
                    <span style={css('display: flex; flex-direction: column; gap: 1px;')}>
                      <span style={css('font-size: 12.5px; font-weight: 700; color: #1f6b46;')}>Auto-saved</span>
                      <span style={css('font-size: 11px; color: #a3a09a;')}>{v.formFootnote}</span>
                    </span>
                  </span>
                  <div data-formactions="1" style={css('display: flex; align-items: center; gap: 8px; flex: 1 1 320px; flex-wrap: wrap;')}>
                    <button type="button" onClick={v.cancelForm} className={hv('border-color: #cbc6bd; color: #4b4741;')} style={css('flex: 1 1 auto; text-align: center; white-space: nowrap; padding: 11px 16px; background: #fff; border: 1px solid #e3e1dc; border-radius: 11px; font-family: inherit; font-size: 13px; font-weight: 600; color: #8a857f; cursor: pointer;')}>Cancel</button>
                    <button type="button" onClick={v.closeForm} className={hv('border-color: #cbc6bd;')} style={css('flex: 1 1 auto; text-align: center; white-space: nowrap; padding: 11px 16px; background: #fff; border: 1px solid #e3e1dc; border-radius: 11px; font-family: inherit; font-size: 13px; font-weight: 600; color: #4b4741; cursor: pointer;')}>Save draft</button>
                    <button type="button" onClick={v.submitForm} disabled={v.submitting} className={hv('transform: translateY(-1px);')} style={css(v.formSubmitStyle)}>✦ {v.submitting ? 'Starting…' : v.formSubmit}</button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {v.isBlog && (
            <div style={css('padding: clamp(14px, 2vw, 20px) clamp(14px, 2.4vw, 26px) 30px; display: flex; flex-direction: column; gap: 12px;')}>

              {v.blogIsSections && (
                <>
                  <div data-pagebar="1" style={css('display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding-bottom: 10px; border-bottom: 1px solid #efece7;')}>
                    <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; font-weight: 600; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>{v.blogSummary}</span>
                    <div style={css('display: flex; align-items: center; gap: 8px; flex-wrap: wrap;')}>
                      <button type="button" onClick={v.toggleAllBlogs} className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('padding: 8px 13px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 600; color: #4b4741; cursor: pointer;')}>{v.blogAllOpen ? 'Collapse all' : 'Expand all'}</button>
                      <button type="button" onClick={v.copyAllBlogs} className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('display: flex; align-items: center; gap: 7px; padding: 8px 13px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 600; color: #4b4741; cursor: pointer;')}>
                        <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="7" y="7" width="9" height="9" rx="1.6"></rect>
                          <path d="M13 5.5V5A1.5 1.5 0 0 0 11.5 3.5H5A1.5 1.5 0 0 0 3.5 5v6.5A1.5 1.5 0 0 0 5 13h.5"></path>
                        </svg>
                        {v.copiedAllBlogs ? 'Copied' : 'Copy all'}
                      </button>
                      <div style={css('position: relative;')}>
                        <button type="button" onClick={v.toggleBlogExport} className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('display: flex; align-items: center; gap: 7px; padding: 8px 13px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 600; color: #4b4741; cursor: pointer;')}>
                          ↓ {v.blogExporting ? 'Building PDF…' : 'Export'} <span style={css('color: #a3a09a; font-size: 10px;')}>▾</span>
                        </button>
                        {v.blogExportOpen && (
                          <>
                            <div onClick={v.closeBlogExport} style={css('position: fixed; inset: 0; z-index: 19;')}></div>
                            <div style={css('position: absolute; top: 100%; right: 0; z-index: 20; margin-top: 6px; width: 250px; padding: 7px; background: #fff; border: 1px solid #e6e4de; border-radius: 14px; box-shadow: 0 22px 44px rgba(20,18,16,.18); display: flex; flex-direction: column; gap: 2px; animation: dcPop .14s ease both;')}>
                              {v.blogExportOptions.map((o, oi) => (
                                <button key={oi} type="button" onClick={o.run} className={hv('background: #faf8f5;')} style={css('display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 9px 11px; background: transparent; border: none; border-radius: 10px; font-family: inherit; cursor: pointer; text-align: left;')}>
                                  <span style={css('font-size: 12.5px; font-weight: 700; color: #0f2f2b;')}>{o.label}</span>
                                  <span style={css('font-size: 11px; color: #8a857f;')}>{o.hint}</span>
                                </button>
                              ))}
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {v.blogExportError && (
                    <span style={css('padding: 9px 12px; border: 1px solid #f6cccc; background: #fdecec; border-radius: 10px; font-size: 12.5px; color: #c04141;')}>{v.blogExportError}</span>
                  )}

                  {v.blogSections.map((s, si) => (
                    <div key={si} data-item-id={s.routeId} data-item-slug={s.routeSlug} style={css('border: 1px solid #e6e4de; border-radius: 14px; background: #fff; box-shadow: 0 1px 3px rgba(20,18,16,.04); overflow: hidden; animation: dcFade .3s ease both;')}>
                      <div data-pagehead="1" style={css('display: flex; align-items: center; gap: 10px; padding: 11px clamp(12px, 2.4vw, 16px); flex-wrap: wrap;')}>
                        <button type="button" onClick={s.toggle} style={css('display: flex; align-items: center; gap: 9px; flex: 1 1 240px; min-width: 0; padding: 0; background: transparent; border: none; cursor: pointer; font-family: inherit; text-align: left;')}>
                          <svg width="16" height="16" viewBox="0 0 20 20" fill="none" style={css(s.chevronStyle)}>
                            <path d="M5.5 8 10 12.5 14.5 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"></path>
                          </svg>
                          <span style={css('flex: none; font-size: 13.5px; font-weight: 700; color: #0f2f2b;')}>{s.title}</span>
                          {s.subtitle && (
                            <span title={s.subtitle} style={css('font-size: 13px; color: #8a857f; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;')}>{s.subtitle}</span>
                          )}
                        </button>
                        <span data-pagemeta="1" style={css('display: flex; align-items: center; gap: 10px; flex: none;')}>
                          {s.badge && <span style={css(s.badgeStyle)}>{s.badge}</span>}
                          <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #a3a09a; white-space: nowrap;")}>{s.words} words</span>
                        </span>
                        <button type="button" onClick={s.copy} title={'Copy ' + s.title} className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('display: flex; align-items: center; gap: 6px; flex: none; padding: 7px 11px; background: #fff; border: 1px solid #e3e1dc; border-radius: 9px; font-family: inherit; font-size: 12px; font-weight: 600; color: #4b4741; cursor: pointer;')}>
                          <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="7" y="7" width="9" height="9" rx="1.6"></rect>
                            <path d="M13 5.5V5A1.5 1.5 0 0 0 11.5 3.5H5A1.5 1.5 0 0 0 3.5 5v6.5A1.5 1.5 0 0 0 5 13h.5"></path>
                          </svg>
                          <span data-lbl="copy">{s.copied ? 'Copied' : 'Copy'}</span>
                        </button>
                      </div>
                      <div id={s.bodyId} style={css(s.bodyStyle)}>
                        <Markdown>{s.body}</Markdown>
                      </div>
                    </div>
                  ))}
                </>
              )}

              {v.blogIsBriefs && v.blogBriefs.map((b, bi) => (
                <div key={bi} style={css('border: 1px solid #e6e4de; border-radius: 16px; background: #fff; box-shadow: 0 1px 3px rgba(20,18,16,.04); overflow: hidden; animation: dcFade .3s ease both;')}>
                  <div style={css('display: flex; align-items: flex-start; gap: 12px; padding: 14px clamp(14px, 2.4vw, 18px); flex-wrap: wrap;')}>
                    <span style={css('display: flex; flex-direction: column; gap: 4px; flex: 1 1 260px; min-width: 0;')}>
                      <span style={css('display: flex; align-items: center; gap: 9px; flex-wrap: wrap;')}>
                        <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: .1em; color: #a3a09a;")}>{b.number}</span>
                        <span style={css(b.statusStyle)}>{b.statusLabel}</span>
                      </span>
                      <span style={css('font-size: 14.5px; font-weight: 700; letter-spacing: -.01em; color: #16181c; line-height: 1.35; text-wrap: pretty;')}>{b.title}</span>
                      <span style={css('display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 12px; color: #8a857f;')}>
                        <span>{b.funnel}</span>
                        <span>{b.areas}</span>
                        {b.rounds && <span>{b.rounds}</span>}
                        <span>{b.words}</span>
                      </span>
                    </span>
                    <span style={css('display: flex; align-items: center; gap: 3px; flex: none; padding: 3px; background: #f2efea; border: 1px solid #e8e5df; border-radius: 12px;')}>
                      {b.tabs.map((t, ti) => (
                        <button key={ti} type="button" onClick={t.select} style={css(t.style)}>{t.label}</button>
                      ))}
                    </span>
                  </div>

                  <div style={css('display: flex; flex-wrap: wrap; gap: 6px; padding: 0 clamp(14px, 2.4vw, 18px) 12px;')}>
                    {b.keywords.map((k, ki) => (
                      <span key={ki} style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #4b4741; background: #f4f2ee; border: 1px solid #e8e5df; padding: 4px 9px; border-radius: 999px;")}>{k.text}</span>
                    ))}
                  </div>

                  <div style={css('border-top: 1px solid #f1eee9; padding: 16px clamp(14px, 2.4vw, 18px) 20px; display: flex; flex-direction: column; gap: 14px;')}>
                    {b.isBlogTab && (
                      <>
                        <div style={css('display: flex; flex-direction: column; gap: 6px;')}>
                          <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>General notes</span>
                          <span style={css('font-size: 13px; line-height: 1.6; color: #58544e;')}>{b.generalNotes}</span>
                        </div>
                        <div style={css('display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px;')}>
                          <div style={css('display: flex; flex-direction: column; gap: 5px; padding: 11px 13px; background: #faf9f6; border: 1px solid #eeebe5; border-radius: 12px;')}>
                            <span style={css("display: flex; align-items: center; justify-content: space-between; gap: 8px; font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>Meta title <span style={css('letter-spacing: 0; text-transform: none;')}>{b.metaTitleChars}</span></span>
                            <span style={css('font-size: 13px; line-height: 1.5; color: #16181c;')}>{b.metaTitle}</span>
                          </div>
                          <div style={css('display: flex; flex-direction: column; gap: 5px; padding: 11px 13px; background: #faf9f6; border: 1px solid #eeebe5; border-radius: 12px;')}>
                            <span style={css("display: flex; align-items: center; justify-content: space-between; gap: 8px; font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>Meta description <span style={css('letter-spacing: 0; text-transform: none;')}>{b.metaDescriptionChars}</span></span>
                            <span style={css('font-size: 13px; line-height: 1.5; color: #16181c;')}>{b.metaDescription}</span>
                          </div>
                        </div>
                        <Markdown>{b.content}</Markdown>
                      </>
                    )}

                    {b.isGmbTab && (
                      <>
                        <div style={css('display: flex; flex-direction: column; gap: 6px;')}>
                          <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>Google My Business post</span>
                          <span style={css('font-size: 13.5px; line-height: 1.65; color: #58544e; text-wrap: pretty;')}>{b.gmbPost}</span>
                        </div>
                        <div style={css('display: flex; flex-direction: column; gap: 6px;')}>
                          <span style={css("display: flex; align-items: center; gap: 8px; font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>GMB FAQ <span style={css('letter-spacing: 0; text-transform: none;')}>{b.gmbFaqWords}</span></span>
                          <Markdown>{b.gmbFaq}</Markdown>
                        </div>
                      </>
                    )}

                    {b.isQcTab && (
                      <>
                        <div style={css('display: flex; align-items: center; gap: 12px;')}>
                          <span style={css('display: flex; align-items: baseline; gap: 3px; padding: 10px 16px; border-radius: 14px; background: #faf9f6; border: 1px solid #eeebe5;')}>
                            <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 22px; font-weight: 500; color: #0f2f2b;")}>{b.scoreLabel}</span>
                          </span>
                          <span style={css('font-size: 12.5px; color: #8a857f;')}>QC score across the eight weighted areas below.</span>
                        </div>
                        <div style={css('display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 160px), 1fr)); gap: 8px;')}>
                          {b.qcAreas.map((a, ai) => (
                            <span key={ai} style={css(a.style)}>
                              <span style={css('font-weight: 600;')}>{a.label}</span>
                              <span style={css("font-family: 'IBM Plex Mono', monospace;")}>{a.value}</span>
                            </span>
                          ))}
                        </div>
                        {b.hasFixes && (
                          <div style={css('display: flex; flex-direction: column; gap: 7px;')}>
                            <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>Suggested fixes</span>
                            <ul style={css('margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 5px;')}>
                              {b.fixes.map((f, fi) => (
                                <li key={fi} style={css('font-size: 13px; line-height: 1.55; color: #58544e;')}>{f.text}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {v.isTable && (
            <div style={css('padding: clamp(14px, 2vw, 20px) clamp(14px, 2.4vw, 26px) 30px; display: flex; flex-direction: column; gap: 12px;')}>

              <div data-pagebar="1" style={css('display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding-bottom: 10px; border-bottom: 1px solid #efece7;')}>
                <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; font-weight: 600; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>Content · {v.tableCount}</span>
                <div style={css('display: flex; align-items: center; gap: 8px; flex-wrap: wrap;')}>
                  <button type="button" onClick={v.toggleAllPages} className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('padding: 8px 13px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 600; color: #4b4741; cursor: pointer;')}>{v.pagesAllOpen ? 'Collapse all' : 'Expand all'}</button>
                  <button type="button" onClick={v.copyAllPages} className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('display: flex; align-items: center; gap: 7px; padding: 8px 13px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 600; color: #4b4741; cursor: pointer;')}>
                    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="7" y="7" width="9" height="9" rx="1.6"></rect>
                      <path d="M13 5.5V5A1.5 1.5 0 0 0 11.5 3.5H5A1.5 1.5 0 0 0 3.5 5v6.5A1.5 1.5 0 0 0 5 13h.5"></path>
                    </svg>
                    {v.copiedAll ? 'Copied' : 'Copy all'}
                  </button>
                  <div style={css('position: relative;')}>
                    <button type="button" onClick={v.toggleExport} className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('display: flex; align-items: center; gap: 7px; padding: 8px 13px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 600; color: #4b4741; cursor: pointer;')}>
                      ↓ Export <span style={css('color: #a3a09a; font-size: 10px;')}>▾</span>
                    </button>
                    {v.exportOpen && (
                      <>
                        <div onClick={v.closeExport} style={css('position: fixed; inset: 0; z-index: 19;')}></div>
                        <div style={css('position: absolute; top: 100%; right: 0; z-index: 20; margin-top: 6px; width: 250px; padding: 7px; background: #fff; border: 1px solid #e6e4de; border-radius: 14px; box-shadow: 0 22px 44px rgba(20,18,16,.18); display: flex; flex-direction: column; gap: 2px; animation: dcPop .14s ease both;')}>
                          {v.exportOptions.map((o, oi) => (
                            <button key={oi} type="button" onClick={o.run} className={hv('background: #faf8f5;')} style={css('display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 9px 11px; background: transparent; border: none; border-radius: 10px; font-family: inherit; cursor: pointer; text-align: left;')}>
                              <span style={css('font-size: 12.5px; font-weight: 700; color: #0f2f2b;')}>{o.label}</span>
                              <span style={css('font-size: 11px; color: #8a857f;')}>{o.hint}</span>
                            </button>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {v.pageCards.map((p, pi) => (
                <div key={pi} data-item-id={p.routeId} data-item-slug={p.routeSlug} style={css('border: 1px solid #e6e4de; border-radius: 16px; background: #fff; box-shadow: 0 1px 3px rgba(20,18,16,.04); overflow: hidden; animation: dcFade .3s ease both;')}>

                  <div data-pagehead="1" style={css('display: flex; align-items: center; gap: 12px; padding: 14px clamp(14px, 2.4vw, 18px); flex-wrap: wrap;')}>
                    <button type="button" onClick={p.toggle} style={css('display: flex; align-items: center; gap: 11px; flex: 1 1 260px; min-width: 0; padding: 0; background: transparent; border: none; cursor: pointer; font-family: inherit; text-align: left;')}>
                      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" style={css(p.chevronStyle)}>
                        <path d="M5.5 8 10 12.5 14.5 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"></path>
                      </svg>
                      <span style={css('width: 34px; height: 34px; border-radius: 10px; background: #f2f6fd; border: 1px solid #e1eaf8; display: flex; align-items: center; justify-content: center; flex: none;')}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b7fbf" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M6 3h9l4 4v14H6z"></path>
                          <path d="M15 3v4h4"></path>
                          <path d="M9 12h7"></path>
                          <path d="M9 16h7"></path>
                        </svg>
                      </span>
                      <span style={css('display: flex; flex-direction: column; gap: 2px; min-width: 0;')}>
                        <span style={css('font-size: 14px; font-weight: 700; letter-spacing: -.01em; color: #16181c;')}>{p.name}</span>
                        <span style={css('font-size: 12px; color: #8a857f; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;')}>{p.desc}</span>
                      </span>
                    </button>

                    <span data-pagemeta="1" style={css('display: flex; align-items: center; gap: 10px; flex: none;')}>
                      <span style={css(p.statusStyle)}><span style={css(p.statusDotStyle)}></span>{p.statusLabel}</span>
                      <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11.5px; color: #a3a09a; white-space: nowrap;")}>{p.words} words</span>
                    </span>

                    <span style={css('display: flex; align-items: center; gap: 6px; flex: none;')}>
                      <button type="button" onClick={p.copy} title={'Copy ' + p.name} className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: #fff; border: 1px solid #e3e1dc; border-radius: 9px; font-family: inherit; font-size: 12px; font-weight: 600; color: #4b4741; cursor: pointer;')}>
                        <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="7" y="7" width="9" height="9" rx="1.6"></rect>
                          <path d="M13 5.5V5A1.5 1.5 0 0 0 11.5 3.5H5A1.5 1.5 0 0 0 3.5 5v6.5A1.5 1.5 0 0 0 5 13h.5"></path>
                        </svg>
                        <span data-lbl="copy">{p.copied ? 'Copied' : 'Copy'}</span>
                      </button>
                      <button type="button" onClick={p.startEdit} aria-pressed={p.editing} title={(p.editing ? 'Close editor for ' : 'Edit ') + p.name} className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css(p.editStyle)}>
                        <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M13.5 3.5 16.5 6.5 7.5 15.5 4 16l.5-3.5z"></path>
                        </svg>
                        <span data-lbl="edit">Edit</span>
                      </button>
                    </span>
                  </div>

                  <div style={css('padding: 0 clamp(14px, 2.4vw, 18px) 12px; margin-top: -6px;')}>
                    <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #a3a09a;")}>{p.meta}</span>
                  </div>

                  <div id={p.bodyId} style={css(p.bodyStyle)}>
                    {p.editing ? (
                      <div style={css('display: flex; flex-direction: column; gap: 10px;')}>
                        <textarea value={v.pageDraft} onChange={v.onPageDraft} className={fc('border-color: #f2b98e;')} style={css("width: 100%; min-height: 320px; padding: 14px 16px; border: 1px solid #e3e1dc; border-radius: 12px; font-family: 'IBM Plex Mono', monospace; font-size: 12.5px; line-height: 1.7; color: #16181c; background: #fff; outline: none; resize: vertical;")}></textarea>
                        <div style={css('display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;')}>
                          <span style={css('font-size: 11.5px; color: #a3a09a;')}>Markdown — ## headings, - bullets, **bold**.</span>
                          <span style={css('display: flex; align-items: center; gap: 8px;')}>
                            <button type="button" onClick={p.cancelEdit} className={hv('border-color: #cbc6bd;')} style={css('padding: 9px 15px; background: #fff; border: 1px solid #e3e1dc; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 600; color: #4b4741; cursor: pointer;')}>Cancel</button>
                            <button type="button" onClick={p.saveEdit} className={hv('transform: translateY(-1px);')} style={css('padding: 9px 17px; background: linear-gradient(140deg, #ef7326, #d9541a); color: #fff; border: none; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 700; cursor: pointer; box-shadow: 0 6px 16px rgba(217,84,26,.22);')}>Save</button>
                          </span>
                        </div>
                      </div>
                    ) : (
                      <Markdown>{p.content}</Markdown>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div style={css(v.cardsWrapStyle)}>
            <div style={css('display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 380px), 1fr)); gap: 20px;')}>
              {v.cards.map((c, ci) => (
                <div key={ci} data-item-id={c.routeId} data-item-slug={c.routeSlug} style={css(c.cardStyle)} className={hv('box-shadow: 0 10px 30px rgba(20,18,16,.08);')}>
                  <div style={css(c.railStyle)}></div>

                  <div style={css('display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 18px; border-bottom: 1px solid #f1eee9; background: linear-gradient(180deg, #fcfbf9, #ffffff);')}>
                    <div style={css('display: flex; align-items: center; gap: 10px;')}>
                      <span style={css(c.indexStyle)}>{c.index}</span>
                      <span style={css('display: flex; flex-direction: column; gap: 2px;')}>
                        <span style={css('display: flex; align-items: center; gap: 7px;')}>
                          <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: .1em; color: #a3a09a;")}>{c.tag}</span>
                          <span style={css(c.versionStyle)}>{c.versionLabel}</span>
                        </span>
                        <span style={css(c.statusStyle)}>{c.statusLabel}</span>
                      </span>
                    </div>
                    <div style={css('display: flex; align-items: center; gap: 6px;')}>
                      {v.showAiEdit && v.aiEditOnTop && (
                        <button type="button" onClick={c.openAiEdit} title="AI Edit" className={hv('background: #efe7fb; border-color: #d6c7f2;')} style={css('display: flex; align-items: center; gap: 6px; padding: 7px 11px; background: #f6f2fd; border: 1px solid #e6dcf8; border-radius: 9px; font-family: inherit; font-size: 12px; font-weight: 600; color: #6a4bbd; cursor: pointer;')}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 3l1.7 4.6L18.5 9l-4.8 1.4L12 15l-1.7-4.6L5.5 9l4.8-1.4L12 3z"></path>
                            <path d="M18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8L18 16z"></path>
                          </svg>
                          <span data-lbl="ai">AI<span data-lbl="edit"> Edit</span></span>
                        </button>
                      )}
                      <button type="button" onClick={c.toggle} style={css(c.approveStyle)} title="Approve">✓</button>
                      {c.editing ? (
                        <>
                          <button type="button" onClick={c.cancelEdit} className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('display: flex; align-items: center; gap: 5px; padding: 7px 11px; background: #fff; border: 1px solid #e3e1dc; border-radius: 9px; font-family: inherit; font-size: 12px; font-weight: 600; color: #4b4741; cursor: pointer;')}>Cancel</button>
                          <button type="button" onClick={c.saveEdit} style={css(c.saveStyle)}>Save</button>
                        </>
                      ) : (
                        <button type="button" onClick={c.startEdit} className={hv('border-color: #cbc6bd; background: #faf9f6;')} style={css('display: flex; align-items: center; gap: 5px; padding: 7px 11px; background: #fff; border: 1px solid #e3e1dc; border-radius: 9px; font-family: inherit; font-size: 12px; font-weight: 600; color: #4b4741; cursor: pointer;')}>Edit</button>
                      )}
                      <button type="button" style={css(c.downloadStyle)} title="Download">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M12 4v11"></path>
                          <path d="M7 11l5 5 5-5"></path>
                          <path d="M5 19h14"></path>
                        </svg>
                      </button>
                    </div>
                  </div>

                  {c.showContent && c.editing && (
                    <div style={css('flex: 1; padding: 18px; display: flex; flex-direction: column; gap: 12px;')}>
                      <label style={css('display: flex; flex-direction: column; gap: 6px;')}>
                        <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>{c.titleLabel}</span>
                        <textarea value={v.cardDraftTitle} onChange={v.onCardTitle} rows="2" className={fc('border-color: #f2b98e;')} style={css('width: 100%; resize: vertical; padding: 10px 12px; border: 1px solid #e3e1dc; border-radius: 11px; font-family: inherit; font-size: 13px; line-height: 1.5; color: #16181c; background: #fff; outline: none;')}></textarea>
                      </label>
                      <label style={css('display: flex; flex-direction: column; gap: 6px; flex: 1; min-height: 0;')}>
                        <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>{c.captionLabel}</span>
                        <textarea value={v.cardDraftCaption} onChange={v.onCardCaption} className={fc('border-color: #f2b98e;')} style={css('width: 100%; flex: 1; min-height: 180px; resize: vertical; padding: 10px 12px; border: 1px solid #e3e1dc; border-radius: 11px; font-family: inherit; font-size: 13px; line-height: 1.6; color: #16181c; background: #fff; outline: none;')}></textarea>
                      </label>
                      <label style={css('display: flex; flex-direction: column; gap: 6px;')}>
                        <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>Hashtags</span>
                        <textarea value={v.cardDraftHashtags} onChange={v.onCardHashtags} rows="2" placeholder="#One #Two #Three" className={fc('border-color: #f2b98e;')} style={css("width: 100%; resize: vertical; padding: 10px 12px; border: 1px solid #e3e1dc; border-radius: 11px; font-family: 'IBM Plex Mono', monospace; font-size: 12px; line-height: 1.6; color: #16181c; background: #fff; outline: none;")}></textarea>
                      </label>
                    </div>
                  )}

                  {c.showContent && !c.editing && (
                    <div style={css('flex: 1; padding: 18px; display: flex; flex-direction: column; gap: 16px;')}>
                      <div style={css('display: flex; flex-direction: column; gap: 6px;')}>
                        <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>{c.titleLabel}</span>
                        <span style={css('font-size: 17px; font-weight: 700; line-height: 1.3; letter-spacing: -.015em; color: #16181c; text-wrap: pretty;')}>{c.title}</span>
                      </div>
                      <div style={css('display: flex; flex-direction: column; gap: 6px;')}>
                        <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>{c.captionLabel}</span>
                        <span style={css('font-size: 13.5px; line-height: 1.68; color: #58544e; white-space: pre-line; text-wrap: pretty;')}>{c.caption}</span>
                      </div>
                      <div style={css('display: flex; flex-direction: column; gap: 12px; font-size: 13.5px; line-height: 1.55; color: #58544e;')}>
                        <span style={css('display: flex; align-items: flex-start; gap: 9px;')}>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b7fbf" strokeWidth="1.8" strokeLinecap="round" style={css('flex: none; margin-top: 2px;')}>
                            <circle cx="12" cy="12" r="9"></circle>
                            <path d="M3 12h18"></path>
                            <path d="M12 3c2.6 2.4 4 5.6 4 9s-1.4 6.6-4 9c-2.6-2.4-4-5.6-4-9s1.4-6.6 4-9z"></path>
                          </svg>
                          <span style={css('word-break: break-word;')}>Find out more on our website! {c.siteUrl}</span>
                        </span>
                        <span style={css('display: flex; align-items: flex-start; gap: 9px;')}>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#d94f6e" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={css('flex: none; margin-top: 2px;')}>
                            <path d="M5 4h4l2 5-2.5 1.5a12 12 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1.1 1A16 16 0 0 1 4 5.1A1 1 0 0 1 5 4z"></path>
                          </svg>
                          <span>Give us a call: {c.tel}</span>
                        </span>
                        <span style={css('display: flex; align-items: flex-start; gap: 9px;')}>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4f6fb5" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={css('flex: none; margin-top: 2px;')}>
                            <rect x="3" y="5" width="18" height="14" rx="2.5"></rect>
                            <path d="M3.5 7.5l8.5 6 8.5-6"></path>
                          </svg>
                          <span style={css('word-break: break-word;')}>Or send us an email at {c.email}</span>
                        </span>
                      </div>
                      <div style={css('display: flex; flex-direction: column; gap: 8px;')}>
                        <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>Hashtags</span>
                        <div style={css('display: flex; flex-wrap: wrap; gap: 6px;')}>
                          {c.hashtags.map((h, hi) => (
                            <span key={hi} className={hv('border-color: #f0bd97; color: #cf5c17;')} style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11.5px; color: #4b4741; background: #f4f2ee; border: 1px solid #e8e5df; padding: 5px 9px; border-radius: 999px;")}>{h.text}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {c.showImage && (
                    <div style={css('flex: 1; display: flex; flex-direction: column;')}>
                      {c.hasImage && (
                        <div style={css(c.canvasStyle)}>
                          <span style={css("align-self: flex-start; font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: .08em; color: #6c6862; background: rgba(255,255,255,.9); padding: 4px 8px; border-radius: 6px;")}>{c.versionLabel}</span>
                          {c.isVideo && (
                            <button type="button" title="Play video" className={hv('background: rgba(20,18,16,.78);')} style={css('display: flex; align-items: center; justify-content: center; width: 62px; height: 62px; border-radius: 999px; border: none; background: rgba(20,18,16,.62); color: #fff; cursor: pointer; backdrop-filter: blur(2px);')}>
                              <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M8.5 6.2l10 5.8-10 5.8z"></path></svg>
                            </button>
                          )}
                          {c.isImageMedia && (
                            <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #6c6862; background: rgba(255,255,255,.9); padding: 6px 10px; border-radius: 7px;")}>{c.imageLabel}</span>
                          )}
                          <span style={css("align-self: flex-end; display: flex; align-items: center; gap: 7px; font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #8a857f; background: rgba(255,255,255,.82); padding: 4px 8px; border-radius: 6px;")}>
                            <span style={css(c.durationStyle)}>{c.duration}</span>{c.ratioLabel}
                          </span>
                        </div>
                      )}
                      {c.noImage && (
                        <div style={css('flex: 1; margin: 18px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; min-height: 240px; border: 1px dashed #ded9d1; border-radius: 16px; background: #faf9f6; padding: 24px; text-align: center;')}>
                          <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: .1em; color: #a3a09a;")}>{c.noMediaLabel}</span>
                          <span style={css('font-size: 13px; line-height: 1.55; color: #7a756e; max-width: 260px; text-wrap: pretty;')}>{c.imageLabel} hasn’t been generated for this {c.unitSingular}.</span>
                          <button type="button" onClick={c.generate} className={hv('transform: translateY(-1px);')} style={css('display: flex; align-items: center; gap: 8px; padding: 11px 17px; background: linear-gradient(140deg, #ef7326, #d9541a); color: #fff; border: none; border-radius: 11px; font-family: inherit; font-size: 13px; font-weight: 700; cursor: pointer; box-shadow: 0 6px 16px rgba(217,84,26,.24);')}>{c.generateMediaLabel}</button>
                        </div>
                      )}
                    </div>
                  )}

                  {c.showPreview && (
                    <div style={css('flex: 1; display: flex; flex-direction: column;')}>
                      {c.hasImage && (
                        <div style={css(c.mosaicStyle)}>
                          <div style={css(c.heroStyle)}>
                            {c.isVideo && (
                              <button type="button" title="Play video" className={hv('background: rgba(20,18,16,.78);')} style={css('display: flex; align-items: center; justify-content: center; width: 54px; height: 54px; border-radius: 999px; border: none; background: rgba(20,18,16,.62); color: #fff; cursor: pointer;')}>
                                <svg width="21" height="21" viewBox="0 0 24 24" fill="currentColor"><path d="M8.5 6.2l10 5.8-10 5.8z"></path></svg>
                              </button>
                            )}
                            {c.isImageMedia && (
                              <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; color: #6c6862; background: rgba(255,255,255,.86); padding: 4px 8px; border-radius: 6px;")}>{c.imageLabel}</span>
                            )}
                          </div>
                          <div style={css('display: grid; gap: 3px;')}>
                            {c.sideThumbs.map((th, thi) => (
                              <div key={thi} style={css(th.style)}></div>
                            ))}
                          </div>
                        </div>
                      )}
                      {c.noImage && (
                        <div style={css('margin: 18px 18px 0; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border: 1px dashed #ded9d1; border-radius: 14px; background: #faf9f6;')}>
                          <span style={css('font-size: 12.5px; color: #7a756e;')}>{c.textOnlyLabel}</span>
                          <button type="button" onClick={c.generate} className={hv('background: #ffeadb;')} style={css('padding: 8px 13px; background: #fff4ec; border: 1px solid #fadfc9; border-radius: 10px; font-family: inherit; font-size: 12px; font-weight: 700; color: #cf5c17; cursor: pointer;')}>✦ Generate</button>
                        </div>
                      )}
                      <div style={css('flex: 1; padding: 16px 18px 18px; display: flex; flex-direction: column; gap: 10px;')}>
                        <div style={css('font-size: 16px; font-weight: 700; line-height: 1.32; letter-spacing: -.012em; text-wrap: pretty;')}>{c.title}</div>
                        <div style={css('font-size: 13px; line-height: 1.65; color: #5b5750; white-space: pre-line; text-wrap: pretty;')}>{c.previewCaption}</div>
                        <div style={css('display: flex; flex-direction: column; gap: 9px; font-size: 12.5px; line-height: 1.5; color: #5b5750;')}>
                          <span style={css('display: flex; align-items: flex-start; gap: 8px;')}>
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#3b7fbf" strokeWidth="1.8" strokeLinecap="round" style={css('flex: none; margin-top: 2px;')}>
                              <circle cx="12" cy="12" r="9"></circle>
                              <path d="M3 12h18"></path>
                              <path d="M12 3c2.6 2.4 4 5.6 4 9s-1.4 6.6-4 9c-2.6-2.4-4-5.6-4-9s1.4-6.6 4-9z"></path>
                            </svg>
                            <span style={css('word-break: break-word;')}>Find out more on our website! {c.siteUrl}</span>
                          </span>
                          <span style={css('display: flex; align-items: flex-start; gap: 8px;')}>
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#d94f6e" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={css('flex: none; margin-top: 2px;')}>
                              <path d="M5 4h4l2 5-2.5 1.5a12 12 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1.1 1A16 16 0 0 1 4 5.1A1 1 0 0 1 5 4z"></path>
                            </svg>
                            <span>Give us a call: {c.tel}</span>
                          </span>
                          <span style={css('display: flex; align-items: flex-start; gap: 8px;')}>
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#4f6fb5" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={css('flex: none; margin-top: 2px;')}>
                              <rect x="3" y="5" width="18" height="14" rx="2.5"></rect>
                              <path d="M3.5 7.5l8.5 6 8.5-6"></path>
                            </svg>
                            <span style={css('word-break: break-word;')}>Or send us an email at {c.email}</span>
                          </span>
                        </div>
                        <div style={css('font-size: 12.5px; line-height: 1.7; color: #cf5c17; font-weight: 600; word-break: break-word;')}>{c.hashLine}</div>
                      </div>
                    </div>
                  )}

                  <div style={css('display: flex; align-items: center; gap: 8px; padding: 14px 18px; border-top: 1px solid #f1eee9; background: #fcfbf9;')}>
                    <div style={css(c.actionsStyle)}>
                      {v.showAiEdit && !v.aiEditOnTop && (
                        <button type="button" onClick={c.openAiEdit} title="AI Edit" className={hv('background: #efe7fb; border-color: #d6c7f2;')} style={css('flex: 1; display: flex; align-items: center; justify-content: center; gap: 7px; padding: 10px; background: #f6f2fd; border: 1px solid #e6dcf8; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 600; color: #6a4bbd; cursor: pointer;')}>
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 3l1.7 4.6L18.5 9l-4.8 1.4L12 15l-1.7-4.6L5.5 9l4.8-1.4L12 3z"></path>
                            <path d="M18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8L18 16z"></path>
                          </svg>
                          <span data-lbl="ai">AI<span data-lbl="edit"> Edit</span></span>
                        </button>
                      )}
                      <button type="button" data-regenbtn="1" title="Regenerate" className={hv('background: #ffeadb; border-color: #f6cca9;')} style={css('flex: 1; display: flex; align-items: center; justify-content: center; gap: 7px; padding: 10px; background: #fff4ec; border: 1px solid #fadfc9; border-radius: 10px; font-family: inherit; font-size: 12.5px; font-weight: 600; color: #cf5c17; cursor: pointer;')}>
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1"></path>
                          <path d="M21 4v4h-4"></path>
                        </svg>
                        <span data-lbl="regen">Regenerate</span>
                      </button>
                    </div>
                    <div style={css(c.iconGroupStyle)}>
                      <button type="button" onClick={c.viewContent} title="Content" style={css(c.contentBtnStyle)} className={hv('border-color: #cbc6bd;')}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M6 3h9l4 4v14H6z"></path>
                          <path d="M15 3v4h4"></path>
                          <path d="M9 12h7"></path>
                          <path d="M9 16h7"></path>
                        </svg>
                      </button>
                      <button type="button" onClick={c.viewImage} title={c.mediaTitle} style={css(c.imageBtnStyle)} className={hv('border-color: #cbc6bd;')}>
                        {c.isVideo && (
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="2.5" y="6" width="13" height="12" rx="3"></rect>
                            <path d="M15.5 11l6-3.2v8.4l-6-3.2z"></path>
                          </svg>
                        )}
                        {c.isImageMedia && (
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="3" y="4" width="18" height="16" rx="3"></rect>
                            <circle cx="8.5" cy="9.5" r="1.6"></circle>
                            <path d="M4 17l5-5 4 4 3-2.5 4 3.5"></path>
                          </svg>
                        )}
                      </button>
                      <button type="button" onClick={c.viewPreview} title="Preview" style={css(c.previewBtnStyle)} className={hv('border-color: #cbc6bd;')}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6z"></path>
                          <circle cx="12" cy="12" r="2.6"></circle>
                        </svg>
                      </button>
                      <div style={css(c.dividerStyle)}></div>
                      <button type="button" onClick={c.openVersions} title="Version history" style={css(c.historyBtnStyle)} className={hv('border-color: #cbc6bd; background: #faf9f6;')}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"></path>
                          <path d="M3 4v4h4"></path>
                          <path d="M12 8v4.5l3 2"></path>
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {v.aiEditOpen && (
          <div onClick={v.closeAiEdit} style={css('position: fixed; inset: 0; background: rgba(18,16,14,.44); backdrop-filter: blur(3px); display: flex; align-items: center; justify-content: center; padding: clamp(0px, calc(6vw - 34px), 40px) clamp(0px, calc(6vw - 34px), 20px); z-index: 60;')}>
            <div onClick={v.stop} data-aiedit="1" style={css('width: min(100%, 1180px); height: min(100%, 760px); display: flex; background: #fff; border-radius: clamp(0px, calc(6vw - 34px), 20px); box-shadow: 0 30px 70px rgba(20,18,16,.3); overflow: hidden; animation: dcPop .18s ease both;')}>

              <div data-aichat="1" style={css('flex: 1 1 420px; max-width: 460px; min-width: 0; display: flex; flex-direction: column; border-right: 1px solid #efece7; background: #fff;')}>
                <div style={css('display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 16px 18px; border-bottom: 1px solid #efece7; background: linear-gradient(180deg, #fcfbf9, #ffffff);')}>
                  <div style={css('display: flex; align-items: center; gap: 11px; min-width: 0;')}>
                    <span style={css('width: 34px; height: 34px; border-radius: 10px; flex: none; display: flex; align-items: center; justify-content: center; background: #f6f2fd; border: 1px solid #e6dcf8; color: #6a4bbd;')}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 3l1.7 4.6L18.5 9l-4.8 1.4L12 15l-1.7-4.6L5.5 9l4.8-1.4L12 3z"></path>
                        <path d="M18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8L18 16z"></path>
                      </svg>
                    </span>
                    <span style={css('display: flex; flex-direction: column; gap: 2px; min-width: 0;')}>
                      <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; letter-spacing: .1em; color: #a3a09a;")}>{v.aiEditTag}</span>
                      <span style={css('font-size: 14px; font-weight: 700; letter-spacing: -.01em; color: #16181c; line-height: 1.35; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;')}>{v.aiEditTitle}</span>
                    </span>
                  </div>
                  <button type="button" onClick={v.closeAiEdit} className={hv('background: #eae7e1; color: #16181c;')} style={css("padding: 5px 9px; background: #f4f2ee; border: none; border-radius: 7px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #8a857f; cursor: pointer; flex: none;")}>ESC</button>
                </div>

                <div ref={v.aiScrollRef} data-aimsgs="1" style={css('flex: 1; min-height: 0; overflow: auto; padding: 16px 18px; display: flex; flex-direction: column; gap: 14px; background: #faf9f6;')}>
                  {v.aiNoMessages && (
                    <span style={css('font-size: 13px; line-height: 1.6; color: #8a857f;')}>No messages yet. Tell the AI what to change about this post.</span>
                  )}
                  {v.aiMessages.map((m, mi) => (
                    <div key={mi} style={css(m.rowStyle)}>
                      <div style={css(m.bubbleStyle)}>
                        {m.headline && <p style={css(m.headlineStyle)}>{m.headline}</p>}
                        <span style={css('white-space: pre-line;')}>{m.body}</span>
                      </div>
                      {m.hasDraft && (
                        <button type="button" onClick={m.use} style={css(m.useStyle)}>✓ {m.useLabel}</button>
                      )}
                    </div>
                  ))}
                </div>

                <div style={css('display: flex; align-items: center; gap: 8px; padding: 14px 18px; border-top: 1px solid #efece7; background: #fff;')}>
                  <div style={css('display: flex; align-items: center; gap: 4px; flex: 1; min-width: 0; padding-right: 5px; border: 1px solid #e3e1dc; border-radius: 11px; background: #fff;')}>
                    <textarea value={v.aiInput} onChange={v.onAiInput} onKeyDown={v.aiInputKey} rows="1" placeholder="e.g. Make this shorter and more urgent" style={css('flex: 1; min-width: 0; resize: none; border: none; outline: none; background: transparent; padding: 11px 13px; font-family: inherit; font-size: 13px; line-height: 1.5; color: #16181c;')}></textarea>
                    <div style={css('position: relative; flex: none;')}>
                      <button type="button" onClick={v.toggleEmoji} title="Add an emoji" aria-label="Add an emoji" className={hv('background: #f4f2ee;')} style={css('display: flex; align-items: center; justify-content: center; width: 30px; height: 30px; border: none; border-radius: 999px; background: transparent; font-size: 15px; cursor: pointer;')}>☺</button>
                      {v.emojiOpen && (
                        <>
                          <div onClick={v.closeEmoji} style={css('position: fixed; inset: 0; z-index: 19;')}></div>
                          <div style={css('position: absolute; bottom: 100%; right: 0; z-index: 20; margin-bottom: 8px; width: 268px; max-height: 210px; overflow: auto; padding: 8px; background: #fff; border: 1px solid #e6e4de; border-radius: 14px; box-shadow: 0 22px 44px rgba(20,18,16,.18); display: grid; grid-template-columns: repeat(10, 1fr); gap: 2px; animation: dcPop .14s ease both;')}>
                            {v.emojis.map((e, ei) => (
                              <button key={ei} type="button" onClick={e.pick} className={hv('background: #f4f2ee;')} style={css('display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; padding: 0; border: none; border-radius: 6px; background: transparent; font-size: 14px; cursor: pointer;')}>{e.char}</button>
                            ))}
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                  <button type="button" onClick={v.sendAi} style={css(v.aiSendStyle)}>{v.aiSending ? 'Sending…' : 'Send'}</button>
                </div>
              </div>

              <div data-aipreview="1" style={css('flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; background: #faf9f6;')}>
                <div style={css('display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px clamp(14px, 2.4vw, 22px); border-bottom: 1px solid #efece7; background: #fff;')}>
                  <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>Current version</span>
                  <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; padding: 2px 7px; border-radius: 6px; background: #fff4ec; color: #a8410a;")}>{v.aiDirty ? 'edited' : 'unchanged'}</span>
                </div>

                <div style={css('flex: 1; min-height: 0; overflow: auto; padding: clamp(14px, 2.4vw, 22px);')}>
                  <div style={css('display: flex; flex-direction: column; gap: 16px; padding: 20px; background: #fff; border: 1px solid #e6e4de; border-radius: 18px; box-shadow: 0 2px 6px rgba(20,18,16,.04);')}>
                    <div style={css('display: flex; flex-direction: column; gap: 6px;')}>
                      <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>{v.aiTitleLabel}</span>
                      <span style={css('font-size: 17px; font-weight: 700; line-height: 1.3; letter-spacing: -.015em; color: #16181c; text-wrap: pretty;')}>{v.aiDraftTitle}</span>
                    </div>
                    <div style={css('display: flex; flex-direction: column; gap: 6px;')}>
                      <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>{v.aiCaptionLabel}</span>
                      <span style={css('font-size: 13.5px; line-height: 1.68; color: #58544e; white-space: pre-line; text-wrap: pretty;')}>{v.aiDraftCaption}</span>
                    </div>
                    <div style={css('display: flex; flex-direction: column; gap: 12px; font-size: 13.5px; line-height: 1.55; color: #58544e;')}>
                      <span style={css('display: flex; align-items: flex-start; gap: 9px;')}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b7fbf" strokeWidth="1.8" strokeLinecap="round" style={css('flex: none; margin-top: 2px;')}>
                          <circle cx="12" cy="12" r="9"></circle>
                          <path d="M3 12h18"></path>
                          <path d="M12 3c2.6 2.4 4 5.6 4 9s-1.4 6.6-4 9c-2.6-2.4-4-5.6-4-9s1.4-6.6 4-9z"></path>
                        </svg>
                        <span style={css('word-break: break-word;')}>Find out more on our website! {v.aiSiteUrl}</span>
                      </span>
                      <span style={css('display: flex; align-items: flex-start; gap: 9px;')}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#d94f6e" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={css('flex: none; margin-top: 2px;')}>
                          <path d="M5 4h4l2 5-2.5 1.5a12 12 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1.1 1A16 16 0 0 1 4 5.1A1 1 0 0 1 5 4z"></path>
                        </svg>
                        <span>Give us a call: {v.aiTel}</span>
                      </span>
                      <span style={css('display: flex; align-items: flex-start; gap: 9px;')}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4f6fb5" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={css('flex: none; margin-top: 2px;')}>
                          <rect x="3" y="5" width="18" height="14" rx="2.5"></rect>
                          <path d="M3.5 7.5l8.5 6 8.5-6"></path>
                        </svg>
                        <span style={css('word-break: break-word;')}>Or send us an email at {v.aiEmail}</span>
                      </span>
                    </div>
                    <div style={css('display: flex; flex-direction: column; gap: 8px;')}>
                      <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 9.5px; letter-spacing: .13em; text-transform: uppercase; color: #a3a09a;")}>Hashtags</span>
                      <div style={css('display: flex; flex-wrap: wrap; gap: 6px;')}>
                        {v.aiDraftHashtags.map((h, hi) => (
                          <span key={hi} style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11.5px; color: #4b4741; background: #f4f2ee; border: 1px solid #e8e5df; padding: 5px 9px; border-radius: 999px;")}>{h.text}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div style={css('display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px clamp(14px, 2.4vw, 22px); border-top: 1px solid #efece7; background: #fff; flex-wrap: wrap;')}>
                  <span style={css('font-size: 12px; color: #8a857f;')}>Changes apply to this card only.</span>
                  <div data-formactions="1" style={css('display: flex; align-items: center; gap: 8px; flex: 1 1 260px; flex-wrap: wrap;')}>
                    <button type="button" onClick={v.closeAiEdit} className={hv('border-color: #cbc6bd;')} style={css('flex: 1 1 auto; text-align: center; white-space: nowrap; padding: 11px 16px; background: #fff; border: 1px solid #e3e1dc; border-radius: 11px; font-family: inherit; font-size: 13px; font-weight: 600; color: #4b4741; cursor: pointer;')}>Cancel</button>
                    <button type="button" onClick={v.applyAiEdit} style={css(v.aiApplyStyle)}>Apply changes</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {v.cardHistoryOpen && (
          <div onClick={v.closeCardHistory} style={css('position: fixed; inset: 0; background: rgba(18,16,14,.4); backdrop-filter: blur(3px); display: flex; align-items: center; justify-content: center; padding: 40px 20px; z-index: 60;')}>
            <div onClick={v.stop} style={css('width: 100%; max-width: 400px; background: #fff; border-radius: 18px; box-shadow: 0 30px 70px rgba(20,18,16,.3); overflow: hidden; animation: dcPop .18s ease both;')}>
              <div style={css('display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 16px 18px; border-bottom: 1px solid #efece7;')}>
                <div style={css('display: flex; flex-direction: column; gap: 3px; min-width: 0;')}>
                  <div style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; letter-spacing: .1em; color: #a3a09a;")}>{v.cardHistoryTag}</div>
                  <div style={css('font-size: 14px; font-weight: 700; letter-spacing: -.01em; color: #16181c; line-height: 1.35; text-wrap: pretty;')}>{v.cardHistoryTitle}</div>
                </div>
                <button type="button" onClick={v.closeCardHistory} style={css("padding: 5px 9px; background: #f4f2ee; border: none; border-radius: 7px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #8a857f; cursor: pointer; flex: none;")}>ESC</button>
              </div>
              <div style={css('max-height: 380px; overflow: auto; padding: 10px; display: flex; flex-direction: column; gap: 8px;')}>
                {v.cardVersions.map((ver, vi) => (
                  <div key={vi} onClick={ver.select} style={css(ver.style)} className={hv('border-color: #cbc6bd;')}>
                    <span style={css(ver.thumbStyle)}>{ver.thumbLabel}</span>
                    <span style={css('display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 0; text-align: left;')}>
                      <span style={css('display: flex; align-items: center; gap: 6px; flex-wrap: wrap;')}>
                        <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 500; color: #16181c;")}>{ver.version}</span>
                        <span style={css(ver.currentStyle)}>Current</span>
                        <span style={css(ver.activeStyle)}>Active</span>
                      </span>
                      <span style={css('font-size: 12px; color: #7a756e; line-height: 1.45; display: block; overflow: hidden; text-overflow: ellipsis;')}>{ver.snippet}</span>
                      <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #a3a09a;")}>{ver.meta}</span>
                    </span>
                    <button type="button" onClick={ver.restore} style={css(ver.restoreStyle)} className={hv('border-color: #f6cca9; color: #cf5c17;')}>Restore</button>
                  </div>
                ))}
              </div>
              <div style={css('padding: 12px 18px; border-top: 1px solid #efece7; background: #faf9f6; font-size: 11.5px; color: #8a857f;')}>Click a version to make it active on the card. Restore makes it the current version.</div>
            </div>
          </div>
        )}

        {v.historyOpen && (
          <div onClick={v.closeHistory} style={css('position: fixed; inset: 0; background: rgba(18,16,14,.44); backdrop-filter: blur(3px); display: flex; align-items: stretch; justify-content: flex-end; z-index: 50;')}>
            <div onClick={v.stop} style={css('width: 100%; max-width: 420px; background: #fff; box-shadow: -20px 0 60px rgba(20,18,16,.24); display: flex; flex-direction: column; animation: dcPop .2s ease both;')}>
              <div style={css('display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 20px 22px; border-bottom: 1px solid #efece7;')}>
                <div style={css('display: flex; flex-direction: column; gap: 4px;')}>
                  <div style={css('font-size: 16px; font-weight: 800; letter-spacing: -.015em; color: #0f2f2b;')}>Run history</div>
                  <div style={css('font-size: 12px; color: #8a857f;')}>{v.historySubtitle}</div>
                </div>
                <button type="button" onClick={v.closeHistory} style={css("padding: 6px 10px; background: #f4f2ee; border: none; border-radius: 8px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #8a857f; cursor: pointer;")}>ESC</button>
              </div>
              <div style={css('flex: 1; min-height: 0; overflow: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px;')}>
                {v.runs.map((r, ri) => (
                  <button key={ri} type="button" onClick={r.select} style={css(r.style)} className={hv('border-color: #cbc6bd;')}>
                    <span style={css('display: flex; align-items: center; justify-content: space-between; gap: 10px;')}>
                      <span style={css('display: flex; align-items: center; gap: 9px;')}>
                        <span style={css(r.dotStyle)}></span>
                        <span style={css('font-size: 13.5px; font-weight: 700; color: #16181c;')}>{r.date}</span>
                        <span style={css(r.tagStyle)}>{r.tag}</span>
                      </span>
                      <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; color: #a3a09a;")}>{r.version}</span>
                    </span>
                    <span style={css('font-size: 12px; color: #7a756e; text-align: left; line-height: 1.5;')}>{r.summary}</span>
                    <span style={css('display: flex; align-items: center; gap: 8px;')}>
                      <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; color: #8a857f; background: #f7f5f1; border: 1px solid #eeebe5; padding: 3px 7px; border-radius: 6px;")}>{r.approved}</span>
                      <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; color: #8a857f; background: #f7f5f1; border: 1px solid #eeebe5; padding: 3px 7px; border-radius: 6px;")}>{r.author}</span>
                    </span>
                  </button>
                ))}
              </div>
              <div style={css('padding: 14px 20px; border-top: 1px solid #efece7; background: #faf9f6; font-size: 12px; color: #8a857f;')}>Selecting a run loads that version of the content into the tabs.</div>
            </div>
          </div>
        )}

        {v.modalOpen && (
          <div onClick={v.closeModal} style={css('position: fixed; inset: 0; background: rgba(18,16,14,.44); backdrop-filter: blur(3px); display: flex; align-items: stretch; justify-content: center; padding: clamp(0px, calc(6vw - 34px), 56px) clamp(0px, calc(6vw - 34px), 20px); z-index: 50;')}>
            <div onClick={v.stop} style={css('width: min(100%, 520px); height: 100%; display: flex; flex-direction: column; background: #fff; border-radius: clamp(0px, calc(6vw - 34px), 18px); box-shadow: 0 30px 70px rgba(20,18,16,.3); overflow: hidden; animation: dcPop .18s ease both;')}>
              <div style={css('display: flex; align-items: center; gap: 10px; padding: 16px 18px; border-bottom: 1px solid #efece7;')}>
                <span style={css('color: #a3a09a; font-size: 15px;')}>⌕</span>
                <input ref={v.searchRef} value={v.query} onChange={v.onQuery} placeholder="Search clients…" style={css('flex: 1; border: none; outline: none; font-family: inherit; font-size: 15px; color: #16181c; background: transparent;')} />
                <button type="button" onClick={v.closeModal} title="Close" aria-label="Close" className={hv('background: #eae7e1; color: #16181c;')} style={css('display: flex; align-items: center; justify-content: center; width: 34px; height: 34px; flex: none; background: #f4f2ee; border: none; border-radius: 10px; color: #6c6862; cursor: pointer;')}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M6 6l12 12"></path><path d="M18 6L6 18"></path>
                  </svg>
                </button>
              </div>
              <div style={css('display: flex; align-items: center; gap: 6px; padding: 10px 18px; border-bottom: 1px solid #efece7;')}>
                {v.clientTabs.map((t, ti) => (
                  <button key={ti} type="button" onClick={t.select} style={css(t.style)}>
                    {t.label}
                    <span style={css(t.countStyle)}>{t.count}</span>
                  </button>
                ))}
              </div>
              <div style={css('flex: 1; min-height: 0; overflow: auto; padding: 8px;')}>
                {v.filteredClients.map((c, ci) => (
                  <button key={ci} type="button" onClick={c.select} style={css(c.style)} className={hv('background: #faf8f5;')}>
                    <span style={css(c.avatarStyle)}>{c.initials}</span>
                    <span style={css('display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; text-align: left;')}>
                      <span style={css('font-size: 14px; font-weight: 600;')}>{c.name}</span>
                      <span style={css('font-size: 12px; color: #8a857f;')}>{c.meta}</span>
                    </span>
                    {c.ago && (
                      <span style={css("font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; color: #a3a09a; flex: none; white-space: nowrap;")}>{c.ago}</span>
                    )}
                    <span style={css(c.checkStyle)}>✓</span>
                  </button>
                ))}
                {v.noResults && (
                  <div style={css('padding: 32px 12px; text-align: center; font-size: 13.5px; color: #8a857f;')}>No clients match that search.</div>
                )}
              </div>
              <div style={css('display: flex; align-items: center; justify-content: flex-end; gap: 12px; padding: 12px 18px; border-top: 1px solid #efece7; background: #faf9f6; font-size: 12px; color: #8a857f;')}>
                <span style={css("font-family: 'IBM Plex Mono', monospace;")}>{v.clientCountLabel}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }
}
