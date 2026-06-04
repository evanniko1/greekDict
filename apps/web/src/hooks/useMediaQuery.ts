import { useEffect, useState } from "react";

// Subscribe to a CSS media query. Used to switch between the mobile (tabbed)
// and desktop (stacked) word-page layouts in JS, so the heavy Cytoscape graph
// mounts exactly once — never inside a display:none container (where it would
// size to 0×0) and never twice.
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() =>
    typeof window !== "undefined" ? window.matchMedia(query).matches : false,
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
