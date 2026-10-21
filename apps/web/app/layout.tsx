import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { AppSidebar } from "@/components/app-sidebar";
import { PersistentSidebarProvider } from "@/components/persistent-sidebar-provider";
import { SiteHeader } from "@/components/site-header";
import { ThemeProvider } from "@/components/theme-provider";
import { SidebarInset } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SITE } from "@/lib/site";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { template: `%s · ${SITE.name}`, default: SITE.name },
  description: SITE.description,
  // Opened from a phone's home screen, the site runs without the browser's bars (app/manifest.ts).
  appleWebApp: { capable: true, title: "Copilot", statusBarStyle: "default" },
};

// The page reaches under a phone's notch and home indicator; the Guide's
// full-screen camera keeps its buttons inside the safe area.
export const viewport: Viewport = {
  viewportFit: "cover",
  themeColor: "#18181b",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // next-themes sets the theme class on <html> before React hydrates.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <TooltipProvider>
            <PersistentSidebarProvider>
              <AppSidebar />
              <SidebarInset>
                <SiteHeader />
                {children}
              </SidebarInset>
            </PersistentSidebarProvider>
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
