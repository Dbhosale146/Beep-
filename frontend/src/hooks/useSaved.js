import { useEffect, useState } from "react";

// Saved jobs, kept in the browser. No accounts, no server, no database.
//
// We store the whole job object rather than only its id, so the Saved tab
// renders straight from local storage with no network call -- it still works
// if the API is down, and a job that has since dropped out of the feed is
// still readable. The trade-off is that a saved card can go stale; the link
// out to the original posting is the source of truth.
const KEY = "beep.saved.v1";

function read() {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    // Private windows and blocked site data both throw here. An empty list is
    // the right answer: the feature degrades, the page still works.
    return [];
  }
}

export function useSaved() {
  const [saved, setSaved] = useState(read);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(saved));
    } catch {
      // Out of quota or storage disabled. Nothing useful to do.
    }
  }, [saved]);

  function isSaved(id) {
    return saved.some((job) => job.id === id);
  }

  function toggle(job) {
    setSaved((previous) =>
      previous.some((j) => j.id === job.id)
        ? previous.filter((j) => j.id !== job.id)
        : [job, ...previous],
    );
  }

  return { saved, isSaved, toggle };
}
