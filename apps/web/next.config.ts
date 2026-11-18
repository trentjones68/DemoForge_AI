import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  agentRules: false,
  logging: { serverFunctions: false },
};

export default nextConfig;
