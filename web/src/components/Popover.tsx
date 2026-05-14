"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

type Placement = "right" | "left" | "bottom" | "top";

type Coords = { top: number; left: number; placement: Placement };

const GAP = 8;            // px gap between trigger and popover
const VIEWPORT_PAD = 12;  // keep this far from window edges

/**
 * A small floating popover anchored to an existing element. We render
 * it in a fixed-position container so it floats above the page grid
 * regardless of the trigger's overflow context. Position is recomputed
 * on open + on resize + scroll. Closes on click-outside or Escape.
 */
export function Popover({
  open,
  anchorEl,
  onClose,
  children,
  preferred = "right",
  width = 280,
}: {
  open: boolean;
  anchorEl: HTMLElement | null;
  onClose: () => void;
  children: React.ReactNode;
  /** First placement to try; we fall back if it doesn't fit. */
  preferred?: Placement;
  /** Target width of the popover content. Used to pick the side. */
  width?: number;
}) {
  const popRef = useRef<HTMLDivElement | null>(null);
  const [coords, setCoords] = useState<Coords | null>(null);

  // Recompute the position whenever the popover is opened or the page
  // layout shifts under us. This is intentionally lightweight — the
  // popover is small enough that we can re-measure on every scroll.
  useLayoutEffect(() => {
    if (!open || !anchorEl) {
      setCoords(null);
      return;
    }
    function measure() {
      if (!anchorEl) return;
      const r = anchorEl.getBoundingClientRect();
      const popHeight = popRef.current?.offsetHeight ?? 320;
      const popWidth = popRef.current?.offsetWidth ?? width;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      const candidates: Array<{ p: Placement; top: number; left: number }> = [
        // Right of the trigger
        {
          p: "right",
          top: r.top + r.height / 2 - popHeight / 2,
          left: r.right + GAP,
        },
        // Left of the trigger
        {
          p: "left",
          top: r.top + r.height / 2 - popHeight / 2,
          left: r.left - popWidth - GAP,
        },
        // Below the trigger, aligned to its left edge
        {
          p: "bottom",
          top: r.bottom + GAP,
          left: Math.min(r.left, vw - popWidth - VIEWPORT_PAD),
        },
        // Above the trigger
        {
          p: "top",
          top: r.top - popHeight - GAP,
          left: Math.min(r.left, vw - popWidth - VIEWPORT_PAD),
        },
      ];

      // Prefer the user-requested placement, then fall through.
      const order: Placement[] = [preferred, "right", "left", "bottom", "top"];
      const seen = new Set<Placement>();
      const ordered: typeof candidates = [];
      for (const p of order) {
        if (seen.has(p)) continue;
        seen.add(p);
        const cand = candidates.find((c) => c.p === p);
        if (cand) ordered.push(cand);
      }

      // Pick the first that fits. Check both axes against the viewport.
      const pick =
        ordered.find((c) => {
          return (
            c.left >= VIEWPORT_PAD &&
            c.left + popWidth <= vw - VIEWPORT_PAD &&
            c.top >= VIEWPORT_PAD &&
            c.top + popHeight <= vh - VIEWPORT_PAD
          );
        }) ?? ordered[0];

      // Clamp to viewport so we never get clipped completely.
      const clampedTop = Math.max(
        VIEWPORT_PAD,
        Math.min(pick.top, vh - popHeight - VIEWPORT_PAD),
      );
      const clampedLeft = Math.max(
        VIEWPORT_PAD,
        Math.min(pick.left, vw - popWidth - VIEWPORT_PAD),
      );

      setCoords({ top: clampedTop, left: clampedLeft, placement: pick.p });
    }
    measure();
    // Re-measure after the popover content has rendered (its height may
    // be different from our default guess).
    const id = window.setTimeout(measure, 0);

    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      clearTimeout(id);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [open, anchorEl, preferred, width]);

  // Close on click-outside (anywhere outside both popover and anchor).
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      const target = e.target as Node | null;
      if (!target) return;
      if (popRef.current?.contains(target)) return;
      if (anchorEl?.contains(target)) return;
      onClose();
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, anchorEl, onClose]);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={popRef}
      role="dialog"
      style={{
        position: "fixed",
        top: coords?.top ?? -9999,
        left: coords?.left ?? -9999,
        width,
        // Hide the popover until we have real coordinates so it doesn't
        // flash at -9999 on the first paint.
        visibility: coords ? "visible" : "hidden",
        zIndex: 60,
      }}
      className="rounded-xl border border-[var(--accent)]/40 bg-[var(--surface)] shadow-2xl"
    >
      {children}
    </div>
  );
}
