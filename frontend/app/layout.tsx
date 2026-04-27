import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FinBot - AI Finance & Insurance Assistant",
  description:
    "RAG-powered chatbot for Indian finance and insurance queries, grounded in official documents and regulations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="min-h-full flex flex-col bg-[var(--bg-primary)] text-[var(--text-primary)]" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
