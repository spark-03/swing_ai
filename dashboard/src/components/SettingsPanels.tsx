const inputClass = "w-full rounded-2xl border border-white/5 bg-black/40 px-4 py-3 font-mono text-sm text-[#D2A24C]/90 shadow-inner outline-none placeholder:text-slate-600";

function SettingsCard({ title, fields }: { title: string; fields: string[] }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.02] p-5 backdrop-blur-md">
      <h2 className="text-lg font-bold tracking-tight text-white font-serif mb-4">{title}</h2>
      <div className="grid gap-4">
        {fields.map((field) => (
          <label className="flex flex-col gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500" key={field}>
            {field}
            <input className={inputClass} disabled placeholder="SYSTEM ENFORCED" />
          </label>
        ))}
      </div>
    </div>
  );
}

export function SettingsPanels() {
  return (
    <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <SettingsCard title="Risk Management" fields={["Max Drawdown", "Max Position Size", "Max Exposure", "Max Open Positions"]} />
      <SettingsCard title="PQS Settings" fields={["Minimum PQS", "Top Candidates Count", "Rotation Threshold", "Rebalance Frequency"]} />
      <SettingsCard title="RL Settings" fields={["Confidence Threshold", "Hold Time", "Exit Aggressiveness"]} />
    </section>
  );
}
