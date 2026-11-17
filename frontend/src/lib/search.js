// The same search the API does, run in the browser over the whole dataset.
//
// Why this exists: GitHub Pages cannot run Python. Without a local search the
// published site would be dead whenever the API is not deployed or is asleep
// on a free tier -- and the one link being graded is the one that must always
// work. With it, the page is live from a static host alone, and the API is an
// upgrade switched on by setting VITE_API_BASE.
//
// This is deliberately a second implementation of logic that already exists in
// backend/api/main.py, which is a real cost: two places to change. It is worth
// it here because the contract is small and frozen -- same parameters in, same
// response shape out -- so `useJobs` and every component cannot tell which one
// answered. If the two ever disagree, main.py is the source of truth.

const SNIPPET_CHARS = 300;

function timeOf(job) {
  // Cached on the object the first time, because sorting re-reads it.
  if (job._ts === undefined) {
    const ms = Date.parse(job.posted_at);
    job._ts = Number.isNaN(ms) ? null : ms;
  }
  return job._ts;
}

function haystackOf(job) {
  if (job._haystack === undefined) {
    job._haystack = [job.title, job.company, job.raw_location]
      .map((v) => v || "")
      .join(" ")
      .toLowerCase();
  }
  return job._haystack;
}

function matches(job, words, role, city, source, since) {
  if (role && job.role !== role) return false;
  if (city && job.city !== city) return false;
  if (source && job.source !== source) return false;
  if (since !== null) {
    const ts = timeOf(job);
    if (ts === null || ts < since) return false;
  }
  if (words.length) {
    const hay = haystackOf(job);
    return words.every((word) => hay.includes(word));
  }
  return true;
}

function counts(jobs, field) {
  const out = new Map();
  for (const job of jobs) {
    const value = job[field];
    if (value) out.set(value, (out.get(value) || 0) + 1);
  }
  // Biggest first, then alphabetical, matching the API.
  return Object.fromEntries([...out.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
}

const SORTS = {
  recent: (a, b) => (timeOf(b) ?? -Infinity) - (timeOf(a) ?? -Infinity),
  oldest: (a, b) => (timeOf(a) ?? Infinity) - (timeOf(b) ?? Infinity),
  company: (a, b) =>
    (a.company || "").localeCompare(b.company || "") || (a.title || "").localeCompare(b.title || ""),
  title: (a, b) =>
    (a.title || "").localeCompare(b.title || "") || (a.company || "").localeCompare(b.company || ""),
};

// Strip the fields we cached on the object and trim the description, so a
// locally-searched job looks exactly like one that came back from the API.
function publicJob(job, full = false) {
  const out = {};
  for (const [key, value] of Object.entries(job)) {
    if (!key.startsWith("_")) out[key] = value;
  }
  const description = out.description || "";
  if (!full && description.length > SNIPPET_CHARS) {
    out.description = `${description.slice(0, SNIPPET_CHARS).trimEnd()}...`;
    out.truncated = true;
  }
  return out;
}

export function searchLocal(jobs, params, lastRefreshed) {
  const words = String(params.q || "")
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);

  const role = params.role || "";
  const city = params.city || "";
  const source = params.source || "";
  const days = Number(params.posted_within_days) || 0;
  const since = days ? Date.now() - days * 86400000 : null;

  const pageSize = Number(params.page_size) || 24;
  const page = Math.max(1, Number(params.page) || 1);

  const base = jobs.filter((j) => matches(j, words, "", "", "", since));
  const results = base.filter((j) => matches(j, [], role, city, source, null));
  results.sort(SORTS[params.sort] || SORTS.recent);

  const start = (page - 1) * pageSize;

  return {
    total: results.length,
    page,
    page_size: pageSize,
    pages: Math.max(1, Math.ceil(results.length / pageSize)),
    total_unfiltered: jobs.length,
    jobs: results.slice(start, start + pageSize).map((j) => publicJob(j)),
    facets: {
      roles: counts(base.filter((j) => matches(j, [], "", city, source, null)), "role"),
      cities: counts(base.filter((j) => matches(j, [], role, "", source, null)), "city"),
      sources: counts(base.filter((j) => matches(j, [], role, city, "", null)), "source"),
    },
    last_refreshed: lastRefreshed || null,
  };
}

export function findLocal(jobs, id) {
  const job = jobs.find((j) => j.id === id);
  if (!job) throw new Error("no job with that id");
  return publicJob(job, true);
}
