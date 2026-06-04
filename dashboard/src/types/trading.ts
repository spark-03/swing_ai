export type HealthStatus = "green" | "yellow" | "red";
export type TradingMode = "Research" | "Backtest" | "Paper Trading" | "Live Trading";

export interface PortfolioSnapshot {
  timestamp: string;
  cash: number;
  equity: number;
  positions: number;
  daily_pnl: number;
}

export interface OpenPosition {
  symbol: string;
  entry_timestamp: string;
  entry_price: number;
  quantity: number;
  slot_capital: number;
  current_price: number;
  pqs: number;
  status: string;
}

export interface TradeHistoryRow {
  timestamp: string;
  symbol: string;
  action: "BUY" | "SELL" | "EXIT" | "ROTATION" | string;
  price: number;
  quantity: number;
  reason: string;
  rl_decision?: string;
}

export interface RotationRow {
  timestamp: string;
  old_symbol: string;
  new_symbol: string;
  old_tqs: number;
  new_tqs: number;
}

export interface PqsRanking {
  timestamp: string;
  rank: number;
  symbol: string;
  pqs: number;
  last_price: number;
}

export interface SystemMetrics {
  cycle_count: number;
  trades_executed: number;
  exits_triggered: number;
  rotations_triggered: number;
  active_positions: number;
  portfolio_value: number;
  last_processed_slot: string | null;
  last_cycle_completed_at: string | null;
  last_error: string | null;
}

export interface DashboardData {
  snapshot: PortfolioSnapshot;
  positions: OpenPosition[];
  trades: TradeHistoryRow[];
  rotations: RotationRow[];
  rankings: PqsRanking[];
  metrics: SystemMetrics;
  logs: string[];
}
