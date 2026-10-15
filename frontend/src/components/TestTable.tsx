"use client";

import StatusBadge from "@/components/StatusBadge";
import type { TestRecordOut } from "@/lib/types";

interface TestTableProps {
  tests: TestRecordOut[];
}

export default function TestTable({ tests }: TestTableProps) {
  if (tests.length === 0) {
    return (
      <div className="text-center py-8 text-slate-400">
        No tests recorded for this analysis.
      </div>
    );
  }

  const categories = {
    REGRESSION: "rose",
    PREEXISTING_FAILURE: "orange",
    FIXED: "emerald",
    STABLE_PASS: "slate",
    ADDED_TEST: "cyan",
    REMOVED_TEST: "amber",
    BASELINE_ONLY: "violet",
    TARGET_ONLY: "amber",
  } as const;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#1e2633] text-left text-slate-400">
            <th className="p-3 font-medium">Test</th>
            <th className="p-3 font-medium">Baseline</th>
            <th className="p-3 font-medium">Modified</th>
            <th className="p-3 font-medium">Category</th>
            <th className="p-3 font-medium">Duration</th>
            <th className="p-3 font-medium">Changed lines executed</th>
          </tr>
        </thead>
        <tbody>
          {tests.map(t => (
            <tr key={t.id} className="border-b border-[#1e2633]/50 hover:bg-[#161b26]">
              <td className="p-3 font-mono text-slate-300 truncate max-w-xs">{t.node_id}</td>
              <td className="p-3"><StatusBadge value={t.baseline_outcome} /></td>
              <td className="p-3"><StatusBadge value={t.modified_outcome} /></td>
              <td className="p-3">
                <StatusBadge value={t.category} />
              </td>
              <td className="p-3 text-slate-400">{t.duration_ms ? `${t.duration_ms.toFixed(1)}ms` : "—"}</td>
              <td className="p-3 text-slate-500 font-mono text-xs">
                {Object.entries(t.executed_changed_lines || {}).map(([file, lines]) => (
                  <span key={file}>{file}:{lines.join(",")}</span>
                )).join("; ") || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}