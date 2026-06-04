import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getAttributions } from "../api/client";
import type { SourceAttribution } from "../api/types";

// Full CC BY-SA / GFDL attribution, driven by the source_attributions table
// (one row per data source). This is the central, authoritative notice the
// footer links to; it spells out license, source link, modification notice and
// the ShareAlike obligation.
export default function LicensingPage() {
  const [items, setItems] = useState<SourceAttribution[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAttributions()
      .then((res) => {
        if (!cancelled) setItems(res.attributions);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <Link to="/" className="text-sm text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100">
        ← Αναζήτηση
      </Link>
      <h1 className="text-2xl font-bold">Πηγές &amp; άδειες</h1>

      <p className="text-sm text-slate-600 dark:text-slate-400">
        Το Λεξόραμα αντλεί τα λεξικογραφικά του δεδομένα από το Βικιλεξικό
        (Wiktionary). Το περιεχόμενο του Βικιλεξικού διατίθεται υπό διπλή άδεια{" "}
        <a
          href="https://creativecommons.org/licenses/by-sa/4.0/"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-slate-800 dark:hover:text-slate-100"
        >
          Creative Commons Attribution-ShareAlike 4.0
        </a>{" "}
        και{" "}
        <a
          href="https://www.gnu.org/licenses/fdl-1.3.html"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-slate-800 dark:hover:text-slate-100"
        >
          GNU Free Documentation License
        </a>
        . Σύμφωνα με τον όρο «Παρόμοια Διανομή» (ShareAlike), τα παράγωγα
        δεδομένα του Λεξοράματος διατίθενται επίσης υπό CC BY-SA 4.0.
      </p>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">
          Δεν ήταν δυνατή η φόρτωση των αποδόσεων ({error}). Τα δεδομένα παραμένουν
          υπό CC BY-SA 4.0 / GFDL.
        </p>
      )}
      {!items && !error && <p className="text-slate-400 dark:text-slate-500">Φόρτωση…</p>}

      <div className="flex flex-col gap-3">
        {items?.map((a) => (
          <section
            key={a.source_name}
            className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="flex flex-wrap items-baseline gap-2">
              <h2 className="font-semibold">{a.source_name}</h2>
              {a.license && (
                <span className="text-xs text-slate-500 dark:text-slate-400">{a.license}</span>
              )}
              {a.retrieved_at && (
                <span className="ml-auto text-xs text-slate-400 dark:text-slate-500">
                  ανάκτηση: {a.retrieved_at}
                </span>
              )}
            </div>
            {a.attribution_text && (
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{a.attribution_text}</p>
            )}
            {a.source_url && (
              <a
                href={a.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-block text-sm text-indigo-600 underline hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
              >
                {a.source_url}
              </a>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
