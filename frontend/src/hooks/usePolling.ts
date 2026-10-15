"use client";

import { useEffect, useRef, useState } from "react";

export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number | null): {
  data: T | null;
  error: string | null;
  loading: boolean;
} {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const result = await fetcherRef.current();
        if (active) {
          setData(result);
          setError(null);
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (active) {
          setLoading(false);
          if (intervalMs !== null) {
            timer = setTimeout(tick, intervalMs);
          }
        }
      }
    };

    tick();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [intervalMs]);

  return { data, error, loading };
}
