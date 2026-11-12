import type { Metadata } from "next";
import "./globals.css";
import "./operations.css";
export const metadata: Metadata = { title: "NetGuardian — Network observability", description: "Evidence-based network diagnostics" };
export default function Layout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
