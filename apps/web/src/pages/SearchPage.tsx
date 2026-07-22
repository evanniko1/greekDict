import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { search } from "../api/client";
import type { SearchResponse } from "../api/types";
import { useDebounce } from "../hooks/useDebounce";
import ResultCard from "../components/ResultCard";
import {
  useRecentSearches,
  useSavedWords,
  clearRecent,
  removeSaved,
} from "../hooks/useUserData";

const EXAMPLES = ["ανθρώπων", "λόγος", "υπολογίζω", "θάλασσα", "eagle"];

function SearchIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

// A row of word chips linking to their word pages. Saved chips carry an inline
// remove (×); recent chips are plain links.
function WordChips({
  words,
  onRemove,
}: {
  words: string[];
  onRemove?: (w: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-2">
      {words.map((w) => (
        <span
          key={w}
          className="group inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white pl-3 text-sm text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-800"
        >
          <Link to={`/word/${encodeURIComponent(w)}`} className={onRemove ? "py-1" : "px-0 py-1 pr-3"}>
            {w}
          </Link>
          {onRemove && (
            <button
              type="button"
              onClick={() => onRemove(w)}
              aria-label={`Αφαίρεση ${w}`}
              className="px-1.5 text-slate-300 transition hover:text-slate-600 dark:text-slate-600 dark:hover:text-slate-300"
            >
              ×
            </button>
          )}
        </span>
      ))}
    </div>
  );
}

export default function SearchPage() {
  const recent = useRecentSearches();
  const saved = useSavedWords();
  const [query, setQuery] = useState("");
  const debounced = useDebounce(query.trim(), 250);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!debounced) {
      setData(null);
      setStatus("idle");
      return;
    }
    let cancelled = false;
    setStatus("loading");
    search(debounced)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setStatus("ok");
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [debounced]);

  // Empty input → the calm, centered landing hero (foundation-model style).
  // Once the user types, the hero collapses and results take over.
  const isLanding = query.trim().length === 0;

  const searchField = (
    <div className="relative w-full">
      <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500">
        <SearchIcon />
      </span>
      <input
        autoFocus
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Αναζήτησε μια λέξη — π.χ. ανθρώπων ή «eagle»"
        className="w-full rounded-2xl border border-slate-300 bg-white py-3.5 pl-12 pr-4 text-lg shadow-sm outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200/70 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-slate-500 dark:focus:ring-slate-700/50"
      />
    </div>
  );

  return (
    <div className={isLanding ? "flex flex-col items-center pt-16 sm:pt-24" : "flex flex-col gap-5"}>
      {isLanding ? (
        <div className="flex w-full flex-col items-center text-center">
          <h1 className="font-display text-5xl sm:text-6xl">Λεξόραμα</h1>
          <p className="mt-3 max-w-md text-balance text-slate-500 dark:text-slate-400">
            Ένα ανοιχτό, οπτικό λεξικό για τα Νέα Ελληνικά. Γράψε οποιονδήποτε τύπο
            και ανάγεται στο λήμμα του — με εξήγηση.
          </p>
          <div className="mt-8 w-full max-w-xl">{searchField}</div>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
            <span className="text-xs text-slate-400 dark:text-slate-500">Δοκίμασε:</span>
            {EXAMPLES.map((w) => (
              <button
                key={w}
                type="button"
                onClick={() => setQuery(w)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1 text-sm text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-800"
              >
                {w}
              </button>
            ))}
          </div>

          {recent.length > 0 && (
            <div className="mt-10 w-full max-w-xl">
              <div className="mb-2 flex items-center justify-center gap-2">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
                  Πρόσφατες αναζητήσεις
                </span>
                <button
                  type="button"
                  onClick={clearRecent}
                  className="text-xs text-slate-400 underline-offset-2 transition hover:text-slate-600 hover:underline dark:text-slate-500 dark:hover:text-slate-300"
                >
                  Καθαρισμός
                </button>
              </div>
              <WordChips words={recent} />
            </div>
          )}

          {saved.length > 0 && (
            <div className="mt-8 w-full max-w-xl">
              <div className="mb-2 text-center">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
                  Αποθηκευμένες λέξεις
                </span>
              </div>
              <WordChips words={saved} onRemove={removeSaved} />
            </div>
          )}
        </div>
      ) : (
        <>
          {searchField}
          <p className="-mt-2 text-xs text-slate-400 dark:text-slate-500">
            Χωρίς διάκριση τόνων. Γράψε έναν τύπο και ανάγεται στο λήμμα του — ή μια
            αγγλική λέξη για να βρεις το ελληνικό λήμμα.
          </p>
        </>
      )}

      {status === "loading" && (
        <p className="text-slate-400 dark:text-slate-500">Αναζήτηση…</p>
      )}

      {status === "error" && (
        <p className="text-red-600 dark:text-red-400">
          Η αναζήτηση απέτυχε{error ? `: ${error}` : ""}
        </p>
      )}

      {status === "ok" && data && !data.resolved && (
        <p className="text-slate-500 dark:text-slate-400">
          Καμία αντιστοίχιση για <span className="font-medium">{data.query}</span>.
        </p>
      )}

      {status === "ok" && data && data.resolved && (
        <div className="flex w-full flex-col gap-3">
          {data.results.map((r) => (
            <ResultCard key={`${r.lemma_id}-${r.matched_surface}`} result={r} />
          ))}
        </div>
      )}
    </div>
  );
}
