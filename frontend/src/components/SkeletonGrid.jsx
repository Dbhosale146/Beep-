// Placeholder cards for the first load, so the page has shape before the data
// arrives instead of flashing empty. Each block has a gradient sweeping across
// it (the shimmer keyframes in animations.css) and the rows are staggered, so
// it reads as "loading" rather than "broken".
export default function SkeletonGrid({ count = 6 }) {
  return (
    <div className="grid" aria-busy="true" aria-label="Loading jobs">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="card skeleton" style={{ "--i": i }}>
          <div className="card-top">
            <div className="sk sk-avatar" />
            <div className="sk-head">
              <div className="sk sk-title" />
              <div className="sk sk-company" />
            </div>
          </div>
          <div className="sk-tags">
            <div className="sk sk-pill" />
            <div className="sk sk-pill wide" />
          </div>
          <div className="sk sk-line" />
          <div className="sk sk-line" />
          <div className="sk sk-line short" />
        </div>
      ))}
    </div>
  );
}
