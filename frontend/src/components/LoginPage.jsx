import { useEffect, useRef } from "react";

// The login wall. Nothing else renders until this hands back a token.
//
// There is no username or password field here, and that is the point worth
// making to anyone reviewing this: Google shows its own sign-in screen, so
// this app never receives a credential. The button below is rendered by
// Google's own script into the div this component provides -- a hand-built
// button could not produce a valid token.

// Setup instructions belong to whoever is running the app, not to the person
// trying to find a job. They go to the console; the page says only what a
// visitor can act on.
function warnDeveloper() {
  console.warn(
    "[auth] Google Sign-In is not configured.\n" +
      "Set VITE_GOOGLE_CLIENT_ID in frontend/.env to an OAuth client id from\n" +
      "https://console.cloud.google.com/apis/credentials, then restart the dev\n" +
      "server (or rebuild). Add this page's origin to the client's authorised\n" +
      "JavaScript origins.",
  );
}

export default function LoginPage({ auth, onSkip }) {
  const slot = useRef(null);

  useEffect(() => {
    if (auth.ready) auth.mountButton(slot.current);
  }, [auth.ready, auth.mountButton]);

  useEffect(() => {
    if (!auth.configured) warnDeveloper();
  }, [auth.configured]);

  return (
    <div className="login">
      <div className="hero-blob hero-blob-a" aria-hidden="true" />
      <div className="hero-blob hero-blob-b" aria-hidden="true" />

      <div className="login-card rise" style={{ "--d": "40ms" }}>
        <div className="login-mark" aria-hidden="true">
          beep
        </div>

        <h1 className="login-title">
          Fresher jobs &amp; internships
          <span className="hero-accent"> in India</span>
        </h1>

        {/* No job count here on purpose: nothing is fetched until after
            sign-in, so the wall has no number to show and does not pretend to. */}
        <p className="login-sub">
          Internships and 0–1 year roles, refreshed every day. Sign in to browse.
        </p>

        <ul className="login-points">
          <li>
            <span aria-hidden="true">◆</span> Collected from company job boards,
            not reposts
          </li>
          <li>
            <span aria-hidden="true">◆</span> Duplicates removed, tagged by role
            and city
          </li>
          <li>
            <span aria-hidden="true">◆</span> Save roles to come back to
          </li>
        </ul>

        <div className="login-action">
          {/* Google renders its button in here once its script has loaded. */}
          <div ref={slot} className="login-gbtn" />

          {auth.configured && !auth.ready && (
            <p className="login-note">Loading sign-in…</p>
          )}

          {auth.error && (
            <p className="login-error">
              Sign-in is unavailable right now. Please try again shortly.
            </p>
          )}

          {!auth.configured && (
            <div className="login-unavailable">
              <p>Sign-in is temporarily unavailable.</p>
              {onSkip && (
                <button className="btn" onClick={onSkip}>
                  Continue without signing in
                </button>
              )}
            </div>
          )}
        </div>

        <p className="login-fine">
          Google handles sign-in — we never see your password. We read only your
          name, email and profile picture.
        </p>
      </div>
    </div>
  );
}
