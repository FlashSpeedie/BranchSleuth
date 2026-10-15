"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { RepositoryOut, RepositoryList, RefOut } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";
import EmptyState from "@/components/EmptyState";

export default function RepositoriesPage() {
  const [repos, setRepos] = useState<RepositoryOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function load() {
    try {
      const data = await api.listRepositories(100);
      setRepos(data.items);
    } catch (e: any) {
      setError(e.message || "Failed to load repositories");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

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
        <h1 className="text-2xl font-semibold">Repositories</h1>
        <Link href="/repositories/new" className="px-4 py-2 rounded-md bg-emerald-500 hover:bg-emerald-400 text-[#0b0e14] font-semibold">
          Add repository
        </Link>
      </div>

      {repos.length === 0 ? (
        <EmptyState
          title="No repositories yet"
          body="Add a repository to start analyzing code changes. Support for GitHub URLs, ZIP uploads, and local paths."
          action={<Link href="/repositories/new" className="px-4 py-2 rounded-md bg-emerald-500 hover:bg-emerald-400 text-[#0b0e14] font-semibold">Add repository</Link>}
        />
      ) : (
        <div className="panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e2633] text-left text-slate-400">
                <th className="p-3 font-medium">Name</th>
                <th className="p-3 font-medium">Source</th>
                <th className="p-3 font-medium">Default branch</th>
                <th className="p-3 font-medium">Snapshots</th>
                <th className="p-3 font-medium">Created</th>
                <th className="p-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {repos.map(r => (
                <tr key={r.id} className="border-b border-[#1e2633]/50 hover:bg-[#161b26]">
                  <td className="p-3">
                    <Link href={`/analyses/new?repo=${r.id}`} className="font-medium hover:underline text-emerald-400">{r.name}</Link>
                  </td>
                  <td className="p-3"><StatusBadge value={r.source_type} /></td>
                  <td className="p-3 text-slate-300">{r.default_branch || "—"}</td>
                  <td className="p-3 text-slate-300">{r.snapshot_count}</td>
                  <td className="p-3 text-slate-500">{new Date(r.created_at).toLocaleString()}</td>
                  <td className="p-3 text-right">
                    <Link href={`/analyses/new?repo=${r.id}`} className="text-emerald-400 hover:underline">Analyze</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}