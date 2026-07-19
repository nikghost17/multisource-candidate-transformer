/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/candidates/:path*",
        destination: "http://localhost:8001/candidates/:path*",
      },
      {
        source: "/health",
        destination: "http://localhost:8001/health",
      },
    ];
  },
};

export default nextConfig;
