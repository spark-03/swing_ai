import { supabase } from "./supabaseClient";
import { mockDashboardData } from "./mockData";
import type {
  DashboardData,
  OpenPosition,
  PortfolioSnapshot,
  PqsRanking,
  RotationRow,
  TradeHistoryRow
} from "../types/trading";

async function fetchTable<T>(table: string, orderColumn = "timestamp"): Promise<T[]> {
  if (!supabase) return [];

  const { data, error } = await supabase
    .from(table)
    .select("*")
    .order(orderColumn, { ascending: false })
    .limit(250);

  if (error) throw error;
  return (data ?? []) as T[];
}

export async function loadDashboardData(): Promise<DashboardData> {
  if (!supabase) {
    return mockDashboardData;
  }

  try {
    const [snapshots, trades, rotations, positions, rankings] = await Promise.all([
      fetchTable<PortfolioSnapshot>("portfolio_snapshots"),
      fetchTable<TradeHistoryRow>("paper_trades"),
      fetchTable<RotationRow>("rotation_log"),
      fetchTable<OpenPosition>("open_positions"),
      fetchTable<PqsRanking>("pqs_rankings", "rank")
    ]);

    const snapshot = snapshots[0] ?? mockDashboardData.snapshot;
    const normalizedPositions: OpenPosition[] = positions.map((p) => ({
      ...p,
      current_price: p.current_price ?? p.entry_price
    }));

    return {
      snapshot,
      positions: normalizedPositions.length > 0 ? normalizedPositions : mockDashboardData.positions,
      trades: trades.length > 0 ? trades : mockDashboardData.trades,
      rotations: rotations.length > 0 ? rotations : mockDashboardData.rotations,
      rankings: rankings.length > 0 ? rankings : mockDashboardData.rankings,
      metrics: mockDashboardData.metrics,
      logs: mockDashboardData.logs
    };
  } catch (err) {
    console.error("Failed to fetch live Supabase rows, falling back to cache:", err);
    return mockDashboardData;
  }
}
