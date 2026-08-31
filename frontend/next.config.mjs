/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The frontend is fully client-side ("use client" everywhere) so we can
  // produce a static export. The Docker image serves /out via FastAPI, which
  // also handles the API at /api.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;