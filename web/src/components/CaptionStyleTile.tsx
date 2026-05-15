"use client";

import { useEffect, useState } from "react";

/**
 * Animated "what this caption style looks like" tile. Cycles through a few
 * sample phrases word-by-word so the picker feels like the live demo —
 * the active word gets the karaoke highlight on every style.
 */

export type CaptionStyle =
  // Original 8
  | "plain"
  | "bold"
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
    <div
      aria-hidden
      className={`relative aspect-[21/9] rounded bg-gradient-to-br from-[#1c1f26] via-[#0e1014] to-[#1a1d24] overflow-hidden ${className}`}
    >
      <span
        className="absolute inset-0 opacity-30"
        style={{
          backgroundImage:
            "radial-gradient(rgba(255,255,255,0.08) 1px, transparent 1px)",
          backgroundSize: "12px 12px",
        }}
      />
      {/* whiteSpace:nowrap forces the demo phrase onto ONE line in every
          style — chunky styles (MrBeast / Comic / Reels) were wrapping
          to 2 lines on narrow grid cells. */}
      <div
        className={`absolute inset-x-0 ${verticalPos} flex justify-center px-2`}
        style={{ whiteSpace: "nowrap" }}
      >
        <StyledPhrase style={style} words={words} activeIdx={wordIdx} />
      </div>
    </div>
  );
}

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
        className="inline-block rounded font-semibold leading-tight"
        style={{
          background: "rgba(0,0,0,0.78)",
          color: "#FFFFFF",
          fontSize: "13px",
          padding: "0.28em 0.85em",
        }}
      >
        {words.join(" ")}
      </span>
    );
  }
  if (style === "bold") {
    return (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#FFFFFF",
          fontSize: "14px",
          paintOrder: "stroke fill",
          WebkitTextStroke: "2px #000",
          textShadow:
            "0 1px 0 #000, 0 -1px 0 #000, 1px 0 0 #000, -1px 0 0 #000",
        }}
      >
        {words.map((w, i) => (
          <span
            key={i}
            style={{
              marginRight: i === words.length - 1 ? 0 : "0.25em",
              color: i === activeIdx ? "#FFE04A" : "#FFFFFF",
            }}
          >
            {w}
          </span>
        ))}
      </span>
    );
  }
  if (style === "highlight") {
    return (
      <span
        className="inline-block rounded font-bold leading-tight"
        style={{
          background: "var(--accent)",
          color: "#0a0a0a",
          fontSize: "13px",
          padding: "0.3em 0.85em",
          boxShadow: "0 2px 8px rgba(0,240,255,0.3)",
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
          fontSize: "14px",
          paintOrder: "stroke fill",
          WebkitTextStroke: "2px #000",
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
          fontSize: "14px",
          paintOrder: "stroke fill",
          WebkitTextStroke: "1.4px #00F0FF",
          textShadow: [
            "0 0 4px #00F0FF",
            "0 0 8px #00F0FF",
            "0 0 14px rgba(0,240,255,0.7)",
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
          fontSize: "14px",
          paintOrder: "stroke fill",
          WebkitTextStroke: "2px #0B2A4A",
          textShadow:
            "0 1px 0 rgba(255,255,255,0.4), 0 -1px 0 rgba(0,0,0,0.6)",
        }}
      >
        {words.join(" ")}
      </span>
    );
  }
  if (style === "typewriter") {
    const visible = words.slice(0, activeIdx + 1).join(" ");
    return (
      <span
        className="inline-block font-medium leading-tight"
        style={{
          background: "#000",
          color: "#FFFFFF",
          fontSize: "12px",
          padding: "0.18em 0.6em",
          fontFamily:
            '"JetBrains Mono", "Courier New", ui-monospace, monospace',
          letterSpacing: "0.02em",
        }}
      >
        {visible}
        <span
          style={{
            display: "inline-block",
            width: "0.55em",
            marginLeft: "0.05em",
            color: "#FFE04A",
          }}
        >
          |
        </span>
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
          fontSize: "13px",
          padding: "0.3em 0.95em",
          letterSpacing: "0.02em",
          boxShadow: "0 2px 6px rgba(179,0,0,0.4)",
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
          fontSize: "12.5px",
          fontWeight: 500,
          textShadow:
            "0 1px 2px rgba(0,0,0,0.95), 0 0 3px rgba(0,0,0,0.8)",
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
          fontSize: "15px",
          fontWeight: 400,
          color: "#FFE04A",
          paintOrder: "stroke fill",
          WebkitTextStroke: "3px #000",
          textShadow:
            "0 2px 0 #000, 0 3px 4px rgba(0,0,0,0.7)",
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
          fontSize: "14px",
          fontWeight: 400,
          color: "#B6FF3C",
          paintOrder: "stroke fill",
          WebkitTextStroke: "2px #000",
          textShadow:
            "0 1px 0 #000, 0 -1px 0 #000, 1px 0 0 #000, -1px 0 0 #000",
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
          fontSize: "15px",
          fontWeight: 400,
          color: "#FFFFFF",
          paintOrder: "stroke fill",
          WebkitTextStroke: "2px #FF1493",
          textShadow:
            "0 0 6px rgba(255,20,147,0.7), 0 0 10px rgba(255,20,147,0.4)",
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
          fontSize: "11.5px",
          fontWeight: 400,
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
        className="inline-block font-bold leading-tight"
        style={{
          color: "#FFFFFF",
          fontSize: "13px",
          padding: "0.16em 0.7em 0.24em",
          background:
            "linear-gradient(to top, rgba(0,240,255,0.85) 0%, rgba(0,240,255,0.85) 24%, transparent 24%)",
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
          fontSize: "12.5px",
          padding: "0.3em 0.95em",
          border: "2.5px solid #FFF",
          borderRadius: "999px",
          boxShadow: "0 3px 8px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.08)",
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
          fontSize: "16px",
          fontWeight: 400,
          color: "#FFE04A",
          paintOrder: "stroke fill",
          WebkitTextStroke: "2.5px #000",
          textShadow:
            "1px 1px 0 #000, 2px 2px 0 #000, 3px 3px 0 rgba(0,0,0,0.5)",
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
          fontSize: "13px",
          fontWeight: 400,
          color: "#FFC107",
          paintOrder: "stroke fill",
          WebkitTextStroke: "2px #B30000",
          textShadow:
            "0 0 6px rgba(255,193,7,0.6), 0 0 12px rgba(179,0,0,0.4)",
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
      style={{ fontSize: "14px" }}
    >
      {words.map((w, i) => (
        <span
          key={i}
          className="inline-block"
          style={{
            marginRight: i === words.length - 1 ? 0 : "0.25em",
            color: i === activeIdx ? "#FFE04A" : "#FFFFFF",
            paintOrder: "stroke fill",
            WebkitTextStroke: "1.3px #000",
            textShadow:
              "0 1px 0 #000, 0 -1px 0 #000, 1px 0 0 #000, -1px 0 0 #000",
          }}
        >
          {w}
        </span>
      ))}
    </span>
  );
}
