// A thin indeterminate bar across the top of the window while a request is in
// flight. It is indeterminate on purpose: we do not know how long the request
// will take, and a fake percentage would be a lie.
//
// It stays mounted and animates opacity rather than unmounting, so it fades
// out instead of vanishing mid-sweep.
export default function ProgressBar({ active }) {
  return (
    <div className={active ? "progress is-on" : "progress"} aria-hidden="true">
      <span />
    </div>
  );
}
