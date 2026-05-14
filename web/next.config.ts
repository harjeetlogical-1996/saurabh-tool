import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Pin the Turbopack workspace root to this folder so it doesn't try to
  // infer it from a parent lockfile (we have a sibling marketing site repo).
  turbopack: { root: path.resolve(__dirname) },
  // Standalone output — drops the prod tree under .next/standalone with a
  // minimal node_modules subset. Cloud Run / Dockerfile uses this to
  // ship a ~40MB final image instead of 500MB.
  output: "standalone",
  // Same workspace pin for the standalone tracer; otherwise it walks up
  // and pulls the sibling marketing project's node_modules into the bundle.
  outputFileTracingRoot: path.resolve(__dirname),
};

export default nextConfig;
