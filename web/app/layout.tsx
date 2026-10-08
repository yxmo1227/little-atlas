import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Little Atlas · Your personal dictionary",
  description: "Write what you learned. Little Atlas organizes it into your own private knowledge library, with source-linked English research.",
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
