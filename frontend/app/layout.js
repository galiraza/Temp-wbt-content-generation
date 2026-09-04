import './globals.css';

export const metadata = {
  title: 'Content Generation — WBT content pipeline',
  description:
    'Pick a client, then review every generated asset in one place. Results land here automatically as runs complete.',
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        {/* Same font loading the design's <helmet> block declares. The inline
            styles reference the families by literal name ('Plus Jakarta Sans',
            'IBM Plex Mono'), so these must stay as plain <link> tags rather
            than next/font, which rewrites family names to hashed ones. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
