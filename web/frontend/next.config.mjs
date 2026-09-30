/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [{
      source: '/api/:path*',
      destination: `${process.env.EVRP_API_ORIGIN || 'http://127.0.0.1:8000'}/api/:path*`,
    }];
  },
};

export default nextConfig;
