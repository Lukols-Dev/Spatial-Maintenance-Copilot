import { Crosshair } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { SITE } from "@/lib/site";

// The root layout's title template does not apply to its own segment.
export const metadata: Metadata = { title: { absolute: SITE.name } };

export default function HomePage() {
  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 p-4 md:p-6">
      <h2 className="text-2xl font-semibold tracking-tight">{SITE.name}</h2>
      <Button asChild>
        <Link href="/annotate">
          <Crosshair />
          Annotate
        </Link>
      </Button>
    </div>
  );
}
