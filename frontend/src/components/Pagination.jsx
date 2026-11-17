// Previous / next plus a few numbered pages.
//
// The window is deliberately small: with 24 pages, rendering every number is
// noise. This shows the first page, the last page, and the neighbours of the
// current one, with gaps collapsed to an ellipsis.
function pageWindow(current, last) {
  const pages = new Set([1, last, current - 1, current, current + 1]);
  const list = [...pages].filter((p) => p >= 1 && p <= last).sort((a, b) => a - b);

  const out = [];
  let previous = 0;
  for (const page of list) {
    if (previous && page - previous > 1) out.push("gap");
    out.push(page);
    previous = page;
  }
  return out;
}

export default function Pagination({ page, pages, onGo }) {
  if (pages <= 1) return null;

  return (
    <nav className="pager" aria-label="Pagination">
      <button className="pager-btn" disabled={page <= 1} onClick={() => onGo(page - 1)}>
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M10 3L5 8l5 5" />
        </svg>
        Previous
      </button>

      <div className="pager-nums">
        {pageWindow(page, pages).map((item, i) =>
          item === "gap" ? (
            <span key={`gap${i}`} className="pager-gap">
              …
            </span>
          ) : (
            <button
              key={item}
              className={item === page ? "pager-num is-on" : "pager-num"}
              aria-current={item === page ? "page" : undefined}
              onClick={() => onGo(item)}
            >
              {item}
            </button>
          ),
        )}
      </div>

      <button className="pager-btn" disabled={page >= pages} onClick={() => onGo(page + 1)}>
        Next
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M6 3l5 5-5 5" />
        </svg>
      </button>
    </nav>
  );
}
