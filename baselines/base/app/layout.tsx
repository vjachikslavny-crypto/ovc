import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import "../styles/globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "OVC Agent Workspace",
  description: "Chat-driven note workspace with graph and RAG search."
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full">
      <body className={`${inter.className} min-h-screen bg-background`}>
        <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 py-6">
          <header className="mb-6 flex flex-col gap-3 border-b border-gray-200 pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-semibold">OVC Agent Workspace</h1>
              <p className="text-sm text-gray-600">
                Chat with your notes, browse the graph, and enrich knowledge with
                structured actions.
              </p>
            </div>
            <nav className="flex flex-wrap gap-2 text-sm text-gray-700">
              <Link href="/chat" className="rounded-md px-3 py-1 hover:bg-muted">
                Chat
              </Link>
              <Link href="/notes" className="rounded-md px-3 py-1 hover:bg-muted">
                Notes
              </Link>
              <Link href="/graph" className="rounded-md px-3 py-1 hover:bg-muted">
                Graph
              </Link>
              <Link href="/settings" className="rounded-md px-3 py-1 hover:bg-muted">
                Settings
              </Link>
              <Link href="/monitor" className="rounded-md px-3 py-1 hover:bg-muted">
                Monitor
              </Link>
            </nav>
          </header>
          <main className="flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
