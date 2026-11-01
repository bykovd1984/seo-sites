import type { NextConfig } from "next";
const nextConfig: NextConfig = {
 output:"standalone",poweredByHeader:false,serverExternalPackages:["node:sqlite"],
 async headers() {
  return [
   {source:"/:path*",headers:[{key:"X-Content-Type-Options",value:"nosniff"},{key:"Referrer-Policy",value:"strict-origin-when-cross-origin"}]},
   {source:"/api/:path*",headers:[{key:"X-Robots-Tag",value:"noindex, nofollow"}]},
   {source:"/images/:path*.webp",headers:[{key:"Cache-Control",value:"public, max-age=31536000, immutable"}]},
  ];
 },
};
export default nextConfig;
