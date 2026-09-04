import 'server-only';
import { createHmac, timingSafeEqual } from 'crypto';

// ── Getting in: two doors, one session ──────────────────────────────────────
// 1. SSO handoff from Command HQ — a one-time ticket minted at Command HQ's
//    /api/meta-ads/launch and spent here at /sso. No password involved.
// 2. Direct login at /login — a single shared admin email/password (env vars),
//    for opening this app straight instead of going through Command HQ.
// Either path ends the same way: a signed session cookie, checked by proxy.js
// on every other route.
//
//   ticket  = signed, single-use, 60s, lives only in the redirect URL
//   session = this app's own cookie, created after ticket verify OR password login
//
// Ported from the old frontend's lib/meta-ads-sso.ts. The ticket format, the
// secret's env name and the cookie name are all kept BYTE-IDENTICAL on purpose:
// Command HQ mints the tickets, so changing any of them would break the handoff.
//
// The token is `base64url(json).base64url(hmac-sha256)` — a JWT in shape, minus
// the header segment, since both ends agree on the algorithm.

const SESSION_COOKIE = 'meta_ads_session';
const SESSION_TTL_SECONDS = 60 * 60 * 4; // 4 hours

function secret() {
  return process.env.META_ADS_SHARED_SECRET?.trim() ?? '';
}

// In-memory single-use tracking, keyed by ticket jti with its expiry so old
// entries can be pruned. Fine for a single-process deployment; a multi-instance
// one should swap this for Redis (SETNX with a TTL matching the ticket
// lifetime) so replay-protection holds across instances too.
const usedJtis = new Map();

function pruneUsed() {
  const now = Date.now();
  for (const [jti, exp] of usedJtis) {
    if (exp < now) usedJtis.delete(jti);
  }
}

/** Constant-time string compare that does not leak the expected length. */
function safeEqualString(a, b) {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  // Pad to equal length before comparing so timingSafeEqual does not throw on a
  // length mismatch — that throw would itself leak the expected length.
  const len = Math.max(bufA.length, bufB.length, 1);
  const paddedA = Buffer.alloc(len);
  const paddedB = Buffer.alloc(len);
  bufA.copy(paddedA);
  bufB.copy(paddedB);
  return bufA.length === bufB.length && timingSafeEqual(paddedA, paddedB);
}

function signatureMatches(body, sig, key) {
  const expected = createHmac('sha256', key).update(body).digest('base64url');
  const a = Buffer.from(sig);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

/**
 * Verify a ticket's signature and expiry, and enforce single use.
 * Returns the payload, or null if it is missing, malformed, expired, tampered
 * with, or already spent.
 */
export function verifyAndConsumeTicket(ticket) {
  if (!ticket) return null;
  const s = secret();
  if (!s) return null;

  const [body, sig] = ticket.split('.');
  if (!body || !sig) return null;
  if (!signatureMatches(body, sig, s)) return null;

  let payload;
  try {
    payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'));
  } catch {
    return null;
  }
  if (typeof payload.exp !== 'number' || Date.now() > payload.exp) return null;
  if (!payload.jti) return null;

  pruneUsed();
  if (usedJtis.has(payload.jti)) return null; // replay
  usedJtis.set(payload.jti, payload.exp);

  return payload;
}

/**
 * Check email/password against the single shared admin credential.
 * Constant-time, so a wrong-length guess cannot be timed apart from a
 * right-length one.
 */
export function checkAdminCredentials(email, password) {
  const expectedEmail = process.env.META_ADS_ADMIN_EMAIL?.trim() ?? '';
  const expectedPassword = process.env.META_ADS_ADMIN_PASSWORD ?? '';
  if (!expectedEmail || !expectedPassword) return null;

  const emailOk = safeEqualString(String(email).trim().toLowerCase(), expectedEmail.toLowerCase());
  const passwordOk = safeEqualString(String(password), expectedPassword);
  if (!emailOk || !passwordOk) return null;

  return { sub: 'admin', name: 'Admin', email: expectedEmail };
}

// The session cookie is signed with the same shared secret. This app has no
// other secret configured, and the value never leaves the server (httpOnly),
// so reusing it here does not widen its exposure.
export function createSessionCookieValue(user) {
  const payload = { ...user, iat: Date.now(), exp: Date.now() + SESSION_TTL_SECONDS * 1000 };
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url');
  const sig = createHmac('sha256', secret()).update(body).digest('base64url');
  return `${body}.${sig}`;
}

export function readSessionCookieValue(value) {
  if (!value) return null;
  const [body, sig] = value.split('.');
  if (!body || !sig) return null;
  if (!signatureMatches(body, sig, secret())) return null;

  try {
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'));
    if (Date.now() > payload.exp) return null;
    return { sub: payload.sub, name: payload.name, email: payload.email };
  } catch {
    return null;
  }
}

/** Cookie options shared by every route that sets or clears the session. */
export const sessionCookieOptions = {
  httpOnly: true,
  secure: process.env.NODE_ENV === 'production',
  sameSite: 'lax',
  path: '/',
};

export const SESSION_COOKIE_NAME = SESSION_COOKIE;
export const SESSION_MAX_AGE_SECONDS = SESSION_TTL_SECONDS;
