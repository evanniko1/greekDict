import { Link } from "react-router-dom";

// Persistent, low-clutter attribution. Per-item `source` badges already carry
// provenance everywhere; this footer satisfies the CC BY-SA / GFDL requirement
// that the license notice be reachable from any page (including deep-linked word
// pages), with the full text + ShareAlike statement on /licensing.
export default function Footer() {
  return (
    <footer className="mt-auto border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="mx-auto max-w-5xl px-4 py-4 text-xs text-slate-400 dark:text-slate-500">
        Λεξικογραφικά δεδομένα από το{" "}
        <a
          href="https://el.wiktionary.org/"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-slate-600 dark:hover:text-slate-300"
        >
          Βικιλεξικό
        </a>{" "}
        υπό τις άδειες CC BY-SA 4.0 / GFDL. Τα δεδομένα έχουν τροποποιηθεί.{" "}
        <Link to="/licensing" className="underline hover:text-slate-600 dark:hover:text-slate-300">
          Πηγές &amp; άδειες
        </Link>
        {" · "}
        <Link to="/about" className="underline hover:text-slate-600 dark:hover:text-slate-300">
          Γλωσσάρι &amp; σχεδιασμός
        </Link>
      </div>
    </footer>
  );
}
