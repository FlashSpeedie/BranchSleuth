"use client";

import type { JobEventOut } from "@/lib/types";

interface EventsTimelineProps {
  events: JobEventOut[];
}

export default function EventsTimeline({ events }: EventsTimelineProps) {
  if (events.length === 0) {
    return (
      <div className="text-center py-8 text-slate-400">
        No events recorded for this analysis.
      </div>
    );
  }

  const levelColors: Record<string, string> = {
    info: "text-sky-400",
    warn: "text-amber-400",
    error: "text-rose-400",
    debug: "text-slate-400",
  };

  return (
    <div className="space-y-3 max-h-[500px] overflow-auto">
      {events.map((e) => (
        <div key={e.id} className="flex gap-3 text-sm">
          <span className="text-slate-500 whitespace-nowrap shrink-0">
            {new Date(e.ts).toLocaleTimeString()}
          </span>
          <span className={`font-mono ${levelColors[e.level] || "text-slate-400"}`}>
            [{e.level.toUpperCase()}]
          </span>
          <span className="text-slate-300 flex-1 truncate">{e.message}</span>
          {e.stage && (
            <span className="px-2 py-0.5 text-xs bg-[#1e2633] rounded text-slate-500 shrink-0">
              {e.stage}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}