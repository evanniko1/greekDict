# Λεξόραμα — Product Review

**Date:** 2026-07-21 · **Commit:** `e793c5f` · **Artifact:** `data/db/lexorama.sqlite` (1,556,893,696 B)
**Companion documents:** [`docs/AUDIT.md`](AUDIT.md) (63 verified methodology findings) · [`BACKLOG.md`](../BACKLOG.md)

This is a product review, not a methodology audit. The audit asked *are the numbers true?*
This asks *is this the right product, and where is the value?* Every quantity below was
measured against the shipped DB or the tracked tree during this review; code claims carry
`file:line`.

One methodological note on the numbers, because it changes every percentage in this
document: **the honest denominator for this dictionary is 109,967 lemmas, not 446,840.**
336,873 rows are `pos='name'` and a further 4,327 are `pos='romanization'`, leaving
**105,640 actual Greek dictionary entries**. Every coverage figure quoted anywhere in the
project against 446,840 is understated by roughly 4×. All coverage figures here use the
content denominator and say so.

---

## 1. What this product actually is today

Λεξόραμα is a **well-engineered, correctly-licensed, provenance-conscious re-presentation
of Greek Wiktionary**, wrapped in a genuinely good Greek-first UI, with a corpus-analytics
layer bolted on that it cannot support. Underneath the 446,840-lemma headline there are
105,640 real Greek words, of which 87,773 (79.8% of the content vocabulary) carry both a
definition and an inflection table — that is a real dictionary and it is the best thing in
the repository. Around it sits an accretion the evidence does not justify: 75.4% of the
lemma table is proper names (336,873 rows, 208,008 senses whose entire body text is one of
four strings — «ανδρικό επώνυμο», «γυναικείο επώνυμο», «ανδρικό όνομα», «γυναικείο όνομα»
— and 1,230,159 form rows, 38.2% of the whole `forms` table, that are declined surnames);
14 word-page surfaces are backed by exactly **two** measured quality numbers, one of which
(`validate_paradigms.py:123`, the ≥0.97 gate) is measured on cells that are disjoint by
construction from the cells that ship (AUDIT F49/C16), and the other of which (classifier
0.560) comes from a single `random_state=0` split that also chose the architecture
(`classify_domains.py:191-193`, F46); the flagship feature — inflected form → lemma with a
grammatical explanation, the thing `AboutPage.tsx:108-113` calls «το πρώτο από τα δύο
χαρακτηριστικά που δικαιολογούν το έργο» — has **zero evaluation in the repo** and is
resolved to a single silently-chosen analysis for 30.9% of ambiguous form/lemma pairs by
physical row order (`main.py:256-259`, F32/F51); the diachronic layer that consumes the
Explore page and a 375-line word-page panel is ~96% estimator noise on 8.8% of the content
vocabulary (9,653 lemmas), with change points that are a corpus-gap artifact; and the
About page's headline principle — «Η ΤΝ εξηγεί· οι πηγές ορίζουν» (`AboutPage.tsx:101`,
`README.md:15`) — describes a component that does not exist, since the "explanation" is an
f-string at `main.py:266-274` and there is no LLM anywhere in the product.

The uncomfortable summary: **the project spent its rigor budget on the layer that cannot
be defended and almost none on the layer that is genuinely differentiated.** It built
Theil–Sen with Mann–Kendall and BH-FDR correction over two single-register corpora, and
never wrote a single relevance judgement for the search box.

---

## 2. What is genuinely focused

These are real, and they are not common. Do not regress them in any redesign.

**2.1 Provenance as a schema constraint, not a promise.** All 16 sourced tables declare
`source TEXT NOT NULL`, and the live DB has **0 NULL or blank source values** across
541,759 senses, 3,216,685 forms, 291,208 relations and 294,045 collocations. The
gold/classifier split is enforced end-to-end (`score 1.0, source 'wiktionary-tag'` vs
`source 'classifier'`). Algorithmically generated paradigm cells are **visually marked in
the UI** — dotted underline, superscript `*`, footnote (`InflectionTables.tsx:72-81`).
Almost no aggregator does this at all; Wordnik attributes per *block*, Lexorama attributes
per *item*. This is the single most valuable asset the project has, and it is the thing
the pitch should be built on.

**2.2 The licensing wall actually holds.** `grep -rniE
"triantafyllid|τριανταφυλλ|academy of athens|χρηστικ|e-lexicon|greek-language.gr"` across
`pipelines/ services/ apps/` returns zero hits. The Wiktionary axis is done properly: dual
CC BY-SA 4.0 / GFDL correctly identified (`ingest_kaikki.py:50,60`), explicit modification
notices in both Greek and English satisfying §3(a)(1)(B), and the cheaper CC BY-SA outbound
path deliberately chosen over GFDL. This is discipline most hobby projects skip and most
commercial ones fake. (It is undermined elsewhere — see §3.5 — but the *instinct* and the
*mechanism* are right.)

**2.3 The core retrieval path is fast and, on exact matches, correct.** The audit's own
evaluation — 800 known-item queries replaying `main.py:296-311` verbatim — returns
**P@1 = 0.915** (binomial 95% CI [0.896, 0.934]), MRR@10 = 0.956, R@10 = 1.000, p50
latency 0.05 ms. Every statement in `main.py` is parameterized; the hot path uses
`idx_search_norm` as a proper index lookup; WAL is on. The engineering under the flagship
feature is sound. What is missing is the evaluation harness and the near-match paths, not
the machine.

**2.4 Honest disclosure instincts, and one genuinely excellent UI element.**
`MethodologyPage.tsx:300-341` `DataStatusBanner` reads `/api/build-status` and tells the
user, in Greek, exactly which documented methods the currently-served data does *not*
reflect — and disappears automatically when a rebuild fixes them. That is the single most
honest UI element I have seen in a project of this kind, and it was the right architectural
choice over a hard-coded disclaimer (which would itself become a lie after a re-ingest).
The amber warning that the domain classifier is ~0.56 accurate (`MethodologyPage.tsx:215-222`)
is the same instinct. The post-audit build manifest (`pipelines/ingest/manifest.py`) is a
hand-rolled 80% of Google's TFDV pattern and it correctly reports **0/6 checks passing**
against the live DB rather than staying quiet.

**2.5 The Greek-first presentation layer.** `labels.ts` (431 lines) translates every
Wiktionary tag into Greek with raw-value fallback so unknown tags never vanish. The whole
UI is Greek. `index.html:2` sets `lang="el"`. There is no English-first product wearing a
Greek skin here — the Greek is the product. (The Greek *typography* is a different story;
see §3.6.)

**2.6 Front-end craft in the places that are hard.** `useUserData.ts` is a module-level
store + `useSyncExternalStore` + cross-tab `storage` sync, correctly handling snapshot
stability and quota failure. `useTheme.ts:57-68` exposes a read-only `useIsDark()` via
`MutationObserver` so Cytoscape can react to theme without owning theme state, with a
pre-paint script (`index.html:9-21`) avoiding FOUC. `useMediaQuery` is used to mount the
Cytoscape canvas exactly once and never inside `display:none`. `RelationGraph` is
lazy-loaded, keeping ~438 kB out of the initial bundle. These are the right solutions to
real problems.

**2.7 The etymology data is clean, deep, and nobody else has it in this shape.** 100,521
content lemmas (91.4%) have etymology prose; 37,427 (34.0%) have a *structured* etymon
chain; 10,578 have ≥2 hops and 2,577 have ≥3. Normalisation is byte-perfect NFC across
446,840 lemmas, 56,327 etymon terms and 200,000 sampled etymology strings — zero decomposed
sequences, 123 distinct polytonic codepoints preserved. This is the one substantial dataset
in the product that the corpus-attribution defects do not touch at all, and it is barely
exploited (see §5.9).

---

## 3. What is NOT focused

### 3.1 The dictionary is 75.4% a surname list, and nothing in the product acknowledges it

336,873 proper-name lemmas own 1,567,032 of 3,663,525 `search_index` rows (42.8%),
1,230,159 form rows, and 208,008 senses whose gloss is one of four boilerplate strings.
The discovery endpoints filter them (`main.py:1027, 1129, 1162, 1334, 1442, 1505`); **search,
word pages, frequency, collocations and examples do not.** The surname «Να» carries Zipf
7.58, rank 45, 9,582,861 tokens and the particle's collocations. Two out of three word
pages in this product render a research-grade chrome — `p-5` card, `text-3xl` headword,
source badge, section headings — around a 15-character string meaning "male surname".

This is not a data-quality problem. It is a **product-architecture** problem, and it has a
known solution: Den Danske Ordbog puts proper names in a separate product (Navneleksikon).
One nav item and one `WHERE pos<>'name'` at the read path converts a 446k surname index
into a 105,640-word dictionary and makes every coverage number in the project stop being
4× understated.

### 3.2 The measurement vacuum, quantified

| Thing measured | Number | Provenance | Status |
|---|---|---|---|
| Paradigm generation precision | ≥0.97 | `validate_paradigms.py:123` | Measured on cells **disjoint by construction** from those shipped (F49/C16); `supported_classes()` is never called; the script only prints |
| Domain classifier accuracy | 0.560 / 0.463 | `classify_domains.py:191-193` | Single seed-0 20% split that also chose the architecture; smallest class has ~3.9 test examples; 95% CI [0.529, 0.591] |
| Search P@1 | 0.915 | **the audit**, not the project | Only IR number that exists anywhere |

A repo-wide grep for `precision@|P@1|MRR|nDCG|recall@|gold set|eval set` across all `.py`,
`.md` and `.tsx` returns **zero hits**. There is no `.github/`, no `Makefile`, no
`pyproject.toml`, no CI. `query_log` holds **33 rows** — and `main.py:678-706`
(`/api/insights/queries`) already computes a resolution rate and the top unresolved
queries from it, rendered nowhere and alerted on never. de Schryver & Joffe raised a
dictionary's hit rate from 67% to 75% purely by reading failed queries; Lexorama logs every
keystroke into a 1.5 GB WAL database and has never read the log.

Fourteen user-facing surfaces, two quality numbers, and the two numbers do not describe the
things that ship.

### 3.3 The analytics layer covers less of the dictionary than anyone assumes

Measured against the 109,967 non-name lemmas:

| Surface | Content lemmas | Coverage |
|---|---:|---:|
| Definitions | 107,272 | **97.5%** |
| Etymology (prose) | 100,521 | **91.4%** |
| Inflection tables | 90,091 | **81.9%** |
| Relations (any edge) | 56,612 | 51.5% |
| Corpus examples | 44,587 | 40.5% |
| Etymon chain (structured) | 37,427 | 34.0% |
| IPA | 31,824 | 28.9% |
| Curated sense examples | 25,769 | 23.4% |
| Collocations | 23,171 | 21.1% |
| Frequency / Zipf | 17,364 | **15.8%** |
| Semantic neighbours | 14,294 | 13.0% |
| Diachronic drift | 9,653 | **8.8%** |
| Descendants | 334 | **0.3%** |

The word page devotes a 375-line dedicated panel (`DiachronicPanel.tsx`, four sub-surfaces:
frequency chart, trajectory chart, drift badges, era-neighbour columns) to a signal present
for 8.8% of the vocabulary and which the audit measured as ~96% estimator noise. It devotes
a schema table, an ingest mode, an API field and a full-width card to descendants at 0.3%.
Meanwhile the frequency meter — a 5-band visual claim about how common a word is — is
backed for 15.8% of content lemmas and computed on counts that sum to 1,026% of the corpus.

### 3.4 The word page has no hierarchy and no design for its own modal case

Computed over all lemmas: **66.6% render exactly 3 cards** (Ορισμοί + Ετυμολογία + Κλίση),
11.0% render 0–2, and only **5.8% render 6–8**. All nine content cards share the identical
shell — `rounded-lg border border-slate-200 bg-white p-5 shadow-sm`, copy-pasted verbatim
12 times — against a `bg-slate-50` page at a **1.03:1** luminance ratio, so the cards are
not visually objects at all. The only ranking signal is source order in a hand-written
array literal at `WordPage.tsx:691-699`: «Ορισμοί» (the reason the page exists, 97.5%
coverage) and «Απόγονοι σε άλλες γλώσσες» (0.3% coverage) are peers. `EntryEtymology`
(`:693`) and `EtymologyTimeline` (`:694`) render **the same `entry.etymons` array twice**,
adjacently, in two visualisations.

There is no anchor nav, no sense overview, no truncation counts, no collapse-all, and
exactly one disclosure control in the whole page (the Κλίση accordion, `:717-754`,
desktop only). Every comparator solves this and none of the solutions require new data:
ANW ships a two-axis jump nav (`Per betekenis` / `Per onderwerp`), DDO ships two
independent density toggles (`Vis forkortet`, `Vis/Skjul overblik`), DWDS ships a sticky
anchor bar plus a global `zuklappen/ausklappen` plus truncation-with-count
(`…325 weitere`, `…9 weitere Beispiele`).

### 3.5 Capabilities that are advertised and absent

| Claim | Where | Reality |
|---|---|---|
| «Η ΤΝ εξηγεί· οι πηγές ορίζουν» | `AboutPage.tsx:101,103`; `README.md:15`; `MethodologyPage.tsx:224` | **No LLM exists in the product.** `main.py:266-274` is an f-string. The one component the project calls ΤΝ (the domain classifier) *originates* lexical content for 5,152 lemmas with no source — the exact inverse of the stated principle |
| «σου λέει ΓΙΑΤΙ (γενική, πληθυντικός)» | `AboutPage.tsx:108-113` | True for 69.1% of ambiguous pairs; for the other 30.9% it asserts one analysis as fact on the basis of a rowid. 1,223,148 of 1,805,293 analyses can never be displayed |
| «Κάθε σχέση … ακμή με συγκεκριμένο τύπο και πηγή — όχι ένας αόριστος «σχετικός όρος»» | `AboutPage.tsx:116-121` | **186,495 of 291,208 relations (64.0%) are exactly `related`.** The source is written to a Cytoscape `data.title` the canvas never draws, with no popper extension installed |
| «Χωρίς διάκριση τόνων» | `SearchPage.tsx:180` | `schema.sql:7-14` was corrected post-audit to state accent is phonemic and `(lemma, pos)` is identity. The UI still advertises the behaviour that deleted ποτέ, νομός, δουλεία, χαλί and κάλος |
| «Τυπικές συνάψεις» | `WordPage.tsx:459` | Leipzig whole-*sentence* co-occurrence, no window, no grammatical relation, no logDice. 31.67% of chips are capitalised; the top-12 for κρίση contains a deputy minister's name and title four times |
| Open data under CC BY-SA 4.0 | `LicensingPage.tsx:55-56`; `docs/licensing.md:52-54` | No LICENSE file, no DATA-LICENSE, no published snapshot. Leipzig and the Parliament corpus are both **CC BY-NC**, incompatible with the declared outbound licence |

The last row is the most consequential, because it does not just make a claim false — it
makes the project's best strategic differentiator (§5.10) legally unavailable until
resolved.

### 3.6 The Greek is typeset by accident

`index.css` is 18 lines and sets no font stack, no `@theme`, no `@font-face`. The font
budget is **0 bytes** against a **799 kB** JS budget. Consequences that are measurable:
on Android, Roboto covers **1 of the 123 polytonic codepoints** this database contains, so
the polytonic etymology falls out of the UI font on every hop — and 13,976 of 41,647 word
pages (33.6%) show a monotonic headword beside a polytonic ancestor. Greek orthography drops
the tonos in all-caps; the app renders **24 distinct Greek strings** through
`text-transform: uppercase`, and Safari does not implement the language tailoring on any
version — so on every iPhone, 24 of 24 section headings are orthographically wrong Greek
(«ΕΤΥΜΟΛΟΓΊΑ», «ΣΗΜΑΣΙΟΛΟΓΙΚΟΊ ΓΕΊΤΟΝΕΣ»). 41,839 IPA transcriptions render in `font-mono`,
where 1,715 rows carry U+0361 (a tie bar designed to span two glyph advances, in a font
where every advance is identical) and 448 carry U+203F, which Segoe UI, Consolas, Courier
New, Arial and Calibri all lack entirely. Prose runs at **98–116 characters per line**
against Bringhurst's 45–75, and Greek needs **+23.1% more vertical ink** than Latin at the
same size (94.2% of Greek content lemmas contain a descender) against Latin-calibrated
Tailwind leading.

For a product whose entire premise is that Greek orthography is worth getting right, this
is a positioning problem, not a polish problem.

### 3.7 Accessibility and shell fundamentals

No `<h1>` on the word page (the headword is `<h2>`, `WordPage.tsx:154`); `document.title`
is never set on any route (grep: 0 hits), so every one of 446,840 word pages is
indistinguishable in the tab strip, browser history and search results; zero
`focus-visible` styles app-wide and exactly one authored focus style; zero `aria-live`
regions; `text-slate-400 dark:text-slate-500` — the single most-used colour token (136
uses) and the literal used for all 7 uppercase section headings — measures **2.56:1**
against WCAG's 4.5:1; `text-xs py-0.5` chips compute to 20–22 px against WCAG 2.2 SC 2.5.8's
24×24 px; and the 26 native `title=` tooltips carrying bootstrap CIs, significance,
similarity scores, classifier confidence and the "algorithmically generated form" warning
are **unreachable on touch and on keyboard**. The product's honesty layer lives in the one
place a phone cannot render.

### 3.8 Six loading states, no error states, no cache

Six unstyled `<p>Φόρτωση…</p>` with no `role="status"`. `ExplorePage` swallows every error
into `setData(null)` at seven call sites, so a failed endpoint renders as a permanent
spinner with no way to distinguish loading from broken. `WordPage.tsx:777-779` prints
`"500 Internal Server Error for /api/word/…"` verbatim into an all-Greek UI. Thirteen raw
`fetch`-in-`useEffect` sites with no client cache; `/api/explore/overview` is fetched twice
on mount. `RelationGraph.tsx:190` includes `isDark` in the effect deps, so toggling the
theme re-runs a 1,500-iteration `cose` layout from scratch.

---

## 4. The value question — surface by surface

**Reach** = share of the 109,967 content lemmas the surface has data for.
**Verdict** = KEEP (working, defensible) · FIX (right idea, broken execution) ·
MERGE (real content, wrong container) · CUT (does not earn its maintenance surface).

### Search & entry

| Surface | Serves | Reach / frequency | Evidence | Verdict |
|---|---|---|---|---|
| **Form→lemma search with explanation** | Every Greek speaker, every session | 3.66M indexed surfaces; the single highest-frequency interaction in the product | P@1 = 0.915 [0.896, 0.934] on exact match — but 30.9% of ambiguous pairs show one rowid-chosen analysis, 68.2% of as-you-type prefixes and 97.9% of 1-char typos return nothing | **FIX — highest priority in the product** |
| Greeklish input | Diaspora, phone users, anyone without a Greek keyboard | Unmeasured usage; uncontested capability | R@1 = 0.737 with 16.3% zero-result on the visual convention; no `v→β` at all; greedy `nt` makes every νθ word unreachable | **FIX** |
| en→el gloss bridge | L2 learners, translators | 58,458 gloss rows | Points at lemmas not senses (up to 58 lemmas per English term); `_en_key` doesn't strip articles so "to run"/"the sea" return nothing; 1,160 weight-1.0 rows point at derogatory senses rendered untagged | **FIX** |
| Zero-result state | Everyone who mistypes | Dead end today | One sentence, no suggestions, no did-you-mean, no prefix continuation | **FIX** |
| Proper-name results interleaved with content | Nobody | 42.8% of the index | Surname «Να» at Zipf 7.58 outranks the particle | **CUT from the dictionary → MOVE to a separate «Ονοματολόγιο»** |

### Word page — the core

| Surface | Serves | Reach | Evidence | Verdict |
|---|---|---|---|---|
| **Definitions** | Everyone | **97.5%** | Per-sense source badges; mean gloss 48.1 chars on content lemmas; 34.7% of content lemmas are polysemous | **KEEP — make it visually primary** |
| **Inflection tables (Κλίση)** | Native speakers checking a form; every L2 learner | **81.9%** (median 9 forms, p90 52) | Generated cells visually flagged — genuinely good. But 33.9% of verbs merge active and mediopassive into one cell (115,326 cells, 5,440 lemmas) and `άνθρωπους` ships as a real form | **KEEP + FIX (voice) — this is the second-best asset** |
| **Etymology (prose)** | Etymology is the #1 organic-interest driver for Greek | **91.4%** | Multi-hop chains, 56,327 etymons, clean NFC, polytonic preserved. 10,926 etymons are the lemma itself and 566 are self-loops (F57, never audited) | **KEEP + audit** |
| EtymologyTimeline | — | Same 34.0% as `etymons` | Renders **the same array** as the card directly above it | **MERGE into the etymology card** |
| IPA / pronunciation | L2 learners; native speakers on rare words | 28.9% | 109 distinct characters, 86 rows with Greek homoglyph contamination, 4 with Cyrillic; rendered in `font-mono` which lacks the tie bar | **KEEP + FIX (font, data hygiene)** |
| Corpus examples | Everyone, when present | 40.5% | Length-only ranking (`ingest_examples.py:76-87`), no rare-word term, no keyword position, **no blacklist** on a 2020 news corpus; per-sentence publisher + date sit unread in `-sources.txt` | **FIX — and the citation fix is also the licensing fix** |
| Curated sense examples | L2 learners | 23.4% | 50,284 strings, mean 120 chars, from Wiktionary — higher quality than the mined ones and less prominent | **KEEP, promote above corpus examples** |
| Family / cognates / neighbours / collocations / descendants (5 separate full-width cards) | Word explorers | 51.5% / — / 13.0% / 21.1% / **0.3%** | Five identical bordered sections; Wordnik ships the same 11 relation types as **one** module with visible counts | **MERGE into one «Σχετικές λέξεις» with counted sub-lists; CUT descendants** |
| Frequency meter | Everyone (it's above the fold) | **15.8%** | Counts sum to 1,026% of corpus; MAX(zipf) = 8.615 on a scale topping ~7; 225 lemmas exceed Zipf 7; source is a *third* corpus (OpenSubtitles) never named on the Methodology page | **CUT until F2 is fixed, then restore as a band, not a number** |
| Usage / domain chips | Learners, register-sensitive users | ~31% displayed | `rare`→«σπάνιος» as a chip collides with the frequency band `rare`→«πολύ σπάνια»; a word can be «ασυνήθιστο» and «σπάνια» at once | **KEEP + FIX vocabulary** |
| Domain confidence percentage | Nobody | ~31% | Uncalibrated softmax under a counterfactual uniform prior (`class_weight='balanced'`); 61.0% of shipped rows are below the code's own floor | **CUT the number; keep a coarse band or nothing** |
| **Relation graph (Cytoscape)** | Looks impressive in a screenshot | 51.5% have any edge; **median degree 3**, 46.4% empty | 438 kB of the 799 kB JS bundle. 64.0% of edges are the untyped `related` the About page says the graph excludes. Mobile «Σχέσεις» tab has **zero accessible content**. Lew et al. (2018): added visual material *competes* with the definition for attention. **No comparator — DWDS, DDO, ANW, Wordnik — uses a node-link canvas for word relations** | **CUT as the default; keep behind a link for the 0.5% of lemmas that reach LIMIT 60** |
| Diachronic panel (4 sub-surfaces) | Researchers, in principle | **8.8%** | ~96% estimator noise; 96.4% of news drift present by slice 3; change points 82.5% concentrated on 2016, the first slice after a three-year corpus hole; CI coverage 82.0% against a nominal 95% | **CUT the drift score, change point and neighbour-overlap; KEEP a documented normalized frequency curve** |

### Explore

| Surface | Serves | Reach | Evidence | Verdict |
|---|---|---|---|---|
| Trends (rising/falling) | Journalists, researchers | Corpus-level | Right estimator (Theil–Sen + MK + BH-FDR — better than Sketch Engine, which shows raw p). But R² pre-selection then tests the same data; #1 falling word of Greek is **αισώπειος**, an artifact of bare endings being indexed as forms | **FIX (blocked on F4/F1) — then it is genuinely good** |
| Keyness (G² / Log Ratio / DP gate) | Researchers | Corpus-level | Correct Gabrielatos design. G² gate passes 88.4% of candidates with no multiple-testing correction; DP gate rejects 0.40%; #4 news-distinctive word is **περιπλέκω**, i.e. the guillemets `«»` | **FIX (blocked on F1)** |
| By-field movers | Nobody clearly | 31% classified at 0.56 accuracy | Compounds an unevaluated classifier with an unevaluated trend | **CUT** |
| Semantic drift / movers list | Nobody | 8.8%, 94% without an interval | Ranks ~20k noisy estimates | **CUT** |
| Two-corpus compare | Researchers | Corpus-level | The one Explore surface with a defensible design; `<circle r={2.5}>` links are 5 px targets and use a raw `<a href>` that full-reloads the SPA | **KEEP + FIX** |
| Second-corpus axis scaffolding (#40) | Nobody | Zero data | Infrastructure with no rows | **CUT** |

### Static pages

| Surface | Serves | Verdict |
|---|---|---|
| **MethodologyPage + DataStatusBanner** | Anyone evaluating trustworthiness | **KEEP — model it on DWDS `/d/plot`**: every parameter, every formula, and a prominent *limitations* section |
| LicensingPage | Legal/reuse | **FIX** — 4 corpora / 2,531,144 rows have no attribution row at all, including the default Explore axis |
| AboutPage | First-time visitors | **FIX** — remove the AI claim, restate the graph claim, keep the form→lemma claim and make it true |

**Net effect of the CUT column:** descendants, the drift/change-point display, movers,
by-field, the second-corpus scaffolding, the numeric confidence, the frequency number, and
the graph-as-default. That removes roughly a third of the surface area and **zero** of the
things users come for.

---

## 5. Where the real value is

Ranked by (value to a Greek speaker) ÷ (effort), with the dependency stated. Items 1–7 make
the existing thing good. Items 8–12 unlock something new.

### Makes the existing thing good

**1. Split the proper names into a separate product.** *(1 day, no dependency, highest
leverage per hour in the entire project.)* One nav item and a read-path filter. 336,873
lemmas leave the dictionary; the dictionary becomes 105,640 words; every coverage number
stops being 4× understated; the search dropdown stops surfacing surnames; the frequency
table stops being contaminated by «Να». DSL solved this exact problem with Navneleksikon —
by product architecture, not by ranking heuristics. There is no cheaper change in this
document.

**2. Make the flagship feature true and measurable.** *(3–5 days.)* Two halves, in order:
(a) change the dedupe key in `_emit` (`main.py:258-259`) from `lemma_id` to
`(lemma_id, features)`, aggregate, and render «ανθρώπων → άνθρωπος · γενική πληθυντικού ή
κλητική ενικού» — the literature is unanimous that a bare query form is undisambiguatable
without context (Greek taggers report 1.82 tags/word), and Perseus/Morpheus, the closest
analogue product, returns *all* analyses; (b) build `tests/eval/` with 500 auto-generated
known-item queries stratified by frequency decile and POS, 150 ambiguous surfaces scored by
set-recall, 150 Greeklish, 100 en→el, and a `scripts/eval_search.py` that gates CI on P@1 /
MRR@10 / R@10 / zero-rate / p95. Sanderson & Zobel show 50 topics suffice for reliable
comparison; 500 makes ~2-point changes measurable. **Then publish the number on the
Methodology page.** A dictionary that publishes its own retrieval accuracy is a category of
one.

**3. Add prefix and typo tolerance.** *(3 days, no dependency.)* 68.2% of as-you-type
prefixes return nothing today; that is a missing `WHERE` clause, not an architecture
problem. Measured on the shipped DB with the existing index: `ανθρ*` = 3.9 ms,
`θαλασ*` = 2.0 ms, `υπολογ*` = 0 ms. Short prefixes need a dedicated small index
(`α*` costs 430 ms over `search_index` but 11 ms over `lemmas.normalized_lemma`). For
typos, gate exactly as the deployed consensus does — 0 edits ≤3 chars, 1 for 4–7, 2 for ≥8
(Elasticsearch AUTO, Algolia 4/8, Typesense) — via a symmetric-delete index or SQLite's
`spellfix1`, which already recognises Greek (`spellfix1_scriptcode` = 200) and whose
`edit_cost_table` lets you make ι/η/υ, ο/ω, ε/αι and ς/σ cheap, which is precisely the error
model Greek typing produces. **Note the ranking trap:** 421,002 lemmas (94.2%) tie at the
frequency sentinel, so `ORDER BY` currently degenerates to insertion order — adding
prefix/fuzzy without a prior first will flood the dropdown with surnames.

**4. Fix verb voice.** *(3 days + re-ingest.)* 33.9% of Greek verbs display active and
mediopassive forms in the same cell — σκοτώνω stores `έχω σκοτώσει` and `έχω σκοτωθεί`
under byte-identical feature lists, and `inflection.ts:216` joins them with `" / "`. To a
native speaker this reads as the dictionary being simply wrong about the primary axis of
the Greek verb. It is the most visible correctness defect in the product.

**5. Fix the corpus-attribution primitive.** *(4 days + re-ingest.)* One form-validity gate
at ingest — reject punctuation, forms with no Greek letter, bare inflectional endings,
`{}[]_\|`, and component tokens of multiword lemmas — plus `for lid in set(ids)` in
`ingest_frequency.py:97-98`. That single change fixes F1, F4, half of F20 and F2, and
un-blocks frequency, Zipf, bands, keyness, trends and the `min_pm` drift gate simultaneously.
Nothing quantitative in the product is defensible until this lands.

**6. Rebuild the word page's information architecture.** *(1–2 weeks, no new data.)*
Branch on **data shape, not viewport**: a compact layout for the 66.6% three-card majority
(headword, POS/gender, IPA, gloss, source, and an explicit «τι δεν έχουμε» panel replacing
the nine silent `return null` sites), and a research layout for the 5.8% with a sticky
two-axis nav on the ANW model (`Per betekenis` / `Per onderwerp` — the same grid navigable
either by sense or by module), DDO-style density toggles, and truncation-with-count on
every list. Merge the five relation cards into one counted module (Wordnik). Give
«Ορισμοί» visual primacy. NN/g measured +47% usability from scannable layout alone and
+124% combined; this is the largest single lever available for a content page, and it
requires zero new data.

**7. Build the design and typography foundation.** *(1–2 weeks.)* A Tailwind v4 `@theme`
block with semantic OKLCH ramps on the Radix model, three primitives (`Card`,
`SectionHeading`, `Chip`) replacing 12 copy-pasted card literals and 18 ad-hoc pills, and a
real font stack — **Noto Sans** for UI/body (the only candidate at 100% modern Greek, 100%
polytonic, 97.1% IPA) with **Gentium Book Plus** bound to a `--font-ipa` token (the only
candidate at 100% of this DB's 68 non-ASCII IPA characters), subset by `unicode-range` with
`font-display: optional` and metric overrides derived from Greek ink, not Latin. Delete
`text-transform: uppercase` from all 24 Greek headings — that alone fixes 100% of iOS and
removes a whole class of browser-tailoring dependency. Fix contrast (2.56:1 → 4.5:1), add
`:focus-visible`, set `document.title` per route, add the `<h1>`.

### Unlocks something new

**8. Greeklish, done properly — the one uncontested capability.** No comparator needs it;
every Greek user does. Today: no `v→β` mapping at all, `x→ξ` only, a duplicate `h` key, and
a truncating `itertools.product` that varies the rightmost unit fastest so `max_candidates=64`
never varies the first vowel of a long word. Replace with a cost-scored beam. Toumazatos et
al. (LREC-COLING 2024) is a dedicated study of exactly this task and finds it unsolved —
which means a well-engineered candidate generator is a *publishable* contribution, not just
a feature. This is territory currently being ceded to Google.

**9. The etymological descent explorer — the best cool feature available, and it depends on
nothing that is broken.** The `etymons` table is 56,327 clean, NFC-normalised, polytonic-
preserving rows over 37,427 content lemmas, 10,578 with ≥2 hops. **Invert it.** «Ποιες
νεοελληνικές λέξεις κατάγονται από το ἄγω;» — one index, one endpoint, one page. Then layer:
descent trees, shared-ancestor discovery between two modern words («τι κοινό έχουν η
*σχολή* και το *σχήμα*;»), a loan-source map (1,549 etymon terms are Arabic/Hebrew/Persian
script; 25,060 are `grc`, 7,773 `grc-koi`, 5,203 `gkm`), and a "borrowing era" filter.
Nobody ships this for Greek. Wiktionary has the data and no interface for it; the Greek
incumbents have the interface and closed data. **This is the feature I would build first
after the name split**, because it is the only substantial dataset in the product that the
corpus defects do not touch, it is intrinsically interesting to the exact audience Greek
lexicography attracts, and it needs no evaluation harness to be trustworthy — the chain
either cites a source or it doesn't. *(Prerequisite: the F57 etymology audit — 10,926
etymons are the lemma itself and 566 are self-loops.)*

**10. Make «Η ΤΝ εξηγεί» true by moving the LLM offline.** *(2–3 weeks.)* Not a runtime
service — a **build-time data source**. An `explanations` + `explanation_claims` table pair,
generated offline, registered through `manifest.py` like every other component, with every
morphological claim routed through a new `paradigm_engine.verify()` before it is written:
`contradicts` drops the explanation, `out_of_scope` demotes the claim to a citation of a
`forms` row, `confirms` stores `verified_by='paradigm_engine'`. The model emits typed claim
JSON through a strict tool schema and **never emits user-facing Greek** — a deterministic
renderer does that. This makes each explanation diffable, provenance-stamped and
individually retractable, exactly as the schema already enforces for 541,759 senses; it
costs a one-time batch rather than per-request; and it turns the product's most prominent
false claim into its most defensible one. The irony worth naming: the *other* place an LLM
is state-of-the-art here is offline relevance labelling for item 2 (Thomas et al., SIGIR
2024 — LLM labels match first-party humans and beat crowd workers), which is what makes the
Greeklish and en→el eval slices affordable for a solo maintainer.

**11. Sense-level en→el.** *(1 week.)* Attach `gloss_index` to `senses.id` rather than
`lemma_id`, and render `classifyTags(...).usage` on `ResultCard`. All three European
comparators (DWDS, DDO, ANW) are strictly monolingual by design; Linguee, fetched live, has
**no Greek dictionary layer at all** — `greek-english/search?query=ανθρώπων` returns only
"External sources (not reviewed)" EU legislative text, no headword, no lemma resolution.
Cross-language entry into a monolingual-quality Greek dictionary is something the incumbents
structurally cannot offer. Today it is a liability (58 lemmas per English term; 1,160
weight-1.0 rows pointing at derogatory senses rendered untagged); one join changes that.

**12. A citable, downloadable, standards-serialised open Greek lexical dataset.**
*(2 weeks — but **blocked on licensing**.)* OntoLex-Lemon/lexicog export with stable sense
URIs and PROV-O provenance, a checksummed snapshot, a Datasheet (Gebru et al.) and a Data
Statement (Bender & Friedman) for each corpus, published via Croissant. DWDS's newspaper
corpus is licence-locked and its curves now require login; DDO is WAF-locked against
automated access; ANW is free-to-read, not free-to-bulk-reuse. Lexorama could be the only
ELEXIS-linkable open Greek lexical resource. **This white space is currently closed by the
project's own licensing failure** — no LICENSE file, and Leipzig + Parliament are both
CC BY-NC against a declared CC BY-SA. Resolve that first or the differentiator does not
exist.

### Explicitly *not* worth building

- **A corpus query workbench.** Svarna (Chatzikyriakidis, arXiv:2607.00970, July 2026) is
  an open Greek corpus workbench — 507M words across institutional, literary, dialectal,
  social-media and historical registers, concordancing + register-normalized frequency +
  collocations + n-grams, MIT-licensed, **built on SQLite FTS5 + FastAPI**, i.e. Lexorama's
  exact stack with the register coverage Lexorama lacks. Link out to it. Do not rebuild it.
- **More statistics on the current corpora.** DWDS, with 26 billion tokens and a national
  academy behind it, ships normalized frequency curves and *stops*. It does not put
  embedding-based semantic drift in its public UI. Two single-register corpora with a
  three-year hole and a 3.3× size discontinuity at 2019 cannot support more than DWDS does.

---

## 6. Positioning and differentiation

**Against Greek Wiktionary.** Lexorama *is* Greek Wiktionary, restructured — so the pitch
can never be "more words". It has to be **"the same open data, but you can actually find
it."** Wiktionary cannot take an inflected form, cannot take Greeklish, has no paradigm
generation for missing cells, has no per-item provenance UI, and has no Greek-first
navigational layer. Lexorama has all four. That is a real product on top of someone else's
data, and it is honest to say so.

**Against Google.** Google wins on a lemma you can already spell. It loses on the three
things Greek morphology actually demands: it will not tell you that ανθρώπων is genitive
plural of άνθρωπος, it will not give you a paradigm table, and it will not tell you where
the answer came from. Lexorama should not compete on "definition of X" — it should compete
on **"what is this word I'm looking at?"**

**Against the Greek incumbents.** The Πύλη για την Ελληνική Γλώσσα (ΛΚΝ Τριανταφυλλίδη,
Κριαράς) is the dominant Greek lookup: better lexicography, closed data, no API, no bulk
reuse — and Lexorama deliberately does not touch it, verified clean by grep. Lexorama
cannot win on lexicographic quality against a national academy and should stop trying. It
wins on **input tolerance, provenance transparency, and openness**. *Caveat this review
owes you:* the comparator work covered DWDS, Ordnet/DDO, Woordenlijst, ANW, Sketch Engine,
Wordnik and Linguee, but **not** the Greek-market incumbents that overlap the flagship
feature most directly — Neurolingo's Λεξισκόπιο and lexigram.gr both do Greek morphological
analysis and inflection. Before committing to the pitch below, spend half a day establishing
exactly what they do and do not do. If one of them already resolves inflected forms with a
grammatical explanation, the differentiator is provenance + openness + Greeklish, not the
parse itself.

**Against the European reference dictionaries.** DWDS redirects `ging → gehen` and says only
"best match" — it never explains *why*, and it fails outright on `Häuser → Hauser`. DDO and
ANW are lemma-indexed. Woordenlijst has the paradigm record shape Lexorama needs
(`label` + machine feature string + hyphenation + `arch` + `keurmerk` + `source` +
`position`) but no definitions and no search UX. **Explaining the form→lemma match is
genuinely uncontested in this comparator set.** It is also the feature that is 30.9%
arbitrary and has no evaluation. That is the whole strategy in one sentence.

### The sharpest version of the pitch

> **«Γράψε τη λέξη όπως τη βρήκες. Θα σου πούμε τι είναι — και από πού το ξέρουμε.»**
> *Type the word as you found it. We'll tell you what it is — and where we know it from.*

Three claims, all defensible after §5 items 1–5, all measurable, none requiring an LLM:

1. **Input tolerance.** Inflected, unaccented, mistyped, or in Greeklish. Measured by
   P@1 / R@10 / zero-rate, published.
2. **The parse, not just the entry.** Every analysis, not one. «γενική πληθυντικού ή
   κλητική ενικού», with the paradigm position shown.
3. **Provenance per item.** Every gloss, form, relation and example carries its source, and
   generated forms are marked as generated. Already true in the schema; make it true in the
   UI everywhere, including `search_index`.

Drop «Η ΤΝ εξηγεί· οι πηγές ορίζουν» entirely until §5.10 ships. It is false, it is
generic, and it is the only line in the product that a hostile reader can disprove in
thirty seconds.

---

## 7. The 90-day plan

Sequenced so that each phase is shippable and the expensive re-ingests happen once, behind
CI, after the schema is settled. Effort in ideal focused days for one developer.

### Days 1–14 — Stop asserting things that are false; delete a third of the surface

The point of this phase is that the product should be *smaller and true* before it is
bigger. All of it is removals, one-line predicates, or copy.

| # | Action | Files | d |
|---|---|---|---|
| 1 | **Verify the Leipzig and Parliament licences.** If CC BY-NC holds, remove the Parliament axis and verbatim `corpus_examples` from any published snapshot, or split the release. **This gates every open-data claim and §5.12.** | `docs/licensing.md`, `SOURCE_META` | 1 |
| 2 | Root LICENSE + DATA-LICENSE; WordNet 3.0 notice and Apache-2.0 NOTICE on `/licensing`; static attribution fallback; add SOURCE_META for the 4 unattributed corpora (2,531,144 rows) | repo root, `LicensingPage.tsx` | 1.5 |
| 3 | Remove the AI claim from `AboutPage.tsx:101,103`, `README.md:15`, `MethodologyPage.tsx:224`. Restate the graph claim to match 64.0% `related`. Delete «Χωρίς διάκριση τόνων» (`SearchPage.tsx:180`) | 4 files | 0.5 |
| 4 | Suppress `change_point_year` when `change_point_score IS NULL`; remove the CI display; remove the "frequency-robust" label from `neighbor_overlap` | `main.py:957, 1013, 1062`, `DiachronicPanel.tsx` | 1 |
| 5 | **Execute the CUT list:** descendants card + table + ingest mode + API field; drift score / change point / neighbour-overlap display; `/api/explore/movers` list; by-field movers; second-corpus scaffolding (#40); numeric domain confidence; frequency *number* (keep the band, relabel as provisional) | ~8 files | 2 |
| 6 | **Proper-name split.** `WHERE pos<>'name'` on search, word-page fan-out, frequency, collocations, examples; new «Ονοματολόγιο» route; report lexicon size as 105,640 | `main.py`, `SearchPage.tsx`, new route | 1 |
| 7 | Cap `_resolve_lemma_ids` + LIMIT (the 46 MB single-response amplification is a live availability bug); `Query(..., ge=, le=)` on all 13 handlers; quantize floats before cache keys; cap `explore_cache` | `main.py` | 1.5 |
| 8 | **CI.** GitHub Actions: `pytest -q` + `npm run typecheck` + `npm run build` + `manifest.py --db` as a gate. `TestClient` tests for all 13 route handlers | `.github/`, `tests/` | 2 |
| 9 | Graph demoted to a link for lemmas with <5 edges (median is 3); `EntryFamily` rendered in the mobile «Σχέσεις» tab so it stops having zero accessible content | `WordPage.tsx`, `RelationGraph.tsx` | 1 |

**Exit criterion:** `/api/build-status` still reports divergence (expected — the DB predates
the fixes), but no page asserts anything the data contradicts, and the CUT list is gone.

### Days 15–45 — Fix the primitive, fix the flagship, re-ingest once

CI is now in place, so the re-ingest is protected. Do **all** schema work before the ingest,
then run it once.

| # | Action | Fixes | d |
|---|---|---|---|
| 10 | **Form-validity gate at ingest** — reject punctuation, no-Greek-letter forms, bare endings, `{}[]_\|`, multiword component tokens | F1, F4, half of F20 | 3 |
| 11 | **Dedup frequency crediting** (`for lid in set(ids)`), `UNIQUE(lemma_id, surface, normalized_surface)` on `search_index`, re-derive Zipf, assert `Σ 10^(zipf−9) ≤ 1.05` in a test | F2 | 1 |
| 12 | **Infer verb voice at ingest** from form morphology + defensive fallback in `inflection.ts:334` | F3 | 3 |
| 13 | Add `source` + `generated` to `search_index`; render «τύπος παραγόμενος από κανόνα» on `ResultCard` (the Woordenlijst `arch`/`keurmerk`/`source` triple, minimum viable) | F26 | 1 |
| 14 | Refuse paradigm generation on unknown gender and invisible stress; drop accent-unstable cells (acc. plural for non-oxytone -ος, nom/acc/voc plural for non-oxytone -ο); delete the 171 double-accented and 300 article forms | F40, F42, F22, F58 | 3 |
| 15 | Ingest `-sources.txt`: publisher URL + date per `corpus_examples` row, rendered under each sentence | F25 — **highest copyright exposure in the DB** | 1 |
| 16 | `record_build()` in the remaining 6 pipelines so `manifest_coverage` can pass; `record_attribution` fails **closed** | R1-followup, F24 | 1 |
| 17 | **Full re-ingest under `schema_version` 2** (recovers ποτέ, νομός, δουλεία, χαλί, κάλος…), then `build_search_index`, `ingest_frequency`, `ingest_frequency_timeseries`, with `seed=`, `workers=1` | R2-followup, F44 | 1 + compute |
| 18 | **All analyses per (surface, lemma)** — dedupe on `(lemma_id, features)`, deterministic ORDER BY tie-breakers, «γενική πληθυντικού · ή κλητική ενικού» on `ResultCard` | F32, F51 | 2 |
| 19 | **`tests/eval/`** — 500 known-item + 150 ambiguous (set-recall) + 150 Greeklish + 100 en→el; `scripts/eval_search.py` through `TestClient`; regression floors in pytest | F27 | 3 |
| 20 | **Prefix + fuzzy passes** — 5-stage cascade, `suggest_index` for short prefixes, length-gated edit distance, name penalty + `log(1+senses)` prior in the ranking (94.2% currently tie at the sentinel) | F29 | 4 |
| 21 | Greeklish: `v→β`, `x→[χ,ξ]`, `b→[μπ,β]`, `d→[δ,ντ]`, `g→[γ,γκ]`, αυ/ευ arms, guard nt/mp/gk against a following `h`, scored beam replacing the truncating product. Fix `_en_key` to import `build_gloss_index._phrases` | F23, F28, F41, F30 | 2.5 |
| 22 | Zero-result recovery panel: «Μήπως εννοούσες X;», prefix continuations, an explicit "not in the dictionary yet" state; same treatment for `/word/:lemma` misses | F29 | 1 |

**Exit criterion:** `/api/build-status` reports **6/6 checks passing**, the methodology
banner disappears on its own, and `scripts/eval_search.py` prints a P@1 you can put on a
slide.

### Days 46–75 — Make it good to use

| # | Action | d |
|---|---|---|
| 23 | **Token layer** — `@theme` with OKLCH semantic ramps, `light-dark()` collapsing the 315 hand-mirrored `dark:` variants, `Card`/`SectionHeading`/`Chip` primitives, Cytoscape + SVG reading tokens via `getComputedStyle` instead of 22 hex literals | 4 |
| 24 | **Typography** — Noto Sans + Gentium Book Plus (`--font-ipa`) with `unicode-range` subsets and Greek-derived metric overrides; delete `text-transform: uppercase` from all 24 headings; measure → ~62ch; leading +23%; `lang="grc"` on 38,036 ancient etymons, `dir="rtl"`/`<bdi>` on 1,549 RTL terms; `lang="en"` at `WordPage.tsx:176` | 4 |
| 25 | **Accessibility floor** — contrast ≥4.5:1 on the section-heading token, global `:focus-visible`, 24px chips, `document.title` per route, `<h1>`, skip link, route-change focus, `role="status"` on the six loading states, real `role="tablist"` or drop the fake tabs | 3 |
| 26 | **Word-page IA** — branch on data shape (compact / research); ANW two-axis nav; DDO density toggles; truncation-with-count; merge the 5 relation cards into one counted module; merge `EtymologyTimeline` into the etymology card; coverage-weighted card order replacing the array literal | 6 |
| 27 | **Promote the 26 `title=` tooltips** into a real disclosure primitive; add text/table fallbacks for charts | 2 |
| 28 | **Search as a real APG combobox** — roles, arrow keys, Enter-to-first-result, `aria-live`, `<form>`, `lang="el" autoCapitalize="off" autoCorrect="off" spellCheck={false} enterKeyHint="search"`; debounce 250 → ~100 ms with `AbortController` and `useDeferredValue` | 2 |
| 29 | **State honesty + perf** — fetch cache (dedupe the double `overview` call), shape-aware skeletons, stop `ExplorePage` swallowing errors into `setData(null)`, `content-visibility: auto` below the fold, remove `isDark` from the Cytoscape effect deps, `path="*"` route + error boundary | 3 |
| 30 | **Copy pass** — one register (2sg informal), one slogan, U+0374 κεραία, `Intl.NumberFormat("el")` replacing 22 `toFixed()`, resolve σπάνιος/σπάνια/ασυνήθιστο, fix `"fro-"` and the Cyrillic `ка` key in `labels.ts` | 2 |

### Days 76–90 — Publish something defensible, then build the new thing

| # | Action | d |
|---|---|---|
| 31 | **Publish the evaluation.** P@1 with CI, any-analysis recall, Greeklish R@1, zero-result rate, per-stage latency — on `MethodologyPage`, next to the analytics claims. Model the page on DWDS `/d/plot`: every parameter, every formula, a prominent limitations section that admits register scope, the 2012/2014/2015 news gap and the 3.3× size step at 2019 | 3 |
| 32 | **Datasheet + Data Statement per corpus** (Gebru et al.; Bender & Friedman) — register description, sampling frame, gap declaration, token counts per slice. The project's pitch *is* documentation; this is product, not compliance | 3 |
| 33 | **Error-report loop** — a typed report button on collocations, corpus examples and domain chips (the DWDS «Ist Ihnen … ein Fehler aufgefallen?» modal, with categories). `query_log` + `/api/insights/queries` already exist and compute a resolution rate that is rendered nowhere. This is the cheapest path from "no evaluation" to a data flywheel | 2 |
| 34 | **Ship the etymological descent explorer** (§5.9) — invert `etymons`, add the F57 post-parse assertions, one endpoint, one page: descent trees, shared-ancestor discovery, loan-source map. The first genuinely new thing, on the cleanest data in the product | 5 |
| 35 | If §7.1 cleared it: **OntoLex-Lemon/lexicog export + checksummed snapshot + Croissant metadata** | 2 |

### What is deliberately *not* in the 90 days

The LLM explanation layer (§5.10), typed collocations via dependency parsing, sense-level
en→el, and any further statistical work on the diachronic axis. All four are good ideas.
None of them survives contact with a product whose flagship feature is unevaluated, whose
frequency counts sum to 1,026% of the corpus, and three quarters of whose entries are
surnames. Fix the foundation, publish the number, then build.

---

## Appendix — the three numbers to put on the wall

1. **105,640** — the real size of this dictionary. Stop saying 446,840.
2. **0.915 [0.896, 0.934]** — the only quality number the product has, produced by an
   audit rather than by the project. Make it reproducible, make it a CI gate, and publish it.
3. **33** — rows in `query_log`. The product has never read its own users.
