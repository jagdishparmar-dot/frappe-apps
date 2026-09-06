import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Vendor Portal",
  description: "Vendor self-service portal for profile and KYC documents",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
