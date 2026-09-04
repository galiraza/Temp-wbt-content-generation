import { NextResponse } from 'next/server';
import { SESSION_COOKIE_NAME, sessionCookieOptions } from '@/lib/session';

// POST /api/logout — clears the session. The old frontend had no way out
// short of waiting four hours for the cookie to expire; this is the one
// addition to its auth flow.
export const dynamic = 'force-dynamic';

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE_NAME, '', { ...sessionCookieOptions, maxAge: 0 });
  return response;
}
