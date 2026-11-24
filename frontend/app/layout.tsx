import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import { SiteHeader } from "@/components/site-header";
import { StudioStatusProvider } from "@/components/studio-status";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Dance Teacher — Learn any dance. Frame by frame.",
  description:
    "Upload any choreography, let AI break it down, practice it, and get instant feedback on your performance.",
};

export const viewport: Viewport = {
  themeColor: "#10120f",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col overflow-x-hidden">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-lime focus:px-3 focus:py-2 focus:text-studio"
        >
          Skip to content
        </a>
        <StudioStatusProvider>
          <SiteHeader />
          <main id="main" className="flex flex-1 flex-col">
            {children}
          </main>
        </StudioStatusProvider>
      </body>
    </html>
  );
}
