# Λεξόραμα — Redesign Specification

**Version** 1.0 · **Date** 2026-07-21 · **Baseline commit** `0565f04` · **Evidence base** [`docs/AUDIT.md`](AUDIT.md) (63 findings, 6 critical)

Every quantity in this document was re-measured in-session against `data/db/lexorama.sqlite`
(read-only) or the tracked tree at `0565f04`. Where a number differs from one of the source
proposals, mine is the measured one and the delta is noted.

---

## 0. How this spec was chosen

Three redesigns were proposed and independently judged on three lenses (user value; solo-maintainer
buildability; invariant respect and honesty about uncertainty). This spec takes **learner-first as
the spine** and grafts four things onto it. The reasoning:

**Spine.** Learner-first is the only proposal whose thesis is stated as *a user with a task* rather
than *a property of the data*. Evidence-first's organising claim — "the primary interaction is not
'read the entry' but 'see the evidence'" — is a claim about lexicographers, and its Template B
deliberately makes the majority page *worse* ("less impressive than today's page because it says
«δεν βρέθηκε» in four places"). Depth-first is right about what to delete and wrong about what
survives: it files synonymy under etymology, which is a regression on a top-three dictionary job.

**Learner-first's §0 measurement is the best analytical contribution in any of the three, and it
reproduces exactly.** Recomputing coverage against 109,967 content lemmas and against the top-5,000
frequency band changes what should be built:

| surface | all 446,840 | content 109,967 | top-5k band (4,126) |
|---|---|---|---|
| inflected forms | 87.3% | **81.9%** (90,091) | **96.4%** (3,976) |
| collocations | 8.4% | **21.1%** (23,171) | **97.9%** (4,040) |
| corpus examples | 17.9% | **40.5%** (44,587) | **92.2%** (3,804) |
| relations (any) | 13.8% | **51.5%** (56,612) | **83.4%** (3,442) |
| **synonym edges** | — | **21.3%** (23,452) | **53.0%** (2,188) |
| IPA | 9.2% | **28.9%** (31,824) | **78.6%** (3,241) |
| etymons | — | **34.0%** (37,427) | **72.0%** (2,971) |
| ≥4 senses | — | **7.6%** (8,382) | **47.2%** (1,948) |
| exactly 1 sense | — | **62.9%** (69,142) | **14.8%** (610) |

The "3-card stub" is a **tail** problem and the "14 surfaces" is a **head** problem, and today's
design applies identical chrome to both. That is the whole brief.

**Grafts, and why.**

| Graft | From | Why |
|---|---|---|
| The name split as *product architecture* (`lemma_class` at the data layer, separate route, excluded from default search, every coverage number recomputed) | depth-first §2.2 | Named strongest element by two independent judges. 336,873/446,840 lemmas are names; 1,567,032/3,663,525 (42.8%) `search_index` rows point at them. No other single change moves as much user value. |
| A `sources` registry with a `kind` column, promoted to the primary visual axis | evidence-first §8.1 | Named strongest by three judges. All 16 sourced tables already carry `source TEXT NOT NULL`; this makes it a *keyed vocabulary* instead of free text, and turns invariant 3 from a convention into a CI-testable constraint. 2–3 days, no re-ingest. |
| `Provenance` as a **kind-first** primitive + `search_index.source`/`generated` columns | depth-first §3.6 | `search_index` (`pipelines/ingest/schema.sql:64-73`) has no `source` column at all, so 170,749 rule-generated forms are served indistinguishably from Wiktionary-attested ones (F26/C19). `build_search_index.py` is 58 lines of pure SQL over `lemmas`+`forms`; re-deriving is hours, not days, and touches no jsonl. |
| `CoverageNote` — one authored panel replacing 22 bare `return null` sites | depth-first §3.5 | Costs nothing. Converts the modal 3-card page from "looks broken" into "complete answer for a rare word." |
| Deletion shipped as a standalone PR *before anything is added* | depth-first, per the buildability judge | Zero data dependencies, order-independent of every Tier 0/1 audit item, and discharges audit CUT items 1–5 and 7 without writing the code those tickets ask for. |

**Corrections applied to all three, from the judgements and from my own verification.**

1. **Four provenance kinds, not three.** `pipelines/ingest/backfill_paradigms.py` sets
   `SOURCE = "generated"` for 170,749 deterministic finite-state paradigm cells. Painting those the
   same colour, under the same Greek string, as language-model prose is a **provenance merge** and
   violates `docs/licensing.md` verbatim ("Never silently merge human, Wiktionary, WordNet, corpus,
   or AI-generated content"). Rule-derived = `derived` / «παραγόμενο από κανόνα». LLM = `generated`
   / «γραμμένο από μοντέλο».
2. **Eval gold is keyed on `(lemma, pos)`, never `lemma_id`,** and the set carries an *authored*
   coverage slice. A known-item set auto-generated **from** `forms` cannot emit a query for a lemma
   that has no rows — so it is structurally blind to F21/C18 (ποτέ, νομός, δουλεία, μονός, κάλος,
   χαλί, στοιχειό, ωρά = 0 rows), the exact failure the queued re-ingest exists to fix. It would
   stay green through the largest coverage change in the project's history. `(lemma, pos)` is also
   the identity key R2 just installed (`schema.sql:15`), so the set survives the re-ingest.
3. **`(si.surface = ?) DESC` stays ORDER BY term 1.** `services/api/app/main.py:311` is
   `ORDER BY (si.surface = ?) DESC, freq_rank ASC, si.rank_weight DESC, si.lemma_id ASC`, and
   `:293-303` documents term 1 as the implementation of invariant 2 (accent-homographs disambiguated
   at ranking). Making a frequency-dominated prior the primary key demotes it to position 4. The
   prior replaces the *sentinel*, at position 2.
4. **The corpus cannot adjudicate an ambiguity between two analyses of an identical surface.**
   «καλής → γενική ενικού θηλυκού **ή** αιτιατική πληθυντικού θηλυκού» share one token count. Any
   split of that count is invented. Removed from the spec; we say «δεν επιλέγουμε» and mean it.
5. **The ByT5 precompute as specified is not implementable.** `AUEB-NLP/ByT5_g2g` maps
   greeklish→Greek; you cannot run it *from* lemmas without inverting it, and `query_log` holds
   **33 rows** — verified. Ship the rule-table fix + scored beam (already audit item 1.10); defer
   ByT5 behind an explicit synthetic-greeklish generation step, honestly costed.
6. **No sentence index.** Evidence-first's Phase 4 is a single point of failure carrying seven
   downstream features, and its own §9 concedes it "will likely multiply a 1.5 GB database". Cut.
   The evidence surfaces we ship are built from `corpus_examples` (294k rows already present),
   `collocations` and `frequency_timeseries`.
7. **ASCII route stems.** Greek path segments percent-encode; `/λ/άνθρωπος` renders as
   `/%CE%BB/%CE%AC%CE%BD...` in every shared link, doubling the existing ugliness of the Greek
   *object* for zero user benefit, and it breaks every existing URL. Route stems stay ASCII; the
   UI stays entirely Greek.
8. **`RelationGraph` is mounted unconditionally on desktop only.** On mobile it sits inside
   `{tab === "rel" && relations}` (`WordPage.tsx:806`). The "438 kB on every pageview" framing is
   overstated; the correct statement is "438 kB on every desktop word page, 86.2% of which have zero
   edges."

---

## 1. Thesis and positioning

**Λεξόραμα is the tool you open when you have just met a Greek word you don't know — in a book, a
subtitle, a sign, a message — and you need to understand it before you lose the thread.**

It answers, in one screen and under a second: *what form is this · what is its dictionary word ·
what does that word mean · how do I say it · what else could it have been.*

It ships one capability no comparator implements: an **explained form→lemma resolution that returns
every valid analysis**, not a coin flip. DWDS redirects `ging → gehen` and never says why, and
collides `Häuser → Hauser` onto an unrelated surname. DDO and ANW are lemma-indexed. Woordenlijst
has the paradigm but no definitions and no search UX. `ανθρώπων → άνθρωπος · γενική πληθυντικού
**ή** κλητική ενικού` is the product.

### What it stops being

- **Not a graph-first visual dictionary.** 385,167 of 446,840 lemmas (86.2%) have zero outgoing
  relation edges; the median among those that have any is 2; only 6,358 lemmas (1.42%) have ≥10.
  `cytoscape` is 438,616 B — **55% of the 799,177 B JS bundle** — to draw a three-node star. The
  dependency is deleted (§6).
- **Not a corpus-analytics platform.** `/explore`'s drift, trends, by-field, movers and compare
  views are retired. The audit established the drift signal is ~96% estimator noise, that change
  points are a corpus-gap artefact, and that keyness rank 4 on the news axis is the Greek guillemet
  indexed as a form of περιπλέκω.
- **Not a 446,840-entry dictionary.** It is a **109,967-entry dictionary plus a separate name
  index** — the ordnet.dk / *Navneleksikon* split. Every public coverage number is recomputed
  against the smaller denominator, which is the cheapest honesty win available.
- **Not a product with an LLM in it — until there is one.** `AboutPage.tsx:101` ships
  «Η ΤΝ εξηγεί· οι πηγές ορίζουν» and `MethodologyPage.tsx:228` ships the same claim reversed.
  There is no LLM anywhere in the product; the "explanation" is an f-string at `main.py:266-274`.
  The slogan is deleted in Phase 0, before the feature is built, not after.

### The positioning line

Replacing «γραφοκεντρικό οπτικό λεξικό» on `AboutPage` and in the `<meta name="description">`:

> **«Γράψε τη λέξη όπως τη βρήκες. Θα σου πούμε τι είναι — και από πού το ξέρουμε.»**

And the principle line, replacing the AI claim:

> **Τώρα:** «Οι πηγές ορίζουν. Δείχνουμε από πού προέρχεται κάθε γραμμή — και τι δεν έχουμε.»
> **Όταν κυκλοφορήσει το μοντέλο:** «Οι πηγές ορίζουν· το μοντέλο μόνο εξηγεί — και ελέγχεται πριν δημοσιευτεί.»

### Declared lexicographic function (Tarp)

A reference tool that does not declare its function cannot be evaluated on its own terms. Λεξόραμα
declares **text reception in L1/L2 Modern Greek** as its primary function, **cognitive** (learning
about the word) as secondary and strictly below the fold, and **text production** as out of scope.
Every layout rule in §4 derives from that ordering.

---

## 2. Design system

### 2.1 What exists today

`apps/web/src/index.css` is **18 lines** — `@import`, a `@custom-variant`, `color-scheme`, and a
body transition. There is **no `@theme` block**, so Tailwind v4's token layer is entirely unused and
every decision is a literal at a call site. Measured: 321 distinct class tokens, 59 spacing steps,
80 colour values, 12 type sizes, 7 radii, the card shell literal repeated 12×, 22 hand-typed hex
literals in SVG/Cytoscape code, and 315 hand-mirrored `dark:` variants. Repo-wide greps over
`apps/web/src`: `focus-visible` **0**, `document.title` **0**, `onKeyDown` **0**, `<form` **0**,
`role="combobox"` **0**, `title=` **26**, `uppercase` **27**, `text-slate-400` **130**,
`return null` **22**.

Two consequences are AA failures, not preferences: `text-slate-400 dark:text-slate-500` is the app's
most-used token and computes to **2.56:1**, applied at 12px to all seven uppercase section headings;
and light-mode cards are `bg-white` on `bg-slate-50` = **1.03:1**, so a card is not perceptible as
an object.

### 2.2 The token file

Replaces `apps/web/src/index.css` entirely. Paste-ready for Tailwind v4.

```css
/* apps/web/src/index.css — the single token authority.
   Components reference SEMANTIC names only. Ramp steps (n1…n12) are private. */

@import "tailwindcss";
@custom-variant dark (&:where(.dark, .dark *));

/* ── FONTS ──────────────────────────────────────────────────────────────────
   Self-hosted, pyftsubset-generated, woff2. Two families, four files.
   `unicode-range` splits polytonic into its own file so it downloads only on a
   page that contains it — measured: 19,665 of 436,425 etymology rows (4.5%)
   contain a Greek-Extended codepoint, and the DB's inventory is 123 distinct
   polytonic, 81 Modern Greek, 54 non-ASCII IPA codepoints.
   `scripts/check_font_coverage.py` asserts the built subsets cover all three
   inventories and FAILS the build otherwise — do not trust font METADATA flags. */

@font-face {                                   /* Latin + Modern Greek + punctuation */
  font-family: "Lexorama Sans"; src: url("/f/lx-sans-core.woff2") format("woff2-variations");
  font-weight: 400 700; font-style: normal; font-display: swap;
  unicode-range: U+0000-024F, U+0370-03FF, U+0300-036F, U+2000-206F, U+20AC;
}
@font-face {                                   /* Greek Extended — polytonic etymons */
  font-family: "Lexorama Sans"; src: url("/f/lx-sans-poly.woff2") format("woff2-variations");
  font-weight: 400 700; font-style: normal; font-display: swap;
  unicode-range: U+1F00-1FFF;
}
@font-face {                                   /* headword + gloss text face */
  font-family: "Lexorama Text"; src: url("/f/lx-text.woff2") format("woff2-variations");
  font-weight: 400 700; font-style: normal; font-display: swap;
  unicode-range: U+0000-024F, U+0370-03FF, U+0300-036F, U+1F00-1FFF, U+2000-206F;
}
@font-face {                                   /* IPA — 54 non-ASCII codepoints in the DB */
  font-family: "Lexorama IPA"; src: url("/f/lx-ipa.woff2") format("woff2");
  font-weight: 400; font-style: normal; font-display: swap;
  unicode-range: U+0250-02AF, U+02B0-02FF, U+1D00-1D7F, U+0300-036F;
}

@theme {
  /* ══ FONT STACKS ══════════════════════════════════════════════════════════
     Fallbacks are ordered by measured Greek coverage, never by `system-ui`.
     The CSSWG states system-ui is "intended to make UI elements look like
     native apps, and not for typesetting large paragraphs of text"
     (csswg-drafts#3658); on Android it resolves to Roboto, whose Greek-Extended
     coverage is near-zero — which is exactly where the etymology feature lives. */
  --font-sans: "Lexorama Sans", "Noto Sans", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  --font-text: "Lexorama Text", "Gentium Book Plus", "Noto Serif", Georgia, serif;
  --font-ipa:  "Lexorama IPA", "Gentium Plus", "Charis SIL", "Lexorama Text", serif;
  --font-mono: "Noto Sans Mono", ui-monospace, Consolas, monospace;   /* code/IDs only, never IPA */

  /* ══ NEUTRAL RAMP — OKLCH, hue 262, near-achromatic ═══════════════════════
     Radix 12-step semantics: 1–2 backgrounds · 3–5 component fill/hover/active
     · 6–8 borders (subtle / interactive / strong) · 9–10 solid · 11–12 text.
     Contrast is designed INTO the scale, so an illegal pair cannot be picked.
     Measured (WCAG 2.x relative luminance) — light: n12/n1 16.30:1,
     n11/n1 6.67:1, n8s/n1 3.04:1. Dark: n12/n1 16.96:1, n11/n1 9.30:1,
     n8s/n1 3.16:1, n2/n1 1.18:1. */
  --lx-l-1:  oklch(99.2% 0.002 262);   --lx-d-1:  oklch(17.6% 0.006 262);
  --lx-l-2:  oklch(97.8% 0.003 262);   --lx-d-2:  oklch(25.0% 0.008 262);
  --lx-l-3:  oklch(96.0% 0.005 262);   --lx-d-3:  oklch(28.5% 0.009 262);
  --lx-l-4:  oklch(94.0% 0.006 262);   --lx-d-4:  oklch(31.5% 0.010 262);
  --lx-l-5:  oklch(91.8% 0.007 262);   --lx-d-5:  oklch(34.5% 0.011 262);
  --lx-l-6:  oklch(88.8% 0.008 262);   --lx-d-6:  oklch(38.5% 0.012 262);
  --lx-l-7:  oklch(84.8% 0.010 262);   --lx-d-7:  oklch(43.0% 0.013 262);
  --lx-l-8:  oklch(66.0% 0.014 262);   --lx-d-8:  oklch(50.0% 0.015 262);  /* ≥3:1 boundary */
  --lx-l-9:  oklch(60.0% 0.020 262);   --lx-d-9:  oklch(60.0% 0.020 262);
  --lx-l-10: oklch(55.2% 0.020 262);   --lx-d-10: oklch(65.2% 0.020 262);
  --lx-l-11: oklch(47.0% 0.018 262);   --lx-d-11: oklch(77.5% 0.016 262);  /* text · secondary */
  --lx-l-12: oklch(23.5% 0.014 262);   --lx-d-12: oklch(96.2% 0.006 262);  /* text · primary */

  /* ══ PROVENANCE — FOUR kinds, four hues. This is the primary semantic axis. ══
     Derived FROM `sources.kind` (§8.2). Never assigned by a component author.
     All ≥6.5:1 on both surface tokens in both themes (measured). */
  /*                       light                        dark                       */
  --lx-ev-attested-l:  oklch(45.2% 0.108 152);  --lx-ev-attested-d:  oklch(80.0% 0.105 152);
  --lx-ev-computed-l:  oklch(45.5% 0.112 248);  --lx-ev-computed-d:  oklch(80.0% 0.100 248);
  --lx-ev-derived-l:   oklch(46.2% 0.098  72);  --lx-ev-derived-d:   oklch(81.5% 0.098  72);
  --lx-ev-generated-l: oklch(47.0% 0.152 300);  --lx-ev-generated-d: oklch(80.0% 0.120 300);

  /* ══ ACCENT + STATUS ══════════════════════════════════════════════════════ */
  --lx-accent-solid-l: oklch(48.0% 0.168 262);  --lx-accent-solid-d: oklch(64.0% 0.160 262);
  --lx-accent-text-l:  oklch(45.2% 0.155 262);  --lx-accent-text-d:  oklch(79.0% 0.115 262);
  --lx-focus-l:        oklch(56.0% 0.190 262);  --lx-focus-d:        oklch(70.0% 0.165 262);
  --lx-danger-l:       oklch(47.0% 0.170  25);  --lx-danger-d:       oklch(76.0% 0.140  25);

  /* ══ SEMANTIC ALIASES — the ONLY colour names a component may reference. ════
     light-dark() keys off `color-scheme`, which the existing base layer already
     sets on :root and .dark, so the manual class toggle drives it unchanged and
     the 315 hand-mirrored `dark:` variants collapse to zero.
     Baseline newly-available May 2024 (Chrome 123 / Firefox 120 / Safari 17.5). */
  --color-page:            light-dark(var(--lx-l-2),  var(--lx-d-1));
  --color-surface:         light-dark(var(--lx-l-1),  var(--lx-d-2));
  --color-surface-subtle:  light-dark(var(--lx-l-3),  var(--lx-d-3));
  --color-surface-hover:   light-dark(var(--lx-l-4),  var(--lx-d-4));
  --color-surface-active:  light-dark(var(--lx-l-5),  var(--lx-d-5));
  --color-border:          light-dark(var(--lx-l-6),  var(--lx-d-6));
  --color-border-interactive: light-dark(var(--lx-l-7), var(--lx-d-7));
  --color-border-strong:   light-dark(var(--lx-l-8),  var(--lx-d-8));   /* 3.04 / 3.16 :1 */
  --color-text:            light-dark(var(--lx-l-12), var(--lx-d-12));
  --color-text-secondary:  light-dark(var(--lx-l-11), var(--lx-d-11));
  --color-accent:          light-dark(var(--lx-accent-solid-l), var(--lx-accent-solid-d));
  --color-link:            light-dark(var(--lx-accent-text-l),  var(--lx-accent-text-d));
  --color-focus:           light-dark(var(--lx-focus-l),        var(--lx-focus-d));
  --color-danger:          light-dark(var(--lx-danger-l),       var(--lx-danger-d));
  --color-attested:        light-dark(var(--lx-ev-attested-l),  var(--lx-ev-attested-d));
  --color-computed:        light-dark(var(--lx-ev-computed-l),  var(--lx-ev-computed-d));
  --color-derived:         light-dark(var(--lx-ev-derived-l),   var(--lx-ev-derived-d));
  --color-generated:       light-dark(var(--lx-ev-generated-l), var(--lx-ev-generated-d));

  /* ══ TYPE — fluid, Greek-calibrated ═══════════════════════════════════════
     Body base is 17→19px, not the current 12–14px (`text-sm` ×64 + `text-xs` ×59
     = 84% of all sizing declarations). Greek diacritics (tonos, dialytika) sit
     above the x-height, so body leading is 1.62, not Latin's 1.5. */
  --text-2xs:  0.8125rem;                                              /* 13px — chips only */
  --text-xs:   clamp(0.875rem,  0.848rem + 0.12vi, 0.9375rem);         /* 14 → 15 */
  --text-sm:   clamp(0.9375rem, 0.900rem + 0.17vi, 1rem);              /* 15 → 16 */
  --text-base: clamp(1.0625rem, 1.020rem + 0.20vi, 1.1875rem);         /* 17 → 19  body/gloss */
  --text-lg:   clamp(1.1875rem, 1.120rem + 0.32vi, 1.375rem);          /* 19 → 22  sense 1 */
  --text-xl:   clamp(1.375rem,  1.270rem + 0.50vi, 1.625rem);          /* 22 → 26 */
  --text-2xl:  clamp(1.75rem,   1.560rem + 0.90vi, 2.25rem);           /* 28 → 36 */
  --text-3xl:  clamp(2.25rem,   1.900rem + 1.65vi, 3rem);              /* 36 → 48  headword */

  --leading-body:    1.62;
  --leading-heading: 1.20;
  --leading-tight:   1.12;
  --tracking-label:  0.01em;
  --tracking-display: -0.011em;

  /* measure in ch — replaces max-w-3xl, which yields 98–116 CPL for Greek */
  --measure-gloss: 58ch;
  --measure-prose: 64ch;
  --width-content: 76rem;                       /* replaces max-w-5xl at App.tsx:18,39 */

  /* ══ SPACE — 4px base, 8 steps, no exceptions (was 59 ad-hoc steps) ═══════ */
  --space-1: 0.25rem;  --space-2: 0.5rem;  --space-3: 0.75rem;  --space-4: 1rem;
  --space-5: 1.5rem;   --space-6: 2rem;    --space-7: 3rem;     --space-8: 4rem;

  /* ══ RADII — 3 (was 7) ════════════════════════════════════════════════════ */
  --radius-sm: 0.375rem;  --radius-md: 0.625rem;  --radius-full: 9999px;

  /* ══ ELEVATION — 3. Light mode separates surfaces by BORDER (WCAG 1.4.11
     ≥3:1 boundary), dark mode by LIGHTNESS (n2/n1 = 1.18:1) plus border.
     A 1.04:1 fill difference is not an object boundary and never was. ═══════ */
  --shadow-0: none;
  --shadow-1: 0 1px 2px light-dark(oklch(23.5% 0.014 262 / 0.06), oklch(0% 0 0 / 0.40));
  --shadow-2: 0 8px 24px -6px light-dark(oklch(23.5% 0.014 262 / 0.16), oklch(0% 0 0 / 0.55)),
              0 2px  6px -2px light-dark(oklch(23.5% 0.014 262 / 0.10), oklch(0% 0 0 / 0.40));

  /* ══ MOTION — 2 durations, 1 easing ═══════════════════════════════════════ */
  --dur-fast: 120ms;  --dur-base: 200ms;
  --ease-out: cubic-bezier(0.2, 0, 0, 1);
}

@layer base {
  :root { color-scheme: light; }
  .dark { color-scheme: dark; }

  html { -webkit-text-size-adjust: 100%; }

  body {
    background: var(--color-page);
    color: var(--color-text);
    font-family: var(--font-sans);
    font-size: var(--text-base);
    line-height: var(--leading-body);
    font-synthesis-weight: none;            /* never fake-bold a Greek face */
    text-rendering: optimizeLegibility;
  }

  /* One global focus ring. There are currently ZERO `focus-visible` rules in the
     app and exactly one authored focus style (SearchPage.tsx:118). */
  :where(a, button, input, select, textarea, summary, [tabindex]):focus-visible {
    outline: 3px solid var(--color-focus);
    outline-offset: 2px;
    border-radius: var(--radius-sm);
  }

  /* IPA never renders in a mono face: JetBrains Mono covers a minority of the
     54 non-ASCII IPA codepoints measured in `pronunciations.ipa`. */
  [data-ipa] { font-family: var(--font-ipa); font-variant-ligatures: none; }

  /* Greek text-transform: BANNED. Greek orthography drops the tonos in all-caps
     (dialytika is retained). CSS Text 3 §text-transform requires the language
     tailoring, but UA support is not universal — WebKit does not implement it,
     so on iOS all 27 `uppercase` sites render orthographically WRONG Greek:
     ΕΤΥΜΟΛΟΓΊΑ, ΣΗΜΑΣΙΟΛΟΓΙΚΟΊ ΓΕΊΤΟΝΕΣ. A dictionary that mis-accents its own
     headings is teaching wrong orthography. Enforced by lint, asserted here. */
  :lang(el) { text-transform: none !important; }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important; animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important; scroll-behavior: auto !important;
    }
  }
}
```

### 2.3 Rules the tokens enforce

| Rule | Mechanism | Replaces |
|---|---|---|
| No component picks a raw colour | Only `--color-*` semantic aliases are exported as Tailwind utilities; ramp steps are `--lx-*` and generate none | 80 ad-hoc colour values |
| No hand-mirrored dark variants | `light-dark()` on every alias | 315 `dark:` variants (17% of all class tokens) |
| SVG and canvas share one colour system | `getComputedStyle(document.documentElement).getPropertyValue('--color-computed')` | 22 hex literals in `RelationGraph.tsx:12-25`, `DiachronicPanel.tsx:10-36`, `ExplorePage.tsx:31-37` |
| Text contrast ≥4.5:1, boundaries ≥3:1, both themes | `scripts/check_contrast.py` walks every semantic pair × both themes; **fails the build** below threshold | `text-slate-400 dark:text-slate-500` at 2.56:1 |
| Greek never renders in a font that lacks the codepoint | `scripts/check_font_coverage.py` diffs built subsets against the DB's live codepoint inventory (123 polytonic / 81 mGreek / 54 IPA); fails the build on a gap | 0 bytes of font budget today, 0 `@font-face` rules in `dist/assets/index-C1CXiPaU.css` |
| No `title=` attribute anywhere | ESLint `react/no-unknown-property` extension + a custom rule | 26 `title=` sites carrying the entire honesty layer, invisible on touch and to keyboards |

**Font budget arithmetic.** Four subsets ≈ 96–120 kB woff2, against 438,616 B of Cytoscape deleted.
Net bundle change is **−320 kB or better**, and the app stops being a dictionary that spent 55% of
its JS on a graph library and nothing on the script it exists to display.

---

## 3. Component inventory

Directory layout is new: `src/components/ui/` (primitives), `src/components/provenance/`,
`src/components/entry/`, `src/components/search/`. Nothing under `ui/` exists today.

### 3.1 Primitives — `src/components/ui/`

| Component | States | Replaces / modifies |
|---|---|---|
| `Surface` | `elevation 0\|1\|2`, `interactive` | The card shell literal `rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:…` typed out **12×** (`WordPage.tsx:152,264,292,354,387,422,456,496,544`, `MethodologyPage.tsx:263`, `DiachronicPanel.tsx:322`, `EtymologyTimeline.tsx:78`) |
| `Heading` | `level 1–4`, `tone default\|secondary` | Three duplicate `SectionHeading` definitions (`WordPage.tsx:605`, `AboutPage.tsx:132`, `MethodologyPage.tsx:271`), all uppercase, all 2.56:1 |
| `Prose` | `measure gloss\|prose` | `max-w-3xl` at `WordPage.tsx:676`, `AboutPage.tsx:140`, `MethodologyPage.tsx:347` |
| `Chip` | default / hover / active / disabled; `min-height: 1.5rem`, `min-width: 1.5rem` | 18 ad-hoc pill implementations, several computing to 20–22px (below WCAG 2.2 SC 2.5.8 minimum) |
| `Button` | primary / secondary / ghost; loading; disabled; `min-height: 2.75rem` on touch | Ad-hoc buttons in `WordPage.tsx:596`, `SearchPage.tsx:55` |
| `Disclosure` | closed / open / `deepLinked` (auto-open + highlight); summary always carries a count | The single Κλίση accordion at `WordPage.tsx:717-754`, desktop-only |
| `Popover` | closed / open / keyboard-open; anchored; Escape-dismissible; touch-reachable | All 26 native `title=` attributes |
| `LiveRegion` | `polite` / `assertive` | Six unstyled `<p>Φόρτωση…</p>` strings (`SearchPage.tsx:187`, `WordPage.tsx:757,773`, `ExplorePage.tsx:152`, `LicensingPage.tsx:65`) |
| `Skeleton` | shape-aware: `stub` (3 blocks) / `rich` (5 blocks) | Same six strings |
| `ErrorState` | `notFound` / `serverError` / `offline`; always offers a search box | `WordPage.tsx:777-779`, which prints `500 Internal Server Error for /api/word/…` into an all-Greek UI |

### 3.2 Provenance — `src/components/provenance/`

This is the distinctive layer and the primary semantic axis. All four consume `sources.kind` (§8.2);
**a component author never chooses a kind.**

| Component | Contract |
|---|---|
| `Provenance` | Kind-first, source-second. Renders marker + Greek label. `attested` → solid dot, «πηγή: Βικιλεξικό (el)». `computed` → hollow dot, «υπολογισμένο από: Leipzig ell_news». `derived` → dashed underline + `*`, «τύπος παραγόμενος από κανόνα». `generated` → violet bracket, «γραμμένο από γλωσσικό μοντέλο». Per **item**, never per block. |
| `Cite` | Resolvable link: Wiktionary page + revision, OMW synset id, Leipzig sentence id, Parliament record id. Replaces `SourceBadge` (`WordPage.tsx:16-25`), which names a source, cannot be clicked, and badges an entire block from `entry.examples[0].source` (`:269, :461, :501`). |
| `Measure` | Mandatory on every `computed` surface. «Dunning G² · πρόταση ως παράθυρο · Ειδήσεις (Leipzig ell_news 2011–2024)». This is DWDS's `(berechnet)` promoted from a parenthesis to a component. |
| `CoverageNote` | The block that replaces 22 `return null` sites. Always rendered. States what was checked and not found, naming the source that was checked. §4.2.4. |
| `ReportError` | Typed error modal on every `computed`, `derived` and `generated` item: «λάθος τύπος» / «άσχετο παράδειγμα» / «λάθος πηγή» / «άλλο» + free text. Writes to a new `error_reports` table. |

### 3.3 Entry — `src/components/entry/`

| Component | Replaces | Note |
|---|---|---|
| `MatchBanner` | *(new)* | Renders only when `?f=` differs from the lemma. Shows **all** analyses. §4.2.1 |
| `HeadwordBlock` | `WordPage.tsx:143-200` + `QuickFacts` (`:553`, wide-desktop-only) | `QuickFacts` is the only lookup-shaped summary in the app and it is gated behind `min-width:1024px`. Inverted: it *is* the identity block, on every viewport. Headword promoted `<h2>` → `<h1>`. |
| `SenseMenu` | *(new)* | Rendered when `senses ≥ 4` (7.6% of content lemmas; **47.2% of the top-5k band**). Anchor-linked signposts. |
| `SenseList` | `EntryDefinitions` (`WordPage.tsx:203-261`) | Sense 1 at `--text-lg`; register/domain tags per sense via existing `classifyTags` in `labels.ts`. |
| `ParadigmTable` | `InflectionTables.tsx` | Keeps the dotted-underline + superscript `*` generated marker (`:72-81`) — genuinely good, now driven by `kind='derived'` instead of a hardcoded `title=`. Adds `?f=` cell highlight. |
| `EtymologySpine` | `EntryEtymology` (`:289`) **and** `EtymologyTimeline` (`:694`) — the same `entry.etymons` array is rendered **twice** today | One rendering. `etymology.text` becomes its caption. Cognates fold in as sibling nodes, deleting `EntryCognates` (`:412`). |
| `SynonymBlock` | *(new — split out of `EntryFamily`)* | **21.3% of content lemmas, 53.0% of the top-5k band.** «Ποια άλλη λέξη;» is a top-three dictionary job. `synonym` (55,360 edges) and `antonym` (11,035) get their own block; `main.py:474-487` already groups by `relation_type`. |
| `WordFamily` | `EntryFamily` (`:347`) | Derivational relations only (`derived`, `hypernym`, `hyponym`). `related` — 186,495 of 291,208 rows (64.0%) — is demoted to a plain trailing list under the heading «Σχετικές λέξεις (χωρίς τύπο σχέσης)», never a peer of a typed edge. |
| `CollocationList` | `EntryCollocations` (`:454`) | **Kept** — 37,662 lemmas, 97.9% of the top-5k band. Relabelled: «Λέξεις που συνεμφανίζονται» + `Measure`, not «Τυπικές συνάψεις» (C24: it is sentence co-occurrence, not a typed collocation). |
| `ExampleList` | `EntryExamples` (`:256`) | Per-example `Cite`, not one badge from `examples[0].source`. `ReportError` per example. |
| `FrequencyBand` | `WordPage.tsx:27-47` | One word + a band, **no Zipf number and no meter**, until F2 is fixed. Per-lemma counts currently sum to 1,026% of the corpus and `MAX(zipf)=8.615` on a scale that tops near 7. |
| `PronounceButton` | `WordPage.tsx:93-135` | **Already correct** — a real `<button>` with `onClick`, `aria-label`, Web Speech `el-GR`, Forvo link-out. Restyled only. |

### 3.4 Search — `src/components/search/`

| Component | Replaces |
|---|---|
| `SearchCombobox` | `SearchPage.tsx:107-121` — one bare `<input>`, no `<form>`, no `<label>`, no key handlers. Full APG combobox. §5.6 |
| `ResultRow` | `ResultCard.tsx` — becomes a `role="option"` renderer, gains `analyses[]` and `via` badging |
| `NameGroup` | *(new)* — the collapsed «Ονόματα και επώνυμα (N)» group |
| `RecoveryPanel` | `SearchPage.tsx:196-200` — one sentence and a dead end, for 97.9% of one-character typos |

### 3.5 Deleted outright

| Deleted | Location | Measured justification |
|---|---|---|
| `RelationGraph` + `cytoscape` + `@types/cytoscape` | 242 LOC; `WordPage.tsx:14,758,806,821`; `main.py:574-658` | 86.2% zero edges; median 2; 1.42% have ≥10; 438,616 B = 55% of the JS bundle |
| `ExplorePage` | 541 LOC; `main.py:1069,1101,1240,1297,1408` | Drift is ~96% estimator noise; keyness rank 4 is a guillemet artefact; trends #1 faller is a bare-ending artefact |
| `DiachronicPanel` | 375 LOC; `main.py:900,1001` | Same; change points are a corpus-gap artefact |
| `EntryNeighbors` | `WordPage.tsx:493-530` | 13.0% of content lemmas; ρ=0.79 with cosine drift, ρ=−0.52 with frequency — neither independent nor frequency-robust (C6). Table kept as an internal diagnostic. |
| `EntryDescendants` | `WordPage.tsx:385-411` | 379 lemmas (0.1%) with its own schema table, ingest mode, API field and card, ranked visually equal to «Ορισμοί» |
| `EntryCognates` | `WordPage.tsx:412-453` | Folded into `EtymologySpine` |
| Domain chips | `main.py:1188` gate | 0.56 accuracy on 18 fields; 61.0% of shipped rows below the code's own `CONF_FLOOR` |
| Mobile tab strip | `WordPage.tsx:781-808` | A `<div>` of `<button>`s with no `role="tablist"`; tab 1 contains ten cards |
| The three viewport-branched JSX trees + `useMediaQuery` gates | `WordPage.tsx:624-625, 781, 810, 827` | Replaced by one tree with `container-type: inline-size` |
| `/movers` route | `App.tsx:45` | Redirect to a deleted page |

Tables stay in the DB and in any OntoLex export, flagged experimental. Deleting a surface from the
*product* is not deleting data from the *dataset*.

---

## 4. Page specs

### 4.1 Routes

| Route | Status | Purpose |
|---|---|---|
| `/` | rebuilt | Search. Combobox + recovery + paste-a-sentence. |
| `/word/:lemma?f=<surface>` | rebuilt | The entry. `f` carries the surface the user typed. |
| `/word/:lemma/inflection` | new | Full paradigm; own `<title>`, own `<h1>`. Learners bookmark and share these. |
| `/name/:name` | new | Name-index entry. Minimal template. `noindex`. 336,873 lemmas. |
| `/text` | new | Paste a paragraph → interlinear analysis. Deep-linkable by `?t=`. |
| `/gaps` | new | Public unresolved-query list + one-field correction form. |
| `/methodology` | merged | Absorbs `/about`. Carries the eval scorecard and the `DataStatusBanner`. |
| `/licensing` | kept | Legal surface, per data layer. |
| `*` | new | Not-found with a search box. `App.tsx:40-48` currently has no catch-all — an unknown URL renders header + empty `<main>` + footer. |
| `/explore`, `/movers`, `/about` | **deleted** | 301 → `/`, `/`, `/methodology` |

### 4.2 The word page

#### Governing constraint

Three zones, three different contracts. **Zone A always renders and always fits one viewport at
375×812.** Zone B is disclosure-only, every summary carries a count. Zone C is provenance.

Today the page renders nine `Entry*` components in a hand-written array literal
(`WordPage.tsx:689-703`), visually identical — same border, same `bg-white`, same `p-5`, same
`shadow-sm`, same 12px uppercase `slate-400` heading — so «Ορισμοί» and «Απόγονοι σε άλλες γλώσσες»
(0.1% coverage) are peer-ranked, and every empty one returns bare `null` so the page silently
changes shape with no explanation.

#### Wireframe — rich lemma (λόγος, 17 senses), ≥640px

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ← Αναζήτηση                                              Αποθήκευση  ⚑Λάθος; │
├──────────────────────────────────────────────────────────────────────────────┤
│ ZONE A · Η ΑΠΑΝΤΗΣΗ                            always rendered · ≤1 viewport │
│                                                                              │
│  ┌── MatchBanner ────────────────── only when ?f= present and ≠ lemma ────┐  │
│  │  λόγου  →  λόγος                                                       │  │
│  │  γενική ενικού                                                         │  │
│  │  ⚠ Ο τύπος «λόγου» μπορεί να είναι και:  αιτιατική ενικού              │  │
│  │  ● πηγή: Βικιλεξικό (el)          [ Δείτε όλα τα λήμματα με αυτόν τον  │  │
│  │                                      τύπο (2) ]                        │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  λόγος                                              ⟨h1 · --text-3xl        │
│                                                       --font-text⟩          │
│  ουσιαστικό, αρσενικό · γεν. εν. λόγου · ον. πληθ. λόγοι                     │
│  [ˈlo.ɣos]  ▶                                       ⟨--font-ipa⟩            │
│  πολύ συχνή λέξη                                    ⟨no Zipf, no meter⟩     │
│                                                                              │
│  Σημασίες (17)                                      ⟨SenseMenu · senses≥4⟩  │
│   1 ομιλία, λόγια        5 αιτία, λόγος ύπαρξης     9  αναλογία             │
│   2 λογική, νους         6 υπόσχεση                 10 …                    │
│   3 …                    7 …                        …και 7 ακόμη            │
│                                                                              │
│  1. ομιλία, λόγια, αυτό που λέγεται      ⟨--text-lg · --measure-gloss⟩       │
│     ⌜ΛΟΓΟΤ.⌝ ⌜ΛΟΓΙΟ⌝                     ● πηγή: Βικιλεξικό (el)             │
├──────────────────────────────────────────────────────────────────────────────┤
│ ZONE B · ΠΕΡΙΣΣΟΤΕΡΑ            disclosure only · coverage-ranked · counted  │
│                                                                              │
│  ▾ Σημασίες 2–17                                            [16 ακόμη]      │
│  ▸ Παραδείγματα από σώματα κειμένων (5)      ○ υπολογισμένο · Ειδήσεις      │
│  ▸ Κλίση (24 τύποι · 19 από πηγή · 5 παραγόμενοι)   ‥‥ 5 παραγόμενοι        │
│  ▸ Συνώνυμα (8) · Αντώνυμα (2)               ● Βικιλεξικό, OMW              │
│  ▸ Ετυμολογία                                ● Βικιλεξικό (el)              │
│  ▸ Οικογένεια λέξεων (12)                    ● Βικιλεξικό (el)              │
│  ▸ Λέξεις που συνεμφανίζονται (12)           ○ Dunning G² · Leipzig ell_news│
│  ▸ Σχετικές λέξεις χωρίς τύπο σχέσης (61)    ● OMW                          │
│                                              [ Σύμπτυξη όλων ]              │
├──────────────────────────────────────────────────────────────────────────────┤
│ ZONE C · ΤΙ ΔΕΝ ΕΧΟΥΜΕ                                     always rendered   │
│  Προφορά (IPA) — ελέγξαμε: Βικιλεξικό (el), Βικιλεξικό (en).                │
│  Δεν έχουμε ηχογράφηση.                     Πώς φτιάχτηκε αυτή η σελίδα →   │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### Wireframe — stub lemma (the 62.9% single-sense case), ≤640px

```
┌────────────────────────────────────┐
│ ← Αναζήτηση            Αποθήκευση  │
├────────────────────────────────────┤
│  θαλασσοταραχή                     │  ← h1, --text-3xl
│  ουσιαστικό, θηλυκό                │
│  γεν. εν. θαλασσοταραχής           │
│                                    │
│  η ταραχή της θάλασσας, η τρικυμία │  ← --text-lg, full, unabbreviated
│  ● πηγή: Βικιλεξικό (el)           │
├────────────────────────────────────┤
│  ▸ Κλίση (8 τύποι · 6 παραγόμενοι) │
├────────────────────────────────────┤
│  ΤΙ ΕΧΟΥΜΕ ΓΙΑ ΑΥΤΗ ΤΗ ΛΕΞΗ        │  ← the CoverageNote. NOT four boxes.
│  ✓ Ορισμός — Βικιλεξικό (el)       │     One panel, checklist form,
│  ✓ Κλίση — 8 τύποι, οι 6           │     --text-sm, --color-text-secondary,
│    παραγόμενοι από κανόνα          │     no card chrome.
│  — Δεν έχουμε παραδείγματα από     │
│    σώματα κειμένων                 │
│  — Δεν έχουμε προφορά (IPA)        │
│  — Δεν έχουμε συνώνυμα             │
│  Γιατί; → Πηγές και κάλυψη         │
└────────────────────────────────────┘
```

This is the single most important layout decision in the redesign and it costs nothing. It converts
the modal page from *silently broken* to *a complete answer for a rare word*. It is explicitly
**one panel, not four**, rejecting evidence-first's Template B: absence is stated once, compactly,
in the user's service — not performed at them across four authored boxes.

#### 4.2.1 `MatchBanner` — all analyses, never one

`_emit` dedupes on `r["lemma_id"]` (`main.py:256-259`), so of the ≥2 analyses that exist for
**582,145 of 2,275,697 (surface, lemma) pairs — 25.6% measured** (the audit's 30.9% counts pairs
differently; either way it is a quarter of the index) exactly one survives, chosen by the `ORDER BY`
tie-break at `:311`, i.e. **physical row order**. 1,223,148 of 1,805,293 analyses can never be
displayed.

The banner shows the primary analysis in full, then «μπορεί να είναι και:» with up to two more, then
«+N ακόμη αναλύσεις». When the matched form's `kind` is `derived`, it says so:
«Ο τύπος αυτός παράγεται από κανόνα κλίσης — δεν είναι καταγεγραμμένος σε πηγή.»

**We never pick a winner.** The differentiator is that Λεξόραμα *explains* rather than guesses;
picking one of two correct analyses by rowid is guessing, and doing it silently is worse.

#### 4.2.2 Progressive-disclosure rules

1. **Order is computed from populated surfaces**, not the hand-written array at `WordPage.tsx:691-699`.
   Rank = `has_data × surface_weight`, where `surface_weight` is a fixed table (senses 100, examples
   80, inflection 75, synonyms 70, etymology 60, family 45, collocations 40, untyped-related 10).
2. **Every summary carries a count.** «Παραδείγματα (5)», «+16 ακόμη», «24 τύποι · 19 από πηγή ·
   5 παραγόμενοι». Today the page truncates nothing and counts nothing, and `main.py:604` silently
   drops at `LIMIT 60` returning no total.
3. **`?f=` auto-opens the paradigm, highlights the matching cell, and scrolls it into view.** The
   highest-value micro-interaction in the redesign: the learner asked about one cell; show them
   where it sits in the system. `Disclosure` gets a `deepLinked` state for exactly this.
4. **`SenseMenu` at `senses ≥ 4`.** Overview-then-detail, the pattern DWDS (`Bedeutungsübersicht`),
   DDO (`Vis overblik`) and ANW (`Per betekenis`) independently converged on, and which Shneiderman's
   mantra names. Signposts are the sense gloss's first clause, mechanically truncated at 40
   characters on a word boundary — **not** LLM-generated. Content-sense glosses average **48.1
   characters** (measured over the 181,889 content senses), not the 32.4 that includes 208,008
   «επώνυμο» name stubs; at 48 characters first-clause truncation is viable. §7 revisits this.
5. **Global `Σύμπτυξη όλων`.** Today the entire page has exactly one disclosure control.
6. **Zone B regions carry `content-visibility: auto` + `contain-intrinsic-size`.**
7. **SEO consequence, learner-specific:** a learner Googles the *inflected* form, so the paradigm
   must be in the prerendered HTML inside a collapsed disclosure — indexed, not lazily fetched.

#### 4.2.3 Mobile, specified separately

- One tree. No tabs, no viewport-branched JSX. Regions use `@container`, not `useMediaQuery`.
- **Zone A must fit 375×812 including sense 1 in full.** Budget: back-link 32px, `MatchBanner`
  0–120px, headword 56px, grammar line 44px, IPA row 32px, band 24px, `SenseMenu` 0–96px,
  sense 1 ≤ 3 lines at `--text-lg` = 84px. Worst case 488px; `MatchBanner` + `SenseMenu` are the two
  optional blocks and both are absent on the modal page.
- Sticky bottom bar, 56px: `[ Αναζήτηση ]  [ Κλίση ]  [ ⚑ ]`. Not tabs — three actions.
- Tap targets ≥44×44 CSS px (`Chip` min 24×24 per SC 2.5.8 with 24px spacing; interactive rows 44px).
- `SearchCombobox` results cap at **6** on mobile, 10 on desktop.
- Zone B disclosures are full-bleed rows, not cards; card chrome costs ~120px of padding around
  20px of content on the modal page.

#### 4.2.4 `CoverageNote` copy contract

Always states **what was checked**, in Greek, naming the source:

```
Παραδείγματα από σώματα κειμένων — ελέγξαμε: Leipzig ell_news (2011–2024),
  Πρακτικά Βουλής (1989–2020). Η λέξη δεν εμφανίζεται αρκετά συχνά.
Συνώνυμα — ελέγξαμε: Βικιλεξικό (el), Open Multilingual WordNet.
Κλίση — δεν υπάρχει τεκμηριωμένο κλιτικό υπόδειγμα για αυτή τη λέξη.
```

### 4.3 Search / landing

```
┌───────────────────────────────── landing (empty query) ──────────────────────┐
│                              Λεξόραμα                                        │
│         Γράψε τη λέξη όπως τη βρήκες. Θα σου πούμε τι είναι.                  │
│                                                                              │
│   ┌────────────────────────────────────────────────────────────┐             │
│   │ 🔍  Γράψε μια λέξη — σε όποιον τύπο τη βρήκες              │             │
│   └────────────────────────────────────────────────────────────┘             │
│        ανθρώπων · θαλασα · anthropos · sea · «Ο άνθρωπος που είδα»            │
│                                                                              │
│   Πρόσφατα:  λόγος ×  θάλασσα ×          Αποθηκευμένα:  άνθρωπος             │
└──────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────── typing: "ανθρωπ" ───────────────────────────┐
│  🔍 ανθρωπ                                                          ✕        │
│  ┌─ role="listbox" ───────────────────────────────────────────────────────┐  │
│  │ άνθρωπος                                    λήμμα                      │  │
│  │   ουσιαστικό · αρσενικό                                                │  │
│  │   ο άνθρωπος ως βιολογικό είδος                                        │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ ανθρώπων → άνθρωπος                         κλιτός τύπος   πρόθεμα     │  │
│  │   γενική πληθυντικού · ή κλητική ενικού                                │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ ανθρώπινος · ανθρωπιά · ανθρωπισμός …                       πρόθεμα    │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ ▸ Ονόματα και επώνυμα (14)                            ⟨collapsed⟩      │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│  6 αποτελέσματα                                        ⟨aria-live="polite"⟩  │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Paste-a-sentence mode.** If the query contains whitespace or >1 token, the listbox is replaced by
an interlinear strip — the actual learner situation, since the word arrives *inside* a sentence, and
no comparator does it.

```
Ο   άνθρωπος   που   είδα      χθες    ήταν       ψηλός
─   ────────   ───   ────      ────    ────       ─────
ο   άνθρωπος   που   βλέπω     χθες    είμαι      ψηλός
άρθ  ον.εν.    αντ.  αόρ.α'εν. επίρρ.  παρατ.γ'εν. ον.εν.
```

Backend: `POST /api/analyze {text}` → one tokenisation + one
`WHERE normalized_surface IN (…)` batch. It reuses the resolver wholesale — roughly 60 lines.

### 4.4 Methodology (`/methodology`)

Absorbs `/about`. Four sections in this order:

1. **`DataStatusBanner`** — kept and promoted. Driven by `/api/build-status`, it names in Greek
   exactly which documented methods the *currently served* data does not reflect. It is the most
   honest element in the product today (`MethodologyPage.tsx:300-341`) and it disappears
   automatically when `check_divergence` passes.
2. **The eval scorecard** (§5.7) — the search numbers, dated, with the build sha. Next to the
   published Greek baselines: Stanza on UD_Greek-GDT Lemmas **96.05**, CoNLL-2018 el_gdt best
   **97.22**, with the rider that those are *contextual* lemmatisation and a dictionary mapping an
   isolated surface to a candidate set is a different, easier task and cannot borrow them.
3. **Coverage**, recomputed against 109,967 content lemmas, with the name index reported separately.
4. **Limitations**, mandatory. Register scope (both corpora are one formal written register; dialect
   coverage is 0.09% of senses, Pontic zero), missing years, the frequency defect, what was cut and
   why.

### 4.5 `/name/:name`

One `Surface`, ~180px: headword, «ανδρικό επώνυμο», etymology if any, `Provenance`, and a link
«Γιατί δεν είναι λήμμα του λεξικού;». No frequency, no paradigm, no examples, no `SenseMenu`.
`<meta name="robots" content="noindex">`, and `Disallow: /name/` in `robots.txt`.

---

## 5. Search UX spec

This is the wedge. It is uncontested territory, it depends on nothing else in this document, and it
is the only surface every user touches.

### 5.1 What ships today

`main.py:249-395` is **three exact-match passes**: `WHERE si.normalized_surface = ?` (`:308`), the
greeklish `IN (...)` fan-out (`:349`), and the gloss lookup (`:369`). No prefix stage. No fuzzy
stage. 68.2% of as-you-type prefixes and 97.9% of one-character typos return nothing, and the zero
state is one sentence and a dead end.

### 5.2 The cascade — five gated stages

Each stage runs only if the previous returned nothing. Each result is tagged `via` so `ResultRow`
can badge it.

| # | stage | index | measured cost | status |
|---|---|---|---|---|
| 1 | exact on `normalized_surface` | `idx_search_norm` (`schema.sql:73`) | **p_avg 0.006 ms** (200 reps, warm) | exists |
| 2 | **prefix** | new `suggest_index(normalized_surface, weight DESC)` | see below | new |
| 3 | **fuzzy** | new `spell_deletes` (symmetric delete) | ~1 ms | new |
| 4 | greeklish | fixed rule table + scored beam | lookup | fix |
| 5 | en→el gloss | `idx_gloss_en` | exists | fix `_en_key` |

**Prefix routing, measured in-session** (ranked top-10 with the frequency join, on the shipped DB):

| prefix | matches in `search_index` | ranked top-10 via `search_index` | via `lemmas` |
|---|---|---|---|
| `ανθρ*` | 2,525 | 4.8 ms | 0.2 ms |
| `λογ*` | 3,145 | 4.9 ms | 0.3 ms |
| `θαλασ*` | 1,165 | 1.8 ms | 0.1 ms |
| `κα*` | 166,008 | **241 ms** | 6.6 ms |
| `α*` | 467,266 | **492 ms** | 9.9 ms |

So: **≥3 characters, serve from `search_index` — free today, no schema change. 1–2 characters, route
to `suggest_index`.** The 68.2% zero-prefix rate is a missing `WHERE` clause, not an architecture
problem.

`suggest_index` is built by a new `pipelines/ingest/build_suggest_index.py`: all content-lemma
surfaces + high-`weight` forms, with a precomputed `weight` and a covering index on
`(normalized_surface, weight DESC)`. Names are excluded by default and live in a second table.

**FTS5 cannot help directly.** `remove_diacritics 2` is Latin-only: it does not strip tonos and does
not lowercase Greek capitals. Any FTS5 must index the **already-computed** `normalized_surface`, or
use `tokenize=trigram`. This is stated so nobody re-derives it the hard way.

### 5.3 Ambiguity — return the set

Change the dedupe key in `_emit` (`main.py:256-259`) from `lemma_id` to `(lemma_id, features)`, and
aggregate:

```jsonc
{
  "lemma": "άνθρωπος", "lemma_id": 4211, "lemma_class": "dictionary",
  "matched_surface": "ανθρώπων",
  "analyses": [
    {"features": "gen|pl", "label": "γενική πληθυντικού",
     "source": "el-wiktionary", "kind": "attested"},
    {"features": "voc|sg", "label": "κλητική ενικού",
     "source": "paradigm-engine", "kind": "derived"}
  ],
  "analyses_total": 2, "truncated": false,
  "via": "direct", "snippet": "…"
}
```

Add `si.features, si.surface` as **terminal** `ORDER BY` tie-breakers at `:311` so ordering survives
`VACUUM` and re-ingest.

**We do not use corpus counts to adjudicate.** Two analyses of the *same surface string* share one
token count; any split of it is invented. Where both analyses are valid we say so and stop.

### 5.4 Ranking — the 421,002-way tie

`main.py:307,311` ranks by `COALESCE(fr.rank, 1000000000)`. `frequency` holds **25,838 rows** against
**446,840 lemmas**, so **421,002 lemmas (94.2%) tie at the sentinel** and the order collapses to
insertion order. And 1,567,032 of 3,663,525 `search_index` rows (**42.8%**) point at `pos='name'`,
so any prefix or fuzzy pass added without the name split floods the dropdown with surnames.

New `lemma_prior`, computed offline by `pipelines/ingest/build_lemma_prior.py`:

```
prior = 1.6 · zipf_or_backoff
      + 0.8 · log(1 + sense_count)        # free signal, 181,889 content senses, unused today
      + 0.5 · evidence_richness           # examples, collocations, etymons, forms, IPA
      − 3.0 · [lemma_class = 'name']
```

Lew & Wolfer's regression over ~780M English Wiktionary look-ups (30,750 entries, R² = .5228) found
corpus frequency dominant at ΔR² = .272 and polysemy next at ΔR² = .053. Sense count is already in
the DB and is currently unused by ranking.

**The new ORDER BY, with term 1 unchanged:**

```sql
ORDER BY (si.surface = ?) DESC,   -- invariant 2: accent-homograph disambiguation at ranking
         lp.prior DESC,           -- replaces COALESCE(fr.rank, 1000000000)
         si.rank_weight DESC,
         si.features ASC, si.surface ASC, si.lemma_id ASC   -- deterministic across VACUUM
```

Demoting `(si.surface = ?) DESC` below a frequency-dominated prior would break the documented
disambiguation at `main.py:293-303`. It stays first.

Names are **grouped, not interleaved and not merely demoted**: a collapsed
«▸ Ονόματα και επώνυμα (N)» group below the content results.

### 5.5 Zero-result and near-miss recovery

```
Δεν βρήκαμε τη λέξη «θαλασα».

  Μήπως εννοούσες:   θάλασσα   ·   θαλασσί   ·   θαλάσσα

  Λέξεις που αρχίζουν με «θαλασ»
  θαλασσινός · θαλάσσιος · θαλασσοπούλι · θαλασσοταραχή       +12 ακόμη

  Ή γράψε ολόκληρη την πρόταση και θα την αναλύσουμε λέξη-λέξη.

  Αν η λέξη υπάρχει και δεν τη βρήκαμε, δεν είναι στις πηγές μας ακόμη.
  Την καταγράψαμε.                                          Δες τι μας λείπει →
```

Three states, distinguished in copy because they need different next actions:

- **«Μήπως εννοούσες X;»** — fuzzy hit, normalised edit distance ≤1, prior above threshold →
  auto-run it, Google-style: «Αποτελέσματα για **θάλασσα** · Αναζήτηση για *θαλασα*».
- **«Δεν υπάρχει ακόμη στο λεξικό»** — parsed fine, no candidates. Links to coverage.
- **«Δεν καταλάβαμε τι γράψατε»** — did not parse (mixed script, symbols).

The same treatment applies to `_resolve_lemma_ids` (`main.py:196-246`), so a `/word/:lemma` miss
lands on a recovery page instead of `WordPage.tsx:777-779` printing
`500 Internal Server Error for /api/word/…` into an all-Greek UI.

**Typo tolerance** is a symmetric-delete (`spell_deletes`) index over the 1,990,733 distinct
`normalized_surface` values, gated exactly as Elasticsearch's `fuzziness: AUTO`: **0 edits for ≤3
characters, 1 for 4–7, 2 for ≥8**. Greek-specific cheap substitutions get edit cost 0.5: ι/η/υ/ει/οι,
ο/ω, ε/αι, ς/σ, and double-consonant collapse. Fuzzy hits rank strictly below exact and prefix.

### 5.6 The input

Full APG combobox, replacing `SearchPage.tsx:107-121`:

```tsx
<form role="search" onSubmit={goToFirstResult}>
  <label htmlFor="q" className="sr-only">Αναζήτηση λέξης στα ελληνικά ή greeklish</label>
  <input
    id="q" role="combobox" aria-autocomplete="list" aria-expanded={open}
    aria-controls="lx-results" aria-activedescendant={activeId}
    lang="el" inputMode="search" enterKeyHint="search" type="search"
    autoCapitalize="off" autoCorrect="off" spellCheck={false}
    placeholder="Γράψε μια λέξη — σε όποιον τύπο τη βρήκες"
  />
</form>
<ul id="lx-results" role="listbox" aria-label="Αποτελέσματα">…</ul>
<p aria-live="polite">{n} αποτελέσματα</p>
```

ArrowDown/Up/Home/End/Enter/Escape. Repo-wide grep for `onKeyDown` across `apps/web/src` returns
**0** hits today, and there is no `<form>`, so Enter does nothing.

### 5.7 Latency budget

| term | today | target | note |
|---|---|---|---|
| debounce | 250 ms (`useDebounce.ts:3`, `SearchPage.tsx:74`) | **90 ms** | Currently the dominant term, consuming most of Nielsen's 1 s / RAIL's 100 ms budget against a 0.006 ms backend |
| exact SQL | 0.006 ms | ≤1 ms | |
| prefix ≥3 | — | ≤10 ms | measured 1.8–4.9 ms |
| prefix 1–2 | — | ≤15 ms | via `suggest_index` |
| fuzzy | — | ≤20 ms | only when 1–2 return nothing |
| **keystroke → painted list** | ~300 ms | **≤150 ms p95** | |

Plus: `AbortController` supersede in `api/client.ts:35-38`; a `Server-Timing` header per stage; and
**stop writing `query_log` on every keystroke** (`main.py:376-391`) — write only on a settled query.
`query_log` holds **33 rows** today, so nothing is lost, and as-you-type traffic stops taking write
locks on a 1.5 GB WAL database.

### 5.8 Greeklish

`normalize_greek.py:151-186` is a Cartesian fan-out capped at 64, re-ranked by lemma frequency alone.
Verified defects in `_GREEKLISH_SINGLE` (`:89-94`): **no `v` key at all**; `x` maps to ξ only;
`h` appears **twice** in the same dict literal (the second silently wins). And `itertools.product`
at `:182` varies the rightmost unit fastest, so the 64-cap never varies the first vowel of a long
word — `anthropos` is unreachable.

**Ship now** (audit item 1.10, 2 d): add `v→β`, `x→[χ,ξ]`, `b→[μπ,β]`, `d→[δ,ντ]`, `g→[γ,γκ]`,
αυ/ευ arms; guard `nt`/`mp`/`gk` against a following `h`; remove the duplicate key; replace the
truncating product with a **cost-scored beam** that keeps the global top-k.

**Defer, honestly costed:** `AUEB-NLP/ByT5_g2g` (shipped inside `gr-nlp-toolkit`) measures
CER/WER 17.70/39.78 on real human Greeklish against the rule-based-plus-LM `rbslm` at 22.70/55.16.
But it maps **greeklish → Greek**, so it cannot be run *from* lemmas to precompute a table, and
`query_log` has 33 real greeklish inputs. Using it requires first *generating* a synthetic greeklish
corpus by applying an inverse transliteration to content lemmas, then running ByT5 over that — plus
adding `gr-nlp-toolkit` + torch to the build environment. That is a separate, sized project, not a
line item.

### 5.9 en→el

`_en_key` (`main.py:178-183`) lowercases, collapses whitespace and strips edge punctuation.
`build_gloss_index._phrases` (`:57-68`) additionally applies
`_ARTICLE = re.compile(r"^(a|an|the|to)\s+")` at `:54`. **Verified: the keys diverge**, so `to run`,
`the sea` and `a house` never match an index built with the article stripped. Fix: import and reuse
`_phrases`; add a test asserting `_en_key(x) in _phrases(x)` over an article-led table.

### 5.10 The eval harness

`evals/` as a first-class subsystem, not a test fixture.

| slice | n | gold | metric |
|---|---|---|---|
| `known_item.jsonl` | 500 | `(lemma, pos)` | P@1, MRR@10 |
| `ambiguous.jsonl` | 150 | the **set** of correct analyses | set recall, not P@1 |
| `greeklish.jsonl` | 150 | `(lemma, pos)` | P@1, zero-rate |
| `en2el.jsonl` | 100 | ranked `(lemma, pos)` list | MRR@10 |
| **`coverage.jsonl`** | 80 | **authored, not generated** | must-exist rate |

**Three design decisions that differentiate this from every proposal's version:**

1. **Gold is `(lemma, pos)`, never `lemma_id`.** `lemma_id` is re-keyed wholesale by the queued
   R2 re-ingest; `(lemma, pos)` is the identity key R2 installed (`schema.sql:15`). The set survives.
2. **`coverage.jsonl` is authored by hand and is the point.** A known-item set auto-generated *from*
   `forms` cannot emit a query for a lemma that has zero rows, so it is structurally incapable of
   detecting F21/C18. Seed it with the eight headwords the audit proved are gone — **ποτέ, νομός,
   δουλεία, μονός, κάλος, χαλί, στοιχειό, ωρά** — plus ~70 more accent-homograph pairs. It is
   expected to **fail today** and to go green at the re-ingest. That is a regression gate that can
   actually see the largest coverage change in the project's history.
3. **The runner drives the real handler through FastAPI `TestClient`.**
   `tests/test_pipeline_e2e.py:51-57` re-implements the ranking SQL and would pass with production
   ranking deleted.

`evals/run_eval.py` emits `evals/results/<git-sha>.json` with P@1, MRR@10, R@10, set-recall,
zero-rate, p95 latency and per-stage attribution, each with a BCa bootstrap CI.
`tests/test_eval_regression.py` fails the build when a metric drops more than the CI half-width
below the recorded baseline.

**Acceptance thresholds (v1):**

| metric | floor | note |
|---|---|---|
| known-item P@1 | ≥ 0.90 | audit-measured baseline 0.915 |
| known-item MRR@10 | ≥ 0.94 | baseline 0.956 |
| ambiguous set-recall | ≥ 0.95 | 1.0 is achievable by construction once `analyses[]` ships |
| greeklish P@1 | ≥ 0.60 | no baseline exists; set after first run |
| en→el MRR@10 | ≥ 0.50 | no baseline exists |
| prefix zero-rate (≥3 chars) | ≤ 0.05 | 0.682 today |
| 1-char-typo zero-rate | ≤ 0.20 | 0.979 today |
| `coverage.jsonl` must-exist | 100% **after re-ingest** | expected-fail before it |
| p95 keystroke→list | ≤ 150 ms | |

Then **publish it**, in Greek, on `/methodology` and in the search footer:

> **Πόσο καλά βρίσκουμε τη σωστή λέξη**
> Σε 500 κλιτούς τύπους: σωστό λήμμα πρώτο **91,5%**. Σε 150 αμφίσημους τύπους: όλες οι σωστές
> αναλύσεις **—%**. Μετρήθηκε στις 21.07.2026, build `0565f04`.

An audit-produced P@1 of 0.915 is currently the only number that exists for the flagship feature.
Making it published, regression-gated and versioned is the entire difference between a claim and a
product.

---

## 6. The graph decision

**Delete `RelationGraph.tsx`, delete the `cytoscape` and `@types/cytoscape` dependencies, delete
`GET /api/word/{lemma}/graph` (`main.py:574-658`).** Replace with a typed list, and — at ≥8 edges
only — a hand-written inline SVG neighbourhood, no library.

### Measured, in-session

| quantity | value |
|---|---|
| lemmas with ≥1 outgoing relation | 61,673 / 446,840 = **13.8%** |
| lemmas with **zero** edges | 385,167 = **86.2%** |
| median edges among lemmas that have any | **2** |
| lemmas with ≥5 edges | 16,528 = **3.70%** |
| lemmas with ≥10 edges | 6,358 = **1.42%** |
| `related` (untyped) share of all relation rows | 186,495 / 291,208 = **64.0%** |
| content lemmas with a `hypernym` edge | 7,779 = 7.1% |
| Cytoscape chunk | **438,616 B** = 55% of the 799,177 B JS bundle |
| `@font-face` rules in the shipped CSS | **0** |

### The argument

1. **The data is not a graph.** A median-2-edge radius-1 star has no paths and no structure. The
   node-link visualisation literature is consistent that node-link diagrams beat matrices only for
   path-finding tasks; there are no paths here.
2. **64.0% of the edges carry no information.** `AboutPage.tsx:116-121` claims «Κάθε σχέση … είναι
   μια ακμή με συγκεκριμένο τύπο και πηγή — όχι ένας αόριστος "σχετικός όρος"». 62.6% of *rendered*
   edges are exactly `related` (C20). And the source is written to a Cytoscape `data.title` field
   the canvas renderer never draws, with no popper extension installed — so the claimed tooltip
   (C21) does not exist.
3. **The cost is the worst byte-per-user ratio in the codebase.** 438 kB, downloaded on every
   desktop word page, 86.2% of which render one Greek sentence. The same budget buys the entire
   Greek font stack four times over.
4. **Eye-tracking evidence says the visual competes with the definition rather than reinforcing it**
   (Lew et al., *IJL* 31(1), 2018) — directly against a design that places a canvas beside a gloss
   without measuring the trade-off.
5. **The typed list is strictly better on every axis that matters.** It carries resolved links, per-
   item `Provenance`, keyboard navigation, text selection, screen-reader access and search-engine
   indexing — none of which the canvas has. On mobile the current Σχέσεις tab has **zero accessible
   content** (F34).

### What survives

- `SynonymBlock` — synonyms and antonyms, typed, first-class. **21.3% of content lemmas, 53.0% of
  the top-5k band.**
- `WordFamily` — derivational relations, grouped by type.
- Untyped `related` — a plain trailing list under an honest heading, never a peer of a typed edge.
- **`/word/:lemma/graph` as a route, not a canvas** — at `edges ≥ 8` (~3% of lemmas) offer
  «Δες τις σχέσεις σαν διάγραμμα →» rendering a hand-written inline SVG: one ring, ≤12 nodes,
  edges coloured from `--color-rel-*` tokens, `role="img"` + a full `aria-label`, and a `<table>`
  fallback carrying identical content. ~120 LOC, 0 kB of dependency.

---

## 7. LLM layer contract

**Status: Phase 7. It ships after the re-ingest, or it does not ship.** Every judgement panel across
all three proposals named the LLM layer as the worst element for a solo maintainer, and they were
right. It is scoped here to exactly one artefact, with hard gates.

### 7.1 Do this first, in Phase 0, and separately

Delete «Η ΤΝ εξηγεί· οι πηγές ορίζουν» (`AboutPage.tsx:101`), the present-tense claim that
«η τεχνητή νοημοσύνη χρησιμοποιείται για να εξηγήσει και να οργανώσει» (`:103-104`), and the
reversed duplicate at `MethodologyPage.tsx:228`. There is no LLM in the product. Removing the claim
is not contingent on building the feature; building the feature is not a justification for having
made the claim.

### 7.2 Scope — one artefact

**`SenseExplanation`: 2–4 sentences of Greek, on gated lemmas only, saying what the sourced rows
cannot.** Nothing else. Specifically **not** shipped:

- ❌ **Sense signposts.** They are `senses.gloss` first-clause truncation at 40 characters. Content
  glosses average **48.1 characters** (measured, 181,889 content senses) — the 32.4 figure that
  motivated an LLM includes 208,008 «επώνυμο» name stubs that the layer hard-refuses anyway. At 48
  characters, mechanical truncation works.
- ❌ **Example-to-sense assignment.** A model emitting `{sense_id, example_row_id}` is making a
  *lexicographic judgment* — which sense a corpus sentence illustrates — verified by a join that
  confirms only that both IDs exist. The result would render a verbatim Leipzig sentence, positioned
  by a model, under an `attested` provenance dot. That is model output masquerading as sourced data,
  in the product that sells «οι πηγές ορίζουν». Forbidden by construction: **sense-example placement
  is never `attested`.**

### 7.3 Architecture

**Build-time only. No LLM ever runs on the request path.** Two tables, registered through
`pipelines/ingest/manifest.py` exactly as every other component is, so `check_divergence` can detect
a DB whose explanations the current prompt could not have produced.

```sql
CREATE TABLE explanations (
  id           INTEGER PRIMARY KEY,
  lemma_id     INTEGER NOT NULL REFERENCES lemmas(id),
  status       TEXT NOT NULL,           -- 'ok' | 'abstained'
  abstain_reason TEXT,                  -- machine-readable
  model        TEXT NOT NULL,
  prompt_hash  TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  source       TEXT NOT NULL DEFAULT 'llm-generated'
);
CREATE TABLE explanation_claims (
  explanation_id INTEGER NOT NULL REFERENCES explanations(id),
  seq            INTEGER NOT NULL,
  claim_type     TEXT NOT NULL,         -- morphology|sense|etymology_hop|usage|contrast
  claim_json     TEXT NOT NULL,
  cite_table     TEXT NOT NULL,         -- senses|forms|etymons|relations|corpus_examples
  cite_row_id    INTEGER NOT NULL,
  verified_by    TEXT,                  -- 'paradigm_engine' | 'sql_join' | NULL
  verdict        TEXT                   -- 'confirms' | 'contradicts' | 'out_of_scope'
);
```

### 7.4 Retrieval

**No vector RAG.** "Retrieval" is a primary-key join over `senses`/`forms`/`etymons`/`relations`,
so recall is 1.0 and precision is 1.0 by construction. The engineering risk is entirely **context
construction**: `main.py:397-573` currently pulls up to 17 senses, 98 relations, 12 collocations and
8 neighbours; feeding that raw is exactly the distractor regime that measurably costs 25–67%
accuracy. The context is capped and ordered: senses (all, ≤8), forms (principal parts only), etymons
(the chain), synonyms (≤6). Nothing else.

### 7.5 Prompt and output contract

The model **never emits user-facing Greek.** Through a `strict: true` tool schema
(`additionalProperties: false`, all fields `required`) it emits an array of typed claims, where
`cite_row_id` is drawn from a **closed enum of the row IDs assembled for that lemma**. Greek prose
is then rendered deterministically from templates, extending the existing `apps/web/src/lib/labels.ts`
(431 lines, already handles gender/case/usage vocabulary with raw-value fallback).

Where a formal grammar over the output space exists, malformed output becomes *impossible* rather
than merely rare — that is the entire warrant for this design over generate-then-attribute, whose
published ceiling (best-system AIS ≈ 65% on NQ; citation support missing ~50% of the time on ELI5)
is far below a dictionary's bar.

### 7.6 Refusal — abstention is a first-class, visible state

Computed **before** generation, deterministically:

- **Hard refuse** `lemma_class = 'name'` — 336,873 lemmas (75.4%).
- **Hard refuse** any lemma whose only glosses are «ανδρικό/γυναικείο επώνυμο/όνομα» — 208,008 senses.
- **Require** ≥2 distinct senses **OR** a parsed etymon chain **OR** ≥1 corpus example.
- Store the refusal as `status='abstained'` with a machine-readable reason.

Abstention renders as authored Greek copy — «Δεν έχουμε αρκετές πηγές για μια εξήγηση αυτής της
λέξης» — never as a bare `null`. Larger models are documented to be good when context is sufficient
and **bad at abstaining when it is not**, and adding context *raises* confidence and hence
hallucination rate; so abstention is a SQL predicate, not a model decision.

### 7.7 Deterministic verification against the paradigm engine

Add `verify(lemma, pos, gender, form, features) -> 'confirms'|'contradicts'|'out_of_scope'` to
`pipelines/ingest/paradigm_engine.py`, reusing `generate()` (`:320`) and the `_cell_key` logic in
`validate_paradigms.py:39`. Today `generate()` is write-time only.

- `contradicts` → the whole explanation is dropped.
- `out_of_scope` → the claim is demoted to a bare citation of a `forms` row.
- `confirms` → stored with `verified_by='paradigm_engine'`.

**This is gated on Tier 1 items 1.3, 1.12 and 1.13 landing.** Until verb voice is inferred and the
accent-unstable cells are dropped, the engine's own output includes non-words (`άνθρωπους`,
`καταστρώματε`, 171 double-accented forms), so a verifier built on it would confirm them.

### 7.8 Visual marking

`--color-generated` (violet, hue 300) and **only** LLM output. Rule-derived paradigm cells get
`--color-derived` (amber, hue 72) and the string «παραγόμενο από κανόνα». Collapsing these two into
one token — as every source proposal did — teaches a user that violet means "a model wrote this",
then paints 170,749 deterministic finite-state outputs violet, destroying trust in the most reliable
surface on the page while simultaneously laundering model prose into the same epistemic class as
arithmetic.

### 7.9 Eval harness and acceptance thresholds

`tests/test_explanations.py`, four **hard** invariants, all pure SQL, all 100% or the build fails:

1. Every `cite_row_id` resolves **and belongs to the claimed `lemma_id`**.
2. Every `claim_type='morphology'` row carries `verified_by='paradigm_engine'` and
   `verdict='confirms'`.
3. Zero claims cite a `source` value absent from the `sources` registry.
4. Zero rows with `status='ok'` on a lemma the refusal gate rejects.

Then the part that is actually hard, and is why this is Phase 7:

| gate | threshold | method |
|---|---|---|
| AIS-style support rate | ≥ 0.95 | held-out sample, atomic-claim decomposition, single annotator |
| morphology verdict | 100% `confirms` | `paradigm_engine.verify()`, automated |
| abstention correctness | ≥ 0.98 | SQL predicate, automated |
| **human spot-check** | **200 items, one annotator, agreement with a second pass ≥ 0.8** | The gold set is **200 items, not 300, and single-annotator with a re-annotation reliability pass** — a solo maintainer cannot run a two-annotator protocol, and specifying one is how a plan silently becomes unshippable. |

**If the AIS gate cannot be met, the layer does not ship and the slogan stays deleted.** That is the
acceptance criterion.

---

## 8. Backend / API changes

### 8.1 Endpoints

| endpoint | change |
|---|---|
| `GET /api/search` | Five-stage cascade; `analyses[]` per result; `lemma_class`; `via` per stage; `kind` per matched surface; names in a separate `name_results[]` array; `Server-Timing` |
| `GET /api/word/{lemma}` | Add `?f=` echo + resolved analyses; add `coverage{}` (what was checked and not found, per surface, with the source checked); add `counts{}` for every truncated list; per-item `source` **and** `kind`; drop `descendants`, `neighbors`; cap the fan-out (F36: one GET currently returns 1,377 entries ≈ 46 MB) |
| `GET /api/word/{lemma}/graph` | **deleted** |
| `GET /api/word/{lemma}/diachronic` | **deleted** |
| `GET /api/insights/drift` | **deleted** |
| `GET /api/explore/*` (5 endpoints) | **deleted** |
| `POST /api/analyze` | **new** — sentence → per-token resolution, batched |
| `GET /api/suggest` | **new** — prefix-only, `suggest_index`-backed, ≤15 ms |
| `GET /api/gaps` | **new** — public unresolved-query list from `query_log` |
| `POST /api/report` | **new** — typed error reports |
| `GET /api/build-status`, `/api/health` | kept and extended: per-surface generation status, `sources` registry coverage |

Deleting 8 of the 14 routes removes roughly 763 of 1,651 LOC from `main.py` (46%).

### 8.2 Schema

```sql
-- The sources registry. FK target for the `source` column on all 16 sourced tables.
-- Turns invariant 3 from a convention a future ingest can quietly violate into a
-- constraint testable in CI. ~2 days, NO re-ingest — every table already carries
-- `source TEXT NOT NULL` with 0 NULL/blank values across 541,759 senses,
-- 3,216,685 forms, 291,208 relations, 294,045 collocations.
CREATE TABLE sources (
  id          TEXT PRIMARY KEY,          -- 'el-wiktionary', 'leipzig-ell_news', 'generated', …
  kind        TEXT NOT NULL              -- attested | computed | derived | generated
              CHECK (kind IN ('attested','computed','derived','generated')),
  label_el    TEXT NOT NULL,             -- «Βικιλεξικό (ελληνικά)»
  license     TEXT NOT NULL,             -- 'CC BY-SA 4.0', 'CC BY-NC 4.0', …
  license_url TEXT NOT NULL,
  url         TEXT,
  redistributable INTEGER NOT NULL       -- 0 for the NC corpora; gates the public snapshot
);

-- F26/C19: `search_index` has NO source column, so 170,749 rule-generated forms
-- are served by /api/search indistinguishably from Wiktionary-attested ones.
-- `build_search_index.py` is 58 LOC of pure SQL over lemmas+forms — re-derivable
-- in hours with no jsonl touch.
ALTER TABLE search_index ADD COLUMN source TEXT REFERENCES sources(id);
ALTER TABLE search_index ADD COLUMN kind   TEXT;            -- denormalised for the hot path
CREATE UNIQUE INDEX idx_search_uniq ON search_index (lemma_id, surface, normalized_surface, features);

-- The name split, materialised at the data layer, not re-derived per query.
-- The rule already exists in `_keep_mover` (main.py:749) but only for discovery lists.
ALTER TABLE lemmas ADD COLUMN lemma_class TEXT;             -- 'dictionary' | 'name'

-- Ranking prior. Replaces COALESCE(fr.rank, 1000000000), which ties 421,002 lemmas.
CREATE TABLE lemma_prior (lemma_id INTEGER PRIMARY KEY REFERENCES lemmas(id),
                          prior REAL NOT NULL, components TEXT NOT NULL);

-- Prefix suggestions for 1–2 char queries (α* costs 492 ms on search_index, 9.9 ms here).
CREATE TABLE suggest_index (normalized_surface TEXT NOT NULL, surface TEXT NOT NULL,
                            lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
                            weight REAL NOT NULL, lemma_class TEXT NOT NULL);
CREATE INDEX idx_suggest ON suggest_index (normalized_surface, weight DESC);

-- Symmetric-delete typo index over the 1,990,733 distinct normalized surfaces.
CREATE TABLE spell_deletes (variant TEXT NOT NULL, normalized_surface TEXT NOT NULL, dist INTEGER NOT NULL);
CREATE INDEX idx_spell ON spell_deletes (variant);

-- Typed error reports from `ReportError`.
CREATE TABLE error_reports (id INTEGER PRIMARY KEY, lemma_id INTEGER, surface_kind TEXT,
                            row_ref TEXT, reason TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL);
```

### 8.3 New pipeline scripts

`build_lemma_prior.py`, `build_suggest_index.py`, `build_spell_index.py`, `build_sources.py`,
`classify_lemma_class.py`. All five are **pure derivations from existing tables** — each is a single
script run, so the queued re-ingest invalidates nothing that cannot be rebuilt in one command. That
is deliberate: it is why the search phase can ship *before* the re-ingest.

### 8.4 Input validation and caching

Every parameter gets `Query(..., ge=, le=)` — there is currently **1** `Query()` constraint in 1,651
lines, and user-supplied floats become permanent `explore_cache` rows costing 20–35 s each (F55).
Front-end: a TanStack Query cache replacing 13 raw `fetch`-in-`useEffect` sites; back-navigation
currently refetches three endpoints.

---

## 9. Accessibility and performance budgets

### 9.1 WCAG 2.2 AA — concrete criteria, each with its current failure

| SC | Requirement | Current state | Mechanism |
|---|---|---|---|
| **1.4.3** Contrast (Minimum) | ≥4.5:1 body, ≥3:1 large | `text-slate-400 dark:text-slate-500` = **2.56:1**, 130 uses, all 7 section headings | `scripts/check_contrast.py` fails the build |
| **1.4.11** Non-text Contrast | ≥3:1 for UI boundaries | Cards are **1.03:1** on the page with no compliant border | `--color-border-strong` = 3.04:1 light / 3.16:1 dark |
| **1.3.1** Info and Relationships | Semantic structure | Headword is `<h2>` (`WordPage.tsx:154`); fake tabs are a `<div>` of `<button>`s | `<h1>` per page; real `role="tablist"` or deletion |
| **2.1.1** Keyboard | All functionality | **0** `onKeyDown` handlers app-wide; results are `<Link>`s in a `<div>`; Enter does nothing | APG combobox, §5.6 |
| **2.4.7** Focus Visible | Visible focus indicator | **0** `focus-visible` rules; 1 authored focus style | Global `:focus-visible` in the base layer |
| **2.4.11** Focus Not Obscured | Focused element not hidden | Sticky header + sticky bottom bar | `scroll-margin-block` on all focusables |
| **2.5.8** Target Size (Minimum) | ≥24×24 CSS px or spacing | 18 ad-hoc pills compute to 20–22px; `<circle r={2.5}>` datapoints | `Chip` min 24×24; charts deleted with `/explore` |
| **3.2.3/3.2.4** Consistent Navigation/Identification | — | Three viewport-branched JSX trees present three different navigations | One tree, container queries |
| **4.1.2** Name, Role, Value | — | No `role`, no `aria-expanded`, no `aria-activedescendant` on the combobox | §5.6 |
| **4.1.3** Status Messages | Programmatic status | Six unstyled `<p>Φόρτωση…</p>`; no live region | `LiveRegion`, `role="status"` |
| **1.1.1** Non-text Content | Text alternative | Cytoscape canvas has none; mobile Σχέσεις tab has **zero** accessible content | Canvas deleted; SVG gets `role="img"` + `aria-label` + `<table>` fallback |
| *(also required)* | `<title>` per route, `lang="el"`, skip link, route-change focus | **0** `document.title`, no `<meta name="description">`, no skip link, no `path="*"` | All added in Phase 4 |

**Banned by lint:** `title=` (26 sites — invisible on touch and to keyboards, and they carry the
frequency source, similarity scores, CIs and the "algorithmically generated form" warning, i.e. the
entire honesty layer), `text-transform: uppercase` on Greek (27 sites), raw hex colours in `.tsx`,
raw `<a href>` to an internal route (`ExplorePage.tsx:441` full-reloads the SPA).

### 9.2 Core Web Vitals and bundle budgets

| metric | target | today | mechanism |
|---|---|---|---|
| **LCP** | ≤ 2.0 s p75 | untested | Zone A is HTML-first; fonts `font-display: swap` + `preload` on the two core subsets |
| **INP** | ≤ 200 ms p75 | untested; 250 ms debounce dominates | debounce 90 ms, `useDeferredValue` on the result render, `AbortController` |
| **CLS** | ≤ 0.1 p75 | risk from `font-display: swap` and from `null`-returning cards | `size-adjust` on fallbacks; `contain-intrinsic-size` on Zone B; `CoverageNote` always occupies space |
| **JS, initial route** | **≤ 180 kB** gzip-equivalent | 799,177 B raw (360,561 index + 438,616 Cytoscape) | Cytoscape deleted; `/explore` deleted |
| **Fonts** | ≤ 120 kB, 4 subsets | **0 bytes, 0 `@font-face` rules** | §2.2 |
| **CSS** | ≤ 40 kB | 37,590 B | token layer replaces 321 ad-hoc class tokens |
| **API p95, `/api/search`** | ≤ 30 ms | 0.006 ms exact / no prefix stage exists | §5.7 |
| **`/api/word` response** | ≤ 250 kB | up to **46 MB** (F36) | fan-out cap + LIMIT |

Enforced by a `bundlesize` check and a Lighthouse CI run in the same GitHub Actions workflow that
runs `pytest` and `npm run typecheck` — of which there is currently **none** (no `.github/`, no
`Makefile`, no `pyproject.toml`, across 86 tracked files).

---

## 10. Sequenced implementation plan

Effort is ideal focused days for one maintainer who knows this codebase — the same unit
`docs/AUDIT.md:§5` uses, so the two plans are addable. Audit remediation R1–R3 are **done**;
Tier 0 is mostly outstanding; ingest criticals F1/F2/F3/F4 plus the R2-followup re-ingest are queued.

Every phase is independently shippable and leaves the product better than it found it.

---

### Phase 0 — Stop shipping falsehoods · **4 d** · no data dependency

Audit Tier 0, minus items the redesign deletes anyway.

- Delete the LLM slogan and the present-tense AI claim (`AboutPage.tsx:101,103-104`,
  `MethodologyPage.tsx:228`) — audit 0.6.
- Suppress `change_point_year` when `change_point_score IS NULL` (`main.py:957`) — 0.1. *(Moot after
  Phase 1, but Phase 1 may slip and this is 0.5 d.)*
- Cap `_resolve_lemma_ids` + LIMIT — 0.7. The 46 MB amplification is a live availability bug.
- `Query(..., ge=, le=)` on every parameter; quantize cache-key floats; cap `explore_cache` — 0.8.
- Root `LICENSE` + `DATA-LICENSE`; WordNet 3.0 notice; Apache-2.0 NOTICE — 0.9.
- **Verify the Leipzig and Parliament licences** — 0.10. Both are CC BY-**NC**; the site claims
  CC BY-SA 4.0 over the derived DB. This gates every "open data" claim and every published snapshot.

**Ships:** a product that no longer asserts things its data contradicts.

---

### Phase 1 — The deletion PR · **5 d** · no data dependency, order-independent

Ships **alone**, before anything is added. This is the only component of any redesign with zero data
dependencies and zero re-ingest cost.

Delete `ExplorePage.tsx` (541), `DiachronicPanel.tsx` (375), `RelationGraph.tsx` (242),
`EntryDescendants`, `EntryNeighbors`, `EntryCognates`, the duplicate `EtymologyTimeline` render, the
mobile tab strip, the three viewport-branched JSX trees, the `/movers` redirect, and the domain
chips. Drop `cytoscape` + `@types/cytoscape`. Delete 8 route handlers (~763 LOC of `main.py`). Add
`path="*"` and an error boundary.

**Ships:** −1,158 LOC front-end, −763 LOC back-end, **−438,616 B JS**. Discharges audit CUT items
1, 2, 3, 4, 5, 7 and Tier 0.4/0.5 without writing the code those tickets ask for. Every subsequent
phase gets cheaper.

---

### Phase 2 — Names, sources, provenance · **8 d** · derivations only, no re-ingest

- `classify_lemma_class.py` → `lemmas.lemma_class`. Rule: `pos='name'` OR gloss ∈ the four
  «επώνυμο/όνομα» strings. Promote `_keep_mover`'s existing logic (`main.py:749`) to the data layer.
- `build_sources.py` → the `sources` registry, `kind ∈ {attested, computed, derived, generated}`,
  with `license` and `redistributable`. Make `record_attribution` **fail closed** (audit 1.6 —
  4 corpora / 2,531,144 rows currently carry no licence at all).
- `search_index.source` + `.kind`, re-derived by `build_search_index.py` (58 LOC, no jsonl touch) —
  audit 1.8.
- `/name/:name` route + template; names excluded from default `/api/search`, returned in
  `name_results[]`; `robots.txt` `Disallow: /name/`.
- **Recompute every public coverage number against 109,967 content lemmas** and publish the name
  index size separately. Report lexicon size as 109,967, not 446,840 — audit 2.16.
- CI test: every `source` value in every sourced table resolves to a `sources` row.

**Ships:** the highest user-value change in the plan. A Greek speaker stops getting surnames.

---

### Phase 3 — The search cascade and the eval harness · **13 d**

This is the wedge and it goes **before any pixel work**.

- `build_lemma_prior.py`, `build_suggest_index.py`, `build_spell_index.py`.
- Restructure `main.py:249-395` into the five gated stages; `analyses[]`; the new `ORDER BY` with
  `(si.surface = ?)` still first; `GET /api/suggest`.
- Fix `_en_key` (audit 1.11) and the greeklish table + beam (audit 1.10).
- `SearchCombobox` (APG), `ResultRow` with `analyses[]`, `NameGroup`, `RecoveryPanel`; debounce
  250 → 90 ms; `AbortController`; `query_log` on settled queries only.
- `evals/` with all five slices, `(lemma, pos)` gold, the authored `coverage.jsonl`,
  `run_eval.py` through `TestClient`, and `tests/test_eval_regression.py`.
- **Add CI** — GitHub Actions running `pytest -q`, `npm run typecheck`, `check_contrast.py`,
  `check_font_coverage.py`, `manifest.py --db` (which already exits non-zero) — audit 1.5.

**Ships:** the flagship feature works, is measured, and the number is public. Ship nothing after this
and the product is still a usable dictionary. `coverage.jsonl` ships **failing**, by design.

---

### Phase 4 — Design system, fonts, accessibility · **10 d** · blocked by nothing

- The `@theme` token file (§2.2); `light-dark()` collapses 315 `dark:` variants.
- `pyftsubset` the four subsets; `scripts/check_font_coverage.py`; preload the two core faces.
- Delete `text-transform: uppercase` from all 27 sites.
- `src/components/ui/` primitives; delete the 12× card literal and the 3 duplicate `SectionHeading`s.
- Global `:focus-visible`; `document.title` per route; `<meta name="description">`; skip link;
  route-change focus; `prefers-reduced-motion`; `<h1>` promotion.
- Container queries replace `useMediaQuery`; `--width-content` replaces `max-w-5xl`.
- Promote all 26 `title=` tooltips into `Popover`/visible text; ban `title=` by lint.
- `check_contrast.py` in CI.

**Ships:** the app stops failing AA and stops rendering orthographically wrong Greek on iOS. This is
also the only phase no re-ingest can invalidate.

---

### Phase 5 — The word page · **10 d**

Zones A/B/C; `MatchBanner`; `HeadwordBlock` absorbing `QuickFacts` on every viewport; `SenseMenu`;
mechanical signpost truncation; `?f=` paradigm auto-open and cell highlight; `CoverageNote`
replacing 22 `return null` sites; `Provenance` per item; `SynonymBlock`; `WordFamily` with `related`
demoted; coverage-ranked disclosure order with counts; `Σύμπτυξη όλων`; `content-visibility`;
`ReportError`.

**Ships:** the entry a user actually reads. Deliberately **after** search, because a beautiful word
page the user cannot reach is worth nothing.

---

### Phase 6 — Re-ingest gate · **audit Tier 1, ~25 d + compute** · maintainer's call

Not this spec's work, but the sequencing depends on it. F1 (form-validity gate), F2 (frequency
dedupe + Zipf), F3 (verb voice), F4 (bare endings), 1.12/1.13 (paradigm refusals), then the
R2-followup full re-ingest under `schema_version 2`.

**What Phases 2–5 did to survive it:**

| artefact | survives? | why |
|---|---|---|
| `evals/*.jsonl` | ✅ | gold is `(lemma, pos)`, never `lemma_id` |
| `coverage.jsonl` | ✅ **and turns green** | it is the gate that proves the re-ingest worked |
| `lemma_prior`, `suggest_index`, `spell_deletes` | ✅ rebuilt | one script run each, by construction |
| `sources` registry | ✅ | keyed on source id, not row id |
| `lemma_class` | ✅ rebuilt | one script run |
| design system, fonts, a11y | ✅ | touch no table |
| word page | ✅ | reads the API, not the schema |

**After the re-ingest, immediately:** re-run `run_eval.py`, publish the new numbers, and restore the
frequency meter and Zipf display (deleted in Phase 5) only if `Σ 10^(zipf−9) ≤ 1.05` passes.

---

### Phase 7 — The LLM layer · **20 d+, gated** · after Phase 6 only

Only if Phases 1–6 have shipped and the `paradigm_engine.verify()` preconditions (Tier 1 items 1.3,
1.12, 1.13) have landed. §7 in full, including the 200-item single-annotator gold set with a
re-annotation reliability pass. **If the AIS gate is not met, it does not ship, and the slogan stays
deleted.**

---

### Totals and the honest caveat

| phase | days | cumulative |
|---|---|---|
| 0 · Truth | 4 | 4 |
| 1 · Deletion | 5 | 9 |
| 2 · Names + sources | 8 | 17 |
| 3 · Search + evals | 13 | 30 |
| 4 · Design system | 10 | 40 |
| 5 · Word page | 10 | 50 |
| *(6 · Re-ingest — audit Tier 1)* | *~25 + compute* | *~75* |
| 7 · LLM (gated) | 20+ | ~95+ |

**50 ideal days to a complete, honest, measured product without the LLM layer.** For one maintainer
at realistic throughput that is roughly two to three calendar quarters alongside the audit's own
Tier 0/1 work — and Phases 0–3 (30 days) deliver the great majority of the user value. Phase 7 is
last for a reason: an equivalent sprint spent on it buys a 2–4 sentence card, while the prefix stage
in Phase 3 unblocks 68.2% of as-you-type queries.

---

## 11. References

Grouped by the section that uses them. URLs marked ✓ were carried from `docs/AUDIT.md`'s verified
reference table; the remainder are standard specification and platform documentation.

### Design systems, tokens, modern CSS

- Design Tokens Community Group. *Design Tokens Format Module*, first stable spec 2025.10 — https://tr.designtokens.org/format/
- Material Design 3. *Design Tokens* (reference / system / component tiering) — https://m3.material.io/foundations/design-tokens/overview
- Radix. *Understanding the Scale* — the 12-step semantic ramp with contrast designed in — https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale
- Tailwind CSS v4. *Theme variables* (`@theme`) — https://tailwindcss.com/docs/theme
- MDN. `light-dark()` — Baseline newly-available May 2024 — https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/light-dark
- MDN. *CSS container queries* — https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_containment/Container_queries
- MDN. `oklch()` — https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/oklch
- web.dev. *content-visibility: the new CSS property that boosts your rendering performance* — https://web.dev/articles/content-visibility
- CSS WG Issue #3658 — `system-ui` is "intended to make UI elements look like native apps, and not for typesetting large paragraphs of text" — https://github.com/w3c/csswg-drafts/issues/3658
- Utopia. *Fluid type scale calculator* — https://utopia.fyi/type/calculator/

### Typography and Greek orthography

- W3C. *CSS Text Module Level 3* §`text-transform` — the language-tailoring requirement for Greek all-caps accent removal — https://www.w3.org/TR/css-text-3/#text-transform
- fontTools. `pyftsubset` — https://fonttools.readthedocs.io/en/latest/subset/
- SIL. *Gentium* (OFL; full Greek + polytonic + IPA) — https://software.sil.org/gentium/
- Google Fonts. *Noto Sans* (OFL) — https://fonts.google.com/noto/specimen/Noto+Sans

### Accessibility and performance

- W3C. *Web Content Accessibility Guidelines 2.2* — https://www.w3.org/TR/WCAG22/
- W3C WAI. *Understanding SC 2.5.8: Target Size (Minimum)* — https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
- W3C WAI-ARIA APG. *Combobox pattern* — https://www.w3.org/WAI/ARIA/apg/patterns/combobox/
- web.dev. *Web Vitals* (LCP / INP / CLS thresholds) — https://web.dev/articles/vitals
- web.dev. *Interaction to Next Paint (INP)* — https://web.dev/articles/inp
- web.dev. *Measure performance with the RAIL model* (100 ms response, 50 ms processing budget) — https://web.dev/articles/rail
- Nielsen. *Response Times: The 3 Important Limits* (0.1 s / 1 s / 10 s) — https://www.nngroup.com/articles/response-times-3-important-limits/

### Information architecture and lexicographic design

- Shneiderman (1996). *The Eyes Have It: A Task by Data Type Taxonomy for Information Visualizations.* IEEE VL — overview first, zoom and filter, details on demand — https://www.cs.umd.edu/~ben/papers/Shneiderman1996eyes.pdf
- Tarp (2008). *Lexicography in the Borderland between Knowledge and Non-Knowledge.* Niemeyer — function theory; a dictionary must declare its functions ✓ — https://academic.oup.com/ijl/article-abstract/22/4/480/1746820
- Tarp & Gouws (2023). *A Necessary Redefinition of Lexicography in the Digital Age.* Lexikos 33(1):425–447 ✓ — https://lexikos.journals.ac.za/pub/article/view/1826
- Lew & de Schryver (2014). *Dictionary Users in the Digital Revolution.* IJL 27(4):341–359 ✓ — https://academic.oup.com/ijl/article-abstract/27/4/341/932743
- Lew (2015). *Observing Online Dictionary Users: Studies Using Wiktionary Log Files.* IJL 28(1) — the log-file paradigm; `query_log` is exactly this substrate ✓ — https://academic.oup.com/ijl/article/28/1/1/1816539
- Lew, Kaźmierczak, Tomczak & Leszkowicz (2018). *Competition of Definition and Pictorial Illustration for Dictionary Users' Attention.* IJL 31(1):53–77 — eye-tracking evidence that added visual material competes with the definition; the direct argument against a canvas beside a gloss ✓ — https://academic.oup.com/ijl/article-abstract/31/1/53/3052177
- Lew & Wolfer (2024). *What Lexical Factors Drive Look-Ups in the English Wiktionary?* SAGE Open 14(1) — ~780M look-ups, 30,750 entries, R²=.5228, frequency ΔR²=.272, polysemy ΔR²=.053 ✓ — https://journals.sagepub.com/doi/10.1177/21582440231219101
- Kilgarriff (1997). *I don't believe in word senses.* Computers and the Humanities 31(2):91–113 ✓ — https://www.kilgarriff.co.uk/Publications/1997-K-CHum-believe.pdf
- Kilgarriff, Husák, McAdam, Rundell & Rychlý (2008). *GDEX: Automatically Finding Good Dictionary Examples in a Corpus.* EURALEX ✓ — https://euralex.org/publications/gdex-automatically-finding-good-dictionary-examples-in-a-corpus/
- Kilgarriff, Rychlý, Smrž & Tugwell (2004). *The Sketch Engine.* EURALEX ✓ — https://www.sketchengine.eu/wp-content/uploads/The_Sketch_Engine_2004.pdf
- Cimiano, McCrae & Buitelaar (2016). *OntoLex-Lemon.* W3C Ontology-Lexica CG Final Report ✓ — https://www.w3.org/2016/05/ontolex/
- Bosque-Gil & Gracia (2019). *The OntoLex Lemon Lexicography Module (lexicog).* W3C CG Final Report ✓ — https://www.w3.org/2019/09/lexicog/
- Lebo, Sahoo & McGuinness (2013). *PROV-O: The PROV Ontology.* W3C Recommendation — a source string is not provenance; provenance names the process ✓ — https://www.w3.org/TR/prov-o/
- Krek et al. (2018). *European Lexicographic Infrastructure (ELEXIS).* EURALEX ✓ — https://euralex.org/publications/european-lexicographic-infrastructure-elexis/

### Search, IR and evaluation

- SQLite. *FTS5* — `remove_diacritics 2` is Latin-only; `tokenize=trigram`; `prefix=` indexes — https://www.sqlite.org/fts5.html
- SQLite. *spellfix1* — `editdist3`, `spellfix1_scriptcode` (Greek = 200) — https://www.sqlite.org/spellfix1.html
- Garbe. *SymSpell* — the symmetric-delete algorithm — https://github.com/wolfgarbe/SymSpell
- Elasticsearch. *Fuzziness `AUTO`* — 0 edits ≤3 chars, 1 for 4–7, 2 for ≥8 — https://www.elastic.co/guide/en/elasticsearch/reference/current/common-options.html#fuzziness
- Voorhees (2000). *Variations in relevance judgments and the measurement of retrieval effectiveness.* IPM 36(5) — assessor-pair overlap 0.301–0.494, yet system rankings are highly stable across judgment sets — https://www.sciencedirect.com/science/article/abs/pii/S030645739000067X
- Efron & Tibshirani (1993). *An Introduction to the Bootstrap.* Chapman & Hall — BCa intervals ✓ — https://www.routledge.com/An-Introduction-to-the-Bootstrap/Efron-Tibshirani/p/book/9780412042317

### Greek NLP

- Koutsikakis, Chalkidis, Malakasiotis & Androutsopoulos (2020). *GREEK-BERT: The Greeks visiting Sesame Street.* SETN ✓ — https://arxiv.org/abs/2008.12014
- Loukas et al. (2025). *GR-NLP-TOOLKIT.* COLING System Demonstrations — POS, morphology, parsing, NER, Greeklish→Greek (`ByT5_g2g`); **lemmatisation deliberately not supported** ✓ — https://aclanthology.org/2025.coling-demos.17/
- Prokopidis & Papageorgiou (2017). *Universal Dependencies for Greek.* UDW@NoDaLiDa — UD_Greek-GDT, CC BY-NC-SA 3.0 (the NC clause is a live licensing-wall issue if Lexorama ever trains on it) ✓ — https://aclanthology.org/W17-0413/
- Prokopidis & Papageorgiou (2020). *A Neural NLP toolkit for Greek.* SETN ✓ — https://nlp.ilsp.gr/setn-2020/3411408.3411430.pdf
- CoNLL 2018 Shared Task, lemmatisation results (el_gdt best 97.22) ✓ — https://universaldependencies.org/conll18/results-lemmas.html
- Toumazatos, Pavlopoulos et al. (2024). *Still All Greeklish to Me: Greeklish to Greek Transliteration.* LREC-COLING — `rbslm` CER/WER 22.70/55.16, ByT5 17.70/39.78, GPT-4 6-shot 9.44/22.74 — https://aclanthology.org/2024.lrec-main.1330/ *(URL to confirm at implementation time; the model is `AUEB-NLP/ByT5_g2g`, shipped in `gr-nlp-toolkit`)*

### LLM grounding and attribution

- Rashkin et al. (2023). *Measuring Attribution in Natural Language Generation Models (AIS).* Computational Linguistics 49(4):777–840 — the formal content of «οι πηγές ορίζουν» ✓ — https://aclanthology.org/2023.cl-4.2/
- Geng, Josifoski, Peyrard & West (2023). *Grammar-Constrained Decoding for Structured NLP Tasks without Finetuning.* EMNLP — where a grammar over the output space exists, malformed output becomes impossible ✓ — https://aclanthology.org/2023.emnlp-main.674/
- Min et al. (2023). *FActScore.* EMNLP — atomic-fact decomposition, the right unit for a grammatical explanation ✓ — https://aclanthology.org/2023.emnlp-main.741/
- Bohnet et al. (2022). *Attributed Question Answering.* — best-system AIS 65.5% ± 1.5 on NQ ✓ — https://arxiv.org/abs/2212.08037
- Gao et al. (2023). *Enabling Large Language Models to Generate Text with Citations (ALCE).* EMNLP — https://aclanthology.org/2023.emnlp-main.398/
- Cuconasu et al. (2024). *The Power of Noise: Redefining Retrieval for RAG Systems.* SIGIR — one related-but-non-answer-bearing distractor costs ~25% accuracy — https://arxiv.org/abs/2401.14887
- Joren et al. (2025). *Sufficient Context: A New Lens on Retrieval Augmented Generation Systems.* ICLR — large models fail to abstain when context is insufficient — https://arxiv.org/abs/2411.06037
- Lewis et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.* NeurIPS ✓ — https://proceedings.neurips.cc/paper_files/paper/2020/file/6b493230205f780e1bc26945df7481e5-Paper.pdf

### Data science and ML operations

- Sambasivan et al. (2021). *"Everyone wants to do the model work, not the data work": Data Cascades in High-Stakes AI.* CHI — 92% of practitioners hit at least one cascade — https://dl.acm.org/doi/10.1145/3411764.3445518
- Breck, Cai, Nielsen, Salib & Sculley (2017). *The ML Test Score.* IEEE Big Data — 28 tests, final score is the **minimum** across four sections; Lexorama's Monitoring section is 0 — https://research.google/pubs/pub46555/
- Benjamini & Hochberg (1995). *Controlling the False Discovery Rate.* JRSS-B ✓ — https://rss.onlinelibrary.wiley.com/doi/10.1111/j.2517-6161.1995.tb02031.x

### Licensing

- Creative Commons. *CC BY-SA 4.0 legal code* ✓ — https://creativecommons.org/licenses/by-sa/4.0/legalcode.en
- Leipzig Corpora Collection. *Terms of Usage* — CC BY-**NC** ✓ — https://wortschatz-leipzig.de/en/usage
- Dritsa, Thoma, Pavlopoulos & Louridas (2022). *A Greek Parliament Proceedings Dataset.* NeurIPS D&B; Zenodo record states CC BY-**NC** 4.0 ✓ — https://zenodo.org/records/4311577
- Bond & Paik (2012). *A Survey of WordNets and their Licenses*; OMW licence table ✓ — https://omwn.org/omw1.html
- Ylonen (2022). *Wiktextract: Wiktionary as Machine-Readable Structured Data.* LREC ✓ — https://aclanthology.org/2022.lrec-1.140/
- Sérasset (2015). *DBnary.* Semantic Web Journal 6(4) — the closest published precedent ✓ — https://www.semantic-web-journal.net/system/files/swj648.pdf

---

*End of specification. Every measurement is re-derivable from `data/db/lexorama.sqlite` and the tree
at commit `0565f04`. Where a figure differs from `docs/AUDIT.md`, the audit's figure and the delta
are noted inline.*
