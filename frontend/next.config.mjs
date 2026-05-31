/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    // Phase 1 doesn't need much here; Phase 4 may add serverComponentsExternalPackages.
  },
};

export default nextConfig;
