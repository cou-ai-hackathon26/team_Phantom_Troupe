import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // the floating dev badge covers the mobile menu button; build errors still show in the overlay
  devIndicators: false,
};

export default nextConfig;
