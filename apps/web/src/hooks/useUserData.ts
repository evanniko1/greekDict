// Client-only personalization: saved words + recent-search history.
//
// Deliberately frontend-only — no account, no server round-trip. Everything
// lives in localStorage and stays on the device, which keeps the privacy story
// simple (we already log anonymous query misses server-side for the flywheel;
// this is the *user's* private list, so it never leaves the browser).
//
// A tiny module-level store backed by `useSyncExternalStore` gives every mounted
// component a consistent, reactive view: saving a word on the word page lights up
// the same chip on the search landing without prop-drilling or context. Cross-tab
// edits sync through the native `storage` event.

import { useSyncExternalStore } from "react";

const SAVED_KEY = "lexorama.saved.v1";
const RECENT_KEY = "lexorama.recent.v1";
const RECENT_CAP = 12; // recent searches are a convenience, not an archive
const SAVED_CAP = 300; // generous, but bounded so localStorage can't grow forever

function parse(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return []; // corrupt / hand-edited storage → treat as empty, never throw
  }
}

const hasLS = typeof localStorage !== "undefined";

// In-memory caches are the source of truth for snapshots. useSyncExternalStore
// requires getSnapshot to return a STABLE reference between emits, so we never
// re-read+re-parse localStorage inside getSnapshot — we mutate these caches.
let savedCache: string[] = hasLS ? parse(localStorage.getItem(SAVED_KEY)) : [];
let recentCache: string[] = hasLS ? parse(localStorage.getItem(RECENT_KEY)) : [];

const listeners = new Set<() => void>();
function emit() {
  listeners.forEach((l) => l());
}
function subscribe(l: () => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

function persist(key: string, val: string[]) {
  if (!hasLS) return;
  try {
    localStorage.setItem(key, JSON.stringify(val));
  } catch {
    // Quota exceeded / Safari private mode — keep the in-memory list working
    // for the session rather than crashing the UI.
  }
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === SAVED_KEY) {
      savedCache = parse(e.newValue);
      emit();
    } else if (e.key === RECENT_KEY) {
      recentCache = parse(e.newValue);
      emit();
    }
  });
}

// --- saved words -----------------------------------------------------------

export function toggleSaved(lemma: string) {
  const w = lemma.trim();
  if (!w) return;
  savedCache = savedCache.includes(w)
    ? savedCache.filter((x) => x !== w)
    : [w, ...savedCache].slice(0, SAVED_CAP);
  persist(SAVED_KEY, savedCache);
  emit();
}

export function removeSaved(lemma: string) {
  if (!savedCache.includes(lemma)) return;
  savedCache = savedCache.filter((x) => x !== lemma);
  persist(SAVED_KEY, savedCache);
  emit();
}

export function useSavedWords(): string[] {
  return useSyncExternalStore(subscribe, () => savedCache, () => savedCache);
}

export function useIsSaved(lemma: string): boolean {
  // Primitive snapshot → stable by value; safe to recompute on every emit.
  return useSyncExternalStore(
    subscribe,
    () => savedCache.includes(lemma),
    () => false,
  );
}

// --- recent searches -------------------------------------------------------

export function recordRecent(term: string) {
  const t = term.trim();
  if (!t || recentCache[0] === t) return; // no-op if already at the top
  recentCache = [t, ...recentCache.filter((x) => x !== t)].slice(0, RECENT_CAP);
  persist(RECENT_KEY, recentCache);
  emit();
}

export function clearRecent() {
  if (recentCache.length === 0) return;
  recentCache = [];
  persist(RECENT_KEY, recentCache);
  emit();
}

export function useRecentSearches(): string[] {
  return useSyncExternalStore(subscribe, () => recentCache, () => recentCache);
}
