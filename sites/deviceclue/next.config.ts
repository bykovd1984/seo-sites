import type { NextConfig } from 'next';
const config: NextConfig = {
  output: 'standalone',
  poweredByHeader: false,
  serverExternalPackages: ['node:sqlite'],
  async headers() {
    return [{ source: '/:path*', headers: [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      { key: 'Content-Signal', value: 'search=yes, ai-input=yes, ai-train=no' },
    ] }, { source: '/api/:path*', headers: [{ key: 'X-Robots-Tag', value: 'noindex, nofollow' }] },
    { source: '/search', headers: [{ key: 'X-Robots-Tag', value: 'noindex, follow' }] }];
  },
};
export default config;
