// The filter row, plus the removable chips showing what is currently applied.
//
// Every option and count comes from the API's facet counts, never from a
// hardcoded list, so the menus always match the data that is actually
// published. The facets also ignore their own dimension, which is why picking
// a city does not empty the city menu.

const WITHIN_OPTIONS = [
  ["0", "Any time"],
  ["1", "Last 24 hours"],
  ["7", "Last 7 days"],
  ["30", "Last 30 days"],
];

const WITHIN_LABEL = Object.fromEntries(WITHIN_OPTIONS);

function Select({ label, value, counts, onChange }) {
  const entries = Object.entries(counts || {});
  return (
    <select
      className={value ? "filter is-active" : "filter"}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={label}
    >
      <option value="">{label}</option>
      {/* A selected value the current search has no results for would
          otherwise vanish from the list and silently reset itself. */}
      {value && !counts?.[value] && <option value={value}>{value} (0)</option>}
      {entries.map(([name, count]) => (
        <option key={name} value={name}>
          {name} ({count})
        </option>
      ))}
    </select>
  );
}

function Chip({ children, onRemove }) {
  return (
    <span className="chip chip-in">
      {children}
      <button onClick={onRemove} aria-label={`Remove filter ${children}`}>
        ×
      </button>
    </span>
  );
}

export default function FilterBar({ filters, facets, onChange, onClear, anyActive }) {
  return (
    <div className="filters">
      <div className="filter-row">
        <Select
          label="All roles"
          value={filters.role}
          counts={facets?.roles}
          onChange={(role) => onChange({ role })}
        />
        <Select
          label="All cities"
          value={filters.city}
          counts={facets?.cities}
          onChange={(city) => onChange({ city })}
        />
        <Select
          label="All sources"
          value={filters.source}
          counts={facets?.sources}
          onChange={(source) => onChange({ source })}
        />
        <select
          className={filters.within !== "0" ? "filter is-active" : "filter"}
          value={filters.within}
          onChange={(e) => onChange({ within: e.target.value })}
          aria-label="Date posted"
        >
          {WITHIN_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {anyActive && (
        <div className="chips">
          {filters.q && <Chip onRemove={() => onChange({ q: "" })}>“{filters.q}”</Chip>}
          {filters.role && <Chip onRemove={() => onChange({ role: "" })}>{filters.role}</Chip>}
          {filters.city && <Chip onRemove={() => onChange({ city: "" })}>{filters.city}</Chip>}
          {filters.source && (
            <Chip onRemove={() => onChange({ source: "" })}>{filters.source}</Chip>
          )}
          {filters.within !== "0" && (
            <Chip onRemove={() => onChange({ within: "0" })}>
              {WITHIN_LABEL[filters.within]}
            </Chip>
          )}
          <button className="chips-clear" onClick={onClear}>
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}
