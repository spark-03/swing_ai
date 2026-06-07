import React, { useEffect, useState, useCallback } from 'react';
import { createClient } from '@supabase/supabase-js';
import {
  TrendingUp, ShieldAlert, Layers, RefreshCw, AlertTriangle,
  ArrowUpRight, ArrowDownRight, Clock, DollarSign, BarChart3
} from 'lucide-react';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || "";
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY || "";
const supabase = (supabaseUrl && supabaseKey) ? createClient(supabaseUrl, supabaseKey) : null;

function formatCurrency(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDateTime(isoString) {
  if (!isoString) return 'N/A';
  try {
    const d = new Date(isoString);
    return d.toLocaleString('en-IN', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return isoString;
  }
}

export default function App() {
  const [positions, setPositions] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [pqsRankings, setPqsRankings] = useState({});
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  const syncLiveCloudData = useCallback(async () => {
    if (!supabase) {
      setErrorMsg('Supabase not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.');
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setErrorMsg('');

      // 1. Fetch open positions with latest data
      const { data: positionsData, error: posError } = await supabase
        .from('open_positions')
        .select('*')
        .order('timestamp', { ascending: false });

      if (posError) throw posError;

      // 2. Fetch dashboard metrics
      const { data: metricsData, error: metError } = await supabase
        .from('dashboard_metrics')
        .select('*')
        .maybeSingle();

      if (metError) throw metError;

      // 3. Fetch latest PQS rankings (for dynamic PQS scores)
      const { data: rankingsData, error: rankError } = await supabase
        .from('pqs_rankings')
        .select('symbol, pqs')
        .order('rank', { ascending: true })
        .limit(100);

      if (rankError) throw rankError;

      // Index rankings by symbol for quick lookup
      const rankingsMap = {};
      if (rankingsData) {
        rankingsData.forEach(r => {
          rankingsMap[r.symbol] = r.pqs;
        });
      }

      // Deduplicate positions by symbol (keep latest entry for each)
      const uniquePositions = [];
      const seenSymbols = new Set();
      if (positionsData) {
        for (const pos of positionsData) {
          if (!seenSymbols.has(pos.symbol)) {
            seenSymbols.add(pos.symbol);
            // Attach dynamic PQS from rankings table
            pos.dynamic_pqs = rankingsMap[pos.symbol] || pos.pqs;
            uniquePositions.push(pos);
          }
        }
      }

      setPositions(uniquePositions);
      setPqsRankings(rankingsMap);
      setMetrics(metricsData || {
        portfolio_value: 1000000.0,
        trades_executed: 0,
        exits_triggered: 0,
        last_processed_slot: 'None Running',
        active_positions: 0,
      });
    } catch (err) {
      console.error('Dashboard sync error:', err);
      setErrorMsg(`Sync failed: ${err.message || err}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    syncLiveCloudData();
    const interval = setInterval(syncLiveCloudData, 60000);
    return () => clearInterval(interval);
  }, [syncLiveCloudData]);

  if (loading && positions.length === 0) {
    return (
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        height: '100vh', background: '#0f172a', color: '#38bdf8',
        fontFamily: 'sans-serif',
      }}>
        <h3>Connecting to Live Trading Data...</h3>
      </div>
    );
  }

  const totalInvested = positions.reduce((sum, p) => sum + (p.entry_price * p.quantity), 0);
  const totalMarketValue = positions.reduce((sum, p) => {
    const price = p.current_price || p.entry_price;
    return sum + (price * p.quantity);
  }, 0);
  const totalUnrealizedPnL = totalMarketValue - totalInvested;
  const totalUnrealizedPnLPct = totalInvested > 0 ? (totalUnrealizedPnL / totalInvested) * 100 : 0;

  return (
    <div style={{
      padding: '32px', fontFamily: 'system-ui, sans-serif',
      background: '#0f172a', color: '#f8fafc', minHeight: '100vh',
    }}>
      {/* Header */}
      <header style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        borderBottom: '1px solid #334155', paddingBottom: '20px',
      }}>
        <div>
          <h1 style={{ margin: 0, color: '#38bdf8', letterSpacing: '-0.025em' }}>
            AI Swing Trading Dashboard
          </h1>
          <p style={{ margin: '6px 0 0 0', color: '#94a3b8' }}>
            Slot Tracker: <code style={{
              background: '#1e293b', padding: '2px 6px', borderRadius: '4px',
              color: '#f43f5e',
            }}>{metrics?.last_processed_slot || 'N/A'}</code>
            {' | '}Holdings: {positions.length} / 3
          </p>
        </div>
        <button onClick={syncLiveCloudData} style={{
          background: '#1e293b', border: '1px solid #475569', color: '#fff',
          padding: '10px 20px', borderRadius: '6px', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: '8px', fontWeight: '500',
        }}>
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </header>

      {errorMsg && (
        <div style={{
          background: '#451a03', border: '1px solid #9a3412', color: '#f97316',
          padding: '16px', borderRadius: '8px', margin: '24px 0',
          display: 'flex', alignItems: 'center', gap: '12px',
        }}>
          <AlertTriangle size={20} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Summary Cards */}
      <section style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '20px', margin: '32px 0',
      }}>
        <div style={{
          background: '#1e293b', padding: '24px', borderRadius: '12px',
          border: '1px solid #334155',
        }}>
          <div style={{ display: 'flex', color: '#38bdf8', gap: '8px', alignItems: 'center', fontSize: '14px', fontWeight: '600' }}>
            <DollarSign size={18} /> <span>PORTFOLIO VALUE</span>
          </div>
          <h2 style={{ fontSize: '28px', margin: '12px 0 0 0', fontWeight: '700' }}>
            {formatCurrency(metrics?.portfolio_value || 1000000)}
          </h2>
        </div>

        <div style={{
          background: '#1e293b', padding: '24px', borderRadius: '12px',
          border: '1px solid #334155',
        }}>
          <div style={{ display: 'flex', color: '#4ade80', gap: '8px', alignItems: 'center', fontSize: '14px', fontWeight: '600' }}>
            <BarChart3 size={18} /> <span>UNREALIZED P&L</span>
          </div>
          <h2 style={{
            fontSize: '28px', margin: '12px 0 0 0', fontWeight: '700',
            color: totalUnrealizedPnL >= 0 ? '#4ade80' : '#f43f5e',
          }}>
            {totalUnrealizedPnL >= 0 ? '+' : ''}{totalUnrealizedPnLPct.toFixed(2)}%
            <span style={{ fontSize: '16px', color: '#64748b', fontWeight: '400', display: 'block' }}>
              {formatCurrency(totalUnrealizedPnL)}
            </span>
          </h2>
        </div>

        <div style={{
          background: '#1e293b', padding: '24px', borderRadius: '12px',
          border: '1px solid #334155',
        }}>
          <div style={{ display: 'flex', color: '#f43f5e', gap: '8px', alignItems: 'center', fontSize: '14px', fontWeight: '600' }}>
            <ShieldAlert size={18} /> <span>RL EXITS</span>
          </div>
          <h2 style={{ fontSize: '28px', margin: '12px 0 0 0', fontWeight: '700' }}>
            {metrics?.exits_triggered || 0}
          </h2>
        </div>
      </section>

      {/* Positions Table */}
      <section style={{
        background: '#1e293b', borderRadius: '12px', border: '1px solid #334155',
        padding: '24px', overflowX: 'auto',
      }}>
        <h3 style={{ marginTop: 0, marginBottom: '20px', color: '#94a3b8', fontSize: '18px' }}>
          Live Open Positions
        </h3>

        {positions.length === 0 ? (
          <p style={{ color: '#64748b', margin: '16px 0' }}>
            No open positions. Waiting for the trading engine to pick stocks.
          </p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: '800px' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #334155', color: '#94a3b8', fontSize: '12px', textTransform: 'uppercase' }}>
                <th style={{ padding: '14px' }}>Symbol</th>
                <th style={{ padding: '14px' }}>Entry Date & Time</th>
                <th style={{ padding: '14px' }}>Entry Price</th>
                <th style={{ padding: '14px' }}>Qty</th>
                <th style={{ padding: '14px' }}>Current Price</th>
                <th style={{ padding: '14px' }}>Unrealized P&L</th>
                <th style={{ padding: '14px' }}>P&L %</th>
                <th style={{ padding: '14px' }}>PQS Score</th>
                <th style={{ padding: '14px' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos, idx) => {
                const entryPrice = parseFloat(pos.entry_price) || 0;
                const currentPrice = parseFloat(pos.current_price) || entryPrice;
                const quantity = parseInt(pos.quantity) || 0;
                const costBasis = entryPrice * quantity;
                const marketValue = currentPrice * quantity;
                const unrealizedPnL = marketValue - costBasis;
                const unrealizedPnLPct = costBasis > 0 ? (unrealizedPnL / costBasis) * 100 : 0;
                const pqsScore = pos.dynamic_pqs || pos.pqs || 0;

                return (
                  <tr key={pos.symbol || idx} style={{ borderBottom: '1px solid #334155', fontSize: '14px' }}>
                    <td style={{ padding: '14px', fontWeight: '700', color: '#f1f5f9' }}>
                      {pos.symbol}
                    </td>
                    <td style={{ padding: '14px', color: '#94a3b8', fontSize: '13px' }}>
                      {formatDateTime(pos.entry_timestamp)}
                    </td>
                    <td style={{ padding: '14px' }}>
                      {formatCurrency(entryPrice)}
                    </td>
                    <td style={{ padding: '14px', color: '#cbd5e1' }}>
                      {quantity}
                    </td>
                    <td style={{ padding: '14px', fontWeight: '600', color: '#38bdf8' }}>
                      {formatCurrency(currentPrice)}
                    </td>
                    <td style={{
                      padding: '14px', fontWeight: '600',
                      color: unrealizedPnL >= 0 ? '#4ade80' : '#f43f5e',
                    }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        {unrealizedPnL >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
                        {formatCurrency(unrealizedPnL)}
                      </span>
                    </td>
                    <td style={{
                      padding: '14px', fontWeight: '600',
                      color: unrealizedPnLPct >= 0 ? '#4ade80' : '#f43f5e',
                    }}>
                      {unrealizedPnLPct >= 0 ? '+' : ''}{unrealizedPnLPct.toFixed(2)}%
                    </td>
                    <td style={{ padding: '14px', color: '#38bdf8', fontWeight: '600' }}>
                      {parseFloat(pqsScore).toFixed(2)}
                    </td>
                    <td style={{ padding: '14px' }}>
                      <span style={{
                        background: '#052e16', color: '#4ade80',
                        padding: '4px 10px', borderRadius: '9999px',
                        fontSize: '12px', fontWeight: '600',
                      }}>
                        {pos.status || 'OPEN'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* Last updated timestamp */}
      <div style={{ marginTop: '20px', color: '#64748b', fontSize: '12px', textAlign: 'right' }}>
        Auto-refreshes every 60 seconds
      </div>
    </div>
  );
}