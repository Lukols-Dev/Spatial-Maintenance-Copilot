"use client";

import * as React from "react";

import { SidebarProvider } from "@/components/ui/sidebar";

// The shadcn sidebar writes its open state to a cookie but leaves reading it
// to a server layout calling cookies(), which a static export cannot do. Here
// the browser reads the cookie instead. The prerendered HTML has the sidebar
// open; a reader who closed it sees it open for one frame on a full reload.

const COOKIE = "sidebar_state";
const CHANGE_EVENT = "sidebar-state-change";
const MAX_AGE_S = 60 * 60 * 24 * 7;

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => window.removeEventListener(CHANGE_EVENT, onChange);
}

function readOpen() {
  return !document.cookie.split("; ").includes(`${COOKIE}=false`);
}

type Props = Omit<React.ComponentProps<typeof SidebarProvider>, "open" | "onOpenChange" | "defaultOpen">;

export function PersistentSidebarProvider(props: Props) {
  const open = React.useSyncExternalStore(subscribe, readOpen, () => true);
  const onOpenChange = React.useCallback((value: boolean) => {
    document.cookie = `${COOKIE}=${value}; path=/; max-age=${MAX_AGE_S}; SameSite=Lax`;
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  return <SidebarProvider open={open} onOpenChange={onOpenChange} {...props} />;
}
