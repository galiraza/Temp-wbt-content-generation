'use client';

// Binds ContentGeneration's state to the URL in both directions:
//   - clicking a client / section / sub-tab / run / view pushes a new path
//   - back, forward, or a pasted deep link pulls that path back into state
//
// It renders nothing of its own, so the page looks exactly as the design does.

import { useCallback, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import ContentGeneration from '@/components/ContentGeneration';
import { contentPath, showsViews } from '@/lib/routes';
import { requestRun } from '@/app/actions';
import { BLOG_VIEWS, DEFAULT_VIEWS, VIEW_SETS } from '@/lib/ui';

const VIEW_OPTS = { viewSets: VIEW_SETS, blogViews: BLOG_VIEWS, defaultViews: DEFAULT_VIEWS };

export default function ContentRoute({ route, routeKey, directory, data }) {
  const router = useRouter();

  // The server hands the slug maps over as arrays, because a Map does not
  // survive the boundary. Rebuild them once rather than on every path build.
  const dir = useMemo(() => ({
    clients: directory.clients,
    sections: directory.sections,
    runs: directory.runs,
    clientSlugs: new Map(directory.clientSlugs),
    runSlugs: new Map(directory.runSlugs),
    clientBySlug: new Map(directory.clientSlugs.map(([id, s]) => [s, id])),
    runBySlug: new Map(directory.runSlugs.map(([id, s]) => [s, id])),
  }), [directory]);

  // `routeKey` is the canonical path currently in the address bar, compared
  // directly rather than cached in a ref: the class's componentDidUpdate runs
  // during commit, before any useEffect, so a ref updated in an effect would
  // still hold the previous path on a Back navigation and push it straight back.
  const onRouteChange = useCallback((next) => {
    const path = contentPath(dir, next, VIEW_OPTS);
    if (path === routeKey) return;

    // A view toggle is a filter, not a place: replace it so Back leaves the
    // section instead of stepping through the views.
    const samePlace = routeKey.split('?')[0] === path.split('?')[0];
    if (samePlace) router.replace(path, { scroll: false });
    else router.push(path, { scroll: false });
  }, [router, routeKey, dir]);

  // Deep link to a single item: bring that card into view. There is no detail
  // screen, so this scrolls and does nothing else.
  const { itemId, itemSlug } = route;
  useEffect(() => {
    if (!itemId && !itemSlug) return;
    const sel = itemSlug
      ? `[data-item-slug="${CSS.escape(itemSlug)}"]`
      : `[data-item-id="${CSS.escape(itemId)}"]`;
    const raf = requestAnimationFrame(() => {
      const el = document.querySelector(sel);
      if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });
    return () => cancelAnimationFrame(raf);
  }, [itemId, itemSlug, routeKey]);

  // The run is queued, not finished: refresh so the panel picks up the new run
  // and its assets as the agents land them.
  const onRequestRun = useCallback(async (payload) => {
    const result = await requestRun(payload);
    if (result.ok) router.refresh();
    return result;
  }, [router]);

  return (
    <ContentGeneration
      onRequestRun={onRequestRun}
      route={route}
      routeKey={routeKey}
      routeOwnsView={showsViews(dir, route.section)}
      onRouteChange={onRouteChange}
      data={data}
      defaultSection={route.section}
      defaultView={route.view}
      showCounts
    />
  );
}
