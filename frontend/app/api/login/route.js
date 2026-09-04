import { NextResponse } from 'next/server';
import {
  SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS,
  checkAdminCredentials, createSessionCookieValue, sessionCookieOptions,
} from '@/lib/session';

// POST /api/login — the direct-login fallback for opening this app without
// going through Command HQ. Same session and cookie as the SSO path, started a
// different way.
export const dynamic = 'force-dynamic';

export async function POST(request) {
  const body = await request.json().catch(() => null);
  const email = typeof body?.email === 'string' ? body.email : '';
  const password = typeof body?.password === 'string' ? body.password : '';

  const session = checkAdminCredentials(email, password);
  if (!session) {
    return NextResponse.json({ error: 'invalid_credentials' }, { status: 401 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE_NAME, createSessionCookieValue(session), {
    ...sessionCookieOptions,
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
  return response;
}
