import { daysAgo, hueFor, initials, isFresh } from "../lib/format.js";

// One job in the results grid.
//
// The whole card is clickable and opens the detail panel rather than leaving
// the site straight away, which is what a job board normally does -- the link
// out to the employer lives on the Apply button in the panel.
//
// `--i` is the card's position in the grid. animations.css turns it into an
// animation-delay, which is what produces the staggered entrance.
export default function JobCard({ job, index, onOpen, saved, onToggleSave }) {
  const posted = daysAgo(job.posted_at);
  const fresh = isFresh(job.posted_at);
  const hue = hueFor(job.company);

  return (
    <article
      className="card card-in"
      style={{ "--i": index, "--hue": hue }}
      onClick={() => onOpen(job.id)}
    >
      <div className="card-top">
        <div className="avatar" aria-hidden="true">
          {initials(job.company)}
        </div>

        <div className="card-head">
          {/* A real button, so keyboard and screen readers get the same
              behaviour as a mouse click on the card. */}
          <h2 className="card-title">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onOpen(job.id);
              }}
            >
              {job.title}
            </button>
          </h2>
          <p className="card-company">{job.company || "Unknown company"}</p>
        </div>

        <button
          className={saved ? "star is-saved" : "star"}
          onClick={(e) => {
            // Without this the click would also open the detail panel.
            e.stopPropagation();
            onToggleSave(job);
          }}
          aria-pressed={saved}
          aria-label={saved ? "Remove from saved" : "Save this job"}
          title={saved ? "Remove from saved" : "Save this job"}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 3.6l2.6 5.3 5.8.85-4.2 4.1 1 5.75L12 16.9l-5.2 2.7 1-5.75-4.2-4.1 5.8-.85z" />
          </svg>
        </button>
      </div>

      <div className="card-tags">
        <span className="pill pill-city">
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M8 1.5c-2.5 0-4.5 2-4.5 4.5C3.5 9.5 8 14.5 8 14.5s4.5-5 4.5-8.5C12.5 3.5 10.5 1.5 8 1.5z" />
            <circle cx="8" cy="6" r="1.6" />
          </svg>
          {job.city}
        </span>
        <span className="pill pill-role">{job.role}</span>
        {posted && (
          <span className={fresh ? "pill pill-date is-fresh" : "pill pill-date"}>
            {fresh && <span className="fresh-dot" aria-hidden="true" />}
            {posted}
          </span>
        )}
      </div>

      {job.description && <p className="card-snippet">{job.description}</p>}

      <div className="card-foot">
        <span className="card-source">{job.source}</span>
        <span className="card-cta">
          View details
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M3 8h10M9 4l4 4-4 4" />
          </svg>
        </span>
      </div>
    </article>
  );
}
