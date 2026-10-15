"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface DiffViewerProps {
  runId: string;
  fileId: string;
}

export default function DiffViewer({ runId, fileId }: DiffViewerProps) {
  const [diff, setDiff] = useState<string>("Loading...");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getFileDiff(runId, fileId)
      .then(setDiff)
      .catch(e => setError(e.message))
      .finally(() => {});
  }, [runId, fileId]);

  if (error) {
    return <div className="p-4 text-rose-400 text-sm">Failed to load diff: {error}</div>;
  }

  const lines = diff.split("\n");
  return (
    <div className="h-[500px] overflow-auto bg-[#080a0f] rounded-md border border-[#1e2633] font-mono text-sm">
      {lines.map((line, i) => (
        <div key={i} className={`px-4 py-0.5 border-b border-[#1e2633]/50 ${line.startsWith("+") ? "diff-add" : line.startsWith("-") ? "diff-del" : "diff-ctx"}`}>
          <span className="mr-4 text-slate-500 w-8 text-right select-none">{i + 1}</span>
          <span className="whitespace-pre-wrap">{line || " "}</span>
        </div>
      ))}
    </div>
  );
}