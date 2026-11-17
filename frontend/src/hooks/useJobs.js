import { useEffect, useState } from "react";

import { fetchJobs } from "../lib/api.js";

// Fetches a page of results whenever the filters change.
//
// Two details that matter more than they look:
//
// 1. Every request is abortable. Responses can arrive out of order, so a slow
//    request for "dev" could land after the fast one for "devops" and
//    overwrite the right results with the wrong ones. Aborting the previous
//    request makes that impossible rather than unlikely.
//
// 2. The previous results stay in state while the next page loads. The UI dims
//    them instead of emptying the grid, so the layout never jumps mid-typing.

export function useJobs(filters, { skip = false } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(!skip);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (skip) return undefined;

    const controller = new AbortController();
    setLoading(true);

    fetchJobs(filters, controller.signal)
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch((e) => {
        // Keep the Error itself, not just its text: App needs e.status to
        // tell an expired session (401) apart from a broken server.
        if (e.name !== "AbortError") setError(e);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [filters, skip]);

  return { data, loading, error };
}
