import type { Metadata } from "next";
import "./globals.css";

import { THEME_SCRIPT } from "@/lib/theme-script";

export const metadata: Metadata = {
  title: "VROS · Verkies",
  description: "Verkies Revenue Operating System",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // The theme script sets data-theme before React hydrates, hence suppressHydrationWarning.
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
