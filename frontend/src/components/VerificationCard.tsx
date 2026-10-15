"use client";

import { useState } from "react";
import StatusBadge from "@/components/StatusBadge";
import type { VerificationAttemptOut } from "@/lib/types";

interface VerificationCardProps {
  attempt: VerificationAttemptOut;
}

export default function VerificationCard({ attempt }: VerificationCardProps) {
  const [expanded, setExpanded] = useState(false);

  const classificationColors = {
    PROVEN_FAILURE: "rose",
    BEHAVIOR_DIVERGENCE: "amber",
    VERIFIED_CHECK_PASSED: "emerald",
    INCONCLUSIVE: "slate",
    BASELINE_FAILURE: "violet",
    UNVERIFIED_RISK: "orange",
  } as const;

  return (
    <div className="panel p-5 border-l-4 border-l-rose-500/50">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="font-mono text-sky-400 text-sm">{attempt.function_qualname}</span>
            <span className="text-xs text-slate-500">{attempt.file_path}</span>
            <StatusBadge value={attempt.classification} />
            <span className="text-xs text-slate-500 px-2 py-0.5 bg-[#1e2633] rounded">{attempt.kind}</span>
          </div>
          <p className="text-slate-400 text-sm mt-2">{attempt.rationale}</p>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="px-3 py-1.5 text-xs text-slate-300 hover:text-white transition-colors"
        >
          {expanded ? "Hide details" : "Show details"}
        </button>
      </div>

      {expanded && (
        <div className="mt-4 space-y-4 border-t border-[#1e2633] pt-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <p className="text-xs text-slate-400">Input</p>
              <pre className="p-2 bg-[#080a0f] rounded text-xs text-slate-300 overflow-auto mono">
                {JSON.stringify(attempt.input_payload, null, 2) || "—"}
              </pre>
            </div>
            <div>
              <p className="text-xs text-slate-400">Baseline outcome</p>
              <pre className="p-2 bg-[#080a0f] rounded text-xs text-slate-300 overflow-auto mono">
                {JSON.stringify(attempt.baseline_outcome, null, 2) || "—"}
              </pre>
            </div>
            <div>
              <p className="text-xs text-slate-400">Modified outcome</p>
              <pre className="p-2 bg-[#080a0f] rounded text-xs text-slate-300 overflow-auto mono">
                {JSON.stringify(attempt.modified_outcome, null, 2) || "—"}
              </pre>
            </div>
            <div>
              <p className="text-xs text-slate-400">Reproducible</p>
              <StatusBadge value={attempt.reproducible ? "passed" : attempt.reproducible === false ? "failed" : "not_run"} />
            </div>
          </div>

          {attempt.property_code && (
            <div>
              <p className="text-xs text-slate-400 mb-1">Property code</p>
              <pre className="p-3 bg-[#080a0f] rounded text-xs text-emerald-300 overflow-auto mono">
                {attempt.property_code}
              </pre>
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2 text-xs">
            <div>
              <p className="text-slate-400">Examples run</p>
              <p>{attempt.detail?.examples_run !== undefined ? String(attempt.detail.examples_run) : "—"}</p>
            </div>
            <div>
              <p className="text-slate-400">Via</p>
              <p>{attempt.detail?.via ? String(attempt.detail.via) : "—"}</p>
            </div>
            <div>
              <p className="text-slate-400">Property checked</p>
              <p>{attempt.detail?.property_checked ? "Yes" : "No"}</p>
            </div>
            <div>
              <p className="text-slate-400">Property held</p>
              <p>{attempt.detail?.property_held ? "Yes" : attempt.detail?.property_held === false ? "No" : "—"}</p>
            </div>
            <div>
              <p className="text-slate-400">Boundary candidates</p>
              <p>{attempt.detail?.boundary_candidates !== undefined ? String(attempt.detail.boundary_candidates) : "—"}</p>
            </div>
          </div>

          {attempt.detail?.reason !== undefined && attempt.detail?.reason !== null && (
            <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded text-amber-300 text-sm">
              <p className="font-medium">Reason:</p>
              <p>{String(attempt.detail.reason)}</p>
            </div>
          )}

          <div>
            <p className="text-xs text-slate-400 mb-1">Environment</p>
            <pre className="p-2 bg-[#080a0f] rounded text-xs text-slate-300 overflow-auto mono">
              {JSON.stringify(attempt.environment, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}