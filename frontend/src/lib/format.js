// Small pure display helpers. Pure on purpose: no state, no DOM, so they are
// trivial to reason about and could be tested without a browser.

export function daysAgo(iso) {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  const days = Math.floor((Date.now() - then.getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1mo ago" : `${months}mo ago`;
}

// "Fresh" posts get a highlighted date pill. Three days is the window where a
// student still has a realistic chance of being early to the application.
export function isFresh(iso) {
  if (!iso) return false;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return false;
  return Date.now() - then.getTime() < 3 * 86400000;
}

export function initials(company) {
  if (!company) return "?";
  const words = company
    .replace(/\b(pvt|private|ltd|limited|inc|llp|technologies|technology|solutions|labs)\b/gi, "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) return company.slice(0, 2).toUpperCase();
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

// A stable colour per company, so the same employer always looks the same.
// Hashing the name beats storing a palette: no lookup table to maintain and
// a company we have never seen still gets a sensible colour.
export function hueFor(text) {
  let hash = 0;
  for (let i = 0; i < (text || "").length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) % 360;
  }
  return hash;
}

export function formatDateTime(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}
