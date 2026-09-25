import type { Metadata } from "next";
import type { ReactNode } from "react";
import { themeInitializationScript } from "../lib/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: "TradingWorkFlow",
  description: "TWF-1 Application Foundation",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{ __html: themeInitializationScript }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
