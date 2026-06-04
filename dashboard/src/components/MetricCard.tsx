import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value: string;
  detail?: string;
  icon?: ReactNode;
}

export function MetricCard({ label, value, detail, icon }: MetricCardProps) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-2xl backdrop-blur-xl transition-all duration-300 hover:border-white/20 hover:bg-white/[0.05]">
      <div className="flex items-center justify-between text-slate-400">
        <span className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">{label}</span>
        <div className="rounded-xl bg-white/5 p-2 border border-white/5 shadow-inner">
          {icon}
        </div>
      </div>
      <div className="mt-4 font-mono text-3xl font-bold tracking-tight text-white">{value}</div>
      {detail ? <div className="mt-2 text-xs font-medium text-slate-500 tracking-wide">{detail}</div> : null}
    </div>
  );
}
