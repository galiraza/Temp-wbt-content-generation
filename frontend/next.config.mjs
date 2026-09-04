/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Emits .next/standalone — a self-contained server with only the modules it
  // actually uses, which is what the Dockerfile's runner stage copies. Without
  // it the image would need the whole node_modules tree.
  output: 'standalone',

  // Next 16 writes AGENTS.md / CLAUDE.md into the project root on first run.
  // Not part of this project, so it stays off.
  agentRules: false,
};

export default nextConfig;
