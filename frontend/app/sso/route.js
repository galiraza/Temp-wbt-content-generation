import { NextResponse } from 'next/server';
import {
  SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS,
  createSessionCookieValue, sessionCookieOptions, verifyAndConsumeTicket,
} from '@/lib/session';

// GET /sso?t=<ticket> — the landing point for the redirect from Command HQ.
// Spends the one-time ticket and, if valid, starts a local session. Everything
// else (proxy.js) requires that session.
export const dynamic = 'force-dynamic';

// Do not resolve paths against request.url: behind a reverse proxy the request
// arrives with an internal container hostname, and that is what the browser
// would be sent to next.
function resolveUrl(path, request) {
  const siteUrl = process.env.NEXT_PUBLIC_APP_URL?.trim().replace(/\/+$/, '');
  return siteUrl ? `${siteUrl}${path}` : new URL(path, request.url).toString();
}

export async function GET(request) {
  const ticket = new URL(request.url).searchParams.get('t');
  const payload = verifyAndConsumeTicket(ticket);

  if (!payload) {
    return NextResponse.redirect(resolveUrl('/denied', request), 303);
  }

  const response = NextResponse.redirect(resolveUrl('/', request), 303);
  response.cookies.set(
    SESSION_COOKIE_NAME,
    createSessionCookieValue({ sub: payload.sub, name: payload.name, email: payload.email }),
    { ...sessionCookieOptions, maxAge: SESSION_MAX_AGE_SECONDS },
  );
  return response;
}
