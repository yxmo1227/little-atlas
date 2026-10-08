import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Little Atlas · Your private notebook",
  description: "A private notebook for ideas, articles, and discoveries. Write, organize, and research with English sources and reference images.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
