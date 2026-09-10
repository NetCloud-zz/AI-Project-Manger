import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // `standalone` keeps the production Docker image small by bundling only the
  // traced runtime dependencies.
  output: "standalone",
  reactStrictMode: true,
  // antd-mobile ships untranspiled ESM that Next must compile itself.
  transpilePackages: ["antd-mobile"],
};

export default nextConfig;
