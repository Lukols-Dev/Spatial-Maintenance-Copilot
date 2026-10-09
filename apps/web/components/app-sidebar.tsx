"use client";

import { Crosshair, FileText, FolderGit2, LocateFixed, MapIcon, ScanEye } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type * as React from "react";

import { ApiStatus } from "@/components/api-status";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { NAV, SITE, normalisePath } from "@/lib/site";

// Icons are components, which cannot cross from a server layout into a client
// component, so they live here, next to the hook that needs them.
const ICONS: Record<string, React.ComponentType> = {
  "/": LocateFixed,
  "/annotate": Crosshair,
  "/atlas": MapIcon,
};

export function AppSidebar(props: React.ComponentProps<typeof Sidebar>) {
  // Exact matches only: no page has sub-pages, and the exported 404 page is
  // served for any unknown path, so a prefix match would highlight a page the
  // prerendered HTML does not.
  const current = normalisePath(usePathname());

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            {/* The home page is also Locate in the list below, which carries aria-current. */}
            <SidebarMenuButton size="lg" asChild tooltip={SITE.name} className="h-auto py-2">
              <Link href="/">
                <div className="flex aspect-square size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                  <ScanEye className="size-4" />
                </div>
                {/* A div, not a span: the button truncates a last span, and the name may take two lines. */}
                <div className="flex-1 text-sm leading-tight font-medium">{SITE.name}</div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <nav aria-label="Pages">
              <SidebarMenu>
                {NAV.map(({ href, title }) => {
                  const Icon = ICONS[href] ?? FileText;
                  const active = current === href;
                  return (
                    <SidebarMenuItem key={href}>
                      <SidebarMenuButton asChild isActive={active} tooltip={title}>
                        <Link href={href} aria-current={active ? "page" : undefined}>
                          <Icon />
                          <span>{title}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </nav>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <ApiStatus />
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton asChild tooltip="Source on GitHub">
              <a href={SITE.repository} target="_blank" rel="noreferrer">
                <FolderGit2 />
                <span>Source on GitHub</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
