/** @type {import('next').NextConfig} */
// "standalone" emits a self-contained server (.next/standalone) used by apps/web/Dockerfile; `next start` still works.
const nextConfig = { reactStrictMode: true, output: "standalone" };
export default nextConfig;
