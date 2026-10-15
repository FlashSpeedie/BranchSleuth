import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "BranchSleuth — Find the bugs your tests miss",
  description: "Change-aware software verification and regression analysis for Python repositories.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-[#1e2633] bg-[#0b0e14]/90 sticky top-0 z-40 backdrop-blur">
          <div className="mx-auto max-w-7xl px-6 h-14 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2.5 group">
              <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-500 flex items-center justify-center text-[#0b0e14] font-black text-sm">
                B
              </span>
              <span className="font-semibold tracking-tight text-[15px]">
                Branch<span className="text-emerald-400">Sleuth</span>
              </span>
            </Link>
            <nav className="flex items-center gap-1 text-sm">
              <Link href="/" className="px-3 py-1.5 rounded-md hover:bg-[#161b26] text-slate-300">
                Dashboard
              </Link>
              <Link href="/repositories" className="px-3 py-1.5 rounded-md hover:bg-[#161b26] text-slate-300">
                Repositories
              </Link>
              <Link
                href="/analyses/new"
                className="ml-2 px-3.5 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-400 text-[#0b0e14] font-semibold"
              >
                New analysis
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
        <footer className="border-t border-[#1e2633] mt-16">
          <div className="mx-auto max-w-7xl px-6 py-6 text-xs text-slate-500 flex justify-between">
            <span>BranchSleuth — change-aware verification for Python</span>
            <span className="mono">every finding comes from a real analysis run</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
