import type { WordForm } from "../api/types";
import { buildInflection } from "../api/inflection";
import type { GridColumn } from "../api/inflection";
import { gramEl } from "../api/labels";

// Collapse consecutive same-group columns into colspan bands for the top header.
function bandSpans(columns: GridColumn[]): { group: string; span: number }[] {
  const bands: { group: string; span: number }[] = [];
  for (const c of columns) {
    const last = bands[bands.length - 1];
    if (last && last.group === c.group) last.span += 1;
    else bands.push({ group: c.group, span: 1 });
  }
  return bands;
}

export default function InflectionTables({
  pos,
  forms,
  lemma,
}: {
  pos: string | null;
  forms: WordForm[];
  lemma?: string;
}) {
  const { grids, nonFinite, other } = buildInflection(pos, forms, lemma);

  if (grids.length === 0 && nonFinite.length === 0 && other.length === 0) return null;

  return (
    <div className="flex flex-col gap-5">
      {grids.map((grid, gi) => (
        <div key={grid.title ?? `grid-${gi}`}>
          {grid.title && (
            <h4 className="mb-1.5 text-sm font-semibold text-slate-600 dark:text-slate-300">{grid.title}</h4>
          )}
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                {grid.columns.some((c) => c.group) && (
                  // Aspect band (ποιόν ενέργειας): groups consecutive columns,
                  // e.g. Εξακολουθητικοί | Συνοπτικοί | Προστακτική.
                  <tr className="text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
                    <th className="py-1 pr-4 font-medium" />
                    {bandSpans(grid.columns).map((b, bi) => (
                      <th
                        key={`band-${bi}`}
                        colSpan={b.span}
                        className="border-b border-slate-100 py-1 pr-4 text-left font-semibold dark:border-slate-800"
                      >
                        {b.group}
                      </th>
                    ))}
                  </tr>
                )}
                <tr className="border-b border-slate-200 text-xs uppercase text-slate-400 dark:border-slate-700 dark:text-slate-500">
                  <th className="py-1 pr-4 font-medium" />
                  {grid.columns.map((c, ci) => (
                    <th key={`${c.label}-${ci}`} className="py-1 pr-4 font-medium">
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {grid.rows.map((r) => (
                  <tr key={r.label} className="border-b border-slate-50 dark:border-slate-800">
                    <th className="py-1 pr-4 text-left text-xs font-medium uppercase text-slate-400 dark:text-slate-500">
                      {r.label}
                    </th>
                    {r.cells.map((cell, ci) => (
                      <td key={ci} className={`py-1 pr-4 ${cell.text ? "font-medium" : "text-slate-300 dark:text-slate-600"}`}>
                        {cell.text ? (
                          cell.generated ? (
                            <span
                              title="Αλγοριθμικά παραγόμενος τύπος — όχι από πηγή"
                              className="cursor-help decoration-dotted decoration-slate-300 underline-offset-4 [text-decoration-line:underline] dark:decoration-slate-600"
                            >
                              {cell.text}
                              <sup className="ml-0.5 text-slate-400 dark:text-slate-500">*</sup>
                            </span>
                          ) : (
                            cell.text
                          )
                        ) : (
                          "—"
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {grid.sources.length > 0 && (
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">Πηγή: {grid.sources.join(", ")}</p>
          )}
          {grid.hasGenerated && (
            <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
              <span className="text-slate-400 dark:text-slate-500">*</span> αλγοριθμικά παραγόμενος τύπος (μηχανή κλίσης), όχι από πηγή
            </p>
          )}
        </div>
      ))}

      {nonFinite.length > 0 && <FormListTable title="Μετοχές & απαρέμφατο" forms={nonFinite} />}
      {other.length > 0 && <FormListTable title="Άλλοι τύποι" forms={other} />}
    </div>
  );
}

// A flat "form → features → source" table, used for non-paradigmatic forms
// (participles/infinitives, and the catch-all so no form is ever lost).
function FormListTable({ title, forms }: { title: string; forms: WordForm[] }) {
  return (
    <div>
      <h4 className="mb-1.5 text-sm font-semibold text-slate-600 dark:text-slate-300">{title}</h4>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs uppercase text-slate-400 dark:border-slate-700 dark:text-slate-500">
            <th className="py-1 pr-4 font-medium">Τύπος</th>
            <th className="py-1 pr-4 font-medium">Χαρακτηριστικά</th>
            <th className="py-1 font-medium">Πηγή</th>
          </tr>
        </thead>
        <tbody>
          {forms.map((f, i) => (
            <tr key={`${f.form}-${i}`} className="border-b border-slate-50 dark:border-slate-800">
              <td className="py-1 pr-4 font-medium">{f.form}</td>
              <td className="py-1 pr-4 text-slate-500 dark:text-slate-400">{f.features.map(gramEl).join(", ")}</td>
              <td className="py-1 text-slate-400 dark:text-slate-500">{f.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
