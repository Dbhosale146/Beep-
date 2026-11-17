import { useEffect, useMemo, useState } from "react";

import EmptyState from "./components/EmptyState.jsx";
import FilterBar from "./components/FilterBar.jsx";
import Header from "./components/Header.jsx";
import JobCard from "./components/JobCard.jsx";
import LoginPage from "./components/LoginPage.jsx";
import JobPanel from "./components/JobPanel.jsx";
import Pagination from "./components/Pagination.jsx";
import ProgressBar from "./components/ProgressBar.jsx";
import SearchBar from "./components/SearchBar.jsx";
import SkeletonGrid from "./components/SkeletonGrid.jsx";
import UserChip from "./components/UserChip.jsx";
import { useAuth } from "./hooks/useAuth.js";
import { useJobs } from "./hooks/useJobs.js";
import { useSaved } from "./hooks/useSaved.js";
import { readUrl, useUrlState } from "./hooks/useUrlState.js";
import { fetchMeta, PAGE_SIZE } from "./lib/api.js";

// App holds the state and composes the pieces. Everything that renders lives
// in components/, everything that fetches or persists lives in hooks/, so this
// file stays a readable outline of how the page behaves.
export default function App() {
  const { filters, update, goToPage, reset } = useUrlState();

  // The raw input value is separate from filters.q so typing stays instant
  // while the request that actually goes out is debounced below.
  const [search, setSearch] = useState(() => readUrl().q);
  const [tab, setTab] = useState("all");
  const [openId, setOpenId] = useState(null);
  const [meta, setMeta] = useState(null);

  const { saved, isSaved, toggle } = useSaved();

  const auth = useAuth();
  // Escape hatch for the case where Google Sign-In has not been configured
  // yet: without it an unconfigured deploy would be a locked door with no key,
  // and the published site would show nothing at all.
  const [bypass, setBypass] = useState(false);
  const unlocked = auth.signedIn || bypass;

  // The Saved tab renders from local storage, so skip the request entirely.
  const { data, loading, error } = useJobs(filters, {
    skip: tab === "saved" || !unlocked,
  });

  // An expired token is not an error to show the user -- it just means the
  // session is over, so drop them back to the login screen.
  useEffect(() => {
    if (error?.status === 401) auth.signOut();
  }, [error, auth.signOut]);

  // Debounce the search box: wait until typing pauses for 300ms before asking
  // the server. Without this, "developer" is nine requests.
  useEffect(() => {
    if (search === filters.q) return undefined;
    const timer = setTimeout(() => update({ q: search }), 300);
    return () => clearTimeout(timer);
  }, [search, filters.q, update]);

  // Run metadata is nice to have, not essential, so a failure here must not
  // take the page down with it.
  //
  // Gated on `unlocked` deliberately. In static mode fetchMeta shares its
  // loader with the job data, so calling it before sign-in would pull the
  // whole dataset down behind the login wall -- the board would be hidden
  // while the network tab showed every job. Nothing is requested until the
  // gate opens.
  useEffect(() => {
    if (!unlocked) return;
    fetchMeta()
      .then(setMeta)
      .catch(() => setMeta(null));
  }, [unlocked]);

  const anyActive = Boolean(
    filters.q || filters.role || filters.city || filters.source || filters.within !== "0",
  );

  function clearAll() {
    setSearch("");
    reset();
  }

  const jobs = tab === "saved" ? saved : data?.jobs || [];

  // Remounting the grid replays the entrance animation, so a new page or a new
  // filter animates in rather than silently swapping contents. Without the
  // key, React would reuse the existing card elements and nothing would move.
  const gridKey = useMemo(
    () => (tab === "saved" ? `saved-${saved.length}` : JSON.stringify(filters)),
    [tab, saved.length, filters],
  );

  const sourceCount = meta?.counts_per_source_published
    ? Object.keys(meta.counts_per_source_published).length
    : null;

  // Every hook above runs unconditionally; the gate is only about what we
  // render. Returning early before a hook would break the hook order.
  if (!unlocked) {
    return (
      <LoginPage auth={auth} onSkip={() => setBypass(true)} />
    );
  }

  return (
    <div className="app">
      <ProgressBar active={loading && tab === "all"} />

      <Header
        total={data?.total_unfiltered}
        refreshed={data?.last_refreshed || meta?.last_refreshed}
        sources={sourceCount}
        action={
          auth.user ? <UserChip user={auth.user} onSignOut={auth.signOut} /> : null
        }
      />

      <div className="sticky">
        <div className="shell">
          <SearchBar
            value={search}
            onChange={setSearch}
            sort={filters.sort}
            onSort={(sort) => update({ sort })}
            tab={tab}
            onTab={setTab}
            savedCount={saved.length}
            busy={loading && tab === "all"}
          />

          {tab === "all" && (
            <FilterBar
              filters={filters}
              facets={data?.facets}
              onChange={update}
              onClear={clearAll}
              anyActive={anyActive}
            />
          )}
        </div>
      </div>

      <main className="shell">
        {error && tab === "all" && (
          <div className="banner pop-in">
            <strong>Could not reach the API.</strong>
            <span className="mono">{error.message}</span>
            <span className="banner-hint">
              Start it with: <code>uvicorn api.main:app --reload --port 8000</code>
            </span>
          </div>
        )}

        {tab === "all" && data && !error && (
          <p className="results">
            <strong>{data.total.toLocaleString("en-IN")}</strong>
            {data.total === 1 ? " job" : " jobs"}
            {data.total !== data.total_unfiltered && (
              <span className="results-of">
                {" "}
                of {data.total_unfiltered.toLocaleString("en-IN")}
              </span>
            )}
            {data.pages > 1 && (
              <span className="results-of">
                {" "}
                · page {data.page} of {data.pages}
              </span>
            )}
          </p>
        )}

        {tab === "saved" && saved.length > 0 && (
          <p className="results">
            <strong>{saved.length}</strong>
            {saved.length === 1 ? " saved job" : " saved jobs"}
          </p>
        )}

        {loading && !data && tab === "all" ? (
          <SkeletonGrid />
        ) : (
          jobs.length > 0 && (
            <div
              key={gridKey}
              className={loading && tab === "all" ? "grid is-loading" : "grid"}
            >
              {jobs.map((job, index) => (
                <JobCard
                  key={job.id}
                  job={job}
                  index={index}
                  onOpen={setOpenId}
                  saved={isSaved(job.id)}
                  onToggleSave={toggle}
                />
              ))}
            </div>
          )
        )}

        {!loading && !error && jobs.length === 0 && (
          <EmptyState
            tab={tab}
            filters={filters}
            onChange={update}
            onClear={clearAll}
            anyActive={anyActive}
          />
        )}

        {tab === "all" && data && (
          <Pagination page={data.page} pages={data.pages} onGo={goToPage} />
        )}
      </main>

      {openId && (
        <JobPanel
          jobId={openId}
          onClose={() => setOpenId(null)}
          saved={isSaved(openId)}
          onToggleSave={toggle}
        />
      )}

      <footer className="footer">
        <div className="shell">
          <p>
            {PAGE_SIZE} per page · collected from Greenhouse, Lever, Ashby and Adzuna
            public APIs, de-duplicated, and tagged by role and city with Gemini.
          </p>
          <p className="footer-dim">
            Links go to the original posting. Saved jobs are stored in this browser only.
          </p>
        </div>
      </footer>
    </div>
  );
}
