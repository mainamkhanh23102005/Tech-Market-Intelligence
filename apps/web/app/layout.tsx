import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tech Market Intelligence",
  description: "Evidence-backed technical job-market statistics",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
