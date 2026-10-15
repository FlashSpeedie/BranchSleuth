const STATUS_STYLES: Record<string, string> = {
  queued: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  preparing: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  analyzing: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  verifying: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  completed: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  failed: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  cancelled: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  REGRESSION: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  PREEXISTING_FAILURE: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  FIXED: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  STABLE_PASS: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  ADDED_TEST: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  REMOVED_TEST: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  PROVEN_FAILURE: "bg-rose-500/20 text-rose-300 border-rose-500/40",
  BEHAVIOR_DIVERGENCE: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  UNVERIFIED_RISK: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  VERIFIED_CHECK_PASSED: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  INCONCLUSIVE: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  BASELINE_FAILURE: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  CHANGED_AND_EXECUTED: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  CHANGED_NOT_EXECUTED: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  COVERAGE_UNAVAILABLE: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  NO_NEW_EXECUTABLE_LINES: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  passed: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  error: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  skipped: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  not_run: "bg-slate-500/15 text-slate-400 border-slate-500/30",
};

export default function StatusBadge({ value, className = "" }: { value: string | null | undefined; className?: string }) {
  if (!value) return <span className={`chip bg-slate-500/10 text-slate-500 border-slate-500/20 ${className}`}>unknown</span>;
  const cls = STATUS_STYLES[value] ?? "bg-slate-500/15 text-slate-300 border-slate-500/30";
  return <span className={`chip border ${cls} ${className}`}>{value.replace(/_/g, " ").toLowerCase()}</span>;
}
