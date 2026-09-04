'use server';

import { revalidatePath } from 'next/cache';
import { createRun, toApiContentType } from '@/lib/api';

/**
 * Kick off a generation run from a form.
 *
 * Returns a plain result rather than throwing, so the form can show what went
 * wrong in place instead of the page collapsing into an error boundary.
 */
export async function requestRun({ clientId, section, values, period }) {
  try {
    const run = await createRun(clientId, {
      contentType: toApiContentType(section),
      source: values || {},
      period,
      requestedBy: 'content-hub',
    });
    // The run is queued, not done: revalidating brings back the panel with the
    // new run in its history and its assets appearing as they land.
    revalidatePath('/content', 'layout');
    return { ok: true, runId: run.run_id, version: run.version, status: run.status };
  } catch (err) {
    return { ok: false, error: err.message || 'Could not start the run.' };
  }
}
