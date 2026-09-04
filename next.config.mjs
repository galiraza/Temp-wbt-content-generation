/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Next 16 writes AGENTS.md / CLAUDE.md into the project root on first run.
  // Not part of this design port, so it stays off.
  agentRules: false,
};

export default nextConfig;
