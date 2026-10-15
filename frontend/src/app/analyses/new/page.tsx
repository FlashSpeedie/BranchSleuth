"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { RepositoryOut, AnalysisOptions, RefOut } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";

const DEFAULT_OPTIONS: AnalysisOptions = {
  run_baseline_tests: true,
  run_modified_tests: true,
  collect_coverage: true,
  targeted_verification: true,
  hypothesis_max_examples: 60,
  hypothesis_deadline_ms: 2000,
  property_code: "",
  property_target: "",
};

function NewAnalysisPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectedRepo = searchParams.get("repo");

  const [repos, setRepos] = useState<RepositoryOut[]>([]);
  const [refs, setRefs] = useState<RefOut[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(true);
  const [loadingRefs, setLoadingRefs] = useState(false);
  const [repoId, setRepoId] = useState(preselectedRepo || "");
  const [baselineRef, setBaselineRef] = useState("");
  const [targetRef, setTargetRef] = useState("");
  const [options, setOptions] = useState<AnalysisOptions>(DEFAULT_OPTIONS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listRepositories(100).then(d => {
      setRepos(d.items);
      if (preselectedRepo && !d.items.find(r => r.id === preselectedRepo)) {
        setRepoId(d.items[0]?.id || "");
      }
    }).finally(() => setLoadingRepos(false));
  }, []);

  useEffect(() => {
    if (!repoId) { setRefs([]); return; }
    setLoadingRefs(true);
    api.listRefs(repoId).then(setRefs).finally(() => setLoadingRefs(false));
  }, [repoId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!repoId) return;
    setLoading(true);
    setError(null);
    try {
      const run = await api.createAnalysis({
        repository_id: repoId,
        baseline_ref: baselineRef || null,
        target_ref: targetRef || null,
        options: { ...options },
      });
      router.push(`/analyses/${run.id}`);
    } catch (e: any) {
      setError(e.message || "Failed to create analysis");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold mb-6">New analysis</h1>
      <form onSubmit={handleSubmit} className="panel p-6 space-y-6">
        <div>
          <label className="block text-sm font-medium mb-2">Repository <span className="text-rose-400">*</span></label>
          {loadingRepos ? (
            <select disabled className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-slate-500">
              <option>Loading...</option>
            </select>
          ) : (
            <select
              value={repoId}
              onChange={e => { setRepoId(e.target.value); setBaselineRef(""); setTargetRef(""); }}
              className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              required
            >
              <option value="">Select repository</option>
              {repos.map(r => (
                <option key={r.id} value={r.id}>{r.name} ({r.source_type})</option>
              ))}
            </select>
          )}
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="block text-sm font-medium mb-2">Baseline ref</label>
            <select
              value={baselineRef}
              onChange={e => setBaselineRef(e.target.value)}
              disabled={loadingRefs}
              className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
            >
              <option value="">Auto (parent of target)</option>
              {refs.map(r => (
                <option key={r.sha} value={r.name}>{r.name} ({r.sha.slice(0, 8)})</option>
              ))}
            </select>
            <p className="text-xs text-slate-500 mt-1">Defaults to parent of target commit</p>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Target ref <span className="text-rose-400">*</span></label>
            <select
              value={targetRef}
              onChange={e => setTargetRef(e.target.value)}
              disabled={loadingRefs}
              className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              required
            >
              <option value="">Select target revision</option>
              {refs.map(r => (
                <option key={r.sha} value={r.name}>{r.name} ({r.sha.slice(0, 8)})</option>
              ))}
            </select>
            <p className="text-xs text-slate-500 mt-1">Defaults to default branch HEAD</p>
          </div>
        </div>

        <details className="border-t border-[#1e2633] pt-6">
          <summary className="cursor-pointer font-medium text-emerald-400">Analysis options</summary>
          <div className="mt-4 space-y-4 text-sm">
            <div className="flex items-center gap-3">
              <input type="checkbox" id="run_baseline_tests" checked={options.run_baseline_tests} onChange={e => setOptions(o => ({ ...o, run_baseline_tests: e.target.checked }))} className="w-4 h-4 accent-emerald-500" />
              <label htmlFor="run_baseline_tests" className="cursor-pointer">Run baseline test suite</label>
            </div>
            <div className="flex items-center gap-3">
              <input type="checkbox" id="run_modified_tests" checked={options.run_modified_tests} onChange={e => setOptions(o => ({ ...o, run_modified_tests: e.target.checked }))} className="w-4 h-4 accent-emerald-500" />
              <label htmlFor="run_modified_tests" className="cursor-pointer">Run modified test suite</label>
            </div>
            <div className="flex items-center gap-3">
              <input type="checkbox" id="collect_coverage" checked={options.collect_coverage} onChange={e => setOptions(o => ({ ...o, collect_coverage: e.target.checked }))} className="w-4 h-4 accent-emerald-500" />
              <label htmlFor="collect_coverage" className="cursor-pointer">Collect per-test coverage</label>
            </div>
            <div className="flex items-center gap-3">
              <input type="checkbox" id="targeted_verification" checked={options.targeted_verification} onChange={e => setOptions(o => ({ ...o, targeted_verification: e.target.checked }))} className="w-4 h-4 accent-emerald-500" />
              <label htmlFor="targeted_verification" className="cursor-pointer">Targeted verification (Hypothesis)</label>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label className="block text-sm font-medium mb-1">Hypothesis max examples</label>
                <input type="number" min="1" max="500" value={options.hypothesis_max_examples} onChange={e => setOptions(o => ({ ...o, hypothesis_max_examples: parseInt(e.target.value) }))} className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/50" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Hypothesis deadline (ms)</label>
                <input type="number" min="50" max="60000" value={options.hypothesis_deadline_ms} onChange={e => setOptions(o => ({ ...o, hypothesis_deadline_ms: parseInt(e.target.value) }))} className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/50" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Property code (optional)</label>
              <textarea value={options.property_code || ""} onChange={e => setOptions(o => ({ ...o, property_code: e.target.value }))} rows={4} className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 mono text-xs" placeholder="def check(kwargs, outcome):\n    subtotal = kwargs['subtotal']\n    if outcome['kind'] != 'return':\n        return False\n    if subtotal <= 100:\n        return outcome['value'] == subtotal\n    return math.isclose(outcome['value'], subtotal * 0.9, rel_tol=1e-9)" />
              <p className="text-xs text-slate-500 mt-1">
                Define <code className="mono">check(kwargs, outcome)</code> returning bool.{" "}
                <code>outcome</code> is <code>{`{kind: "return", value: ...}`}</code> or{" "}
                <code>{`{kind: "exception", ...}`}</code>.
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Property target (optional)</label>
              <input type="text" value={options.property_target || ""} onChange={e => setOptions(o => ({ ...o, property_target: e.target.value }))} placeholder="tinyshop/pricing.py::apply_discount" className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50" />
              <p className="text-xs text-slate-500 mt-1">Format: <code className="mono">path/file.py::qualname</code>. If set, property only applies to this function.</p>
            </div>
          </div>
        </details>

        {error && (
          <div className="p-3 rounded-md bg-rose-500/15 border border-rose-500/30 text-rose-300 text-sm">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-3 pt-4">
          <Link href="/analyses" className="px-4 py-2 rounded-md border border-[#1e2633] text-slate-300 hover:bg-[#161b26]">Cancel</Link>
          <button type="submit" disabled={loading} className="px-4 py-2 rounded-md bg-emerald-500 hover:bg-emerald-400 text-[#0b0e14] font-semibold disabled:opacity-50">
            {loading ? "Creating..." : "Start analysis"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function NewAnalysisPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-400"></div></div>}>
      <NewAnalysisPageContent />
    </Suspense>
  );
}