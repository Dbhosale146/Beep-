import { useEffect, useState } from "react";

import { fetchJob } from "../lib/api.js";
import { daysAgo, hueFor, initials } from "../lib/format.js";

// The detail drawer. Slides in from the right while the backdrop fades, which
// reads as "same page, more detail" rather than a navigation.
//
// It fetches the one job by id because the list endpoint only sends a
// 300-character snippet and the full description is up to 1,200.
export default function JobPanel({ jobId, onClose, saved, onToggleSave }) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    setJob(null);
    setError(null);
    fetchJob(jobId, controller.signal)
      .then(setJob)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [jobId]);

  // Escape closes the drawer, and the page behind it stops scrolling while it
  // is open. Both are the first things someone tries.
  useEffect(() => {
    function onKey(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  const posted = job ? daysAgo(job.posted_at) : null;

  return (
    <div className="scrim" onClick={onClose} role="dialog" aria-modal="true">
      {/* Clicking the backdrop closes; clicking inside must not. */}
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="drawer-close" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path d="M5 5l10 10M15 5L5 15" />
          </svg>
        </button>

        {error && (
          <div className="drawer-error">
            <p>Could not load this job.</p>
            <p className="mono">{error}</p>
          </div>
        )}

        {!job && !error && (
          <div className="drawer-loading">
            <div className="sk sk-title" />
            <div className="sk sk-company" />
            <div className="sk sk-line" />
            <div className="sk sk-line" />
            <div className="sk sk-line short" />
          </div>
        )}

        {job && (
          <div className="drawer-body" style={{ "--hue": hueFor(job.company) }}>
            <div className="drawer-head">
              <div className="avatar avatar-lg" aria-hidden="true">
                {initials(job.company)}
              </div>
              <div>
                <h2 className="drawer-title">{job.title}</h2>
                <p className="drawer-company">{job.company || "Unknown company"}</p>
              </div>
            </div>

            <div className="card-tags">
              <span className="pill pill-city">{job.city}</span>
              <span className="pill pill-role">{job.role}</span>
              {posted && <span className="pill pill-date">{posted}</span>}
              <span className="pill">{job.source}</span>
            </div>

            <div className="drawer-actions">
              {/* noreferrer because these are third-party job pages. */}
              <a className="btn btn-primary" href={job.url} target="_blank" rel="noreferrer">
                Apply on {job.source}
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M6 3h7v7M13 3L4 12" />
                </svg>
              </a>
              <button
                className={saved ? "btn btn-saved" : "btn"}
                onClick={() => onToggleSave(job)}
              >
                {saved ? "★ Saved" : "☆ Save"}
              </button>
            </div>

            <dl className="drawer-facts">
              <div>
                <dt>Location as posted</dt>
                <dd>{job.raw_location || "—"}</dd>
              </div>
              <div>
                <dt>Source</dt>
                <dd>{job.source}</dd>
              </div>
              <div>
                <dt>Fresher role</dt>
                <dd>{job.is_fresher ? "Yes" : "Not confirmed"}</dd>
              </div>
            </dl>

            <h3 className="drawer-section">Description</h3>
            <p className="drawer-desc">{job.description || "No description provided."}</p>
          </div>
        )}
      </aside>
    </div>
  );
}
