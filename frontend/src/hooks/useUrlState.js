import { useCallback, useState } from "react";

// The URL is the state.
//
// Filters live in the query string, so a search can be bookmarked, shared and
// reloaded. This is the single biggest difference between "a page with filters
// on it" and something that behaves like a real job site, and it costs about
// thirty lines.

export const BLANK = {
  q: "",
  role: "",
  city: "",
  source: "",
  within: "0",
  sort: "recent",
  page: 1,
};

export function readUrl() {
  const p = new URLSearchParams(window.location.search);
  return {
    q: p.get("q") || "",
    role: p.get("role") || "",
    city: p.get("city") || "",
    source: p.get("source") || "",
    within: p.get("within") || "0",
    sort: p.get("sort") || "recent",
    page: Math.max(1, Number(p.get("page")) || 1),
  };
}

function writeUrl(filters) {
  const p = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    // Leave defaults out, so a plain search gives a clean shareable URL.
    if (value && value !== BLANK[key]) p.set(key, String(value));
  }
  const qs = p.toString();
  // replaceState, not pushState: typing in the search box would otherwise add
  // a history entry per keystroke and make the back button useless.
  window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
}

export function useUrlState() {
  const [filters, setFilters] = useState(readUrl);

  // Any change except a page change goes back to page 1, because staying on
  // page 7 of a search that now has two results is confusing.
  const update = useCallback((patch) => {
    setFilters((previous) => {
      const next = { ...previous, page: 1, ...patch };
      writeUrl(next);
      return next;
    });
  }, []);

  const goToPage = useCallback((page) => {
    setFilters((previous) => {
      const next = { ...previous, page };
      writeUrl(next);
      return next;
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const reset = useCallback(() => {
    writeUrl(BLANK);
    setFilters({ ...BLANK });
  }, []);

  return { filters, update, goToPage, reset };
}
