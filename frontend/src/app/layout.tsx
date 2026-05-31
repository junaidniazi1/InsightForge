import "./globals.css";
import type { Metadata } from "next";
import { Nav } from "@/components/nav";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/toaster";

export const metadata: Metadata = {
  title: {
    default: "InsightForge — AI Data Analysis & Dashboards",
    template: "%s · InsightForge",
  },
  description:
    "Bring raw data, get instant profiling, one-click cleaning, auto-built dashboards, and plain-language AI insights.",
  applicationName: "InsightForge",
  icons: {
    icon: "/icon.svg",
    shortcut: "/icon.svg",
    apple: "/icon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning is the official next-themes pattern: the
    // server renders without a `class`, then the client adds `class="dark"`
    // or `class="light"` on mount — without this React would warn about the
    // legit mismatch.
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen">
        <ThemeProvider>
          <Nav />
          <main className="animate-fade-in mx-auto max-w-7xl px-6 py-8">
            {children}
          </main>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
