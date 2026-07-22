// Typed API client. All requests are origin-relative /api/* — Vite proxies them
// to the backend on :8011 in dev (see vite.config.ts).
import type {
  AttributionsResponse,
  BuildStatusResponse,
  ByFieldResponse,
  CompareResponse,
  DiachronicResponse,
  DriftInsightsResponse,
  GraphResponse,
  HealthResponse,
  InterestingResponse,
  OverviewResponse,
  SearchResponse,
  TrendsResponse,
  WordResponse,
} from "./types";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} for ${path}`);
  }
  return (await res.json()) as T;
}

export function health(): Promise<HealthResponse> {
  return getJSON<HealthResponse>("/api/health");
}

export function buildStatus(): Promise<BuildStatusResponse> {
  return getJSON<BuildStatusResponse>("/api/build-status");
}

export function search(q: string, limit = 10): Promise<SearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  return getJSON<SearchResponse>(`/api/search?${params}`);
}

export function getWord(lemma: string): Promise<WordResponse> {
  return getJSON<WordResponse>(`/api/word/${encodeURIComponent(lemma)}`);
}

export function getGraph(lemma: string): Promise<GraphResponse> {
  return getJSON<GraphResponse>(`/api/word/${encodeURIComponent(lemma)}/graph`);
}

export function getDiachronic(lemma: string): Promise<DiachronicResponse> {
  return getJSON<DiachronicResponse>(`/api/word/${encodeURIComponent(lemma)}/diachronic`);
}

export function getDriftInsights(
  corpus = "parliament",
  limit = 30,
): Promise<DriftInsightsResponse> {
  const params = new URLSearchParams({ corpus, limit: String(limit) });
  return getJSON<DriftInsightsResponse>(`/api/insights/drift?${params}`);
}

// ── Exploration page ──
export function getExploreOverview(): Promise<OverviewResponse> {
  return getJSON<OverviewResponse>(`/api/explore/overview`);
}

export function getExploreInteresting(
  corpus = "parliament",
  limit = 25,
): Promise<InterestingResponse> {
  const params = new URLSearchParams({ corpus, limit: String(limit) });
  return getJSON<InterestingResponse>(`/api/explore/interesting?${params}`);
}

export function getExploreByField(
  corpus = "parliament",
  perField = 8,
): Promise<ByFieldResponse> {
  const params = new URLSearchParams({ corpus, per_field: String(perField) });
  return getJSON<ByFieldResponse>(`/api/explore/by-field?${params}`);
}

export function getExploreTrends(
  corpus = "parliament",
  limit = 20,
): Promise<TrendsResponse> {
  const params = new URLSearchParams({ corpus, limit: String(limit) });
  return getJSON<TrendsResponse>(`/api/explore/trends?${params}`);
}

export function getExploreCompare(): Promise<CompareResponse> {
  return getJSON<CompareResponse>(`/api/explore/compare`);
}

export function getAttributions(): Promise<AttributionsResponse> {
  return getJSON<AttributionsResponse>("/api/attributions");
}
