import { useCallback, useEffect, useRef, useState } from "react";

import { setAuthToken } from "../lib/api.js";

// Google Sign-In, using Google Identity Services.
//
// There is no password field anywhere in this app, on purpose. Google shows
// its own sign-in screen in a popup it controls; we are handed an ID token (a
// JWT that Google signed) and never see a credential. Collecting someone's
// Gmail password in our own form would be phishing, and Google blocks it.
//
// The token goes to the API in the Authorization header, and backend/api/auth.py
// verifies Google's signature on it. That check is the real gate. Everything
// in this file is about the user experience of obtaining the token.

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";
const STORAGE_KEY = "beep.auth.v1";
const GIS_SRC = "https://accounts.google.com/gsi/client";

export const AUTH_CONFIGURED = Boolean(CLIENT_ID);

// Read the token's own payload, for the name and picture to put in the header.
//
// This is NOT verification -- a JWT payload is just base64, and anyone can
// write one. It is safe here only because nothing is trusted on the strength
// of it: the token still has to satisfy the server before any data is handed
// over. Treat it as "what this token claims", never "who this user is".
function decodeClaims(token) {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const binary = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    // atob yields one byte per character; re-decode as UTF-8 so a name with
    // non-ASCII characters is not mangled.
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
}

function sessionFrom(token) {
  const claims = decodeClaims(token);
  if (!claims?.exp) return null;
  // Google ID tokens last about an hour. An expired one is useless, so drop it
  // rather than show a signed-in header that every request then rejects.
  if (claims.exp * 1000 <= Date.now()) return null;
  return {
    token,
    expiresAt: claims.exp * 1000,
    user: {
      email: claims.email,
      name: claims.name || claims.email,
      picture: claims.picture,
    },
  };
}

function restore() {
  try {
    const token = localStorage.getItem(STORAGE_KEY);
    return token ? sessionFrom(token) : null;
  } catch {
    // Private windows and blocked site data throw. Signed out is the safe
    // interpretation.
    return null;
  }
}

let scriptPromise = null;

function loadGoogleScript() {
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = GIS_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("could not load Google Sign-In"));
    document.head.appendChild(script);
  });
  // Do not cache a failure, or a retry would keep returning it.
  scriptPromise.catch(() => {
    scriptPromise = null;
  });
  return scriptPromise;
}

export function useAuth() {
  const [session, setSession] = useState(restore);
  const [ready, setReady] = useState(!AUTH_CONFIGURED);
  const [error, setError] = useState(null);
  const initialised = useRef(false);

  // Keep the API module's token in step with our state, so no component has to
  // remember to pass it on every call.
  useEffect(() => {
    setAuthToken(session?.token || null);
  }, [session]);

  useEffect(() => {
    try {
      if (session) localStorage.setItem(STORAGE_KEY, session.token);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Storage unavailable. The session still works for this page view.
    }
  }, [session]);

  useEffect(() => {
    if (!AUTH_CONFIGURED) return;
    loadGoogleScript()
      .then(() => setReady(true))
      .catch((e) => {
        setError(e.message);
        setReady(true);
      });
  }, []);

  // Sign the user out when their token expires, instead of letting the page
  // sit there looking signed in while every request fails.
  useEffect(() => {
    if (!session) return undefined;
    const ms = session.expiresAt - Date.now();
    const timer = setTimeout(() => setSession(null), Math.max(0, ms));
    return () => clearTimeout(timer);
  }, [session]);

  const signOut = useCallback(() => {
    setSession(null);
    try {
      // Stops Google silently signing the same account straight back in.
      window.google?.accounts?.id?.disableAutoSelect?.();
    } catch {
      // Not loaded. Nothing to disable.
    }
  }, []);

  // Renders Google's own button into `element`. It has to be Google's button:
  // the flow is theirs, and a hand-rolled one cannot produce a valid token.
  const mountButton = useCallback(
    (element) => {
      if (!element || !AUTH_CONFIGURED || !window.google?.accounts?.id) return;

      if (!initialised.current) {
        window.google.accounts.id.initialize({
          client_id: CLIENT_ID,
          callback: (response) => {
            const next = sessionFrom(response.credential);
            if (next) {
              setSession(next);
              setError(null);
            } else {
              setError("Google returned a token we could not read.");
            }
          },
        });
        initialised.current = true;
      }

      element.replaceChildren();
      window.google.accounts.id.renderButton(element, {
        theme: "outline",
        size: "large",
        shape: "pill",
        text: "signin_with",
        logo_alignment: "left",
        width: 260,
      });
    },
    [],
  );

  return {
    configured: AUTH_CONFIGURED,
    ready,
    error,
    user: session?.user || null,
    signedIn: Boolean(session),
    signOut,
    mountButton,
  };
}
