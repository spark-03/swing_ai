import type { HealthStatus } from "../types/trading";

const styles: Record<HealthStatus, string> = {
  green: "bg-[#67E8A5]/10 text-[#67E8A5] ring-[#67E8A5]/30",
  yellow: "bg-[#D2A24C]/10 text-[#D2A24C] ring-[#D2A24C]/30",
  red: "bg-[#FF6B6B]/10 text-[#FF6B6B] ring-[#FF6B6B]/30"
};

export function StatusPill({ status, label }: { status: HealthStatus; label: string }) {
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-mono tracking-wide ring-1 backdrop-blur-md ${styles[status]}`}>
      {label}
    </span>
  );
}
