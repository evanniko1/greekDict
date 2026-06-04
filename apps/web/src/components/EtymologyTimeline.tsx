import { Link } from "react-router-dom";
import type { WordEntry } from "../api/types";
import { langEl, etyRelEl } from "../api/labels";

// Layer A of the diachronic story: a horizontal timeline that places a word's
// attested ancestors onto the canonical stages of Greek, oldest → newest.
//
// This is built entirely from data we already ingest (Wiktionary etymons), with
// no extra corpus: each etymon carries a source-language code (grc, grc-koi,
// gkm, el, ine-pro…) which maps cleanly onto a historical period. The current
// lemma anchors the "Νέα ελληνική" end. Non-Greek sources (Latin, Turkish,
// Italian…) can't sit on the Greek axis, so they surface as a "loan from" note.
//
// Later layers (B: frequency-over-time, C: semantic drift via diachronic
// embeddings) will hang off this same spine.

interface Period {
  id: string;
  label: string;
  short: string;
  langs: string[];
}

// Ordered oldest → newest. Dialect codes fold into the Ancient stage.
const PERIODS: Period[] = [
  { id: "pie", label: "Πρωτοϊνδοευρωπαϊκή", short: "ΠΙΕ", langs: ["ine-pro"] },
  {
    id: "ancient",
    label: "Αρχαία ελληνική",
    short: "Αρχαία",
    langs: ["grc", "grc-dor", "grc-att", "grc-ion", "grc-aeo"],
  },
  { id: "koine", label: "Ελληνιστική Κοινή", short: "Κοινή", langs: ["grc-koi"] },
  { id: "medieval", label: "Μεσαιωνική / Βυζαντινή", short: "Μεσαιωνική", langs: ["gkm", "gkm-cyp"] },
  { id: "modern", label: "Νέα ελληνική", short: "Νέα", langs: ["el"] },
];

const LANG_TO_PERIOD = new Map<string, number>();
PERIODS.forEach((p, i) => p.langs.forEach((l) => LANG_TO_PERIOD.set(l, i)));

interface TimelineTerm {
  term: string;
  relation: string;
}

export default function EtymologyTimeline({ entry }: { entry: WordEntry }) {
  // Bucket each language-tagged etymon into its Greek period.
  const buckets: TimelineTerm[][] = PERIODS.map(() => []);
  const loans: { term: string; lang: string | null; relation: string }[] = [];

  for (const e of entry.etymons) {
    const idx = e.lang ? LANG_TO_PERIOD.get(e.lang) : undefined;
    if (idx == null) {
      // Non-Greek source (or untagged): a borrowing/derivation we can't date.
      if (e.lang) loans.push({ term: e.term, lang: e.lang, relation: e.relation });
      continue;
    }
    buckets[idx].push({ term: e.term, relation: e.relation });
  }

  // Anchor the modern end with the headword itself if nothing else sits there.
  const modernIdx = PERIODS.length - 1;
  if (buckets[modernIdx].length === 0) {
    buckets[modernIdx].push({ term: entry.lemma, relation: "current" });
  }

  // Only render periods that actually carry a node, but keep them in order so
  // the connecting spine reads chronologically.
  const active = PERIODS.map((p, i) => ({ period: p, idx: i, terms: buckets[i] })).filter(
    (x) => x.terms.length > 0,
  );

  // Needs genuine historical depth to be worth drawing — at least two stages,
  // or one stage plus a datable loan. Otherwise the EntryEtymology list suffices.
  if (active.length < 2 && loans.length === 0) return null;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        Διαχρονική πορεία
      </h3>

      {loans.length > 0 && (
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
          Δάνειο από{" "}
          {loans.map((l, i) => (
            <span key={i}>
              {i > 0 && ", "}
              <span className="font-medium">{l.term}</span>
              {l.lang && <span className="text-slate-400 dark:text-slate-500"> ({langEl(l.lang) || l.lang})</span>}
            </span>
          ))}
          .
        </p>
      )}

      <ol className="flex items-stretch gap-0 overflow-x-auto pb-1">
        {active.map((stage, i) => {
          const isModern = stage.idx === modernIdx;
          return (
            <li key={stage.period.id} className="flex min-w-[8.5rem] flex-1 items-stretch">
              <div className="flex w-full flex-col">
                {/* Spine: dot + connector to the next stage. */}
                <div className="flex items-center">
                  <span
                    className={`h-3 w-3 shrink-0 rounded-full ${
                      isModern ? "bg-emerald-500 dark:bg-emerald-400" : "bg-slate-300 dark:bg-slate-600"
                    }`}
                  />
                  {i < active.length - 1 && (
                    <span className="h-0.5 flex-1 bg-slate-200 dark:bg-slate-700" />
                  )}
                </div>
                <div className="mt-2 pr-3">
                  <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">{stage.period.short}</p>
                  <ul className="mt-1.5 flex flex-col gap-1">
                    {stage.terms.map((t, ti) => (
                      <li key={ti}>
                        {isModern && t.relation === "current" ? (
                          <span className="text-sm font-semibold text-emerald-700 dark:text-emerald-300">
                            {t.term}
                          </span>
                        ) : (
                          <Link
                            to={`/word/${encodeURIComponent(t.term)}`}
                            className="text-sm text-slate-700 underline-offset-2 hover:underline dark:text-slate-200"
                            title={etyRelEl(t.relation)}
                          >
                            {t.term}
                          </Link>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
