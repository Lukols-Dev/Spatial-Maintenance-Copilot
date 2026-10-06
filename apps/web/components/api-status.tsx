"use client";

import { Server } from "lucide-react";

import { SidebarMenuButton } from "@/components/ui/sidebar";
import { API_URL } from "@/lib/api";
import { refreshHealth, useHealth } from "@/lib/health";
import { cn } from "@/lib/utils";

export function StatusDot({ state }: { state: "checking" | "online" | "offline" }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block size-2 shrink-0 rounded-full",
        state === "online" && "bg-emerald-500",
        state === "offline" && "bg-destructive",
        state === "checking" && "animate-pulse bg-muted-foreground",
      )}
    />
  );
}

/** Sidebar entry: the perception service's health, rechecked on click. */
export function ApiStatus() {
  const health = useHealth();
  const label =
    health.state === "online"
      ? `API online · v${health.version}`
      : health.state === "offline"
        ? "API offline"
        : "Checking API…";
  // The collapsed sidebar shows only the icon; its tooltip carries the rest.
  const detail = health.state === "offline" ? health.error : API_URL;

  return (
    <SidebarMenuButton
      onClick={refreshHealth}
      tooltip={`${label} (${detail}). Click to check again.`}
      aria-label={`${label}. Check again.`}
    >
      <Server />
      <span className="flex items-center gap-2">
        <StatusDot state={health.state} />
        {label}
      </span>
    </SidebarMenuButton>
  );
}
