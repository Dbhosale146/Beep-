import { useEffect, useRef, useState } from "react";

// Counts a number up to its target when it first appears.
//
// Driven by requestAnimationFrame rather than setInterval, so it runs on the
// browser's paint clock, pauses in a background tab and never queues up frames
// it cannot draw. easeOutCubic makes it decelerate instead of ticking linearly.
//
// Honours prefers-reduced-motion by jumping straight to the final value: an
// animated number is decoration, and decoration is the first thing to drop for
// anyone who has asked for less movement.
export function useCountUp(target, duration = 900) {
  const [value, setValue] = useState(0);
  const frame = useRef(0);

  useEffect(() => {
    if (!target) {
      setValue(0);
      return undefined;
    }

    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setValue(target);
      return undefined;
    }

    const start = performance.now();

    function step(now) {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - progress) ** 3;
      setValue(Math.round(target * eased));
      if (progress < 1) frame.current = requestAnimationFrame(step);
    }

    frame.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame.current);
  }, [target, duration]);

  return value;
}
