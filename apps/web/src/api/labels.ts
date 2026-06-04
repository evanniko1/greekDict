// Greek display labels for backend enum-ish values (pos, gender, match_type,
// relation_type). The DB stores Wiktionary's English tags; this is a pure
// presentation layer — keys stay English, only the displayed text is Greek.
// Unknown values fall back to the raw value so nothing silently disappears.

const POS_EL: Record<string, string> = {
  noun: "ουσιαστικό",
  "proper noun": "κύριο όνομα",
  verb: "ρήμα",
  adjective: "επίθετο",
  adverb: "επίρρημα",
  pronoun: "αντωνυμία",
  preposition: "πρόθεση",
  conjunction: "σύνδεσμος",
  article: "άρθρο",
  determiner: "προσδιοριστής",
  numeral: "αριθμητικό",
  particle: "μόριο",
  interjection: "επιφώνημα",
  prefix: "πρόθημα",
  suffix: "επίθημα",
  phrase: "φράση",
  proverb: "παροιμία",
  name: "κύριο όνομα",
  romanization: "λατινική γραφή",
};

const GENDER_EL: Record<string, string> = {
  masculine: "αρσενικό",
  feminine: "θηλυκό",
  neuter: "ουδέτερο",
  common: "κοινού γένους",
};

const MATCH_EL: Record<string, string> = {
  lemma: "λήμμα",
  inflected_form: "κλιτός τύπος",
  greeklish: "γκρίκλις",
  translation: "μετάφραση",
};

// Grammatical features/tags carried on senses (s.tags) and forms (f.features):
// case, number, gender, tense, mood, voice, person, degree, register. These
// are Wiktionary's English grammar labels; translate the common ones.
const GRAM_EL: Record<string, string> = {
  // gender
  masculine: "αρσενικό",
  feminine: "θηλυκό",
  neuter: "ουδέτερο",
  // number
  singular: "ενικός",
  plural: "πληθυντικός",
  // case
  nominative: "ονομαστική",
  genitive: "γενική",
  accusative: "αιτιατική",
  vocative: "κλητική",
  dative: "δοτική",
  // tense / aspect
  present: "ενεστώτας",
  past: "παρελθόν",
  future: "μέλλοντας",
  imperfect: "παρατατικός",
  aorist: "αόριστος",
  perfect: "παρακείμενος",
  pluperfect: "υπερσυντέλικος",
  perfective: "συνοπτικός",
  imperfective: "εξακολουθητικός",
  // mood / voice
  indicative: "οριστική",
  subjunctive: "υποτακτική",
  imperative: "προστακτική",
  dependent: "εξαρτημένος",
  active: "ενεργητική",
  passive: "παθητική",
  // non-finite / extra aspect tags (mostly land in "Άλλοι τύποι")
  participle: "μετοχή",
  infinitive: "απαρέμφατο",
  "infinitive-aorist": "απαρέμφατο αορίστου",
  gerund: "γερούνδιο",
  progressive: "εξακολουθητικός",
  continuative: "εξακολουθητικός",
  // person
  "first-person": "α' πρόσωπο",
  "second-person": "β' πρόσωπο",
  "third-person": "γ' πρόσωπο",
  // degree
  comparative: "συγκριτικός",
  superlative: "υπερθετικός",
  // register / usage
  formal: "επίσημο",
  informal: "ανεπίσημο",
  colloquial: "καθομιλουμένη",
  figurative: "μεταφορικά",
  literally: "κυριολεκτικά",
  archaic: "αρχαϊσμός",
  obsolete: "απαρχαιωμένο",
  slang: "αργκό",
  vulgar: "χυδαίο",
  transitive: "μεταβατικό",
  intransitive: "αμετάβατο",
  diminutive: "υποκοριστικό",
  augmentative: "μεγεθυντικό",
  romanization: "λατινική γραφή",
  romanized: "λατινική γραφή",
  canonical: "λήμμα",
  rare: "σπάνιος",

  // verb/noun inflection classes (Wiktionary type-a/type-b ≈ Greek συζυγίες)
  "type-a": "α' συζυγία",
  "type-b": "β' συζυγία",
  // declinability
  indeclinable: "άκλιτο",
  invariable: "άκλιτο",
  defective: "ελλειπτικό",
  deponent: "αποθετικό",
  // number specials
  dual: "δυϊκός",
  "plural-only": "μόνο στον πληθυντικό",
  "singular-only": "μόνο στον ενικό",
  "plural-normally": "συνήθως στον πληθυντικό",
  "in-plural": "στον πληθυντικό",
  uncountable: "μη μετρήσιμο",
  countable: "μετρήσιμο",
  distributive: "διανεμητικό",
  // clitic pronoun strength (δυνατός / αδύνατος τύπος)
  strong: "δυνατός τύπος",
  weak: "αδύνατος τύπος",
  // determination
  definite: "οριστικό",
  indefinite: "αόριστο",
  absolute: "απόλυτο",
  possessive: "κτητικό",
  personal: "προσωπικό",
  relational: "σχεσιακό",
  // orthography / form variants
  alternative: "εναλλακτικός τύπος",
  "alt-of": "εναλλακτικός τύπος",
  variant: "παραλλαγή",
  "short-form": "σύντομος τύπος",
  contraction: "συναίρεση",
  "before-vowel": "προ φωνήεντος",
  lowercase: "πεζά",
  uppercase: "κεφαλαία",
  abbreviation: "συντομογραφία",
  initialism: "αρκτικόλεξο",
  acronym: "ακρωνύμιο",
  numeral: "αριθμητικό",
  letter: "γράμμα",
  morpheme: "μόρφημα",
  misspelling: "ανορθογραφία",
  "error-unrecognized-form": "μη αναγνωρισμένος τύπος",
  // scripts / transliteration
  transliteration: "μεταγραφή",
  latin: "λατινικό",
  cyrillic: "κυριλλικό",
  calque: "μεταφραστικό δάνειο",
  // language registers / historical strata
  katharevousa: "καθαρεύουσα",
  demotic: "δημοτική",
  koine: "κοινή",
  vernacular: "καθομιλουμένη",
  standard: "πρότυπο",
  nonstandard: "μη πρότυπο",
  dialectal: "διαλεκτικό",
  regional: "τοπικό",
  dated: "παρωχημένο",
  historical: "ιστορικό",
  uncommon: "ασυνήθιστο",
  idiomatic: "ιδιωματικό",
  // syntactic government
  "with-accusative": "με αιτιατική",
  "with-nominative": "με ονομαστική",
  "with-genitive": "με γενική",
  "without-noun": "χωρίς ουσιαστικό",
  transitive_intransitive: "μεταβατικό/αμετάβατο",
  "no-past": "χωρίς παρελθοντικό τύπο",
  // pragmatics / register extras
  figuratively: "μεταφορικά",
  offensive: "προσβλητικό",
  derogatory: "υποτιμητικό",
  ironic: "ειρωνικό",
  humorous: "χιουμοριστικό",
  poetic: "ποιητικό",
  neologism: "νεολογισμός",
  familiar: "οικείο",
  broadly: "ευρέως",
  especially: "ειδικά",
  demonym: "εθνώνυμο",
};

// Subject/domain labels carried on senses (from Wiktionary `topics`, merged into
// s.tags at ingest). Distinct from register: these say WHICH FIELD a sense belongs
// to (medicine, law…). Unknown domains fall back to the raw value.
const DOMAIN_EL: Record<string, string> = {
  medicine: "ιατρική",
  anatomy: "ανατομία",
  biology: "βιολογία",
  biochemistry: "βιοχημεία",
  botany: "βοτανική",
  zoology: "ζωολογία",
  chemistry: "χημεία",
  physics: "φυσική",
  engineering: "μηχανική",
  sciences: "επιστήμες",
  "natural-sciences": "φυσικές επιστήμες",
  "physical-sciences": "θετικές επιστήμες",
  "human-sciences": "ανθρωπιστικές επιστήμες",
  "social-sciences": "κοινωνικές επιστήμες",
  mathematics: "μαθηματικά",
  geometry: "γεωμετρία",
  astronomy: "αστρονομία",
  computing: "πληροφορική",
  technology: "τεχνολογία",
  law: "νομική",
  business: "οικονομία",
  economics: "οικονομία",
  finance: "οικονομικά",
  politics: "πολιτική",
  government: "διακυβέρνηση",
  lifestyle: "καθημερινή ζωή",
  military: "στρατιωτικός όρος",
  nautical: "ναυτικός όρος",
  religion: "θρησκεία",
  christianity: "χριστιανισμός",
  mythology: "μυθολογία",
  philosophy: "φιλοσοφία",
  history: "ιστορία",
  geography: "γεωγραφία",
  grammar: "γραμματική",
  linguistics: "γλωσσολογία",
  language: "γλώσσα",
  music: "μουσική",
  art: "τέχνη",
  architecture: "αρχιτεκτονική",
  clothing: "ένδυση",
  food: "φαγητό",
  cooking: "μαγειρική",
  athletics: "αθλητισμός",
  sports: "αθλητισμός",
  meteorology: "μετεωρολογία",
  mammals: "θηλαστικά",
  insects: "έντομα",
  fish: "ψάρια",
  birds: "πτηνά",
  vegetable: "λαχανικά",
  countries: "χώρες",
  greek: "ελληνικά",
};

// Register / period / dialect labels — the "how/when is this used" tags. Display
// text reuses GRAM_EL (which already carries these). This Set drives classification
// so they render as prominent usage chips rather than muted grammar tags.
const USAGE_KEYS = new Set([
  "figuratively", "figurative", "literally", "broadly", "especially",
  "formal", "informal", "colloquial", "familiar", "vulgar", "offensive",
  "derogatory", "disapproving", "ironic", "humorous", "euphemistic", "poetic",
  "literary", "slang", "idiomatic", "proverbial",
  "dated", "archaic", "obsolete", "historical", "rare", "uncommon", "neologism",
  "katharevousa", "koine", "hellenistic", "demotic", "vernacular",
  "dialectal", "regional", "cypriot", "cretan", "pontic",
  "nonstandard", "proscribed",
]);

// A few grammatical tags that are genuinely informative on a sense (verb
// government / countability). The rest (case, number, gender, person) are
// inflectional noise on senses and are hidden — they live in the Κλίση tables.
const USEFUL_GRAM_KEYS = new Set([
  "transitive", "intransitive", "impersonal", "reflexive", "pronominal",
  "countable", "uncountable", "auxiliary", "copulative",
]);

const DIALECT_USAGE_EL: Record<string, string> = {
  cypriot: "κυπριακό",
  cretan: "κρητικό",
  pontic: "ποντιακό",
  hellenistic: "ελληνιστικό",
  proverbial: "παροιμιακό",
  literary: "λόγιο",
  disapproving: "αποδοκιμαστικό",
  euphemistic: "ευφημισμός",
  proscribed: "αποδοκιμαζόμενο",
  reflexive: "αυτοπαθές",
  pronominal: "μεσοπαθητικό",
  auxiliary: "βοηθητικό",
  copulative: "συνδετικό",
};

// Frequency band → Greek display label + an integer level (0..4) for the meter.
const FREQ_BAND_EL: Record<string, string> = {
  very_common: "πολύ συχνή",
  common: "συχνή",
  moderate: "μέτρια συχνότητα",
  uncommon: "σπάνια",
  rare: "πολύ σπάνια",
};
const FREQ_BAND_LEVEL: Record<string, number> = {
  very_common: 5,
  common: 4,
  moderate: 3,
  uncommon: 2,
  rare: 1,
};

const REL_EL: Record<string, string> = {
  synonym: "συνώνυμο",
  antonym: "αντώνυμο",
  related: "σχετικό",
  derived: "παράγωγο",
  hypernym: "υπερώνυμο",
  hyponym: "υπώνυμο",
  current: "λήμμα",
  // etymological origin edges (short labels for the graph legend)
  inherited: "κληρονομιά",
  borrowed: "δάνειο",
  calque: "μεταφρ. δάνειο",
  cognate: "συγγενές",
};

// Full-sentence etymology relation labels for the word page (e.g. "δάνειο από").
const ETY_REL_EL: Record<string, string> = {
  inherited: "κληρονομήθηκε από",
  derived: "παράγεται από",
  borrowed: "δάνειο από",
  calque: "μεταφραστικό δάνειο από",
  cognate: "συγγενές με",
};

// Source-language codes (Wiktionary/ISO + proto-language codes) → Greek names.
const LANG_EL: Record<string, string> = {
  el: "νέα ελληνικά",
  grc: "αρχαία ελληνικά",
  "grc-koi": "ελληνιστική κοινή",
  gkm: "μεσαιωνική ελληνική",
  "gkm-cyp": "μεσαιωνική κυπριακή",
  "grc-dor": "δωρική",
  "grc-att": "αττική",
  "grc-ion": "ιωνική",
  "grc-aeo": "αιολική",
  "ine-pro": "πρωτοϊνδοευρωπαϊκή",
  "grk-pro": "πρωτοελληνική",
  la: "λατινικά",
  "la-lat": "ύστερη λατινική",
  "la-med": "μεσαιωνική λατινική",
  "la-vul": "δημώδης λατινική",
  it: "ιταλικά",
  "roa-oit": "παλαιά ιταλικά",
  vec: "βενετικά",
  fr: "γαλλικά",
  "fro-": "παλαιά γαλλικά",
  es: "ισπανικά",
  pt: "πορτογαλικά",
  tr: "τουρκικά",
  ota: "οθωμανικά τουρκικά",
  ar: "αραβικά",
  fa: "περσικά",
  he: "εβραϊκά",
  en: "αγγλικά",
  de: "γερμανικά",
  nl: "ολλανδικά",
  ru: "ρωσικά",
  "sla-pro": "πρωτοσλαβική",
  bg: "βουλγαρικά",
  sh: "σερβοκροατικά",
  sq: "αλβανικά",
  hy: "αρμενικά",
  xcl: "κλασική αρμενική",
  sa: "σανσκριτικά",
  "iir-pro": "πρωτοϊνδοϊρανική",
  hbo: "βιβλική εβραϊκά",
  arc: "αραμαϊκά",
  cop: "κοπτικά",
  egy: "αιγυπτιακά",
  ка: "γεωργιανά",
  ka: "γεωργιανά",
  mk: "σλαβομακεδονικά",
  ro: "ρουμανικά",
  pl: "πολωνικά",
  uk: "ουκρανικά",
  yi: "γίντις",
  ja: "ιαπωνικά",
  zh: "κινεζικά",
  hi: "χίντι",
  ur: "ουρντού",
};

const lookup = (table: Record<string, string>, value: string): string =>
  table[value.trim().toLowerCase()] ?? value;

export const posEl = (v: string): string => lookup(POS_EL, v);
export const genderEl = (v: string): string => lookup(GENDER_EL, v);
export const matchEl = (v: string): string => lookup(MATCH_EL, v);
export const relEl = (v: string): string => lookup(REL_EL, v);
export const gramEl = (v: string): string => lookup(GRAM_EL, v);
export const etyRelEl = (v: string): string => lookup(ETY_REL_EL, v);
export const langEl = (v: string): string => lookup(LANG_EL, v);

export const domainEl = (v: string): string => lookup(DOMAIN_EL, v);
export const freqBandEl = (v: string): string => lookup(FREQ_BAND_EL, v);
export const freqBandLevel = (v: string): number => FREQ_BAND_LEVEL[v.trim().toLowerCase()] ?? 0;
// Usage label display: dialect/extra map first, then the shared grammar/register map.
export const usageEl = (v: string): string => {
  const k = v.trim().toLowerCase();
  return DIALECT_USAGE_EL[k] ?? GRAM_EL[k] ?? v;
};

export interface ClassifiedTags {
  usage: string[]; // register / period / dialect — prominent chips
  domain: string[]; // subject field — secondary-coloured chips
  grammar: string[]; // useful grammatical tags only (verb government, countability)
}

// Split a sense's flat tag list into the three display buckets. Pure inflectional
// tags (case/number/gender/person) are dropped — they belong to the Κλίση tables,
// not to a sense's usage. Order within each bucket follows the source order.
export function classifyTags(tags: string[]): ClassifiedTags {
  const usage: string[] = [];
  const domain: string[] = [];
  const grammar: string[] = [];
  const seen = new Set<string>();
  for (const raw of tags) {
    const k = raw.trim().toLowerCase();
    if (!k || k === "no-gloss" || seen.has(k)) continue;
    seen.add(k);
    if (USAGE_KEYS.has(k)) usage.push(k);
    else if (k in DOMAIN_EL) domain.push(k);
    else if (USEFUL_GRAM_KEYS.has(k)) grammar.push(k);
    // else: inflectional / structural tag — intentionally hidden here.
  }
  return { usage, domain, grammar };
}
