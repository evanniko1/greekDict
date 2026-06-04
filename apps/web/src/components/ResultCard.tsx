import { Link } from "react-router-dom";
import type { SearchResult } from "../api/types";
import { genderEl, gramEl, matchEl, posEl } from "../api/labels";

// The backend builds `explanation` with raw English feature tags
// (e.g. "ανθρώπων → άνθρωπος (genitive, plural)"). Keep the DB/API English but
// translate for display, consistent with the labels.ts presentation layer.
function explainForm(result: SearchResult): string {
  const base = `${result.matched_surface} → ${result.lemma}`;
  if (!result.features) return base;
  const feats = result.features
    .split(",")
    .map((t) => gramEl(t.trim()))
    .filter(Boolean)
    .join(", ");
  return feats ? `${base} (${feats})` : base;
}

export default function ResultCard({ result }: { result: SearchResult }) {
  const isForm = result.match_type === "inflected_form";
  const isTranslation = result.match_type === "translation";
  // Headline: inflected forms and translations show the bridge ("eagle → αετός");
  // a plain lemma hit just shows the lemma.
  const headline = isForm ? explainForm(result) : isTranslation ? result.explanation : result.lemma;
  return (
    <Link
      to={`/word/${encodeURIComponent(result.lemma)}`}
      className="block rounded-lg border border-slate-200 bg-white px-5 py-4 shadow-sm transition hover:border-slate-300 hover:shadow dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700"
    >
      {/* Resolution explanation is the hero element. */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-xl font-semibold text-slate-900 dark:text-slate-100">
          {headline}
        </div>
        <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {matchEl(result.match_type)}
        </span>
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
        {result.pos && (
          <span className="rounded bg-slate-50 px-1.5 py-0.5 dark:bg-slate-800">{posEl(result.pos)}</span>
        )}
        {result.gender && (
          <span className="rounded bg-slate-50 px-1.5 py-0.5 dark:bg-slate-800">{genderEl(result.gender)}</span>
        )}
        {result.via === "greeklish" && (
          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
            μέσω γκρίκλις
          </span>
        )}
        {result.via === "translation" && (
          <span className="rounded bg-sky-50 px-1.5 py-0.5 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300">
            μέσω αγγλικών
          </span>
        )}
      </div>

      {result.snippet && (
        <p className="mt-2 line-clamp-2 text-sm text-slate-600 dark:text-slate-400">{result.snippet}</p>
      )}
    </Link>
  );
}
