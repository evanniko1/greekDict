import { Link } from "react-router-dom";

// Two things in one page:
//  1. Γλωσσάρι — plain-Greek explanations of the grammatical terms the app uses,
//     so a non-linguist can read a word page.
//  2. Σχεδιαστική λογική — why the app is built the way it is (graph-first,
//     typed+sourced edges, form→lemma resolution, "AI explains, sources define").

interface Term {
  term: string;
  def: string;
  example?: string;
}

const GLOSSARY: { group: string; terms: Term[] }[] = [
  {
    group: "Βασικές έννοιες",
    terms: [
      {
        term: "Λήμμα",
        def: "Η βασική, λεξικογραφική μορφή μιας λέξης — αυτή που βρίσκεις στο λεξικό.",
        example: "άνθρωπος, γράφω, καλός",
      },
      {
        term: "Κλιτός τύπος",
        def: "Μια κλιμένη/κλιτή μορφή ενός λήμματος. Το Λεξόραμα αναγνωρίζει τον τύπο και τον εξηγεί, ανεβάζοντάς τον στο λήμμα του.",
        example: "ανθρώπων → άνθρωπος (γενική, πληθυντικός)",
      },
      {
        term: "Κλίση",
        def: "Το σύνολο των μορφών που παίρνει μια λέξη. Στα ουσιαστικά/επίθετα λέγεται κλίση· στα ρήματα, συζυγία/κλίση.",
      },
    ],
  },
  {
    group: "Ονόματα (ουσιαστικά & επίθετα)",
    terms: [
      {
        term: "Πτώση",
        def: "Η συντακτική θέση του ονόματος. Η νέα ελληνική έχει τέσσερις: ονομαστική, γενική, αιτιατική, κλητική (όχι δοτική).",
      },
      { term: "Αριθμός", def: "Ενικός (ένα) ή πληθυντικός (πολλά)." },
      { term: "Γένος", def: "Αρσενικό, θηλυκό ή ουδέτερο." },
    ],
  },
  {
    group: "Ρήματα",
    terms: [
      {
        term: "Φωνή",
        def: "Ενεργητική (το υποκείμενο ενεργεί) ή παθητική (το υποκείμενο δέχεται την ενέργεια).",
        example: "γράφω / γράφομαι",
      },
      {
        term: "Έγκλιση",
        def: "Ο τρόπος που παρουσιάζεται η πράξη: οριστική (γεγονός), υποτακτική (με να/ας), προστακτική (διαταγή).",
      },
      {
        term: "Ποιόν ενέργειας (όψη)",
        def: "Δείχνει αν η πράξη ειδωθεί ως συνεχής ή ως συνοπτική — η βάση οργάνωσης των ρηματικών χρόνων.",
      },
      {
        term: "Εξακολουθητικοί χρόνοι",
        def: "Συνεχιζόμενη/επαναλαμβανόμενη πράξη: Ενεστώτας, Παρατατικός, Εξακολουθητικός Μέλλοντας.",
        example: "γράφω, έγραφα, θα γράφω",
      },
      {
        term: "Συνοπτικοί χρόνοι",
        def: "Στιγμιαία/ολοκληρωμένη πράξη: Αόριστος, Συνοπτικός Μέλλοντας, και ο εξαρτημένος (υποτακτική με να/θα).",
        example: "έγραψα, θα γράψω, να γράψω",
      },
      {
        term: "Μετοχή / Απαρέμφατο",
        def: "Ονοματικοί τύποι του ρήματος. Μετοχή: γράφοντας, γραμμένος. Απαρέμφατο (αορίστου): (έχω) γράψει.",
      },
    ],
  },
  {
    group: "Σχέσεις & ιστορία",
    terms: [
      {
        term: "Συνώνυμο / Αντώνυμο",
        def: "Λέξεις με όμοια / αντίθετη σημασία.",
      },
      {
        term: "Υπερώνυμο / Υπώνυμο",
        def: "Γενικότερη / ειδικότερη έννοια.",
        example: "ζώο (υπερώνυμο) → σκύλος (υπώνυμο)",
      },
      {
        term: "Ετυμολογία",
        def: "Η προέλευση και η ιστορία της λέξης — από πού κληρονομήθηκε, παράχθηκε ή δανείστηκε.",
        example: "άνθρωπος ← αρχαία ελληνικά ἄνθρωπος",
      },
    ],
  },
];

const PRINCIPLES: { title: string; body: string }[] = [
  {
    // The page used to claim, in the present tense, that AI explains and organises the
    // data. There is no language model anywhere in this product — the only computed
    // additions are a logistic-regression domain classifier and the rule-based paradigm
    // engine, both of which are marked wherever they appear. Claiming otherwise was the
    // single least defensible sentence on the site (audit F31, §3.9).
    title: "Οι πηγές ορίζουν",
    body:
      "Κάθε ορισμός, τύπος και σχέση κρατά την πηγή του (badge «Πηγή»). Καμία σημασία " +
      "δεν παράγεται αυτόματα: το Λεξόραμα δεν χρησιμοποιεί γλωσσικό μοντέλο που γράφει " +
      "ορισμούς. Οι μόνες υπολογισμένες προσθήκες είναι στατιστικές — η πρόβλεψη " +
      "θεματικού πεδίου (~) και οι αλγοριθμικά παραγόμενοι τύποι κλίσης (*) — και " +
      "σημειώνονται πάντα ως τέτοιες. Ό,τι άλλο βλέπεις προέρχεται από ανοιχτά, " +
      "παραπεμπόμενα δεδομένα.",
  },
  {
    title: "Επίλυση τύπου → λήμμα που εξηγείται",
    body:
      "Αντί να σου πει απλώς «δεν βρέθηκε», το Λεξόραμα παίρνει έναν κλιτό τύπο " +
      "(π.χ. ανθρώπων), τον ανεβάζει στο λήμμα του (άνθρωπος) και σου λέει ΓΙΑΤΙ " +
      "(γενική, πληθυντικός). Αυτό είναι το πρώτο από τα δύο χαρακτηριστικά που " +
      "δικαιολογούν το έργο.",
  },
  {
    title: "Γράφος με τυποποιημένες & παραπεμπόμενες ακμές",
    body:
      "Οι λέξεις δεν είναι νησιά. Κάθε σχέση (συνώνυμο, παράγωγο, ετυμολογική " +
      "καταγωγή…) είναι μια ακμή με συγκεκριμένο τύπο και πηγή — όχι ένας αόριστος " +
      "«σχετικός όρος». Έτσι ο γράφος είναι εξηγήσιμος και ελέγξιμος.",
  },
  {
    title: "Ανοιχτά δεδομένα, ελληνικά πρώτα",
    body:
      "Τα δεδομένα προέρχονται από το Βικιλεξικό (CC BY-SA / GFDL). Η διεπαφή είναι " +
      "εξ ολοκλήρου στα ελληνικά· οι αγγλικοί όροι του Wiktionary μεταφράζονται μόνο " +
      "για εμφάνιση, ενώ τα δίγλωσσα δεδομένα διατηρούνται για μελλοντική λειτουργία " +
      "ελληνικά↔αγγλικά.",
  },
];

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mt-8 mb-3 text-lg font-semibold tracking-tight">{children}</h2>
  );
}

export default function AboutPage() {
  return (
    <div className="flex max-w-3xl flex-col gap-2">
      <Link to="/" className="text-sm text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100">
        ← Αναζήτηση
      </Link>
      <h1 className="mt-2 text-2xl font-bold tracking-tight">Γλωσσάρι & σχεδιαστική λογική</h1>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Τι σημαίνουν οι όροι που βλέπεις στις σελίδες λέξεων — και γιατί το Λεξόραμα
        είναι φτιαγμένο έτσι.
      </p>

      <SectionHeading>Γλωσσάρι όρων</SectionHeading>
      <div className="flex flex-col gap-5">
        {GLOSSARY.map((g) => (
          <section key={g.group}>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
              {g.group}
            </h3>
            <dl className="flex flex-col divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900">
              {g.terms.map((t) => (
                <div key={t.term} className="flex flex-col gap-0.5 px-4 py-3 sm:flex-row sm:gap-4">
                  <dt className="font-semibold sm:w-48 sm:shrink-0">{t.term}</dt>
                  <dd className="text-sm text-slate-600 dark:text-slate-400">
                    {t.def}
                    {t.example && (
                      <span className="mt-1 block text-slate-400 dark:text-slate-500">
                        π.χ. {t.example}
                      </span>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>

      <SectionHeading>Σχεδιαστική λογική</SectionHeading>
      <div className="grid gap-3 sm:grid-cols-2">
        {PRINCIPLES.map((p) => (
          <section
            key={p.title}
            className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
          >
            <h3 className="font-semibold">{p.title}</h3>
            <p className="mt-1.5 text-sm text-slate-600 dark:text-slate-400">{p.body}</p>
          </section>
        ))}
      </div>

      <p className="mt-6 text-sm text-slate-500 dark:text-slate-400">
        Για τις πηγές και τις άδειες των δεδομένων, δες τη σελίδα{" "}
        <Link to="/licensing" className="underline hover:text-slate-800 dark:hover:text-slate-100">
          Πηγές &amp; άδειες
        </Link>
        .
      </p>
    </div>
  );
}
