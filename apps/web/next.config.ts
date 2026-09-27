import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // The official callback carries a short-lived request token in its query.
  logging: { incomingRequests: { ignore: [/^\/brokers\/callback(?:[/?]|$)/] } },
  async headers() {
    return [
      {
        source: "/brokers/callback",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Cache-Control", value: "no-store" },
        ],
      },
    ];
  },
};

export default nextConfig;
