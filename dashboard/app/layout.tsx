import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CGAE — Comprehension-Gated Portfolio Manager",
  description: "AI trading agents gated by robustness on Arc × Circle",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />
      </head>
      <body className="bg-white text-circle-text antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
