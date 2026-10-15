"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { RepositoryOut, AnalysisRun, RepositoryList, AnalysisList } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";
import EmptyState from "@/components/EmptyState";

function formatTime(dateStr: string | null | undefined) {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  return d.toLocaleString();
}

function durationHuman(seconds: number | null | undefined) {
  if (!seconds) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(0);
  return `${m}m ${s}s`;
}

export default function Dashboard() {
  const [repos, setRepos] = useState<RepositoryOut[]>([]);
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [r, a] = await Promise.all([
        api.listRepositories(5),
        api.listAnalyses(10),
      ]);
      setRepos(r.items);
      setRuns(a.items);
    } catch (e: any) {
      setError(e.message || "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const totalRuns = runs.length;
  const completedRuns = runs.filter(r => r.status === "completed").length;
  const failedRuns = runs.filter(r => r.status === "failed").length;
  const provenFailures = runs.reduce((sum, r) => sum + (r.summary?.proven_failures || 0), 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-400"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <Link href="/analyses/new" className="px-4 py-2 rounded-md bg-emerald-500 hover:bg-emerald-400 text-[#0b0e14] font-semibold">
          New analysis
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="panel p-5">
          <p className="text-sm text-slate-400">Total analyses</p>
          <p className="text-3xl font-semibold mt-1">{totalRuns}</p>
        </div>
        <div className="panel p-5">
          <p className="text-sm text-slate-400">Completed</p>
          <p className="text-3xl font-semibold text-emerald-400 mt-1">{completedRuns}</p>
        </div>
        <div className="panel p-5">
          <p className="text-sm text-slate-400">Failed</p>
          <p className="text-3xl font-semibold text-rose-400 mt-1">{failedRuns}</p>
        </div>
        <div className="panel p-5">
          <p className="text-sm text-slate-400">Confirmed failures</p>
          <p className="text-3xl font-semibold text-rose-400 mt-1">{provenFailures}</p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="panel p-5">
          <h2 className="font-semibold mb-4 flex items-center gap-2">
            <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
            Recent repositories
          </h2>
          {repos.length === 0 ? (
            <EmptyState
              title="No repositories yet"
              body="Add a repository to start analyzing code changes."
              action={<Link href="/repositories" className="px-3 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-400 text-[#0b0e14] font-semibold">Add repository</Link>}
            />
          ) : (
            <ul className="space-y-2">
              {repos.map(r => (
                <li key={r.id} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-3">
                    <span className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center text-emerald-400 font-semibold text-xs">R</span>
                    <div>
                      <p className="font-medium">{r.name}</p>
                      <p className="text-slate-500">{r.source_type} · {formatTime(r.created_at)}</p>
                    </div>
                  </div>
                  <Link href={`/analyses/new?repo=${r.id}`} className="text-emerald-400 hover:underline text-sm">Analyze</Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="panel p-5">
          <h2 className="font-semibold mb-4 flex items-center gap-2">
            <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>
            Recent analyses
          </h2>
          {runs.length === 0 ? (
            <EmptyState
              title="No analyses yet"
              body="Run an analysis to see results here."
              action={<Link href="/analyses/new" className="px-3 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-400 text-[#0b0e14] font-semibold">New analysis</Link>}
            />
          ) : (
            <ul className="space-y-2">
              {runs.map(r => (
                <li key={r.id} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-3">
                    <StatusBadge value={r.status} />
                    <div>
                      <p className="font-medium truncate max-w-xs">{r.repository_name || "Unknown repo"}</p>
                      <p className="text-slate-500 text-xs">{formatTime(r.created_at)} · {durationHuman(r.duration_seconds)}</p>
                    </div>
                  </div>
                  <Link href={`/analyses/${r.id}`} className="text-emerald-400 hover:underline text-sm">View</Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}