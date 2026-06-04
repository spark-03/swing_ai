import { AlertTriangle, Pause, Play, RotateCcw, ShieldAlert } from "lucide-react";
import type { TradingMode } from "../types/trading";

const controlButton =
  "flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-4 text-xs font-semibold tracking-wider uppercase text-slate-400 transition-all duration-200 hover:border-[#D2A24C]/50 hover:bg-white/5 hover:text-white disabled:cursor-not-allowed disabled:opacity-40";

export function ControlPanel() {
  const modes: TradingMode[] = ["Research", "Backtest", "Paper Trading", "Live Trading"];

  return (
    <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {/* Engine Core Execution Block */}
      <div className="rounded-3xl border border-white/10 bg-white/[0.02] p-5 backdrop-blur-md">
        <h2 className="text-lg font-bold tracking-tight text-white font-serif">Bot Control</h2>
        <p className="mt-1 text-xs text-slate-500">Backend mutation controls require explicit execution authority.</p>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <button className={controlButton} disabled><Play className="mb-2 h-5 w-5 text-[#67E8A5]" />Start Bot</button>
          <button className={controlButton} disabled><Pause className="mb-2 h-5 w-5 text-slate-400" />Stop Bot</button>
          <button className={controlButton} disabled><RotateCcw className="mb-2 h-5 w-5 text-[#D2A24C]" />Force Cycle</button>
          <button className={controlButton} disabled><ShieldAlert className="mb-2 h-5 w-5 text-blue-400" />Safe Mode</button>
        </div>
      </div>

      {/* Model Routine Toggle States */}
      <div className="rounded-3xl border border-white/10 bg-white/[0.02] p-5 backdrop-blur-md">
        <h2 className="text-lg font-bold tracking-tight text-white font-serif">Trading Mode</h2>
        <p className="mt-1 text-xs text-slate-500">Active behavioral environment selection parameters.</p>
        <div className="mt-5 grid gap-2">
          {modes.map((mode) => {
            const isActive = mode === "Paper Trading";
            return (
              <button 
                className={`w-full rounded-2xl border px-4 py-3 text-left text-xs font-semibold tracking-wider uppercase transition-all duration-200 ${
                  isActive 
                    ? "border-[#D2A24C] bg-[#D2A24C]/10 text-[#D2A24C]" 
                    : "border-white/5 bg-black/20 text-slate-500 cursor-not-allowed"
                }`}
                disabled={!isActive}
                key={mode}
              >
                <div className="flex items-center justify-between">
                  <span>{mode}</span>
                  {isActive && <span className="h-1.5 w-1.5 rounded-full bg-[#D2A24C] animate-pulse" />}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* High-Risk Isolation Switches */}
      <div className="rounded-3xl border border-[#FF6B6B]/20 bg-[#FF6B6B]/5 p-5 backdrop-blur-md md:col-span-2 lg:col-span-1">
        <h2 className="flex items-center gap-2 text-lg font-bold tracking-tight text-white font-serif">
          <AlertTriangle className="h-5 w-5 text-[#FF6B6B]" /> Emergency Controls
        </h2>
        <p className="mt-1 text-xs text-slate-400">Confirmation-gated safety procedures to protect capital states.</p>
        <div className="mt-5 grid gap-2">
          {["Close All Positions", "Disable Entries", "Disable Rotations"].map((label) => (
            <button 
              className="w-full rounded-2xl border border-[#FF6B6B]/30 bg-[#FF6B6B]/10 px-4 py-3 text-left text-xs font-bold tracking-wider uppercase text-[#FF6B6B] transition-all duration-200 hover:bg-[#FF6B6B]/20 disabled:cursor-not-allowed disabled:opacity-40"
              disabled
              key={label}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
