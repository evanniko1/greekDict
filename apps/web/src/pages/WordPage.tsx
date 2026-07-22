import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getWord } from "../api/client";
import type { WordEntry, WordResponse } from "../api/types";
import { genderEl, gramEl, posEl, etyRelEl, langEl, relEl, classifyTags, usageEl, domainEl, freqBandEl, freqBandLevel } from "../api/labels";
import InflectionTables from "../components/InflectionTables";
import EtymologyTimeline from "../components/EtymologyTimeline";
import DiachronicPanel from "../components/DiachronicPanel";
import { useIsSaved, toggleSaved, recordRecent } from "../hooks/useUserData";

// The relation graph was a Cytoscape node-link canvas (438 kB, 55% of the JS bundle).
// It was the wrong encoding for this data — median degree 2, ~46% of content lemmas
// with zero edges, 64% of edges the untyped "related" catch-all (audit F33/F34) — so
// the typed relations are rendered as text lists (EntryFamily / EntryCognates) instead.
// The GET /api/word/{lemma}/graph endpoint and the relations/etymons tables are KEPT;
// only the rendering changed. See docs/DELETION-REVIEW.md item 3.

function SourceBadge({ source }: { source: string }) {
  return (
    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
      {source}
    </span>
  );
}

// Frequency meter: a 5-segment bar (filled by band level) + Greek band label.
// Corpus frequency, summed over the lemma's inflected forms — see the frequency
// table. Source-tagged via the title so provenance stays attached.
function FrequencyMeter({ freq }: { freq: NonNullable<WordEntry["frequency"]> }) {
  const level = freqBandLevel(freq.band);
  return (
    <span
      className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400"
      title={`Συχνότητα: ${freqBandEl(freq.band)} (Zipf ${freq.zipf.toFixed(1)}) · πηγή: ${freq.source}`}
    >
      <span className="flex items-end gap-0.5" aria-hidden>
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className={`w-1 rounded-sm ${
              i <= level ? "bg-emerald-500 dark:bg-emerald-400" : "bg-slate-200 dark:bg-slate-700"
            }`}
            style={{ height: `${4 + i * 2}px` }}
          />
        ))}
      </span>
      {freqBandEl(freq.band)}
    </span>
  );
}

// Usage labels for one sense, classified into register/dialect (prominent amber),
// subject domain (indigo), and a curated few grammatical tags (muted). Pure
// inflectional tags are dropped (classifyTags hides them) — they live in Κλίση.
function SenseLabels({ tags, keyPrefix }: { tags: string[]; keyPrefix: string }) {
  const { usage, domain, grammar } = classifyTags(tags);
  if (usage.length === 0 && domain.length === 0 && grammar.length === 0) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {usage.map((t, i) => (
        <span
          key={`${keyPrefix}-u-${i}`}
          className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-500/15 dark:text-amber-300"
        >
          {usageEl(t)}
        </span>
      ))}
      {domain.map((t, i) => (
        <span
          key={`${keyPrefix}-d-${i}`}
          className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300"
        >
          {domainEl(t)}
        </span>
      ))}
      {grammar.map((t, i) => (
        <span
          key={`${keyPrefix}-g-${i}`}
          className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400"
        >
          {gramEl(t)}
        </span>
      ))}
    </div>
  );
}

// Pronunciation playback. Two distinct, honestly-labelled sources:
//  · a synthesized Greek voice via the browser's Web Speech API (no audio data
//    shipped or ingested — the device speaks the headword on demand), and
//  · a link-out to Forvo for authentic human recordings, where the audio lives
//    under its own licence ("AI explains; sources define" — we never re-host it).
// The button hides if the browser has no speech support; the Forvo link always
// shows as a fallback.
function PronounceControls({ lemma }: { lemma: string }) {
  const synthOK = typeof window !== "undefined" && "speechSynthesis" in window;
  const speak = () => {
    try {
      const u = new SpeechSynthesisUtterance(lemma);
      u.lang = "el-GR";
      const el = window.speechSynthesis.getVoices().find((v) => v.lang?.toLowerCase().startsWith("el"));
      if (el) u.voice = el; // prefer a real Greek voice; else the lang hint guides the default
      u.rate = 0.95;
      window.speechSynthesis.cancel(); // stop any in-flight utterance first
      window.speechSynthesis.speak(u);
    } catch {
      /* speech synthesis can throw on some locked-down browsers — fail silent */
    }
  };
  return (
    <span className="flex items-center gap-1.5">
      {synthOK && (
        <button
          type="button"
          onClick={speak}
          title="Ακρόαση προφοράς (συνθετική φωνή)"
          aria-label={`Ακρόαση προφοράς: ${lemma}`}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 transition hover:border-slate-300 hover:text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M11 5 6 9H2v6h4l5 4V5z" />
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
          </svg>
        </button>
      )}
      <a
        href={`https://forvo.com/word/${encodeURIComponent(lemma)}/#el`}
        target="_blank"
        rel="noopener noreferrer"
        title="Ανθρώπινες ηχογραφήσεις στο Forvo (εξωτερικός σύνδεσμος)"
        className="text-xs text-slate-400 underline-offset-2 transition hover:text-slate-600 hover:underline dark:text-slate-500 dark:hover:text-slate-300"
      >
        Forvo ↗
      </a>
    </span>
  );
}

// Header + senses for one entry (the "Ορισμοί" content). For a Modern Greek
// dictionary we show the Greek (el-wiktionary) glosses as primary; the English
// (en-wiktionary) glosses are offered behind a toggle for bilingual mode (#39) —
// useful for learners and as the human-readable side of cross-language search.
function EntryDefinitions({ entry, showEn }: { entry: WordEntry; showEn: boolean }) {
  const greek = entry.senses.filter((s) => s.source.toLowerCase().startsWith("el"));
  const english = entry.senses.filter((s) => s.source.toLowerCase().startsWith("en"));
  // If a lemma has no Greek gloss at all, fall back to showing English as primary
  // (and then there's nothing left to hide behind the toggle).
  const senses = greek.length > 0 ? greek : entry.senses;
  // English glosses only hide behind the (page-level) toggle when this entry has
  // Greek primary glosses too; otherwise English is already shown as primary above.
  const hasEnToggle = greek.length > 0 && english.length > 0;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="font-display text-3xl">{entry.lemma}</h2>
        {entry.pronunciations.length > 0 && (
          <span className="font-mono text-base text-slate-500 dark:text-slate-400" title="Προφορά (IPA)">
            {entry.pronunciations.map((p) => `/${p.ipa}/`).join(" ")}
          </span>
        )}
        <PronounceControls lemma={entry.lemma} />
        {entry.pos && <span className="text-sm text-slate-500 dark:text-slate-400">{posEl(entry.pos)}</span>}
        {entry.gender && <span className="text-sm text-slate-500 dark:text-slate-400">· {genderEl(entry.gender)}</span>}
        {entry.frequency && <FrequencyMeter freq={entry.frequency} />}
        <span className="ml-auto flex flex-wrap gap-1">
          {entry.sources.filter(Boolean).map((s) => (
            <SourceBadge key={s} source={s} />
          ))}
        </span>
      </div>

      {senses.length > 0 && (
        <ol className="mt-4 flex list-decimal flex-col gap-3 pl-5">
          {senses.map((s, si) => (
            <li key={si} className="pl-1">
              <div className="flex items-start gap-2">
                <span className="flex-1">{s.gloss}</span>
                <SourceBadge source={s.source} />
              </div>
              <SenseLabels tags={s.tags} keyPrefix={`${si}`} />
              {s.examples.length > 0 && (
                <ul className="mt-1 flex flex-col gap-0.5 border-l-2 border-slate-100 pl-3 dark:border-slate-700">
                  {s.examples.map((ex, i) => (
                    <li key={`${si}-ex-${i}`} className="text-sm italic text-slate-500 dark:text-slate-400">
                      {ex}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}

      {hasEnToggle && showEn && (
        <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
          <ol className="flex list-decimal flex-col gap-3 pl-5">
            {english.map((s, si) => (
              <li key={`en-${si}`} className="pl-1">
                <div className="flex items-start gap-2">
                  <span className="flex-1" lang="en">{s.gloss}</span>
                  <SourceBadge source={s.source} />
                </div>
                <SenseLabels tags={s.tags} keyPrefix={`en-${si}`} />
                {s.examples.length > 0 && (
                  <ul className="mt-1 flex flex-col gap-0.5 border-l-2 border-slate-100 pl-3 dark:border-slate-700">
                    {s.examples.map((ex, i) => (
                      <li key={`en-${si}-ex-${i}`} className="text-sm italic text-slate-500 dark:text-slate-400" lang="en">
                        {ex}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

// Client-side fold matching the backend normalize(): NFD + strip combining
// marks + lowercase + fold final sigma. Used only to decide which tokens in an
// example sentence to highlight — not a search key.
function normEl(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/ς/g, "σ");
}

// Bold the occurrences of the headword (any inflected form) inside a corpus
// sentence, keeping surrounding punctuation un-bolded.
function highlightSentence(sentence: string, targets: Set<string>) {
  return sentence.split(/(\s+)/).map((tok, i) => {
    if (tok === "" || /^\s+$/.test(tok)) return <span key={i}>{tok}</span>;
    const lead = tok.match(/^[^\p{L}\p{N}]*/u)?.[0] ?? "";
    const trail = tok.match(/[^\p{L}\p{N}]*$/u)?.[0] ?? "";
    const core = tok.slice(lead.length, tok.length - trail.length);
    if (core && targets.has(normEl(core))) {
      return (
        <span key={i}>
          {lead}
          <mark className="rounded bg-amber-100 px-0.5 font-medium text-amber-900 dark:bg-amber-400/20 dark:text-amber-200">
            {core}
          </mark>
          {trail}
        </span>
      );
    }
    return <span key={i}>{tok}</span>;
  });
}

// KWIC examples for one entry: authentic corpus sentences using this word, with
// the headword highlighted. These are emergent usage (Wortschatz Leipzig news
// corpus), distinct from the curated senses.examples — so they carry a source
// badge. Placed right under the definitions so learners see the word "in the wild".
function EntryExamples({ entry }: { entry: WordEntry }) {
  if (entry.examples.length === 0) return null;
  const targets = new Set<string>([normEl(entry.lemma), ...entry.forms.map((f) => normEl(f.form))]);
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          Παραδείγματα χρήσης
        </h3>
        <SourceBadge source={entry.examples[0].source} />
      </div>
      <ul className="flex flex-col gap-2.5">
        {entry.examples.map((ex, i) => (
          <li
            key={i}
            className="border-l-2 border-slate-200 pl-3 text-sm leading-relaxed text-slate-700 dark:border-slate-700 dark:text-slate-300"
          >
            {highlightSentence(ex.sentence, targets)}
          </li>
        ))}
      </ul>
    </section>
  );
}

// Etymology for one entry: the prose origin + structured typed origins
// (inherited / borrowed / derived / calque / cognate), each with its source
// language and provenance badge. "AI explains; sources define" — these come
// straight from Wiktionary's etymology templates.
function EntryEtymology({ entry }: { entry: WordEntry }) {
  if (!entry.etymology && entry.etymons.length === 0) return null;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          Ετυμολογία
        </h3>
        {entry.etymology && <SourceBadge source={entry.etymology.source} />}
      </div>
      {entry.etymology && (
        <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">{entry.etymology.text}</p>
      )}
      {entry.etymons.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5">
          {entry.etymons.map((e, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
              <span className="text-slate-400 dark:text-slate-500">{etyRelEl(e.relation)}</span>
              <span className="font-medium">{e.term}</span>
              {e.lang && (
                <span className="text-xs text-slate-500 dark:text-slate-400">({langEl(e.lang)})</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// Word family for one entry: the typed lexical relations (synonyms, antonyms,
// derived & related terms) as a readable, grouped list of clickable chips —
// the same edges the graph draws, but scannable without opening the graph.
// Resolved targets link to their word page; unresolved ones are plain text.
// Show the most useful families first; "related" is often large so we cap it.
const FAMILY_ORDER = ["synonym", "antonym", "derived", "related", "hypernym", "hyponym"];
const FAMILY_CAP = 24;

function FamilyChip({ term, resolved }: { term: string; resolved: boolean }) {
  const cls =
    "rounded-full px-2.5 py-0.5 text-sm transition border";
  if (resolved) {
    return (
      <Link
        to={`/word/${encodeURIComponent(term)}`}
        className={`${cls} border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-400 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-slate-500`}
      >
        {term}
      </Link>
    );
  }
  return (
    <span className={`${cls} border-transparent bg-slate-50 text-slate-400 dark:bg-slate-800/60 dark:text-slate-500`}>
      {term}
    </span>
  );
}

function EntryFamily({ entry }: { entry: WordEntry }) {
  const groups = entry.family.filter((g) => g.terms.length > 0);
  if (groups.length === 0) return null;
  const ordered = [...groups].sort(
    (a, b) => FAMILY_ORDER.indexOf(a.relation) - FAMILY_ORDER.indexOf(b.relation),
  );
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        Οικογένεια λέξεων
      </h3>
      <div className="flex flex-col gap-3">
        {ordered.map((g) => {
          const shown = g.terms.slice(0, FAMILY_CAP);
          const extra = g.terms.length - shown.length;
          return (
            <div key={g.relation} className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{relEl(g.relation)}</span>
              <div className="flex flex-wrap gap-1.5">
                {shown.map((t, i) => (
                  <FamilyChip key={`${g.relation}-${i}`} term={t.term} resolved={t.resolved} />
                ))}
                {extra > 0 && (
                  <span className="self-center text-xs text-slate-400 dark:text-slate-500">+{extra} ακόμη</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// Descendants for one entry: words in OTHER languages formed from this Greek
// lemma (the forward mirror of etymology). Each carries its language, optional
// romanisation, and provenance badge. Data is en-wiktionary only.
function EntryDescendants({ entry }: { entry: WordEntry }) {
  if (entry.descendants.length === 0) return null;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          Απόγονοι σε άλλες γλώσσες
        </h3>
        <SourceBadge source={entry.descendants[0].source} />
      </div>
      <ul className="flex flex-col gap-1.5">
        {entry.descendants.map((d, i) => (
          <li key={i} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
            <span className="text-xs text-slate-500 dark:text-slate-400">{langEl(d.lang || "") || d.lang_name}</span>
            <span className="font-medium">{d.term}</span>
            {d.roman && <span className="text-xs italic text-slate-400 dark:text-slate-500">{d.roman}</span>}
            <span className="text-xs text-slate-400 dark:text-slate-500">· {etyRelEl(d.relation)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

// Cognate cross-links ("Ομόρριζες λέξεις"): other Modern-Greek lemmas that
// descend from one of this word's etymological ancestors. Grouped by the shared
// root so the kinship is explicit ("κοινή ρίζα: grc χρῶμα"). Derived from shared
// Wiktionary etymons — the source badge makes that provenance visible.
function EntryCognates({ entry }: { entry: WordEntry }) {
  if (!entry.cognates || entry.cognates.length === 0) return null;
  // group by (shared_root, shared_lang), preserving the API's closeness order
  const groups: { root: string; lang: string | null; terms: string[] }[] = [];
  for (const c of entry.cognates) {
    const last = groups[groups.length - 1];
    if (last && last.root === c.shared_root && last.lang === c.shared_lang) last.terms.push(c.term);
    else groups.push({ root: c.shared_root, lang: c.shared_lang, terms: [c.term] });
  }
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          Ομόρριζες λέξεις
        </h3>
        <SourceBadge source={entry.cognates[0].source} />
      </div>
      <div className="flex flex-col gap-3">
        {groups.map((g, gi) => (
          <div key={gi} className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
              κοινή ρίζα: <span className="font-semibold">{g.root}</span>
              {g.lang && <span className="text-slate-400 dark:text-slate-500"> ({langEl(g.lang) || g.lang})</span>}
            </span>
            <div className="flex flex-wrap gap-1.5">
              {g.terms.map((t, i) => (
                <FamilyChip key={`${gi}-${i}`} term={t} resolved={true} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// Collocations for one entry: words that statistically co-occur with this lemma
// in a corpus (Wortschatz Leipzig), ranked by association strength. A collocate
// that is itself a known lemma links to its word page; the rest are plain chips.
// Distinct from Οικογένεια λέξεων (curated lexical relations): these are emergent
// usage patterns, "words you'll find nearby", and carry a corpus source badge.
function EntryCollocations({ entry }: { entry: WordEntry }) {
  if (entry.collocations.length === 0) return null;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          Τυπικές συνάψεις
        </h3>
        <SourceBadge source={entry.collocations[0].source} />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {entry.collocations.map((c, i) => {
          const cls = "rounded-full px-2.5 py-0.5 text-sm transition border";
          return c.collocate_lemma_id != null ? (
            <Link
              key={i}
              to={`/word/${encodeURIComponent(c.collocate)}`}
              className={`${cls} border-teal-200 bg-teal-50 text-teal-700 hover:border-teal-400 hover:bg-teal-100 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-300 dark:hover:border-teal-400`}
            >
              {c.collocate}
            </Link>
          ) : (
            <span
              key={i}
              className={`${cls} border-transparent bg-slate-50 text-slate-500 dark:bg-slate-800/60 dark:text-slate-400`}
            >
              {c.collocate}
            </span>
          );
        })}
      </div>
    </section>
  );
}

// Distributional neighbours for one entry: words that appear in SIMILAR CONTEXTS
// in the corpus, learned by a word-embedding model (e.g. καναπές → πολυθρόνα).
// Deliberately NOT labelled «σημασιολογικοί» (semantic) — cosine proximity in a
// static word2vec space is context similarity, not meaning identity: it pulls in
// co-hyponyms, antonyms and topical associates alike. The old «ομοιότητα X%»
// tooltip presented that cosine as a meaning-similarity percentage, which
// overclaims (audit; DELETION-REVIEW item 5). The raw score is kept off the UI.
function EntryNeighbors({ entry }: { entry: WordEntry }) {
  if (entry.neighbors.length === 0) return null;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-1 flex items-center gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          Λέξεις σε παρόμοια συμφραζόμενα
        </h3>
        <SourceBadge source={entry.neighbors[0].source} />
      </div>
      <p className="mb-3 text-xs text-slate-400 dark:text-slate-500">
        Λέξεις που εμφανίζονται σε παρόμοια περιβάλλοντα στο σώμα κειμένων — γειτνίαση
        χρήσης, όχι ταυτότητα σημασίας.
      </p>
      <div className="flex flex-wrap gap-1.5">
        {entry.neighbors.map((n, i) => (
          <Link
            key={i}
            to={`/word/${encodeURIComponent(n.neighbor)}`}
            className="rounded-full border border-violet-200 bg-violet-50 px-2.5 py-0.5 text-sm text-violet-700 transition hover:border-violet-400 hover:bg-violet-100 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-300 dark:hover:border-violet-400"
          >
            {n.neighbor}
          </Link>
        ))}
      </div>
    </section>
  );
}

// Declension/conjugation for one entry (the "Κλίση" content), grouped into
// proper Greek paradigm tables.
function EntryForms({
  entry,
  showLemma,
  embedded,
}: {
  entry: WordEntry;
  showLemma: boolean;
  embedded?: boolean;
}) {
  if (entry.forms.length === 0) return null;
  const inner = (
    <>
      {showLemma && (
        <div className="mb-3 flex flex-wrap items-baseline gap-2">
          <h2 className="text-lg font-semibold">{entry.lemma}</h2>
          {entry.pos && <span className="text-sm text-slate-500 dark:text-slate-400">{posEl(entry.pos)}</span>}
        </div>
      )}
      <InflectionTables pos={entry.pos} forms={entry.forms} lemma={entry.lemma} />
    </>
  );
  if (embedded) return <div>{inner}</div>;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      {inner}
    </section>
  );
}

// At-a-glance facts for the desktop right rail: a compact summary card so the
// key attributes (POS, gender, frequency, pronunciation) are visible alongside
// the graph without scrolling the definitions. Built from the primary entry.
function QuickFacts({ entries }: { entries: WordEntry[] }) {
  const e = entries[0];
  if (!e) return null;
  const rows: { k: string; v: React.ReactNode }[] = [];
  if (e.pos) rows.push({ k: "Μέρος λόγου", v: posEl(e.pos) });
  if (e.gender) rows.push({ k: "Γένος", v: genderEl(e.gender) });
  if (e.frequency) rows.push({ k: "Συχνότητα", v: freqBandEl(e.frequency.band) });
  if (e.pronunciations.length > 0)
    rows.push({ k: "Προφορά", v: <span className="font-mono">{e.pronunciations.map((p) => `/${p.ipa}/`).join(" ")}</span> });
  if (rows.length === 0) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        Με μια ματιά
      </h3>
      <dl className="flex flex-col gap-1.5 text-sm">
        {rows.map((r) => (
          <div key={r.k} className="flex items-baseline justify-between gap-3">
            <dt className="text-slate-400 dark:text-slate-500">{r.k}</dt>
            <dd className="text-right font-medium text-slate-700 dark:text-slate-200">{r.v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// Save/unsave the current word to the device's saved list. A filled bookmark
// means saved; the list is surfaced on the search landing. Purely local — see
// hooks/useUserData.
function SaveButton({ lemma }: { lemma: string }) {
  const saved = useIsSaved(lemma);
  return (
    <button
      type="button"
      onClick={() => toggleSaved(lemma)}
      aria-pressed={saved}
      title={saved ? "Αφαίρεση από τα αποθηκευμένα" : "Αποθήκευση λέξης"}
      className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium transition ${
        saved
          ? "border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300"
          : "border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
      }`}
    >
      <svg width="15" height="15" viewBox="0 0 24 24" fill={saved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
      </svg>
      {saved ? "Αποθηκευμένη" : "Αποθήκευση"}
    </button>
  );
}

function SectionHeading({ children, id }: { children: React.ReactNode; id?: string }) {
  return (
    <h3 id={id} className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">{children}</h3>
  );
}

export default function WordPage() {
  const { lemma } = useParams<{ lemma: string }>();
  const [data, setData] = useState<WordResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "notfound" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [formsOpen, setFormsOpen] = useState(false);
  // Bilingual mode (#39) is a single page-level toggle shared by every stacked
  // homograph entry, rather than one button per entry — one switch flips them all.
  const [showEn, setShowEn] = useState(false);

  useEffect(() => {
    if (!lemma) return;
    let cancelled = false;
    setStatus("loading");
    setFormsOpen(false);
    setShowEn(false);
    getWord(lemma)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setStatus("ok");
        // Record the canonical lemma (not the typed surface) so history chips
        // link straight to a resolved word page.
        recordRecent(res.entries[0]?.lemma ?? lemma);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        setStatus(msg.startsWith("404") ? "notfound" : "error");
      });
    return () => {
      cancelled = true;
    };
  }, [lemma]);

  const hasForms = !!data && data.entries.some((e) => e.forms.length > 0);
  // The typed, sourced lexical relations that the graph used to render — now shown
  // as text lists. Only mount the «Σχέσεις» section when there is something in it.
  const hasRelations =
    !!data &&
    data.entries.some(
      (e) => e.family.some((g) => g.terms.length > 0) || (e.cognates?.length ?? 0) > 0,
    );

  const multipleEntries = !!data && data.entries.length > 1;

  // Total English glosses that sit behind the page-level bilingual toggle: only
  // those on entries that also carry Greek primary glosses (others show English
  // as primary already). Drives whether/what the single shared switch reveals.
  const enToggleCount = !data
    ? 0
    : data.entries.reduce((n, e) => {
        const hasGreek = e.senses.some((s) => s.source.toLowerCase().startsWith("el"));
        const en = e.senses.filter((s) => s.source.toLowerCase().startsWith("en")).length;
        return n + (hasGreek && en > 0 ? en : 0);
      }, 0);

  const definitions = data && (
    <div className="flex max-w-3xl flex-col gap-4">
      {enToggleCount > 0 && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setShowEn((v) => !v)}
            className="flex items-center gap-1 text-xs font-medium text-sky-700 hover:underline dark:text-sky-300"
            aria-expanded={showEn}
          >
            {showEn ? "Απόκρυψη" : "Εμφάνιση"} αγγλικών ορισμών (English) · {enToggleCount}
          </button>
        </div>
      )}
      {data.entries.map((e) => (
        <div key={e.lemma_id} className="flex flex-col gap-4">
          <EntryDefinitions entry={e} showEn={showEn} />
          <EntryExamples entry={e} />
          <EntryEtymology entry={e} />
          <EtymologyTimeline entry={e} />
          <EntryNeighbors entry={e} />
          <EntryCollocations entry={e} />
          <EntryDescendants entry={e} />
        </div>
      ))}
    </div>
  );

  // Σχέσεις — the typed, sourced lexical relations, as text lists (replaces the
  // Cytoscape graph). Family = curated Wiktionary relations; cognates = shared root.
  const relations = data && hasRelations && (
    <section aria-labelledby="rel-heading" className="flex flex-col gap-4">
      <SectionHeading id="rel-heading">Σχέσεις</SectionHeading>
      {data.entries.map((e) => (
        <div key={e.lemma_id} className="flex flex-col gap-4">
          <EntryFamily entry={e} />
          <EntryCognates entry={e} />
        </div>
      ))}
    </section>
  );

  // Collapsible κλίση (progressive disclosure): paradigm tables are long and
  // secondary to the definitions, so on desktop they collapse by default and
  // expand on demand — keeping the graph rail and definitions above the fold.
  const formsDisclosure = data && hasForms && (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <button
        type="button"
        onClick={() => setFormsOpen((o) => !o)}
        aria-expanded={formsOpen}
        className="flex w-full items-center justify-between gap-2 px-5 py-3.5 text-left transition hover:bg-slate-50 dark:hover:bg-slate-800/50"
      >
        <span className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Κλίση
        </span>
        <span className="flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500">
          {formsOpen ? "Απόκρυψη" : "Δείτε όλη την κλίση"}
          <svg
            className={`h-4 w-4 transition-transform ${formsOpen ? "rotate-180" : ""}`}
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden
          >
            <path
              fillRule="evenodd"
              d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.17l3.71-3.94a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      </button>
      {formsOpen && (
        <div className="border-t border-slate-200 p-5 dark:border-slate-800">
          <div className="flex flex-col gap-6">
            {data.entries.map((e) => (
              <EntryForms key={e.lemma_id} entry={e} showLemma={multipleEntries} embedded />
            ))}
          </div>
        </div>
      )}
    </section>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <Link to="/" className="text-sm text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100">
          ← Αναζήτηση
        </Link>
        {status === "ok" && data && (
          <SaveButton lemma={data.entries[0]?.lemma ?? lemma ?? ""} />
        )}
      </div>

      {status === "loading" && <p className="text-slate-400 dark:text-slate-500">Φόρτωση…</p>}
      {status === "notfound" && (
        <p className="text-slate-500 dark:text-slate-400">Δεν βρέθηκε λήμμα για «{lemma}».</p>
      )}
      {status === "error" && (
        <p className="text-red-600 dark:text-red-400">Αποτυχία φόρτωσης{error ? `: ${error}` : ""}</p>
      )}

      {/*
        One layout tree (audit F34). The three viewport-forked trees + useMediaQuery
        existed only to mount the single Cytoscape canvas exactly once; with the graph
        gone the fork is unnecessary, so everything is one semantic document that a
        container query splits into a reading column + a facts rail on wide screens.
        No JS breakpoints, no fake tab widget — real headings, scroll order preserved.
      */}
      {status === "ok" && data && (
        <div className="@container">
          <div className="grid grid-cols-1 items-start gap-6 @3xl:grid-cols-[minmax(0,1fr)_290px]">
            <div className="flex min-w-0 flex-col gap-6">
              {definitions}
              {relations}
              {lemma && <DiachronicPanel lemma={lemma} />}
              {formsDisclosure}
            </div>
            <aside className="flex flex-col gap-4 @3xl:sticky @3xl:top-4">
              <QuickFacts entries={data.entries} />
            </aside>
          </div>
        </div>
      )}
    </div>
  );
}
