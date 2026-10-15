"use client";

export const dynamic = "force-dynamic";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { AnalysisRun, ChangedFileOut, GraphOut, JobEventOut, TestRecordOut, VerificationAttemptOut } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";
import EmptyState from "@/components/EmptyState";
import EvidenceGraph from "@/components/EvidenceGraph";
import DiffViewer from "@/components/DiffViewer";
import TestTable from "@/components/TestTable";
import VerificationCard from "@/components/VerificationCard";
import EventsTimeline from "@/components/EventsTimeline";

type Tab = "overview" | "graph" | "diff" | "tests" | "verifications" | "events" | "report";

export default function AnalysisDetailPage() {
  const params = useParams();
  const runId = params.id as string;

  const [run, setRun] = useState<AnalysisRun | null>(null);
  const [files, setFiles] = useState<ChangedFileOut[]>([]);
  const [graph, setGraph] = useState<GraphOut | null>(null);
  const [events, setEvents] = useState<JobEventOut[]>([]);
  const [tests, setTests] = useState<TestRecordOut[]>([]);
  const [verifications, setVerifications] = useState<VerificationAttemptOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [error, setError] = useState<string | null>(null);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);

  async function load() {
    try {
      const [r, f, g, e, t, v] = await Promise.all([
        api.getAnalysis(runId),
        api.listFiles(runId),
        api.getGraph(runId),
        api.listEvents(runId, 200),
        api.listTests(runId),
        api.listVerifications(runId),
      ]);
      setRun(r);
      setFiles(f);
      setGraph(g);
      setEvents(e);
      setTests(t);
      setVerifications(v);
    } catch (e: any) {
      setError(e.message || "Failed to load analysis");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [runId]);

  const runtimeStatus = run?.summary?.runtime_status ?? "unknown";

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-400"></div>
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="panel p-8 text-center">
        <h2 className="text-xl font-semibold text-rose-400">Failed to load analysis</h2>
        <p className="text-slate-400 mt-2">{error || "Analysis not found"}</p>
        <Link href="/analyses" className="inline-block mt-4 text-emerald-400 hover:underline">Back to analyses</Link>
      </div>
    );
  }

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "overview", label: "Overview" },
    { id: "graph", label: "Evidence graph", count: graph?.nodes.length },
    { id: "diff", label: "Changed code", count: files.length },
    { id: "tests", label: "Tests", count: tests.length },
    { id: "verifications", label: "Verifications", count: verifications.length },
    { id: "events", label: "Events", count: events.length },
    { id: "report", label: "Report" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{run.repository_name || "Analysis"}</h1>
          <p className="text-slate-400 text-sm mt-1">
            {run.baseline_ref || "auto"} ({run.resolved_baseline_sha?.slice(0, 8) || "—"}) →
            {run.target_ref || "auto"} ({run.resolved_target_sha?.slice(0, 8) || "—"})
          </p>
        </div>
        <div className="flex items-center gap-4">
          <StatusBadge value={run.status} />
          <Link href={api.reportUrl(run.id, "md")} className="px-3 py-1.5 rounded-md border border-[#1e2633] text-slate-300 hover:bg-[#161b26] text-sm">
            Download MD
          </Link>
          <Link href={api.reportUrl(run.id, "json")} className="px-3 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-400 text-[#0b0e14] font-semibold text-sm">
            Download JSON
          </Link>
        </div>
      </div>

      <div className="panel p-4">
        <div className="grid gap-4 md:grid-cols-4 mb-4">
          <div className="p-3 bg-[#0b0e14] rounded-md">
            <p className="text-xs text-slate-400">Status</p>
            <p className="font-semibold text-lg">{run.stage || run.status}</p>
          </div>
          <div className="p-3 bg-[#0b0e14] rounded-md">
            <p className="text-xs text-slate-400">Duration</p>
            <p className="font-semibold text-lg">{run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s` : "—"}</p>
          </div>
          <div className="p-3 bg-[#0b0e14] rounded-md">
            <p className="text-xs text-slate-400">Runtime</p>
            <p className="font-semibold text-lg capitalize">{runtimeStatus}</p>
          </div>
          <div className="p-3 bg-[#0b0e14] rounded-md">
            <p className="text-xs text-slate-400">Proven failures</p>
            <p className="font-semibold text-lg text-rose-400">{run.summary?.proven_failures || 0}</p>
          </div>
        </div>
        {run.error_message && (
          <div className="p-3 rounded-md bg-rose-500/15 border border-rose-500/30 text-rose-300 text-sm">
            {run.error_message}
          </div>
        )}
      </div>

      <div className="border-b border-[#1e2633]">
        <nav className="flex gap-1 overflow-x-auto px-4" role="tablist">
          {tabs.map(t => (
            <button
              key={t.id}
              role="tab"
              aria-selected={activeTab === t.id}
              onClick={() => setActiveTab(t.id)}
              className={`px-4 py-2 rounded-t-md text-sm font-medium whitespace-nowrap transition-colors ${
                activeTab === t.id
                  ? "bg-[#10141d] text-emerald-400 border-b-2 border-emerald-400"
                  : "text-slate-400 hover:text-slate-200 hover:bg-[#161b26]"
              }`}
            >
              {t.label} {t.count !== undefined && <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-[#1e2633] rounded-full">{t.count}</span>}
            </button>
          ))}
        </nav>
      </div>

      <div className="panel p-6">
        {activeTab === "overview" && (
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-3">
              <StatCard title="Changed files" value={run.summary?.changed_files || 0} />
              <StatCard title="Changed scopes" value={run.summary?.changed_scopes || 0} />
              <StatCard title="Uncovered changed lines" value={run.summary?.uncovered_changed_lines || 0} color="rose" />
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <StatCard title="Tests run" value={run.summary?.tests?.count || 0} />
              <StatCard title="Regressions" value={run.summary?.tests?.categories?.REGRESSION || 0} color="rose" />
              <StatCard title="Fixed" value={run.summary?.tests?.categories?.FIXED || 0} color="emerald" />
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <StatCard title="Proven failures" value={run.summary?.verifications?.classifications?.PROVEN_FAILURE || 0} color="rose" />
              <StatCard title="Behavior divergences" value={run.summary?.verifications?.classifications?.BEHAVIOR_DIVERGENCE || 0} color="amber" />
              <StatCard title="Inconclusive" value={run.summary?.verifications?.classifications?.INCONCLUSIVE || 0} color="slate" />
            </div>
            <div className="border-t border-[#1e2633] pt-4">
              <h3 className="font-semibold mb-2">Runtime info</h3>
              <dl className="grid grid-cols-2 gap-2 text-sm">
                <dt className="text-slate-400">Worker image</dt>
                <dd className="mono text-slate-300">{run.runtime_info?.worker_image || "—"}</dd>
                <dt className="text-slate-400">Python version</dt>
                <dd className="mono text-slate-300">{run.runtime_info?.python_version || "—"}</dd>
                <dt className="text-slate-400">Dependencies</dt>
                <dd className="mono text-slate-300 max-w-xs truncate">{run.runtime_info?.dependencies || "—"}</dd>
              </dl>
            </div>
          </div>
        )}

        {activeTab === "graph" && (
          <div className="h-[600px]">
            {graph ? (
              <EvidenceGraph graph={graph} onNodeClick={setSelectedFileId} />
            ) : (
              <EmptyState title="No graph data" body="No evidence graph available for this analysis." />
            )}
          </div>
        )}

        {activeTab === "diff" && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold">Changed files ({files.length})</h3>
              <select
                value={selectedFileId || ""}
                onChange={e => setSelectedFileId(e.target.value || null)}
                className="px-3 py-1.5 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white text-sm"
              >
                <option value="">Select file</option>
                {files.map(f => (
                  <option key={f.id} value={f.id}>{f.path} ({f.change_type})</option>
                ))}
              </select>
            </div>
            {selectedFileId ? (
              <DiffViewer runId={runId} fileId={selectedFileId} />
            ) : (
              <EmptyState title="Select a file" body="Choose a file from the dropdown to view its diff." />
            )}
          </div>
        )}

        {activeTab === "tests" && (
          <TestTable tests={tests} />
        )}

        {activeTab === "verifications" && (
          <div className="space-y-4">
            {verifications.length === 0 ? (
              <EmptyState title="No verification attempts" body="Enable targeted verification in analysis options to run property-based probes." />
            ) : (
              verifications.map(v => <VerificationCard key={v.id} attempt={v} />)
            )}
          </div>
        )}

        {activeTab === "events" && (
          <EventsTimeline events={events} />
        )}

        {activeTab === "report" && (
          <div className="space-y-4">
            <p className="text-slate-400">Download the full evidence report in Markdown or JSON format.</p>
            <div className="flex gap-3">
              <Link href={api.reportUrl(run.id, "md")} className="px-4 py-2 rounded-md bg-emerald-500 hover:bg-emerald-400 text-[#0b0e14] font-semibold">
                Download Markdown report
              </Link>
              <Link href={api.reportUrl(run.id, "json")} className="px-4 py-2 rounded-md border border-[#1e2633] text-slate-300 hover:bg-[#161b26]">
                Download JSON report
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ title, value, color = "emerald" }: { title: string; value: number; color?: "emerald" | "rose" | "amber" | "slate" }) {
  const colors = {
    emerald: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    rose: "text-rose-400 bg-rose-500/10 border-rose-500/20",
    amber: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    slate: "text-slate-300 bg-slate-500/10 border-slate-500/20",
  };
  return (
    <div className={`p-4 rounded-md border ${colors[color]}`}>
      <p className="text-xs text-slate-400">{title}</p>
      <p className="text-3xl font-semibold mt-1">{value}</p>
    </div>
  );
}