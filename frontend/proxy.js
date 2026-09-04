import { NextResponse } from 'next/server';
import { readSessionCookieValue, SESSION_COOKIE_NAME } from '@/lib/session';

// Gates every page behind a session, started either via /sso (the Command HQ
// handoff) or /login (direct email/password). Anyone without a valid session
// lands on /login — /denied is reserved for a ticket that is actually
// invalid, expired or reused, not for "never signed in at all".
export function proxy(request) {
  const session = readSessionCookieValue(request.cookies.get(SESSION_COOKIE_NAME)?.value);
  if (!session) {
    // Do not resolve "/login" against request.url: behind a reverse proxy the
    // request arrives with an internal container hostname, and that is what the
    // browser would be sent to next. Use the app's own public URL instead.
    const siteUrl = process.env.NEXT_PUBLIC_APP_URL?.trim().replace(/\/+$/, '');
    const loginUrl = siteUrl ? `${siteUrl}/login` : new URL('/login', request.url);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}

export const config = {
  /*
   * Every route except:
   * - /sso        where an SSO ticket is exchanged for a session
   * - /login      the direct-login form
   * - /api/login  what that form posts to
   * - /denied     the rejection page — avoid a redirect loop
   * - static assets
   */
  matcher: ['/((?!sso|login|api/login|denied|_next/static|_next/image|favicon.ico).*)'],
};
