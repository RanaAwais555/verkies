import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  title: { default: "VROS", template: "%s · VROS" },
  description: "Verkies Revenue Operating System",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#090c13" },
    { media: "(prefers-color-scheme: light)", color: "#e9eef7" },
  ],
};

// Applied before first paint so the page never flashes the wrong theme. Dark is the default;
// a choice made with the theme toggle is remembered in this browser only.
const THEME_SCRIPT = `(function(){var t="dark";try{var s=localStorage.getItem("vros-theme");if(s==="light"||s==="dark")t=s;}catch(e){}document.documentElement.dataset.theme=t;})();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-theme="dark" className={`${geist.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
