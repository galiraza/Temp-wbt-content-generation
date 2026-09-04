import { redirect } from 'next/navigation';
import { ROOT } from '@/lib/routes';

// The hub lives under /content/... Which client it opens on depends on live
// data — the most recently run — so the bare root hands off to the catch-all
// and lets it resolve and redirect to the canonical path.
export default function Home() {
  redirect(ROOT);
}
