"use client";

import { useEffect, useState } from "react";

/**
 * Animated "what this caption style looks like" tile. Cycles through a few
 * sample phrases word-by-word so the picker feels like the live demo —
 * the active word gets the karaoke highlight on every style.
 */

export type CaptionStyle =
  // Original 7 (Bold removed 2026-05)
  | "plain"
  | "highlight"
  | "karaoke"
  | "outline"
  | "neon"
  | "gradient"
  | "typewriter"
  // 10 new
  | "news"
  | "cinema"
  | "mrbeast"
  | "reels"
  | "tiktok"
  | "whisper"
  | "underline"
  | "sticker"
  | "comic"
  | "retro";

// Keep tile phrases short so even the chunky styles (MrBeast / Comic /
// Reels) fit in ONE line within the small grid cell. The actual rendered
// captions inside the video are unaffected — this is just the picker
// preview.
const PHRASES = [
  ["how", "it", "looks"],
  ["preview", "live"],
];

const WORD_MS = 360;

export function CaptionStyleTile({
  style,
  position = "bottom",
  className = "",
}: {
  style: CaptionStyle;
  position?: "top" | "middle" | "bottom";
  className?: string;
}) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), WORD_MS);
    return () => clearInterval(id);
  }, []);

  const totalWords = PHRASES.reduce((n, p) => n + p.length, 0);
  let cursor = tick % totalWords;
  let phrase = PHRASES[0];
  for (const p of PHRASES) {
    if (cursor < p.length) {
      phrase = p;
      break;
    }
    cursor -= p.length;
  }
  const wordIdx = cursor;
  // Keep tile previews in normal case for readability — the actual
  // burned render still applies the style's uppercase rule. Tile is
  // just showing the visual treatment, not the casing.
  const words = phrase;

  const verticalPos =
    position === "top"
      ? "top-3"
      : position === "middle"
        ? "top-1/2 -translate-y-1/2"
        : "bottom-3";

  return (
    // Tile container mirrors a 9:16 reel so the demo CSS sizes
    // (declared in cqh below) come out at the SAME visual proportions
    // as the rendered mp4. Without containerType:size, cqh units don't
    // resolve and everything collapses to default font size.
    //
    // We set aspectRatio inline (instead of Tailwind's aspect-[9/16])
    // because Tailwind v4 sometimes drops the arbitrary aspect class
    // when the parent is a `<button>` — leaving the tile collapsed to
    // 0 height and the styled text invisible.
    <div
      aria-hidden
      className={`relative rounded bg-gradient-to-br from-[#1c1f26] via-[#0e1014] to-[#1a1d24] overflow-hidden ${className}`}
      style={{
        containerType: "size",
        aspectRatio: "9 / 16",
        width: "100%",
      }}
    >
      <span
        className="absolute inset-0 opacity-30"
        style={{
          backgroundImage:
            "radial-gradient(rgba(255,255,255,0.08) 1px, transparent 1px)",
          backgroundSize: "12px 12px",
        }}
      />
      <div
        className={`absolute inset-x-0 ${verticalPos} flex justify-center px-2`}
        style={{ whiteSpace: "nowrap" }}
      >
        <StyledPhrase style={style} words={words} activeIdx={wordIdx} />
      </div>
    </div>
  );
}

/**
 * All sizes below are in `cqh` (container-query-height) units so the
 * preview scales with the 9:16 tile container. Numbers track the
 * backend STYLE_PRESETS in api/tools/captions.py — `font_size_ratio`
 * × FONT_SCALE (0.95) × 100 = cqh value. Strokes are similarly tied
 * to the backend `outline_width` so demo and render stay in sync.
 */
function StyledPhrase({
  style,
  words,
  activeIdx,
}: {
  style: CaptionStyle;
  words: string[];
  activeIdx: number;
}) {
  if (style === "plain") {
    return (
      <span
        className="inline-block rounded font-bold leading-tight"
        style={{
          background: "rgba(0,0,0,0.69)",
          color: "#FFFFFF",
          paintOrder: "stroke fill",
          WebkitTextStroke: "0.4cqh #000",
          fontSize: "4.3cqh",
          padding: "0.25em 0.6em",
        }}
      >
        {words.join(" ")}
      </span>
    );
  }
  if (style === "highlight") {
    return (
      <span
        className="inline-block rounded font-bold leading-tight"
        style={{
          background: "#00F0FF",
          color: "#FFFFFF",
          paintOrder: "stroke fill",
          WebkitTextStroke: "0.2cqh #000",
          fontSize: "4.3cqh",
          padding: "0.25em 0.6em",
        }}
      >
        {words.join(" ")}
      </span>
    );
  }
  if (style === "outline") {
    return (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          fontSize: "4.8cqh",
          paintOrder: "stroke fill",
          WebkitTextStroke: "0.62cqh #000",
        }}
      >
        {words.map((w, i) => (
          <span
            key={i}
            style={{
              marginRight: i === words.length - 1 ? 0 : "0.25em",
              color: i === activeIdx ? "#FFE04A" : "#00F0FF",
            }}
          >
            {w}
          </span>
        ))}
      </span>
    );
  }
  if (style === "neon") {
    return (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#FFFFFF",
          fontSize: "4.8cqh",
          paintOrder: "stroke fill",
          WebkitTextStroke: "0.77cqh #00F0FF",
          textShadow: [
            "0 0 0.7cqh #00F0FF",
            "0 0 1.4cqh #00F0FF",
            "0 0 2.5cqh rgba(0,240,255,0.7)",
          ].join(", "),
        }}
      >
        {words.map((w, i) => (
          <span
            key={i}
            style={{
              marginRight: i === words.length - 1 ? 0 : "0.25em",
              opacity: i === activeIdx ? 1 : 0.7,
            }}
          >
            {w}
          </span>
        ))}
      </span>
    );
  }
  if (style === "gradient") {
    return (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#00F0FF",
          fontSize: "4.9cqh",
          paintOrder: "stroke fill",
          WebkitTextStroke: "1cqh #0B2A4A",
          textShadow:
            "0 0.15cqh 0 rgba(255,255,255,0.4), 0 -0.15cqh 0 rgba(0,0,0,0.6)",
        }}
      >
        {words.join(" ")}
      </span>
    );
  }
  if (style === "typewriter") {
    return (
      <span
        className="inline-block font-medium leading-tight"
        style={{
          background: "#000",
          color: "#FFFFFF",
          fontSize: "3.8cqh",
          padding: "0.18em 0.6em",
          fontFamily:
            '"JetBrains Mono", "Courier New", ui-monospace, monospace',
          letterSpacing: "0.02em",
        }}
      >
        {words.join(" ")}
      </span>
    );
  }
  if (style === "news") {
    return (
      <span
        className="inline-block font-bold leading-tight"
        style={{
          background: "#B30000",
          color: "#FFFFFF",
          fontSize: "4.2cqh",
          padding: "0.22em 0.8em",
          letterSpacing: "0.02em",
        }}
      >
        {words.join(" ")}
      </span>
    );
  }
  if (style === "cinema") {
    return (
      <span
        className="inline-block leading-tight"
        style={{
          color: "#FFFFFF",
          fontSize: "3.6cqh",
          fontWeight: 500,
          paintOrder: "stroke fill",
          WebkitTextStroke: "0.6cqh #000",
          fontStyle: "italic",
        }}
      >
        {words.join(" ")}
      </span>
    );
  }
  if (style === "mrbeast") {
    return (
      <span
        className="inline-block leading-none tracking-tight"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          fontSize: "5.5cqh",
          fontWeight: 400,
          color: "#FFE04A",
          paintOrder: "stroke fill",
          WebkitTextStroke: "0.66cqh #000",
          textShadow: "0 0.22cqh 0 #000",
        }}
      >
        {words.join(" ").toUpperCase()}
      </span>
    );
  }
  if (style === "reels") {
    return (
      <span
        className="inline-block leading-tight tracking-wide"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          fontSize: "5.2cqh",
          fontWeight: 400,
          color: "#B6FF3C",
          paintOrder: "stroke fill",
          WebkitTextStroke: "0.52cqh #000",
        }}
      >
        {words.join(" ").toUpperCase()}
      </span>
    );
  }
  if (style === "tiktok") {
    return (
      <span
        className="inline-block leading-tight"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          fontSize: "5cqh",
          fontWeight: 400,
          color: "#FFFFFF",
          paintOrder: "stroke fill",
          WebkitTextStroke: "0.5cqh #FF1493",
          textShadow: "0 0.15cqh 0 rgba(255,20,147,0.6)",
        }}
      >
        {words.join(" ")}
      </span>
    );
  }
  if (style === "whisper") {
    return (
      <span
        className="inline-block leading-tight"
        style={{
          color: "#C0C0C0",
          fontSize: "3.4cqh",
          fontWeight: 400,
          paintOrder: "stroke fill",
          WebkitTextStroke: "0.2cqh #000",
          letterSpacing: "0.04em",
        }}
      >
        {words.join(" ").toLowerCase()}
      </span>
    );
  }
  if (style === "underline") {
    return (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#FFFFFF",
          fontSize: "4.4cqh",
          paintOrder: "stroke fill",
          WebkitTextStroke: "1cqh #00F0FF",
        }}
      >
        {words.join(" ")}
      </span>
    );
  }
  if (style === "sticker") {
    return (
      <span
        className="inline-block font-bold leading-tight"
        style={{
          background: "#000",
          color: "#FFF1D0",
          fontSize: "4.4cqh",
          padding: "0.22em 0.7em",
          // libass can't do rounded corners — keep square.
          border: "0.75cqh solid #FFF",
        }}
      >
        {words.join(" ")}
      </span>
    );
  }
  if (style === "comic") {
    return (
      <span
        className="inline-block leading-none tracking-tight"
        style={{
          fontFamily: 'var(--font-bangers), "Bangers", "Impact", system-ui',
          fontSize: "5.1cqh",
          fontWeight: 400,
          color: "#FFE04A",
          paintOrder: "stroke fill",
          WebkitTextStroke: "0.56cqh #000",
          textShadow:
            "0.2cqh 0.2cqh 0 #000, 0.4cqh 0.4cqh 0 #000, 0.6cqh 0.6cqh 0 rgba(0,0,0,0.5)",
        }}
      >
        {words.join(" ").toUpperCase()}
      </span>
    );
  }
  if (style === "retro") {
    return (
      <span
        className="inline-block leading-tight tracking-wide"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          fontSize: "4.8cqh",
          fontWeight: 400,
          color: "#FFC107",
          paintOrder: "stroke fill",
          WebkitTextStroke: "0.43cqh #B30000",
          textShadow: "0.24cqh 0.24cqh 0 rgba(179,0,0,0.7)",
          letterSpacing: "0.06em",
        }}
      >
        {words.join(" ").toUpperCase()}
      </span>
    );
  }
  // karaoke
  return (
    <span
      className="inline-block font-extrabold leading-tight"
      style={{ fontSize: "4.8cqh" }}
    >
      {words.map((w, i) => (
        <span
          key={i}
          className="inline-block"
          style={{
            marginRight: i === words.length - 1 ? 0 : "0.25em",
            color: i === activeIdx ? "#FFE04A" : "#FFFFFF",
            paintOrder: "stroke fill",
            WebkitTextStroke: "0.6cqh #000",
          }}
        >
          {w}
        </span>
      ))}
    </span>
  );
}
