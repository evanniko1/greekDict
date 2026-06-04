// Groups a flat list of inflected forms into proper Greek paradigm tables.
//
// The forms come from en-wiktionary with English feature tags (e.g.
// ["active","imperfective","indicative","present","singular","third-person"]).
// We bucket them into a familiar dictionary layout:
//   - verbs  → one grid per voice (Ενεργητική/Παθητική), columns = tense/mood,
//              rows = person × number.
//   - nouns/adjectives → columns = number, rows = case; split by gender if tagged.
// Non-inflectional rows (the headword "canonical" form, Latin "romanization")
// are dropped. Anything that doesn't fit a known cell falls through to
// `other` so no form is ever silently lost.

import { gramEl } from "./labels";
import type { WordForm } from "./types";

const GENDERS = ["masculine", "feminine", "neuter"];

// The headword row Wiktionary tags "canonical" is really the lemma's base form
// (verb → present·indicative·1st·singular·active; nominal → nominative·singular),
// but it carries no person/case tags and its text can have a trailing Latin
// annotation (e.g. "υπολογίζω active"). Recover it into the right cell instead
// of dropping it; skip "romanization" (Latin transliteration — not a paradigm).
function expandHeadword(pos: string | null, f: WordForm): WordForm | null {
  const lower = f.features.map((x) => x.toLowerCase());
  if (lower.includes("romanization") || lower.includes("romanized")) return null;
  if (!lower.includes("canonical")) return f;

  const tokens = f.form.split(/\s+/);
  const trailing: string[] = [];
  while (tokens.length > 1 && /^[a-zA-Z]+$/.test(tokens[tokens.length - 1])) {
    trailing.push(tokens.pop()!.toLowerCase());
  }
  const form = tokens.join(" ");

  if ((pos ?? "").toLowerCase().includes("verb")) {
    const voice = trailing.includes("passive") ? "passive" : "active";
    return {
      form,
      source: f.source,
      features: ["indicative", "present", "first-person", "singular", voice],
    };
  }
  const gender = lower.find((x) => GENDERS.includes(x));
  return {
    form,
    source: f.source,
    features: gender ? ["nominative", "singular", gender] : ["nominative", "singular"],
  };
}

// A column carries an aspect "band" (group) so the rendered table can show a
// two-tier header — exactly how Βικιλεξικό groups Modern Greek verb forms:
//   Εξακολουθητικοί (imperfective) · Συνοπτικοί (perfective) · Προστακτική
// Nominal grids leave `group` empty (no band row is rendered).
export interface GridColumn {
  label: string;
  group: string;
}

// A rendered cell. `generated` is true when every form filling it came from the
// paradigm engine (source='generated') — the UI marks these so users can always
// tell an algorithmically-inflected form from a Wiktionary-sourced one.
export interface GridCell {
  text: string;
  generated: boolean;
}

export interface Grid {
  title: string | null;
  columns: GridColumn[];
  rows: { label: string; cells: GridCell[] }[];
  sources: string[];
  hasGenerated: boolean;
}

export interface Inflection {
  grids: Grid[];
  nonFinite: WordForm[];
  other: WordForm[];
}

// Non-finite / nominal verb forms get their own box (μετοχές, απαρέμφατο).
const NONFINITE = new Set(["participle", "infinitive", "infinitive-aorist", "gerund"]);

interface ColDef {
  key: string;
  label: string;
  group: string;
  match: (t: Set<string>) => boolean;
}
interface RowDef {
  key: string;
  label: string;
  need: string[];
}

// Aspect bands (ποιόν ενέργειας) / mood bands for the two-tier column header.
const ASP_IMPF = "Εξακολουθητικοί";
const ASP_PERF = "Συνοπτικοί";
const ASP_PERFECT = "Συντελεσμένοι";
const ASP_SUBJ = "Υποτακτική";
const ASP_IMPER = "Προστακτική";

// Two divergent verb vocabularies live in the data and must BOTH be matched:
//   • en-wiktionary uses aspect tags — `imperfective`/`perfective`, `dependent`,
//     `past`, `imperfect`, `future`, `imperative`.
//   • el-wiktionary (school grammar) uses tense/mood tags WITHOUT aspect —
//     `present`, `imperfect`, `aorist`, `future`, `subjunctive`, `perfect`,
//     `pluperfect`, `imperative`. Its periphrastic tenses (έχω γράψει,
//     είχα γράψει, θα έχω γράψει, να έχω γράψει) are full forms.
// The el `subjunctive`/`imperative` tags carry no aspect, so disambiguateAspect()
// injects `imperfective`/`perfective`/`perfect` by cross-referencing the
// aspect-tagged forms before bucketing. Empty columns are dropped by buildGrid.
const VERB_COLS: ColDef[] = [
  // — Εξακολουθητικοί (imperfective) —
  { key: "pres", group: ASP_IMPF, label: "Ενεστώτας", match: (t) => t.has("present") && !t.has("past") && !t.has("imperfect") && !t.has("future") && !t.has("dependent") && !t.has("subjunctive") && !t.has("imperative") && !t.has("perfect") && !t.has("pluperfect") },
  // Παρατατικός: el tags it `imperfect`; en tags it `imperfect` + `past` + `imperfective`.
  { key: "imperf", group: ASP_IMPF, label: "Παρατατικός", match: (t) => t.has("imperfect") && !t.has("future") && !t.has("subjunctive") && !t.has("imperative") },
  // Εξακ. μέλλοντας (θα γράφω): el `future`+`imperfect`; en `future`+`imperfective`.
  { key: "futi", group: ASP_IMPF, label: "Εξακ. Μέλλοντας", match: (t) => t.has("future") && (t.has("imperfective") || t.has("imperfect")) && !t.has("perfect") },
  // — Συνοπτικοί (perfective) —
  // Αόριστος: el `aorist`; en `past`+`perfective`.
  { key: "aor", group: ASP_PERF, label: "Αόριστος", match: (t) => (t.has("aorist") || (t.has("past") && t.has("perfective"))) && !t.has("imperfect") && !t.has("future") && !t.has("subjunctive") && !t.has("imperative") },
  // Συνοπτ. μέλλοντας (θα γράψω): en `future`+`perfective`; el bare `future` (no aspect/perfect).
  { key: "futp", group: ASP_PERF, label: "Συνοπτ. Μέλλοντας", match: (t) => t.has("future") && (t.has("perfective") || (!t.has("imperfect") && !t.has("imperfective") && !t.has("perfect") && !t.has("subjunctive"))) },
  // — Συντελεσμένοι (perfect, periphrastic — el only) —
  { key: "perf", group: ASP_PERFECT, label: "Παρακείμενος", match: (t) => t.has("perfect") && !t.has("future") && !t.has("subjunctive") && !t.has("imperative") },
  { key: "plup", group: ASP_PERFECT, label: "Υπερσυντέλικος", match: (t) => t.has("pluperfect") },
  { key: "futperf", group: ASP_PERFECT, label: "Συντελ. Μέλλοντας", match: (t) => t.has("future") && t.has("perfect") },
  // — Υποτακτική (subjunctive) — el `subjunctive` / en `dependent`, aspect injected. —
  { key: "subi", group: ASP_SUBJ, label: "Εξακολουθητική", match: (t) => (t.has("subjunctive") || t.has("dependent")) && t.has("imperfective") && !t.has("perfect") },
  { key: "subp", group: ASP_SUBJ, label: "Συνοπτική", match: (t) => (t.has("subjunctive") || t.has("dependent")) && t.has("perfective") && !t.has("perfect") },
  { key: "subperf", group: ASP_SUBJ, label: "Παρακειμένου", match: (t) => t.has("subjunctive") && t.has("perfect") },
  // Subjunctive that couldn't be aspect-classified (el-only verb, no reference forms).
  { key: "sub", group: ASP_SUBJ, label: "Υποτακτική", match: (t) => (t.has("subjunctive") || t.has("dependent")) && !t.has("imperfective") && !t.has("perfective") && !t.has("perfect") },
  // — Προστακτική (imperative) —
  { key: "imperi", group: ASP_IMPER, label: "Εξακολουθητική", match: (t) => t.has("imperative") && t.has("imperfective") },
  { key: "imperp", group: ASP_IMPER, label: "Συνοπτική", match: (t) => t.has("imperative") && t.has("perfective") },
  // Bare imperative with no recoverable aspect — keep it visible.
  { key: "imper", group: ASP_IMPER, label: "Προστακτική", match: (t) => t.has("imperative") && !t.has("imperfective") && !t.has("perfective") },
];

const VERB_ROWS: RowDef[] = [
  { key: "1s", label: "α΄ ενικ.", need: ["first-person", "singular"] },
  { key: "2s", label: "β΄ ενικ.", need: ["second-person", "singular"] },
  { key: "3s", label: "γ΄ ενικ.", need: ["third-person", "singular"] },
  { key: "1p", label: "α΄ πληθ.", need: ["first-person", "plural"] },
  { key: "2p", label: "β΄ πληθ.", need: ["second-person", "plural"] },
  { key: "3p", label: "γ΄ πληθ.", need: ["third-person", "plural"] },
];

const NOM_COLS: ColDef[] = [
  { key: "sg", group: "", label: "Ενικός", match: (t) => t.has("singular") },
  { key: "pl", group: "", label: "Πληθυντικός", match: (t) => t.has("plural") },
];

const NOM_ROWS: RowDef[] = [
  { key: "nom", label: "Ονομαστική", need: ["nominative"] },
  { key: "gen", label: "Γενική", need: ["genitive"] },
  { key: "acc", label: "Αιτιατική", need: ["accusative"] },
  { key: "voc", label: "Κλητική", need: ["vocative"] },
  { key: "dat", label: "Δοτική", need: ["dative"] },
];

function buildGrid(
  title: string | null,
  forms: WordForm[],
  cols: ColDef[],
  rows: RowDef[],
): { grid: Grid | null; leftover: WordForm[] } {
  const cellMap = new Map<string, string[]>();
  const cellSrc = new Map<string, Set<string>>(); // per-cell contributing sources
  const usedCols = new Set<string>();
  const usedRows = new Set<string>();
  const sources = new Set<string>();
  const leftover: WordForm[] = [];

  for (const f of forms) {
    const t = new Set(f.features.map((x) => x.toLowerCase()));
    const col = cols.find((c) => c.match(t));
    const row = rows.find((r) => r.need.every((n) => t.has(n)));
    if (col && row) {
      const k = `${row.key}|${col.key}`;
      const arr = cellMap.get(k) ?? [];
      if (!arr.includes(f.form)) arr.push(f.form);
      cellMap.set(k, arr);
      const ss = cellSrc.get(k) ?? new Set<string>();
      ss.add(f.source || "");
      cellSrc.set(k, ss);
      usedCols.add(col.key);
      usedRows.add(row.key);
      if (f.source) sources.add(f.source);
    } else {
      leftover.push(f);
    }
  }

  const activeCols = cols.filter((c) => usedCols.has(c.key));
  const activeRows = rows.filter((r) => usedRows.has(r.key));
  if (activeCols.length === 0 || activeRows.length === 0) {
    return { grid: null, leftover: forms };
  }

  // A cell is "generated" only when it has forms AND every contributing source
  // is the engine — so a cell with even one Wiktionary form is shown as sourced.
  const isGen = (k: string): boolean => {
    const ss = cellSrc.get(k);
    return !!ss && ss.size > 0 && [...ss].every((s) => s === "generated");
  };
  let hasGenerated = false;
  const gridRows = activeRows.map((r) => ({
    label: r.label,
    cells: activeCols.map((c) => {
      const k = `${r.key}|${c.key}`;
      const text = (cellMap.get(k) ?? []).join(" / ");
      const generated = text ? isGen(k) : false;
      if (generated) hasGenerated = true;
      return { text, generated };
    }),
  }));

  return {
    grid: {
      title,
      columns: activeCols.map((c) => ({ label: c.label, group: c.group })),
      rows: gridRows,
      sources: [...sources],
      hasGenerated,
    },
    leftover,
  };
}

// Particles that precede periphrastic verb forms; stripped to recover the bare
// verb so it can be matched against the aspect-tagged reference forms.
const PARTICLES = new Set(["να", "θα", "ας", "μη", "μην", "δεν", "δε"]);

function stripParticles(form: string): string {
  const toks = form.split(/\s+/).filter(Boolean);
  while (toks.length > 1 && PARTICLES.has(toks[0].toLowerCase())) toks.shift();
  return toks.join(" ");
}

// Perfect periphrasis: auxiliary έχω/έχεις/… (perfect) or είχα/είχες/… (pluperfect).
const PERFECT_AUX = /^(έχ|είχ)/;

// el-wiktionary tags subjunctive/imperative with NO aspect, so "να γράφω"
// (imperfective) and "να γράψω" (perfective) look identical. Recover the aspect
// by cross-referencing forms that DO carry an explicit aspect tag (en-wiktionary
// + the seeded headword), matched by full form or by particle-stripped bare form.
// Subjunctive perfect ("να έχω γράψει") is detected by its auxiliary. Forms that
// already carry an aspect tag, or that can't be classified, are returned as-is.
function disambiguateAspect(forms: WordForm[]): WordForm[] {
  const aspectOf = new Map<string, string>();
  for (const f of forms) {
    const t = f.features.map((x) => x.toLowerCase());
    const a = t.includes("imperfective") ? "imperfective" : t.includes("perfective") ? "perfective" : null;
    if (!a) continue;
    if (!aspectOf.has(f.form)) aspectOf.set(f.form, a);
    const bare = stripParticles(f.form);
    if (!aspectOf.has(bare)) aspectOf.set(bare, a);
  }
  return forms.map((f) => {
    const t = f.features.map((x) => x.toLowerCase());
    if (t.includes("imperfective") || t.includes("perfective")) return f;
    const isSubj = t.includes("subjunctive");
    if (!isSubj && !t.includes("imperative")) return f;
    const bare = stripParticles(f.form);
    const add = isSubj && PERFECT_AUX.test(bare)
      ? "perfect"
      : aspectOf.get(f.form) ?? aspectOf.get(bare) ?? null;
    return add ? { ...f, features: [...f.features, add] } : f;
  });
}

// el-wiktionary's periphrastic-table parser sometimes emits malformed cells: a
// lone separator ("/"), or a run-on listing every person ("έχω έχεις, έχει, …
// γραμμένο"). They carry no person/number, so they'd litter "Άλλοι τύποι". Drop
// them — the clean per-person forms are present alongside.
function isJunkForm(f: WordForm): boolean {
  const form = f.form.trim();
  if (form.length < 2) return true;
  if (form.includes(",")) return true; // run-on auxiliary list
  // A Greek verb form never contains Latin letters — anything that does is a
  // Wiktionary table-header artifact ("Formed using present…", "dependent (for
  // simple past)") or a stray romanization, not a real form.
  if (/[A-Za-z]/.test(form)) return true;
  // el periphrastic-table artifacts: person-less "type-b" stative-perfect cells.
  if (f.features.some((x) => x.toLowerCase() === "type-b")) return true;
  return false;
}

function partition<T>(items: T[], pred: (x: T) => boolean): [T[], T[]] {
  const yes: T[] = [];
  const no: T[] = [];
  for (const i of items) (pred(i) ? yes : no).push(i);
  return [yes, no];
}

export function buildInflection(
  pos: string | null,
  allForms: WordForm[],
  lemma?: string,
): Inflection {
  const forms = allForms
    .map((f) => expandHeadword(pos, f))
    .filter((f): f is WordForm => f !== null && !isJunkForm(f));
  const grids: Grid[] = [];
  let other: WordForm[] = [];

  const isVerb = (pos ?? "").toLowerCase().includes("verb");

  // Wiktionary's form tables omit the headword's own base form (the lemma IS
  // the nominative singular / present·1st·sg·active). Seed it so that cell isn't
  // blank. buildGrid dedups by form text, so this is a no-op if it's present.
  const hasGenderForms = forms.some((f) =>
    f.features.some((x) => GENDERS.includes(x.toLowerCase())),
  );
  if (lemma) {
    // Only tag the headword with gender when the real forms are gendered
    // (adjectives) — otherwise it would split a single-gender noun's paradigm.
    const headFeatures = isVerb
      ? ["present", "indicative", "active", "first-person", "singular", "imperfective"]
      : hasGenderForms
        ? ["nominative", "singular", "masculine"]
        : ["nominative", "singular"];
    forms.unshift({ form: lemma, source: "", features: headFeatures });
  }

  if (isVerb) {
    // Recover aspect for el-style subjunctive/imperative so periphrastic tenses
    // land in proper columns instead of "Άλλοι τύποι".
    const verbForms = disambiguateAspect(forms);
    const [passive, active] = partition(verbForms, (f) =>
      f.features.some((x) => x.toLowerCase() === "passive"),
    );
    for (const [title, sub] of [
      ["Ενεργητική φωνή", active],
      ["Παθητική φωνή", passive],
    ] as const) {
      if (sub.length === 0) continue;
      const { grid, leftover } = buildGrid(title, sub, VERB_COLS, VERB_ROWS);
      if (grid) grids.push(grid);
      other = other.concat(leftover);
    }
  } else {
    const hasGender = forms.some((f) =>
      f.features.some((x) => GENDERS.includes(x.toLowerCase())),
    );
    if (hasGender) {
      let rest = forms;
      for (const g of GENDERS) {
        const [sub, remaining] = partition(rest, (f) =>
          f.features.some((x) => x.toLowerCase() === g),
        );
        rest = remaining;
        if (sub.length === 0) continue;
        const { grid, leftover } = buildGrid(gramEl(g), sub, NOM_COLS, NOM_ROWS);
        if (grid) grids.push(grid);
        other = other.concat(leftover);
      }
      if (rest.length) {
        const { grid, leftover } = buildGrid(null, rest, NOM_COLS, NOM_ROWS);
        if (grid) grids.push(grid);
        other = other.concat(leftover);
      }
    } else {
      const { grid, leftover } = buildGrid(null, forms, NOM_COLS, NOM_ROWS);
      if (grid) grids.push(grid);
      other = other.concat(leftover);
    }
  }

  // Split participles/infinitives out of the leftover into their own box.
  const [nonFinite, rest] = partition(other, (f) =>
    f.features.some((x) => NONFINITE.has(x.toLowerCase())),
  );

  return { grids, nonFinite, other: rest };
}
