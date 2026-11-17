import { useEffect, useRef, useState } from "react";

// The signed-in user in the header, with a sign-out menu.
export default function UserChip({ user, onSignOut }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);

  // Click outside or press Escape to dismiss. Both are what people expect of
  // a menu, and skipping them is the kind of thing that feels unfinished.
  useEffect(() => {
    if (!open) return undefined;
    function onDown(event) {
      if (!box.current?.contains(event.target)) setOpen(false);
    }
    function onKey(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const initial = (user.name || user.email || "?").trim().charAt(0).toUpperCase();

  return (
    <div className="userchip" ref={box}>
      <button
        className="userchip-btn"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        {user.picture ? (
          // referrerPolicy because Google's CDN rejects requests that carry
          // our origin as the referrer, and the avatar silently 403s without it.
          <img src={user.picture} alt="" referrerPolicy="no-referrer" />
        ) : (
          <span className="userchip-initial" aria-hidden="true">
            {initial}
          </span>
        )}
        <span className="userchip-name">{user.name}</span>
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M4 6l4 4 4-4" />
        </svg>
      </button>

      {open && (
        <div className="userchip-menu pop-in" role="menu">
          <div className="userchip-who">
            <strong>{user.name}</strong>
            <span>{user.email}</span>
          </div>
          <button className="userchip-signout" onClick={onSignOut} role="menuitem">
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
