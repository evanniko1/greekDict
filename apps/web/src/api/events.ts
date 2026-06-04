// Curated historical-events timeline overlaid on the frequency-over-time charts.
//
// IMPORTANT — framing: these markers are CONTEXT, not causation. A usage shift
// that lines up with an event is a prompt for interpretation, not proof the event
// caused it. The list is deliberately small and limited to widely-agreed, dated
// public events that plausibly touch public/Greek political-news vocabulary. It is
// hand-curated (no source dump) and easy to extend.

export interface HistoryEvent {
  year: number;
  el: string; // short Greek label (shown)
  en: string; // English gloss (tooltip / methodology page)
}

// Sorted by year. Spans both corpus axes (parliament 1989–2020, news 2011–2024);
// each chart only renders the events that fall inside its own year range.
export const HISTORY_EVENTS: HistoryEvent[] = [
  { year: 2001, el: "Ένταξη στην Ευρωζώνη", en: "Greece joins the eurozone" },
  { year: 2002, el: "Κυκλοφορία του ευρώ", en: "Euro enters circulation" },
  { year: 2004, el: "Ολυμπιακοί Αγώνες Αθήνας", en: "Athens Olympic Games" },
  { year: 2008, el: "Παγκόσμια χρηματοπιστωτική κρίση", en: "Global financial crisis" },
  { year: 2010, el: "1ο Μνημόνιο / ΔΝΤ", en: "First bailout memorandum (IMF/EU)" },
  { year: 2012, el: "PSI — αναδιάρθρωση χρέους", en: "PSI sovereign-debt restructuring" },
  { year: 2015, el: "Δημοψήφισμα & capital controls", en: "Bailout referendum & capital controls" },
  { year: 2018, el: "Λήξη μνημονίων · Συμφωνία Πρεσπών", en: "End of bailouts · Prespa Agreement" },
  { year: 2020, el: "Πανδημία COVID-19", en: "COVID-19 pandemic" },
  { year: 2022, el: "Ενεργειακή κρίση & πληθωρισμός", en: "Energy crisis & inflation" },
];

// Events whose year falls within [first, last] (inclusive). Used by the charts to
// avoid drawing markers outside a corpus's covered span.
export function eventsInRange(first: number | null, last: number | null): HistoryEvent[] {
  if (first == null || last == null) return [];
  const lo = Math.min(first, last), hi = Math.max(first, last);
  return HISTORY_EVENTS.filter((e) => e.year >= lo && e.year <= hi);
}
