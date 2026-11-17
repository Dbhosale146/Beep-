// What the page says when there is nothing to show.
//
// An empty grid with "no results" is a dead end. This names what was searched
// and offers the specific escape route -- dropping the city is almost always
// the filter that was too narrow, so that gets its own button.
export default function EmptyState({ tab, filters, onChange, onClear, anyActive }) {
  if (tab === "saved") {
    return (
      <div className="empty pop-in">
        <div className="empty-icon" aria-hidden="true">
          ☆
        </div>
        <h3>Nothing saved yet</h3>
        <p>Tap the star on any job to keep it here. Saved jobs stay in this browser.</p>
      </div>
    );
  }

  return (
    <div className="empty pop-in">
      <div className="empty-icon" aria-hidden="true">
        ⌕
      </div>
      <h3>No matching roles</h3>
      <p>
        Nothing for {filters.role ? <strong>{filters.role}</strong> : "fresher roles"}
        {filters.city && (
          <>
            {" "}
            in <strong>{filters.city}</strong>
          </>
        )}
        {filters.q && (
          <>
            {" "}
            matching <strong>“{filters.q}”</strong>
          </>
        )}
        .
      </p>

      <div className="empty-actions">
        {filters.city && (
          <button className="btn" onClick={() => onChange({ city: "" })}>
            Search all cities
          </button>
        )}
        {filters.within !== "0" && (
          <button className="btn" onClick={() => onChange({ within: "0" })}>
            Include older posts
          </button>
        )}
        {anyActive && (
          <button className="btn btn-ghost" onClick={onClear}>
            Clear all filters
          </button>
        )}
      </div>
    </div>
  );
}
