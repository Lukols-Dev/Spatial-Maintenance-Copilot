"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ModeToggle } from "@/components/mode-toggle";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { subPageFor, titleFor } from "@/lib/site";

export function SiteHeader() {
  const path = usePathname();
  const title = titleFor(path);
  // A sub-page names the page it belongs to, which leads back to it.
  const sub = subPageFor(path);

  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur supports-backdrop-filter:bg-background/60">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 data-[orientation=vertical]:h-4" />
      {sub && (
        <>
          <Link href={sub.parent} className="text-sm text-muted-foreground hover:text-foreground">
            {titleFor(sub.parent)}
          </Link>
          <ChevronRight aria-hidden className="size-4 text-muted-foreground" />
        </>
      )}
      <h1 className="text-sm font-medium">{title}</h1>
      <div className="ml-auto">
        <ModeToggle />
      </div>
    </header>
  );
}
