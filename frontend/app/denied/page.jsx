// Where /sso sends a ticket that failed. Distinct from /login on purpose:
// "your link did not work" is a different problem from "you are not signed in",
// and sending the first to the login form reads as though the password is
// wrong when the real fault is an expired or reused link.

export const metadata = { title: 'Link expired — Content Generation' };

const HQ = process.env.COMMAND_HQ_URL || 'https://hq.webuildtrades.com';

export default function DeniedPage() {
  return (
    <main style={S.page}>
      <div style={S.card}>
        <div style={S.badge}>!</div>
        <h1 style={S.title}>That link did not work</h1>
        <p style={S.body}>
          Sign-in links are single use and last about a minute. This one had
          already been used, had expired, or was not signed correctly.
        </p>
        <p style={S.body}>Open the app again from Command HQ for a fresh one.</p>
        <div style={S.actions}>
          <a href={HQ} style={S.primary}>Back to Command HQ</a>
          <a href="/login" style={S.secondary}>Sign in with a password</a>
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
    width: 'min(100%, 440px)', padding: 30, background: '#fff',
    border: '1px solid #e6e4de', borderRadius: 22,
    boxShadow: '0 1px 3px rgba(20,18,16,.04)',
  },
  badge: {
    width: 38, height: 38, borderRadius: 999, display: 'flex', alignItems: 'center',
    justifyContent: 'center', background: '#fff4ec', border: '1px solid #fadfc9',
    color: '#cf5c17', fontWeight: 800, fontSize: 17,
  },
  title: { margin: '16px 0 0', fontSize: 22, fontWeight: 800, letterSpacing: '-.02em', color: '#0f2f2b' },
  body: { margin: '10px 0 0', fontSize: 13.5, lineHeight: 1.6, color: '#6c6862' },
  actions: { marginTop: 22, display: 'flex', gap: 10, flexWrap: 'wrap' },
  primary: {
    padding: '11px 17px', borderRadius: 12, textDecoration: 'none',
    background: 'linear-gradient(140deg, #ef7326, #d9541a)', color: '#fff',
    fontSize: 13, fontWeight: 700, boxShadow: '0 6px 18px rgba(217,84,26,.24)',
  },
  secondary: {
    padding: '11px 17px', borderRadius: 12, textDecoration: 'none',
    background: '#fff', border: '1px solid #e3e1dc', color: '#4b4741',
    fontSize: 13, fontWeight: 600,
  },
};
