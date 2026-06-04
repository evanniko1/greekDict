import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  getDriftInsights,
  getExploreByField,
  getExploreCompare,
  getExploreInteresting,
  getExploreOverview,
  getExploreTrends,
} from "../api/client";
import { domainEl } from "../api/labels";
import { eventsInRange } from "../api/events";
import type {
  ByFieldResponse,
  CompareResponse,
  DriftInsightsResponse,
  InterestingResponse,
  OverviewResponse,
  TrendsResponse,
} from "../api/types";

// ─────────────────────────────────────────────────────────────────────────────
// Λεξόραμα — exploration page. A discovery surface over the diachronic layers.
// Cardinal rule: corpora stay on SEPARATE axes everywhere; the only section that
// puts them together is "Σύγκριση", which is explicitly a comparison. Every change
// measure is literature-backed (cosine drift = Hamilton 2016; neighbor-overlap =
// Gonen 2020; frequency-gating controls the Dubossarsky 2017 bias; keyness =
// corpus-linguistics log-ratio).
// ─────────────────────────────────────────────────────────────────────────────

const CORPUS_META: Record<string, { label: string; stroke: string }> = {
  parliament: { label: "Κοινοβούλιο", stroke: "#6366f1" },
  news: { label: "Ειδήσεις", stroke: "#f59e0b" },
  wiki: { label: "Βικιπαίδεια", stroke: "#10b981" },
  web: { label: "Ιστός", stroke: "#ec4899" },
  literature: { label: "Λογοτεχνία", stroke: "#8b5cf6" },
};
// Corpus axes are no longer a fixed pair: any corpus with diachronic data shows up
// (each on its own axis, never merged). The available set is discovered at runtime
// from the overview endpoint; "parliament" is the default until that resolves.
type Corpus = string;
const DEFAULT_CORPUS = "parliament";

type SectionProps = {
  corpus: Corpus;
  onCorpus: (c: Corpus) => void;
  corpora: readonly string[];
};

function meta(c: string) {
  return CORPUS_META[c] ?? { label: c, stroke: "#64748b" };
}

function WordLink({ lemma, className = "" }: { lemma: string; className?: string }) {
  return (
    <Link
      to={`/word/${encodeURIComponent(lemma)}`}
      className={`font-medium text-slate-800 transition hover:text-violet-700 dark:text-slate-100 dark:hover:text-violet-300 ${className}`}
    >
      {lemma}
    </Link>
  );
}

// A labeled horizontal bar row used by most ranked lists. `value` drives the bar
// width relative to `max`; `display` is the number shown on the right.
function BarRow({
  rank,
  lemma,
  value,
  max,
  display,
  stroke,
  sub,
}: {
  rank?: number;
  lemma: string;
  value: number;
  max: number;
  display: string;
  stroke: string;
  sub?: string;
}) {
  const pct = max > 0 ? Math.round((Math.abs(value) / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2 rounded-md px-1 py-1 sm:gap-3">
      {rank != null && (
        <span className="w-5 shrink-0 text-right text-xs tabular-nums text-slate-400 dark:text-slate-600">{rank}</span>
      )}
      <span className="w-20 shrink-0 truncate text-sm sm:w-28" title={lemma}>
        <WordLink lemma={lemma} />
      </span>
      <span className="relative h-2 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${pct}%`, backgroundColor: stroke }} />
      </span>
      <span className="w-10 shrink-0 text-right text-xs tabular-nums text-slate-500 dark:text-slate-400 sm:w-12">{display}</span>
      {sub && <span className="hidden w-16 shrink-0 text-right text-xs tabular-nums text-slate-400 dark:text-slate-600 sm:inline">{sub}</span>}
    </div>
  );
}

function SectionCard({ id, title, blurb, children, aside }: {
  id: string;
  title: string;
  blurb: string;
  children: React.ReactNode;
  aside?: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold tracking-tight">{title}</h2>
          <p className="mt-0.5 max-w-2xl text-xs text-slate-500 dark:text-slate-400">{blurb}</p>
        </div>
        {aside}
      </div>
      {children}
    </section>
  );
}

function CorpusToggle({ value, onChange, options }: {
  value: Corpus;
  onChange: (c: Corpus) => void;
  options: readonly string[];
}) {
  if (options.length < 2) return null; // nothing to toggle with a single axis
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((c) => {
        const on = c === value;
        const m = meta(c);
        return (
          <button
            key={c}
            onClick={() => onChange(c)}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition ${
              on ? "border-transparent text-white" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            }`}
            style={on ? { backgroundColor: m.stroke } : undefined}
          >
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: on ? "#fff" : m.stroke }} />
            {m.label}
          </button>
        );
      })}
    </div>
  );
}

const Loading = () => <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-600">Φόρτωση…</p>;
const Empty = ({ msg }: { msg: string }) => <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-600">{msg}</p>;

// §1 — corpus overview / cumulative view ─────────────────────────────────────
function OverviewSection() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  useEffect(() => {
    getExploreOverview().then(setData).catch(() => setData(null));
  }, []);
  return (
    <SectionCard
      id="overview"
      title="Επισκόπηση σωμάτων κειμένων"
      blurb="Το μέγεθος των δύο σωμάτων κειμένων μέσα στον χρόνο — λέξεις ανά έτος και συνολικά. Δείχνει γιατί οι δύο άξονες δεν συγχωνεύονται: διαφορετική εποχή, διαφορετική κλίμακα. Οι κάθετες γραμμές σημειώνουν ιστορικά γεγονότα (πλαίσιο, όχι αιτιότητα)."
    >
      {!data ? <Loading /> : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {data.corpora.map((c) => {
            const m = meta(c.corpus);
            const maxTok = Math.max(1, ...c.points.map((p) => p.tokens));
            const W = 320, H = 60;
            const xOf = (i: number) => (c.points.length <= 1 ? W / 2 : (i / (c.points.length - 1)) * W);
            const yOf = (v: number) => H - (v / maxTok) * (H - 6);
            const pts = c.points.map((p, i) => `${xOf(i)},${yOf(p.tokens)}`).join(" ");
            const millions = (c.total_tokens / 1e6).toFixed(0);
            // Map an event year → x by locating the matching slice index.
            const yearIndex = new Map(c.points.map((p, i) => [p.year, i]));
            const markers = eventsInRange(c.first_year, c.last_year)
              .map((e) => ({ e, i: yearIndex.get(e.year) }))
              .filter((mk): mk is { e: typeof mk.e; i: number } => mk.i != null);
            return (
              <div key={c.corpus} className="rounded-lg border border-slate-100 p-3 dark:border-slate-800">
                <div className="mb-1 flex items-center gap-2">
                  <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: m.stroke }} />
                  <span className="font-semibold">{m.label}</span>
                  <span className="ml-auto text-xs text-slate-400 dark:text-slate-500">{c.first_year}–{c.last_year}</span>
                </div>
                <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Λέξεις ανά έτος με ιστορικά γεγονότα">
                  {markers.map((mk) => (
                    <line key={mk.e.year} x1={xOf(mk.i)} y1={2} x2={xOf(mk.i)} y2={H}
                      className="stroke-slate-300 dark:stroke-slate-600" strokeWidth={1} strokeDasharray="2 2">
                      <title>{`${mk.e.year} — ${mk.e.el}`}</title>
                    </line>
                  ))}
                  <polyline points={pts} fill="none" stroke={m.stroke} strokeWidth={2} strokeLinejoin="round" />
                </svg>
                <dl className="mt-2 grid grid-cols-3 gap-1 text-center text-xs">
                  <div><dt className="text-slate-400 dark:text-slate-500">λέξεις</dt><dd className="font-semibold tabular-nums">{millions}M</dd></div>
                  <div><dt className="text-slate-400 dark:text-slate-500">τομές</dt><dd className="font-semibold tabular-nums">{c.n_slices}</dd></div>
                  <div><dt className="text-slate-400 dark:text-slate-500">με μετατόπιση</dt><dd className="font-semibold tabular-nums">{c.drift_lemmas.toLocaleString("el")}</dd></div>
                </dl>
              </div>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}

// §2 — biggest movers (cosine drift) ─────────────────────────────────────────
function BiggestSection({ corpus, onCorpus, corpora }: SectionProps) {
  const [data, setData] = useState<DriftInsightsResponse | null>(null);
  useEffect(() => {
    setData(null);
    getDriftInsights(corpus, 20).then(setData).catch(() => setData(null));
  }, [corpus]);
  const m = meta(corpus);
  const movers = data?.movers ?? [];
  const max = movers.length ? movers[0].drift_score : 1;
  return (
    <SectionCard
      id="biggest"
      title="Μεγαλύτερες μετατοπίσεις"
      blurb="Κατάταξη με απόσταση συνημιτόνου των διανυσμάτων (Hamilton κ.ά. 2016), με όριο συχνότητας και στις δύο άκρες ώστε να μη μετράμε τον θόρυβο σπάνιων λέξεων (Dubossarsky κ.ά. 2017)."
      aside={<CorpusToggle value={corpus} onChange={onCorpus} options={corpora} />}
    >
      {!data ? <Loading /> : movers.length === 0 ? <Empty msg="Καμία διαθέσιμη μετατόπιση." /> : (
        <div className="flex flex-col gap-0.5">
          {movers.map((mv, i) => (
            <BarRow key={mv.lemma_id} rank={i + 1} lemma={mv.lemma} value={mv.drift_score} max={max}
              display={mv.drift_score.toFixed(2)} stroke={m.stroke} sub={`${mv.first_year}→${mv.last_year}`} />
          ))}
        </div>
      )}
    </SectionCard>
  );
}

// §3 — interesting movers: two metrics side by side ──────────────────────────
function InterestingSection({ corpus, onCorpus, corpora }: SectionProps) {
  const [data, setData] = useState<InterestingResponse | null>(null);
  useEffect(() => {
    setData(null);
    getExploreInteresting(corpus, 15).then(setData).catch(() => setData(null));
  }, [corpus]);
  const m = meta(corpus);
  const nb = data?.neighbor ?? [];
  const fg = data?.freq_gated ?? [];
  const nbMax = nb.length ? nb[0].change : 1;
  const fgMax = fg.length ? fg[0].drift_score : 1;
  return (
    <SectionCard
      id="interesting"
      title="Πιο ενδιαφέρουσες μετατοπίσεις"
      blurb="Δύο μέτρα ανθεκτικά στη συχνότητα, δίπλα-δίπλα. Αριστερά: πόσοι σημασιολογικοί γείτονες άλλαξαν (Gonen κ.ά. 2020). Δεξιά: απόσταση συνημιτόνου, αλλά μόνο για λέξεις αρκετά συχνές και στις δύο άκρες."
      aside={<CorpusToggle value={corpus} onChange={onCorpus} options={corpora} />}
    >
      {!data ? <Loading /> : (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">Ανανέωση γειτόνων (Gonen)</h3>
            <p className="mb-2 text-[11px] leading-snug text-slate-400 dark:text-slate-500">
              Πόσο ανανεώθηκε το σύνολο των κοντινότερων γειτόνων μιας λέξης από την πρώτη
              στην τελευταία τομή (k=150, από κοινό λεξιλόγιο συχνών λέξεων). Δείτε τη{" "}
              <Link to="/methodology#gonen" className="underline hover:text-violet-600 dark:hover:text-violet-300">μεθοδολογία</Link>.
            </p>
            {nb.length === 0 ? <Empty msg="—" /> : (
              <div className="flex flex-col gap-0.5">
                {nb.map((mv, i) => (
                  <BarRow key={mv.lemma_id} rank={i + 1} lemma={mv.lemma} value={mv.change} max={nbMax}
                    display={`${Math.round(mv.change * 100)}%`} stroke={m.stroke} />
                ))}
              </div>
            )}
          </div>
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">Μετατόπιση με όριο συχνότητας</h3>
            {fg.length === 0 ? <Empty msg="—" /> : (
              <div className="flex flex-col gap-0.5">
                {fg.map((mv, i) => (
                  <BarRow key={mv.lemma_id} rank={i + 1} lemma={mv.lemma} value={mv.drift_score} max={fgMax}
                    display={mv.drift_score.toFixed(2)} stroke={m.stroke} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </SectionCard>
  );
}

// §4 — movers by field ───────────────────────────────────────────────────────
function ByFieldSection({ corpus, onCorpus, corpora }: SectionProps) {
  const [data, setData] = useState<ByFieldResponse | null>(null);
  useEffect(() => {
    setData(null);
    getExploreByField(corpus, 6).then(setData).catch(() => setData(null));
  }, [corpus]);
  const m = meta(corpus);
  const fields = data?.fields ?? [];
  return (
    <SectionCard
      id="byfield"
      title="Μετατοπίσεις ανά πεδίο"
      blurb="Οι λέξεις που μετατοπίστηκαν περισσότερο μέσα σε κάθε θεματικό πεδίο. Το πεδίο προκύπτει από τις ετικέτες χρήσης του Wiktionary· όπου λείπουν, ένας επιβλεπόμενος ταξινομητής το προβλέπει από το διανυσματικό περιβάλλον της λέξης (σημειώνεται με ~)."
      aside={<CorpusToggle value={corpus} onChange={onCorpus} options={corpora} />}
    >
      {!data ? <Loading /> : fields.length === 0 ? <Empty msg="Δεν υπάρχουν δεδομένα ανά πεδίο." /> : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {fields.map((f) => (
            <div key={f.field} className="rounded-lg border border-slate-100 p-3 dark:border-slate-800">
              <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold" style={{ color: m.stroke }}>
                {domainEl(f.field)}
                {f.inferred_share >= 0.5 && (
                  <span
                    className="rounded bg-slate-100 px-1 py-px text-[10px] font-medium text-slate-400 dark:bg-slate-800 dark:text-slate-500"
                    title={`Κυρίως από πρόβλεψη ταξινομητή (${Math.round(f.inferred_share * 100)}%)`}
                  >~</span>
                )}
              </h3>
              <ul className="flex flex-col gap-1">
                {f.movers.map((mv) => (
                  <li key={mv.lemma_id} className="flex items-center justify-between gap-2 text-sm">
                    <span className="flex items-center gap-1">
                      <WordLink lemma={mv.lemma} />
                      {mv.domain_source === "classifier" && (
                        <span
                          className="text-[10px] text-slate-300 dark:text-slate-600"
                          title={`Πεδίο από πρόβλεψη ταξινομητή${mv.domain_score != null ? ` (εμπιστοσύνη ${Math.round(mv.domain_score * 100)}%)` : ""}`}
                        >~</span>
                      )}
                    </span>
                    <span className="text-xs tabular-nums text-slate-400 dark:text-slate-500">{mv.drift_score.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

// §5 — risers & fallers (frequency trend) ────────────────────────────────────
function TrendsSection({ corpus, onCorpus, corpora }: SectionProps) {
  const [data, setData] = useState<TrendsResponse | null>(null);
  useEffect(() => {
    setData(null);
    getExploreTrends(corpus, 14).then(setData).catch(() => setData(null));
  }, [corpus]);
  const rising = data?.rising ?? [];
  const falling = data?.falling ?? [];
  const riseMax = Math.max(1, ...rising.map((r) => Math.abs(r.slope)));
  const fallMax = Math.max(1, ...falling.map((r) => Math.abs(r.slope)));
  const fmtPm = (v: number | null) => (v == null ? "·" : v.toFixed(1));
  return (
    <SectionCard
      id="trends"
      title="Ανερχόμενες & φθίνουσες λέξεις"
      blurb="Η τάση της συχνότητας (ανά εκατομμύριο λέξεις) σε όλη την περίοδο — η κλίση της ευθείας ελαχίστων τετραγώνων. Δείχνονται μόνο σταθερές τάσεις (R² ≥ 0,25). Αλλαγή στη χρήση, όχι στη σημασία."
      aside={<CorpusToggle value={corpus} onChange={onCorpus} options={corpora} />}
    >
      {!data ? <Loading /> : (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400">↑ Ανερχόμενες</h3>
            <div className="flex flex-col gap-0.5">
              {rising.map((mv, i) => (
                <BarRow key={mv.lemma_id} rank={i + 1} lemma={mv.lemma} value={mv.slope} max={riseMax}
                  display={`${fmtPm(mv.first_pm)}→${fmtPm(mv.last_pm)}`} stroke="#10b981"
                  sub={`R²${mv.r2.toFixed(2)}${mv.significant ? " ✸" : ""}`} />
              ))}
            </div>
          </div>
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-600 dark:text-rose-400">↓ Φθίνουσες</h3>
            <div className="flex flex-col gap-0.5">
              {falling.map((mv, i) => (
                <BarRow key={mv.lemma_id} rank={i + 1} lemma={mv.lemma} value={mv.slope} max={fallMax}
                  display={`${fmtPm(mv.first_pm)}→${fmtPm(mv.last_pm)}`} stroke="#f43f5e"
                  sub={`R²${mv.r2.toFixed(2)}${mv.significant ? " ✸" : ""}`} />
              ))}
            </div>
          </div>
        </div>
      )}
      {data && (
        <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
          ✸ = στατιστικά σημαντική κλίση (έλεγχος t, p &lt; 0,05). Το R² δείχνει πόσο
          σταθερή είναι η τάση· το p αν ξεχωρίζει από το μηδέν δεδομένου του αριθμού ετών.
        </p>
      )}
    </SectionCard>
  );
}

// §6 — cross-corpus comparison: quadrant + keyness ───────────────────────────
function CompareSection() {
  const [data, setData] = useState<CompareResponse | null>(null);
  useEffect(() => {
    getExploreCompare().then(setData).catch(() => setData(null));
  }, []);
  const pairs = data?.pairs ?? [];
  const pMeta = meta("parliament"), nMeta = meta("news");
  // Axes are percentile ranks (0..1) within each corpus — raw cosine drift is not
  // commensurable across corpora, so we compare each word's relative position instead.
  const maxAxis = 1;
  const W = 300, H = 300, PAD = 28;
  const xOf = (v: number) => PAD + (v / maxAxis) * (W - 2 * PAD);
  const yOf = (v: number) => H - PAD - (v / maxAxis) * (H - 2 * PAD);
  const pct = (v: number) => `${Math.round(v * 100)}%`;

  const kP = data?.keyness.parliament ?? [];
  const kN = data?.keyness.news ?? [];
  const kMax = Math.max(1, ...[...kP, ...kN].map((k) => Math.abs(k.log_ratio)));

  return (
    <SectionCard
      id="compare"
      title="Σύγκριση σωμάτων κειμένων"
      blurb="Η μόνη ενότητα όπου τα δύο σώματα κειμένων συναντιούνται — ρητά ως σύγκριση. Αριστερά: συμφωνούν για το πόσο μετατοπίστηκε μια λέξη; (θέση κατάταξης μέσα σε κάθε σώμα, όχι απόλυτη τιμή — οι ακατέργαστες αποστάσεις δεν είναι συγκρίσιμες). Δεξιά: ποιες λέξεις χαρακτηρίζουν κάθε σώμα κειμένων (keyness· DP = δείκτης διασποράς Gries, χαμηλό = ομοιόμορφα κατανεμημένη, όχι έξαρση μίας χρονιάς)."
    >
      {!data ? <Loading /> : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* agreement / divergence quadrant */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">Συμφωνία / απόκλιση μετατόπισης</h3>
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Μετατόπιση Κοινοβουλίου έναντι Ειδήσεων">
              {/* axes */}
              <line x1={PAD} y1={H - PAD} x2={W - 6} y2={H - PAD} className="stroke-slate-200 dark:stroke-slate-700" />
              <line x1={PAD} y1={6} x2={PAD} y2={H - PAD} className="stroke-slate-200 dark:stroke-slate-700" />
              {/* diagonal = perfect agreement */}
              <line x1={xOf(0)} y1={yOf(0)} x2={xOf(maxAxis)} y2={yOf(maxAxis)} className="stroke-slate-200 dark:stroke-slate-700" strokeDasharray="3 3" />
              {pairs.map((p) => (
                <a key={p.lemma_id} href={`/word/${encodeURIComponent(p.lemma)}`}>
                  <circle cx={xOf(p.parliament)} cy={yOf(p.news)} r={2.5} fill="#8b5cf6" fillOpacity={0.6}>
                    <title>{`${p.lemma} · Κοινοβ. κατάταξη ${pct(p.parliament)} (απόσταση ${p.parliament_drift.toFixed(2)}) / Ειδήσ. κατάταξη ${pct(p.news)} (απόσταση ${p.news_drift.toFixed(2)})`}</title>
                  </circle>
                </a>
              ))}
              <text x={W - 6} y={H - PAD + 14} textAnchor="end" className="fill-slate-400 text-[9px]" style={{ fill: pMeta.stroke }}>Κοινοβούλιο (κατάταξη) →</text>
              <text x={PAD - 6} y={12} className="fill-slate-400 text-[9px]" style={{ fill: nMeta.stroke }}>Ειδήσεις (κατάταξη) ↑</text>
            </svg>
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">Άξονες: θέση κατάταξης της λέξης μέσα σε κάθε σώμα κειμένων (0–100%). Πάνω-δεξιά: μετατοπίστηκε έντονα και στα δύο. Εκτός διαγωνίου: άλλαξε στο ένα σώμα κειμένων, όχι στο άλλο.</p>
          </div>
          {/* keyness */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: pMeta.stroke }}>Χαρακτηριστικές: Κοινοβ.</h3>
              <div className="flex flex-col gap-0.5">
                {kP.map((k) => (
                  <BarRow key={k.lemma_id} lemma={k.lemma} value={k.log_ratio} max={kMax}
                    display={`${k.log_ratio > 0 ? "+" : ""}${k.log_ratio.toFixed(1)}`} stroke={pMeta.stroke}
                    sub={[k.dp_parliament != null ? `DP${k.dp_parliament.toFixed(2)}` : null,
                          k.g2 != null ? `G²${Math.round(k.g2)}` : null].filter(Boolean).join(" · ") || undefined} />
                ))}
              </div>
            </div>
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: nMeta.stroke }}>Χαρακτηριστικές: Ειδήσ.</h3>
              <div className="flex flex-col gap-0.5">
                {kN.map((k) => (
                  <BarRow key={k.lemma_id} lemma={k.lemma} value={k.log_ratio} max={kMax}
                    display={k.log_ratio.toFixed(1)} stroke={nMeta.stroke}
                    sub={[k.dp_news != null ? `DP${k.dp_news.toFixed(2)}` : null,
                          k.g2 != null ? `G²${Math.round(k.g2)}` : null].filter(Boolean).join(" · ") || undefined} />
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

const NAV = [
  { id: "overview", label: "Επισκόπηση" },
  { id: "biggest", label: "Μεγαλύτερες" },
  { id: "interesting", label: "Ενδιαφέρουσες" },
  { id: "byfield", label: "Ανά πεδίο" },
  { id: "trends", label: "Τάσεις" },
  { id: "compare", label: "Σύγκριση" },
];

export default function ExplorePage() {
  const [corpus, setCorpus] = useState<Corpus>(DEFAULT_CORPUS);
  // Discover which corpus axes actually have diachronic data, so the toggles list
  // exactly the available axes (a freshly-ingested wiki/web axis appears here with
  // no further wiring; each stays its own axis — the comparison stays explicit).
  const [corpora, setCorpora] = useState<readonly string[]>([DEFAULT_CORPUS, "news"]);
  useEffect(() => {
    getExploreOverview()
      .then((d) => {
        const list = d.corpora.map((c) => c.corpus);
        if (list.length) {
          setCorpora(list);
          setCorpus((cur) => (list.includes(cur) ? cur : list[0]));
        }
      })
      .catch(() => undefined);
  }, []);
  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Εξερεύνηση</h1>
        <p className="max-w-2xl text-sm text-slate-600 dark:text-slate-400">
          Πώς άλλαξε η ελληνική γλώσσα μέσα στον χρόνο — συχνότητα και σημασία — σε
          σώματα κειμένων που κρατούν τον δικό τους άξονα το καθένα.
        </p>
        <nav className="flex flex-wrap gap-2 text-sm">
          {NAV.map((n) => (
            <a key={n.id} href={`#${n.id}`}
              className="rounded-full border border-slate-200 px-3 py-1 text-slate-600 transition hover:border-violet-300 hover:text-violet-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-violet-500/40">
              {n.label}
            </a>
          ))}
        </nav>
      </header>

      <OverviewSection />
      <BiggestSection corpus={corpus} onCorpus={setCorpus} corpora={corpora} />
      <InterestingSection corpus={corpus} onCorpus={setCorpus} corpora={corpora} />
      <ByFieldSection corpus={corpus} onCorpus={setCorpus} corpora={corpora} />
      <TrendsSection corpus={corpus} onCorpus={setCorpus} corpora={corpora} />
      <CompareSection />

      <p className="max-w-2xl text-xs leading-relaxed text-slate-400 dark:text-slate-600">
        Η μετατόπιση δείχνει αλλαγή στα συμφραζόμενα μιας λέξης, όχι απαραίτητα στον ορισμό της.
        Τα κύρια ονόματα και τα επιρρήματα έχουν εξαιρεθεί από τις κατατάξεις. Πηγές:
        Πρακτικά Βουλής 1989–2020 · Leipzig ell_news 2011–2024.
      </p>
    </div>
  );
}
