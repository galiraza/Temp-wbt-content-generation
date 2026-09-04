'use client';

import { useState } from 'react';

// The direct-login door. The other one is /sso, where a Command HQ ticket is
// exchanged for the same session — nothing here is involved in that path.
//
// A full page reload rather than router.push after signing in: the session is
// an httpOnly cookie read by proxy.js, and only a real navigation makes the
// gate re-run with it.

const HQ = process.env.NEXT_PUBLIC_COMMAND_HQ_URL || 'https://hq.webuildtrades.com';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (res.ok) {
        window.location.assign('/');
        return;
      }
      setError(res.status === 401
        ? 'That email and password do not match.'
        : 'Could not sign in. Try again.');
    } catch {
      setError('Could not reach the server.');
    }
    setBusy(false);
  }

  return (
    <main style={S.page}>
      <div style={S.card}>
        <div style={S.head}>
          <div style={S.eyebrow}>WBT content pipeline</div>
          <h1 style={S.title}>Sign in</h1>
          <p style={S.sub}>
            Or open it from Command HQ, which signs you in on the way through.
          </p>
        </div>

        <form onSubmit={submit} style={S.form}>
          <label style={S.field}>
            <span style={S.label}>Email</span>
            <input
              type="email" value={email} required autoFocus autoComplete="username"
              onChange={(e) => setEmail(e.target.value)} style={S.input}
            />
          </label>

          <label style={S.field}>
            <span style={S.label}>Password</span>
            <input
              type="password" value={password} required autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)} style={S.input}
            />
          </label>

          {error ? <p style={S.error}>{error}</p> : null}

          <button type="submit" disabled={busy} style={{ ...S.submit, opacity: busy ? 0.6 : 1 }}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div style={S.foot}>
          <a href={HQ} style={S.link}>Go to Command HQ →</a>
        </div>
      </div>
    </main>
  );
}

const S = {
  page: {
    minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 24, background: '#f6f5f2',
    fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif", color: '#16181c',
  },
  card: {
    width: 'min(100%, 420px)', background: '#fff', border: '1px solid #e6e4de',
    borderRadius: 22, boxShadow: '0 1px 3px rgba(20,18,16,.04)', overflow: 'hidden',
  },
  head: {
    padding: '26px 26px 18px', borderBottom: '1px solid #efece7',
    background: 'linear-gradient(180deg, #fcfbf9, #ffffff)',
  },
  eyebrow: {
    fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, fontWeight: 500,
    letterSpacing: '.16em', textTransform: 'uppercase', color: '#a3a09a',
  },
  title: { margin: '6px 0 0', fontSize: 26, fontWeight: 800, letterSpacing: '-.025em', color: '#0f2f2b' },
  sub: { margin: '6px 0 0', fontSize: 13, lineHeight: 1.55, color: '#6c6862' },
  form: { padding: 26, display: 'flex', flexDirection: 'column', gap: 14 },
  field: { display: 'flex', flexDirection: 'column', gap: 6 },
  label: {
    fontFamily: "'IBM Plex Mono', monospace", fontSize: 9.5, letterSpacing: '.13em',
    textTransform: 'uppercase', color: '#a3a09a',
  },
  input: {
    padding: '11px 13px', border: '1px solid #e3e1dc', borderRadius: 11,
    fontFamily: 'inherit', fontSize: 13.5, color: '#16181c', background: '#fff', outline: 'none',
  },
  error: {
    margin: 0, padding: '9px 12px', border: '1px solid #f6cccc', background: '#fdecec',
    borderRadius: 10, fontSize: 12.5, color: '#c04141',
  },
  submit: {
    marginTop: 2, padding: '12px 18px', border: 'none', borderRadius: 12,
    background: 'linear-gradient(140deg, #ef7326, #d9541a)', color: '#fff',
    fontFamily: 'inherit', fontSize: 13.5, fontWeight: 700, cursor: 'pointer',
    boxShadow: '0 6px 18px rgba(217,84,26,.24)',
  },
  foot: {
    padding: '14px 26px', borderTop: '1px solid #efece7', background: '#faf9f6',
    fontSize: 12.5,
  },
  link: { color: '#d9541a', textDecoration: 'none', fontWeight: 600 },
};
