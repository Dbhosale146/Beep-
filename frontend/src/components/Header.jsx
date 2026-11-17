import { useCountUp } from "../hooks/useCountUp.js";
import { formatDateTime } from "../lib/format.js";

// The hero. Three animated things happen here:
//   - two blurred gradient blobs drift slowly behind the text (CSS only)
//   - the title and subtitle rise into place on load, staggered
//   - the job count counts up from zero
//
// `action` is the top-right slot, which App fills with the signed-in user.
export default function Header({ total, refreshed, sources, action }) {
  const count = useCountUp(total || 0);
  const when = formatDateTime(refreshed);

  return (
    <header className="hero">
      {/* Decoration only, so hidden from assistive tech. */}
      <div className="hero-blob hero-blob-a" aria-hidden="true" />
      <div className="hero-blob hero-blob-b" aria-hidden="true" />

      <div className="hero-inner">
        <div className="hero-top">
          <span className="hero-eyebrow rise" style={{ "--d": "0ms" }}>
            <span className="live-dot" aria-hidden="true" />
            Refreshed daily from public job-board APIs
          </span>
          {action}
        </div>

        <h1 className="hero-title rise" style={{ "--d": "70ms" }}>
          Fresher jobs &amp; internships
          <span className="hero-accent"> in India</span>
        </h1>

        <p className="hero-sub rise" style={{ "--d": "140ms" }}>
          {total ? (
            <>
              <strong className="hero-count">{count.toLocaleString("en-IN")}</strong>{" "}
              open roles
              {sources ? <> across {sources} sources</> : null}
            </>
          ) : (
            "Loading roles..."
          )}
          {when && <span className="hero-when"> · updated {when}</span>}
        </p>
      </div>
    </header>
  );
}
