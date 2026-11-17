import { useEffect, useRef } from "react";

// The login wall. Nothing else renders until this hands back a token.
//
// There is no username or password field here, and that is the point worth
// making to anyone reviewing this: Google shows its own sign-in screen, so
// this app never receives a credential. The button below is rendered by
// Google's own script into the div this component provides -- a hand-built
// button could not produce a valid token.
export default function LoginPage({ auth, onSkip }) {
  const slot = useRef(null);

  useEffect(() => {
    if (auth.ready) auth.mountButton(slot.current);
  }, [auth.ready, auth.mountButton]);

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
          Fresher and internship roles collected daily from public job-board
          APIs, de-duplicated and tagged by role and city. Sign in to browse them.
        </p>

        <div className="login-action">
          {/* Google renders its button in here once its script has loaded. */}
          <div ref={slot} className="login-gbtn" />

          {!auth.ready && <p className="login-note">Loading Google Sign-In…</p>}

          {auth.error && <p className="login-error">{auth.error}</p>}

          {!auth.configured && (
            <div className="login-unconfigured">
              <p>
                <strong>Google Sign-In is not configured yet.</strong>
              </p>
              <p className="login-note">
                Set <code>VITE_GOOGLE_CLIENT_ID</code> in <code>frontend/.env</code> to
                a Google OAuth client id, then rebuild. Until then the sign-in
                button cannot be shown.
              </p>
              {onSkip && (
                <button className="btn" onClick={onSkip}>
                  Continue without signing in
                </button>
              )}
            </div>
          )}
        </div>

        <p className="login-fine">
          We never see your password — Google handles sign-in and returns a
          signed token. We read only your name, email and profile picture.
        </p>
      </div>
    </div>
  );
}
