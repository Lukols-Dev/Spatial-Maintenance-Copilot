import type { MetadataRoute } from "next";

import { SITE } from "@/lib/site";

// Added to a phone's home screen, the site opens as an app: without the
// browser's bars, on Localise, the page a phone is used for.

// A static export writes the manifest once, at build time.
export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: SITE.name,
    short_name: "Copilot",
    description: SITE.description,
    start_url: "/localise/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#000000",
    theme_color: "#18181b",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
