import { useEffect, useRef, useState } from "react";

// The search field, plus the tab switch and the sort menu.
//
// The input is uncontrolled by the filters on purpose: `value` tracks local
// typing state so the field stays instant, and the parent is only told after
// the debounce in App.jsx. Binding it straight to the fetched filters would
// make every keystroke wait on the network.
export default function SearchBar({
  value,
  onChange,
  sort,
  onSort,
  tab,
  onTab,
  savedCount,
  busy,
}) {
  const inputRef = useRef(null);
  const [focused, setFocused] = useState(false);

  // "/" focuses search, Escape clears it. Both are conventions people already
  // know from other sites, and each is two lines.
  useEffect(() => {
    function onKey(event) {
      const typingElsewhere =
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement ||
        event.target instanceof HTMLSelectElement;

      if (event.key === "/" && !typingElsewhere) {
        event.preventDefault();
        inputRef.current?.focus();
      }
      if (event.key === "Escape" && document.activeElement === inputRef.current) {
        onChange("");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onChange]);

  return (
    <div className="bar">
      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "all"}
          className={tab === "all" ? "tab is-on" : "tab"}
          onClick={() => onTab("all")}
        >
          All jobs
        </button>
        <button
          role="tab"
          aria-selected={tab === "saved"}
          className={tab === "saved" ? "tab is-on" : "tab"}
          onClick={() => onTab("saved")}
        >
          Saved
          {savedCount > 0 && <span className="tab-badge pop">{savedCount}</span>}
        </button>
      </div>

      <div className={focused ? "search is-focused" : "search"}>
        <svg className="search-icon" viewBox="0 0 20 20" aria-hidden="true">
          <circle cx="8.5" cy="8.5" r="5.5" />
          <line x1="12.8" y1="12.8" x2="17" y2="17" />
        </svg>

        <input
          ref={inputRef}
          type="search"
          placeholder="Search role, company or city..."
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          aria-label="Search jobs"
        />

        {/* A spinner inside the field is the honest place for it: it marks the
            thing that is actually waiting, not the whole page. */}
        {busy ? (
          <span className="search-spinner" aria-hidden="true" />
        ) : (
          !value && <kbd className="search-kbd">/</kbd>
        )}

        {value && (
          <button className="search-clear" onClick={() => onChange("")} aria-label="Clear search">
            ×
          </button>
        )}
      </div>

      <label className="sort">
        <span className="sort-label">Sort</span>
        <select value={sort} onChange={(e) => onSort(e.target.value)} aria-label="Sort by">
          <option value="recent">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="company">Company A–Z</option>
          <option value="title">Title A–Z</option>
        </select>
      </label>
    </div>
  );
}
