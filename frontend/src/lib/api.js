import { findLocal, searchLocal } from "./search.js";

// One contract, two implementations.
//
//   VITE_API_BASE set   -> talk to the Python API over HTTP
//   not set             -> load data/jobs.json once and search it in-browser
//
// Both return the identical response shape, so hooks and components never
// learn which one answered. That is the whole point: the published site works
// on a static host with no server, and switching the real API on is one
// environment variable, not a rewrite.
//
// Locally `npm run dev` uses "/api", which vite.config.js proxies to port
// 8000, so development is always against the real API.
const CONFIGURED = import.meta.env.VITE_API_BASE;
const IS_DEV = import.meta.env.DEV;

const BASE = (CONFIGURED || (IS_DEV ? "/api" : "")).replace(/\/+$/, "");
export const USING_API = Boolean(BASE);

export const PAGE_SIZE = 24;

// The Google ID token, kept here so no component has to thread it through
// every call. useAuth keeps this in step with the session.
let authToken = null;

export function setAuthToken(token) {
  authToken = token || null;
}

// Where the static build finds the pipeline's output. Relative, because the
// site is served from a /<repo>/ path on GitHub Pages.
const LOCAL_JOBS = "data/jobs.json";
const LOCAL_META = "data/run_meta.json";

// ---------------------------------------------------------------- HTTP mode

function url(path, params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    // Skip empty values so the URL stays readable and the server keeps its
    // own defaults rather than being handed a blank string.
    if (value !== "" && value !== null && value !== undefined && value !== 0) {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return `${BASE}${path}${qs ? `?${qs}` : ""}`;
}

async function getJson(target, signal) {
  const headers = authToken ? { Authorization: `Bearer ${authToken}` } : undefined;
  const response = await fetch(target, { signal, headers });
  if (!response.ok) {
    // The API sends {"detail": "..."} on an error. Surface that text if it is
    // there, because "data/jobs.json is missing, run the pipeline" is a far
    // more useful message than "503".
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // Not JSON. Keep the status line.
    }
    const error = new Error(detail);
    // Carried so the caller can tell "your session ended" apart from "the
    // server is broken", and sign the user out instead of showing an error.
    error.status = response.status;
    throw error;
  }
  return response.json();
}

// Whether the API itself demands a signed-in caller. Served unauthenticated so
// the login screen can load before anyone has a token.
export function fetchAuthConfig(signal) {
  if (!USING_API) return Promise.resolve({ configured: false, required: false });
  return getJson(`${BASE}/auth/config`, signal);
}

// ---------------------------------------------------------------- local mode

// The dataset is fetched once and reused. A promise rather than the data, so
// several components asking at the same moment share one request instead of
// starting three.
let localPromise = null;

function loadLocal() {
  if (!localPromise) {
    localPromise = Promise.all([
      getJson(LOCAL_JOBS),
      // run_meta is nice to have; a missing one must not break the page.
      getJson(LOCAL_META).catch(() => null),
    ]).then(([jobs, meta]) => ({ jobs, meta }));

    // Do not cache a failure: a reload would otherwise keep returning it.
    localPromise.catch(() => {
      localPromise = null;
    });
  }
  return localPromise;
}

// ---------------------------------------------------------------- public API

function params(filters) {
  return {
    q: filters.q,
    role: filters.role,
    city: filters.city,
    source: filters.source,
    posted_within_days: Number(filters.within) || 0,
    sort: filters.sort,
    page: filters.page,
    page_size: PAGE_SIZE,
  };
}

export async function fetchJobs(filters, signal) {
  if (USING_API) return getJson(url("/jobs", params(filters)), signal);

  const { jobs, meta } = await loadLocal();
  return searchLocal(jobs, params(filters), meta?.last_refreshed);
}

export async function fetchJob(id, signal) {
  if (USING_API) return getJson(url(`/jobs/${encodeURIComponent(id)}`, {}), signal);

  const { jobs } = await loadLocal();
  return findLocal(jobs, id);
}

export async function fetchMeta(signal) {
  if (USING_API) return getJson(url("/meta", {}), signal);

  const { meta } = await loadLocal();
  return meta || {};
}
