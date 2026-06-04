import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getDiachronic } from "../api/client";
import type { DiachronicResponse, DiachronicSeries, FreqPoint } from "../api/types";
import { eventsInRange } from "../api/events";

// Display names + colors per corpus. Two corpora are drawn as SEPARATE labeled
// lines and never merged — a frequency time series is only valid within one
// consistent corpus (Parliament = deep primary axis, news = parallel secondary).
const CORPUS_META: Record<string, { label: string; stroke: string; chip: string }> = {
  parliament: {
    label: "Κοινοβούλιο",
    stroke: "#6366f1", // indigo-500
    chip: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300",
  },
  news: {
    label: "Ειδήσεις",
    stroke: "#f59e0b", // amber-500
    chip: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  },
  wiki: {
    label: "Βικιπαίδεια",
    stroke: "#10b981", // emerald-500
    chip: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  },
  web: {
    label: "Ιστός",
    stroke: "#ec4899", // pink-500
    chip: "bg-pink-100 text-pink-800 dark:bg-pink-500/15 dark:text-pink-300",
  },
  literature: {
    label: "Λογοτεχνία",
    stroke: "#8b5cf6", // violet-500
    chip: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  },
};

function meta(corpus: string) {
  return (
    CORPUS_META[corpus] ?? {
      label: corpus,
      stroke: "#64748b",
      chip: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
    }
  );
}

// Inline SVG multi-line sparkline — no chart dependency (keeps the bundle lean,
// same approach as the frequency meter). Per-million is comparable across corpora
// (each year normalized by its slice's token total), so all series share one
// y-axis; the x-axis spans the union of every series' years.
const W = 460;
const H = 120;
const PAD = { l: 8, r: 8, t: 10, b: 18 };

function FrequencyChart({ series }: { series: DiachronicSeries[] }) {
  const withData = series.filter((s) => s.frequency.length > 0);
  if (withData.length === 0) return null;

  const allYears = withData.flatMap((s) => s.frequency.map((p) => p.year));
  const minYear = Math.min(...allYears);
  const maxYear = Math.max(...allYears);
  const maxVal = Math.max(
    1,
    ...withData.flatMap((s) => s.frequency.map((p) => p.per_million ?? 0)),
  );

  const xOf = (year: number) =>
    maxYear === minYear
      ? PAD.l + (W - PAD.l - PAD.r) / 2
      : PAD.l + ((year - minYear) / (maxYear - minYear)) * (W - PAD.l - PAD.r);
  const yOf = (val: number) =>
    H - PAD.b - (val / maxVal) * (H - PAD.t - PAD.b);

  // Historical-event markers (context, not causation) inside this word's span.
  const markers = eventsInRange(minYear, maxYear);

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Συχνότητα ανά έτος">
        {/* baseline */}
        <line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b}
          className="stroke-slate-200 dark:stroke-slate-700" strokeWidth={1} />
        {/* historical-event markers — vertical dashed lines (drawn behind series) */}
        {markers.map((e) => (
          <line key={e.year} x1={xOf(e.year)} y1={PAD.t} x2={xOf(e.year)} y2={H - PAD.b}
            className="stroke-slate-300 dark:stroke-slate-600" strokeWidth={1} strokeDasharray="2 3">
            <title>{`${e.year} — ${e.el}`}</title>
          </line>
        ))}
        {/* year ticks (first + last) */}
        <text x={PAD.l} y={H - 4} className="fill-slate-400 text-[10px]">{minYear}</text>
        <text x={W - PAD.r} y={H - 4} textAnchor="end" className="fill-slate-400 text-[10px]">{maxYear}</text>
        {withData.map((s) => {
          const m = meta(s.corpus);
          const pts = s.frequency.map((p) => `${xOf(p.year)},${yOf(p.per_million ?? 0)}`).join(" ");
          return (
            <g key={s.corpus}>
              <polyline points={pts} fill="none" stroke={m.stroke} strokeWidth={2}
                strokeLinejoin="round" strokeLinecap="round" />
              {s.frequency.map((p: FreqPoint) => (
                <circle key={p.year} cx={xOf(p.year)} cy={yOf(p.per_million ?? 0)} r={2} fill={m.stroke}>
                  <title>{`${m.label} · ${p.year}: ${(p.per_million ?? 0).toFixed(1)} ανά εκατ. λέξεις`}</title>
                </circle>
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// Semantic-trajectory chart (#35): cosine distance of each slice from the
// reference (first) slice, per corpus. Unlike the single first↔last drift number,
// this shows the SHAPE of change — a word that drifted then reverted dips back
// toward 0. The change-point year (steepest step) is ringed.
function TrajectoryChart({ series }: { series: DiachronicSeries[] }) {
  const withData = series.filter((s) => s.trajectory.length >= 2);
  if (withData.length === 0) return null;

  const allYears = withData.flatMap((s) => s.trajectory.map((p) => p.year));
  const minYear = Math.min(...allYears);
  const maxYear = Math.max(...allYears);
  const maxVal = Math.max(
    0.1,
    ...withData.flatMap((s) => s.trajectory.map((p) => p.distance_from_ref)),
  );

  const xOf = (year: number) =>
    maxYear === minYear
      ? PAD.l + (W - PAD.l - PAD.r) / 2
      : PAD.l + ((year - minYear) / (maxYear - minYear)) * (W - PAD.l - PAD.r);
  const yOf = (val: number) => H - PAD.b - (val / maxVal) * (H - PAD.t - PAD.b);

  const markers = eventsInRange(minYear, maxYear);

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Σημασιολογική τροχιά ανά έτος">
        <line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b}
          className="stroke-slate-200 dark:stroke-slate-700" strokeWidth={1} />
        {markers.map((e) => (
          <line key={e.year} x1={xOf(e.year)} y1={PAD.t} x2={xOf(e.year)} y2={H - PAD.b}
            className="stroke-slate-300 dark:stroke-slate-600" strokeWidth={1} strokeDasharray="2 3">
            <title>{`${e.year} — ${e.el}`}</title>
          </line>
        ))}
        <text x={PAD.l} y={H - 4} className="fill-slate-400 text-[10px]">{minYear}</text>
        <text x={W - PAD.r} y={H - 4} textAnchor="end" className="fill-slate-400 text-[10px]">{maxYear}</text>
        {withData.map((s) => {
          const m = meta(s.corpus);
          const cp = s.drift?.change_point_year ?? null;
          const pts = s.trajectory.map((p) => `${xOf(p.year)},${yOf(p.distance_from_ref)}`).join(" ");
          return (
            <g key={s.corpus}>
              <polyline points={pts} fill="none" stroke={m.stroke} strokeWidth={2}
                strokeLinejoin="round" strokeLinecap="round" />
              {s.trajectory.map((p) => (
                <g key={p.year}>
                  <circle cx={xOf(p.year)} cy={yOf(p.distance_from_ref)}
                    r={p.year === cp ? 4 : 2} fill={m.stroke}
                    stroke={p.year === cp ? m.stroke : "none"} strokeWidth={p.year === cp ? 1.5 : 0}
                    fillOpacity={p.year === cp ? 0.35 : 1}>
                    <title>
                      {`${m.label} · ${p.year}: απόσταση ${p.distance_from_ref.toFixed(3)} από το ${minYear}` +
                        (p.year === cp ? " — σημείο καμπής (μεγαλύτερη μεταβολή)" : "")}
                    </title>
                  </circle>
                </g>
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function DriftBadge({ s }: { s: DiachronicSeries }) {
  if (!s.drift) return null;
  const m = meta(s.corpus);
  const d = s.drift;
  const pct = Math.min(100, Math.round(d.drift_score * 100));
  // Endpoint-bootstrap 95% CI (#36) — present only after bootstrap_drift ran.
  const hasCi = d.drift_ci_lo != null && d.drift_ci_hi != null;
  const sig = d.drift_significant; // true | false | null
  const ciTitle = hasCi
    ? ` 95% διάστημα εμπιστοσύνης (bootstrap) ${d.drift_ci_lo!.toFixed(3)}–${d.drift_ci_hi!.toFixed(3)}.` +
      (sig === true
        ? " Στατιστικά σημαντική: η μετατόπιση ξεπερνά τον θόρυβο εκτίμησης της ίδιας λέξης."
        : sig === false
        ? " Μη σημαντική: εντός του θορύβου εκτίμησης σε αυτή τη συχνότητα."
        : "")
    : "";
  return (
    <div
      className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400"
      title={`Σημασιολογική μετατόπιση: απόσταση συνημιτόνου ${d.drift_score.toFixed(3)} μεταξύ ${d.first_year} και ${d.last_year} (${d.n_slices} τομές). Μεγαλύτερη = μεγαλύτερη αλλαγή στα συμφραζόμενα.${ciTitle}`}
    >
      <span className={`rounded px-1.5 py-0.5 font-medium ${m.chip}`}>{m.label}</span>
      <span>μετατόπιση {d.drift_score.toFixed(2)}</span>
      <span className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        <span className="block h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: m.stroke }} />
      </span>
      {hasCi && (
        <span className="text-slate-400 dark:text-slate-500">
          ±95% [{d.drift_ci_lo!.toFixed(2)}–{d.drift_ci_hi!.toFixed(2)}]
        </span>
      )}
      {sig === true && (
        <span
          className="rounded px-1.5 py-0.5 font-medium text-emerald-700 bg-emerald-100 dark:bg-emerald-500/15 dark:text-emerald-300"
          title="Η μετατόπιση ξεπερνά τον θόρυβο εκτίμησης της ίδιας λέξης (bootstrap)."
        >
          σημαντική
        </span>
      )}
      {sig === false && (
        <span
          className="rounded px-1.5 py-0.5 font-medium text-slate-500 bg-slate-100 dark:bg-slate-800 dark:text-slate-400"
          title="Εντός του θορύβου εκτίμησης σε αυτή τη συχνότητα — δεν ξεχωρίζει από τον θόρυβο (bootstrap)."
        >
          μη σημαντική
        </span>
      )}
      <span className="text-slate-400 dark:text-slate-500">{d.first_year}→{d.last_year}</span>
      {d.change_point_year != null ? (
        <span className="text-slate-400 dark:text-slate-500" title={
          d.change_point_score != null
            ? `Εμπιστοσύνη z=${d.change_point_score.toFixed(1)} (το βήμα ξεχωρίζει από τα υπόλοιπα)`
            : undefined
        }>· καμπή ~{d.change_point_year}</span>
      ) : (
        <span className="text-slate-400 dark:text-slate-500" title="Κανένα έτος δεν ξεχωρίζει στατιστικά ως σημείο καμπής (#44)">· χωρίς σαφές σημείο καμπής</span>
      )}
    </div>
  );
}

function NeighborChips({ items }: { items: { neighbor: string; score: number }[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((n, i) => (
        <Link
          key={i}
          to={`/word/${encodeURIComponent(n.neighbor)}`}
          title={`ομοιότητα ${(n.score * 100).toFixed(0)}%`}
          className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-xs text-violet-700 transition hover:border-violet-400 hover:bg-violet-100 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-300 dark:hover:border-violet-400"
        >
          {n.neighbor}
        </Link>
      ))}
    </div>
  );
}

// "Then ↔ now" company a word kept, within one corpus. Columns are labeled by the
// actual year (not the words "then/now") — when only one era has neighbors that
// labeling would otherwise mislead.
function EraNeighbors({ s }: { s: DiachronicSeries }) {
  const then = s.neighbors_then;
  const now = s.neighbors_now;
  if (!then && !now) return null;
  const m = meta(s.corpus);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${m.chip}`}>{m.label}</span>
        <span className="text-xs text-slate-400 dark:text-slate-500">σημασιολογικοί γείτονες ανά εποχή</span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {then && (
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{then.year}</span>
            <NeighborChips items={then.items} />
          </div>
        )}
        {now && (
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{now.year}</span>
            <NeighborChips items={now.items} />
          </div>
        )}
      </div>
    </div>
  );
}

// Diachronic evolution panel: how a word's frequency and meaning changed over
// time, per corpus. Fetches lazily on lemma change; renders nothing when a word
// has no diachronic data (most rare words), so it's safe to mount everywhere.
export default function DiachronicPanel({ lemma }: { lemma: string }) {
  const [data, setData] = useState<DiachronicResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    getDiachronic(lemma)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      });
    return () => {
      cancelled = true;
    };
  }, [lemma]);

  if (!data) return null;
  const hasFreq = data.series.some((s) => s.frequency.length > 0);
  const driftSeries = data.series.filter((s) => s.drift);
  const trajSeries = data.series.filter((s) => s.trajectory.length >= 2);
  const eraSeries = data.series.filter((s) => s.neighbors_then || s.neighbors_now);
  if (!hasFreq && driftSeries.length === 0 && trajSeries.length === 0 && eraSeries.length === 0)
    return null;

  const legend = data.series.filter((s) => s.frequency.length > 0);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          Διαχρονική εξέλιξη
        </h3>
        {legend.length > 0 && (
          <span className="ml-auto flex flex-wrap gap-2">
            {legend.map((s) => {
              const m = meta(s.corpus);
              return (
                <span key={s.corpus} className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                  <span className="inline-block h-2 w-3 rounded-sm" style={{ backgroundColor: m.stroke }} />
                  {m.label}
                </span>
              );
            })}
          </span>
        )}
      </div>

      {hasFreq && (
        <div className="flex flex-col gap-1">
          <span className="text-xs text-slate-400 dark:text-slate-500">Συχνότητα ανά εκατομμύριο λέξεις</span>
          <FrequencyChart series={data.series} />
        </div>
      )}

      {trajSeries.length > 0 && (
        <div className="mt-4 flex flex-col gap-1">
          <span className="text-xs text-slate-400 dark:text-slate-500">
            Σημασιολογική τροχιά — απόσταση από την πρώτη τομή (το σχήμα της αλλαγής, όχι μόνο τα άκρα)
          </span>
          <TrajectoryChart series={data.series} />
        </div>
      )}

      {driftSeries.length > 0 && (
        <div className="mt-4 flex flex-col gap-1.5">
          {driftSeries.map((s) => (
            <DriftBadge key={s.corpus} s={s} />
          ))}
        </div>
      )}

      {eraSeries.length > 0 && (
        <div className="mt-4 flex flex-col gap-4 border-t border-slate-100 pt-4 dark:border-slate-800">
          {eraSeries.map((s) => (
            <EraNeighbors key={s.corpus} s={s} />
          ))}
        </div>
      )}
    </section>
  );
}
