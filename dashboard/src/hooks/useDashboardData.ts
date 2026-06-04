import { useEffect, useState } from "react";
import { loadDashboardData } from "../services/dashboardService";
import type { DashboardData } from "../types/trading";

export function useDashboardData(refreshMs = 60000) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function refresh() {
      try {
        const next = await loadDashboardData();
        if (mounted) {
          setData(next);
          setError(null);
        }
      } catch (err) {
        if (mounted) setError(err instanceof Error ? err.message : "Unknown dashboard database exception");
      } finally {
        if (mounted) setLoading(false);
      }
    }

    refresh();
    const timer = window.setInterval(refresh, refreshMs);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [refreshMs]);

  return { data, error, loading };
}
