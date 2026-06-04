import type { ReactNode } from "react";

interface DataTableProps<T> {
  title: string;
  rows: T[];
  columns: Array<{\n    key: string;\n    header: string;\n    render: (row: T) => ReactNode;\n  }>;\n}

export function DataTable<T>({ title, rows, columns }: DataTableProps<T>) {
  return (
    <section className="rounded-3xl border border-white/10 bg-[#101820]/60 p-6 shadow-2xl backdrop-blur-xl">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-xl font-bold tracking-tight text-white font-serif">{title}</h2>
        <span className="rounded-xl bg-white/5 px-3 py-1 text-xs font-mono font-semibold text-slate-400 border border-white/5">
          {rows.length} records
        </span>
      </div>
      <div className="overflow-x-auto scrollbar-thin scrollbar-thumb-white/10">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">
            <tr>
              {columns.map((column) => (
                <th className="border-b border-white/10 pb-4 font-semibold" key={column.key}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 text-slate-300">
            {rows.map((row, index) => (
              <tr className="group transition-colors duration-150 hover:bg-white/[0.02]" key={index}>
                {columns.map((column) => (
                  <td className="py-4 text-sm font-normal group-hover:text-white" key={column.key}>
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
