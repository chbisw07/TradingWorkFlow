import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "../components/shell/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "TradingWorkFlow",
  description: "TWF-1 Application Foundation",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
