import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  agentRules: false,
  experimental: { serverActions: { bodySizeLimit: "3mb" } },
  logging: { serverFunctions: false },
};

export default nextConfig;
