// Shared types mirroring the FastAPI payloads in services/api/app/main.py.

export type MatchType = "lemma" | "inflected_form" | "greeklish" | "translation";

export interface SearchResult {
  lemma_id: number;
  lemma: string;
  pos: string | null;
  gender: string | null;
  match_type: MatchType;
  matched_surface: string;
  features: string | null;
  explanation: string;
  via: string;
  score: number;
  snippet: string | null;
}

export interface SearchResponse {
  query: string;
  normalized: string;
  resolved: boolean;
  results: SearchResult[];
}

export interface Sense {
  index: number;
  gloss: string;
  tags: string[];
  examples: string[];
  source: string;
}

export interface WordForm {
  form: string;
  features: string[];
  source: string;
}

export interface Etymon {
  relation: string; // inherited | borrowed | derived | calque | cognate
  lang: string | null; // source-language code (grc, ine-pro, la…)
  term: string;
  source: string;
}

export interface Etymology {
  text: string;
  source: string;
}

export interface Pronunciation {
  ipa: string;
  source: string;
}

export interface FamilyTerm {
  term: string;
  resolved: boolean;
  source: string;
}

export interface FamilyGroup {
  relation: string; // synonym | antonym | derived | related | hypernym | hyponym
  terms: FamilyTerm[];
}

export interface Descendant {
  relation: string; // borrowed | inherited | calque | derived
  lang: string | null; // language code of the descendant
  lang_name: string | null; // display name from the dump
  term: string;
  roman: string | null;
  source: string;
}

// "Ομόρριζες λέξεις": another Modern-Greek lemma sharing an etymological
// ancestor with this one (derived from shared Wiktionary etymons).
export interface Cognate {
  term: string;
  shared_root: string; // the common ancestor term (e.g. grc χρῶμα, ine-pro *gʰrēw-)
  shared_lang: string | null; // ancestor language code
  resolved: boolean;
  source: string;
}

export interface Frequency {
  count: number;
  rank: number;
  zipf: number;
  band: string; // very_common | common | moderate | uncommon | rare
  source: string;
}

export interface Collocation {
  collocate: string;
  collocate_lemma_id: number | null; // links the chip to a word page when known
  score: number; // association strength (log-likelihood)
  source: string;
}

export interface CorpusExample {
  sentence: string; // an authentic corpus sentence using the lemma
  source: string;
}

export interface SemanticNeighbor {
  neighbor: string; // display lemma of a distributional near-synonym
  neighbor_lemma_id: number | null;
  score: number; // cosine similarity (0..1)
  source: string;
}

export interface WordEntry {
  lemma_id: number;
  lemma: string;
  pos: string | null;
  gender: string | null;
  sources: string[];
  pronunciations: Pronunciation[];
  family: FamilyGroup[];
  descendants: Descendant[];
  cognates: Cognate[];
  frequency: Frequency | null;
  collocations: Collocation[];
  examples: CorpusExample[];
  neighbors: SemanticNeighbor[];
  senses: Sense[];
  forms: WordForm[];
  etymology: Etymology | null;
  etymons: Etymon[];
}

export interface WordResponse {
  lemma: string;
  entries: WordEntry[];
}

// ── Diachronic (Layer B/C): one labeled series per corpus, never merged ──

export interface FreqPoint {
  year: number;
  per_million: number | null;
  count: number;
}

export interface DriftSummary {
  drift_score: number; // point estimate: bootstrap mean when available, else single-model (#50)
  first_year: number;
  last_year: number;
  n_slices: number;
  change_point_year: number | null; // steepest-step year, or null when not a clear outlier (#44)
  change_point_score?: number | null; // robust z of that step vs the others; kept even when suppressed (#44)
  // Endpoint-bootstrap 95% CI on the drift score + significance (#36). NULL until
  // bootstrap_drift.py has run for the corpus. `drift_significant` true when the
  // drift CI clears this word's own same-slice estimation-noise band.
  drift_ci_lo: number | null;
  drift_ci_hi: number | null;
  drift_significant: boolean | null;
}

// One point on the per-slice semantic trajectory (#35): cosine distance of the
// lemma's vector in that slice from the reference (first dense) slice. Exposes the
// SHAPE of change — a word that drifted then reverted shows a mid-series bump.
export interface TrajectoryPoint {
  year: number;
  distance_from_ref: number;
}

export interface EraNeighborItem {
  neighbor: string;
  neighbor_lemma_id: number | null;
  score: number;
}

export interface EraNeighbors {
  year: number;
  items: EraNeighborItem[];
}

export interface DiachronicSeries {
  corpus: string; // "parliament" | "news"
  frequency: FreqPoint[];
  drift: DriftSummary | null;
  trajectory: TrajectoryPoint[]; // per-slice distance from reference (#35)
  neighbors_then: EraNeighbors | null;
  neighbors_now: EraNeighbors | null;
}

export interface DiachronicResponse {
  lemma: string;
  lemma_id: number;
  series: DiachronicSeries[];
}

export interface DriftMover {
  lemma: string;
  lemma_id: number;
  drift_score: number;
  first_year: number;
  last_year: number;
}

export interface DriftInsightsResponse {
  corpus: string;
  movers: DriftMover[];
}

// ── Exploration page (/explore) ──
export interface OverviewPoint {
  year: number;
  tokens: number;
  types: number;
}

export interface CorpusOverview {
  corpus: string;
  points: OverviewPoint[];
  total_tokens: number;
  n_slices: number;
  first_year: number | null;
  last_year: number | null;
  drift_lemmas: number;
}

export interface OverviewResponse {
  corpora: CorpusOverview[];
}

// Neighbor-overlap mover (Gonen 2020): `change` = 1 − Jaccard(neighbors then, now).
export interface NeighborMover {
  lemma: string;
  lemma_id: number;
  change: number;
  first_year: number;
  last_year: number;
}

export interface InterestingResponse {
  corpus: string;
  min_pm: number;
  neighbor: NeighborMover[];
  freq_gated: DriftMover[];
}

// A field mover carries its domain provenance (#38): 'wiktionary-tag' = a clean
// Wiktionary topic tag (gold); 'classifier' = inferred by the supervised domain
// classifier, with domain_score the softmax confidence.
export interface FieldMover extends DriftMover {
  domain_source: "wiktionary-tag" | "classifier";
  domain_score: number | null;
}

export interface FieldGroup {
  field: string; // English domain key; map via labels.domainEl
  movers: FieldMover[];
  inferred_share: number; // 0..1 share of shown movers that are classifier-inferred
}

export interface ByFieldResponse {
  corpus: string;
  fields: FieldGroup[];
}

export interface TrendMover {
  lemma: string;
  lemma_id: number;
  slope: number;
  avg_pm: number;
  r2: number; // goodness-of-fit of the linear trend (0..1); gated server-side
  p_value: number; // two-sided OLS slope t-test p-value (#36)
  significant: boolean; // p_value < 0.05 — the tilt is distinguishable from zero
  first_year: number;
  last_year: number;
  first_pm: number | null;
  last_pm: number | null;
}

export interface TrendsResponse {
  corpus: string;
  rising: TrendMover[];
  falling: TrendMover[];
}

export interface DriftPair {
  lemma: string;
  lemma_id: number;
  parliament: number; // percentile rank (0..1) of drift within the parliament corpus
  news: number; // percentile rank (0..1) of drift within the news corpus
  parliament_drift: number; // raw cosine drift (tooltip only — not commensurable across corpora)
  news_drift: number;
}

export interface KeynessItem {
  lemma: string;
  lemma_id: number;
  log_ratio: number; // Hardie Log Ratio (effect size), log2 of the freq ratio (#46)
  log_ratio_ci_lo?: number; // 95% CI on the log ratio (#46)
  log_ratio_ci_hi?: number;
  g2?: number; // Dunning log-likelihood G² (significance, ~χ²₁; gated at p<0.001) (#46)
  pm_parliament: number;
  pm_news: number;
  dp_parliament?: number;
  dp_news?: number;
}

export interface CompareResponse {
  pairs: DriftPair[];
  keyness: {
    parliament: KeynessItem[];
    news: KeynessItem[];
  };
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  resolved: boolean;
  lemma_id: number | null;
  etymon?: boolean;
  lang?: string | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight: number;
  source_name: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface HealthResponse {
  ok: boolean;
  db: string;
  db_exists: boolean;
}

export interface SourceAttribution {
  source_name: string;
  source_url: string | null;
  license: string | null;
  attribution_text: string | null;
  retrieved_at: string | null;
}

export interface AttributionsResponse {
  attributions: SourceAttribution[];
}
