import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static files for S3 + CloudFront: no server at runtime.
  output: "export",
  // /annotate is written as annotate/index.html rather than annotate.html next
  // to an annotate/ folder, which any static host can serve as a directory.
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
