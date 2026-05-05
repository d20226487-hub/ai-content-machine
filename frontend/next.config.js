const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Pin the workspace root so Next ignores unrelated package-lock.json files
  // sitting higher up in the directory tree.
  outputFileTracingRoot: path.join(__dirname),
  // Standalone output bundles only the files the server actually needs into
  // .next/standalone/, so the production Docker image can copy a few hundred
  // MB instead of the full ~600 MB node_modules. Read by `next build`; ignored
  // by `next dev`, so this has no effect on the local dev workflow.
  output: "standalone",
};

module.exports = nextConfig;
