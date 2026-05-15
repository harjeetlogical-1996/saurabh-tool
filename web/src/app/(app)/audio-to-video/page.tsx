"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, apiClient, type Job } from "@/lib/api";
import { useMe } from "@/components/MeProvider";
import { CaptionStyleTile } from "@/components/CaptionStyleTile";

const SIZE_OPTIONS = [
  { v: "9:16", label: "9:16 — Reels / Shorts / TikTok" },
  { v: "16:9", label: "16:9 — YouTube widescreen" },
  { v: "1:1", label: "1:1 — Instagram square" },
  { v: "4:5", label: "4:5 — Instagram portrait" },
];

// Audio language hint sent with the upload. "auto" lets Gemini detect.
// Mirrors AUDIO_LANGUAGE_HINTS in the Python backend — keep these
// strings in sync when adding a new language.
const AUDIO_LANGUAGE_OPTIONS = [
  { v: "auto",     label: "Auto-detect" },
  { v: "english",  label: "English" },
  { v: "hindi",    label: "Hindi" },
  { v: "hinglish", label: "Hinglish (Hindi + English mix)" },
  { v: "marathi",  label: "Marathi" },
  { v: "tamil",    label: "Tamil" },
  { v: "bengali",  label: "Bengali" },
  { v: "gujarati", label: "Gujarati" },
  { v: "punjabi",  label: "Punjabi" },
  { v: "telugu",   label: "Telugu" },
  { v: "kannada",  label: "Kannada" },
  { v: "malayalam",label: "Malayalam" },
  { v: "spanish",  label: "Spanish" },
  { v: "french",   label: "French" },
  { v: "german",   label: "German" },
  { v: "portuguese",label:"Portuguese" },
  { v: "japanese", label: "Japanese" },
  { v: "korean",   label: "Korean" },
  { v: "arabic",   label: "Arabic" },
  { v: "other",    label: "Other (let Gemini detect)" },
];

const STYLE_OPTIONS = [
  { v: "photoreal", label: "Photorealistic" },
  { v: "cinematic", label: "Cinematic film" },
  { v: "3d_pixar", label: "3D Pixar" },
  { v: "anime", label: "Anime" },
  { v: "watercolor", label: "Watercolor" },
  { v: "comic", label: "Comic book" },
];

type AnimationOption = {
  v: string;
  label: string;
  desc: string;
  cls: string;
};

const ANIMATION_OPTIONS: AnimationOption[] = [
  { v: "mixed",     label: "Mixed",       desc: "Each scene different",    cls: "anim-mixed" },
  { v: "ken_burns", label: "Ken Burns",   desc: "Classic slow zoom + pan", cls: "anim-ken-burns" },
  { v: "zoom_in",   label: "Zoom in",     desc: "Punchy push-in",          cls: "anim-zoom-in" },
  { v: "zoom_out",  label: "Zoom out",    desc: "Reveal, pulls back",      cls: "anim-zoom-out" },
  { v: "pan_lr",    label: "Pan L → R",   desc: "Horizontal sweep",        cls: "anim-pan-lr" },
  { v: "pan_rl",    label: "Pan R → L",   desc: "Reverse sweep",           cls: "anim-pan-rl" },
  { v: "pulse",     label: "Pulse",       desc: "Rhythmic zoom",           cls: "anim-pulse" },
  { v: "none",      label: "Static",      desc: "No motion (fastest)",     cls: "" },
];

const MAX_FILES = 50;
const POLL_MS = 1500;

/**
 * Cost-estimate constants. These are conservative ballpark figures the
 * UI uses to set expectations before a render — they intentionally err
 * slightly high so users aren't surprised by a bigger Gemini bill.
 *
 * Updated against current Google AI pricing (see your Cloud billing for
 * exact numbers per project). Treat as ranges, not invoices.
 */
const COST_PER_IMAGE_INR = 2.5;        // Gemini 2.5 Flash Image (~$0.03)
const COST_PER_PLAN_CHUNK_INR = 0.4;   // Gemini Flash audio listen, per ~75s chunk
const PLAN_CHUNK_SIZE_SEC = 75;

/** Stable key for a File object — used to memo per-file probe results. */
function fileKey(f: File): string {
  return `${f.name}|${f.size}|${f.lastModified}`;
}

/**
 * Given a duration in seconds and the chosen segment length, return
 * { scenes, planChunks, cost } for the estimate panel.
 */
function estimateForDuration(
  durationSec: number,
  segmentSec: number,
): { scenes: number; planChunks: number; cost: number } {
  if (!Number.isFinite(durationSec) || durationSec <= 0) {
    return { scenes: 0, planChunks: 0, cost: 0 };
  }
  const scenes = Math.max(1, Math.round(durationSec / Math.max(1, segmentSec)));
  const planChunks = Math.max(1, Math.ceil(durationSec / PLAN_CHUNK_SIZE_SEC));
  const cost =
    scenes * COST_PER_IMAGE_INR + planChunks * COST_PER_PLAN_CHUNK_INR;
  return { scenes, planChunks, cost };
}

/** Format seconds as "1m 23s" or "23s" — for the estimate panel. */
function formatDuration(s: number): string {
  if (!Number.isFinite(s) || s <= 0) return "0s";
  const m = Math.floor(s / 60);
  const ss = Math.round(s % 60);
  return m > 0 ? `${m}m ${ss}s` : `${ss}s`;
}

export default function AudioToVideoPage() {
  const { state, refresh } = useMe();
  const me = state.status === "ready" ? state.me : null;
  const ready = state.status === "ready";

  const [files, setFiles] = useState<File[]>([]);
  const [label, setLabel] = useState("");
  const [size, setSize] = useState("9:16");
  const [stylePreset, setStylePreset] = useState("photoreal");
  // Default = "auto" (Gemini paces scenes to match audio rhythm). User
  // can flip to a fixed number from the Advanced toggle for power-user
  // control. Stored as number|"auto" so we don't lose intent.
  const [segmentSeconds, setSegmentSeconds] = useState<number | "auto">(
    "auto",
  );
  const [animationStyle, setAnimationStyle] = useState("mixed");
  const [audioLanguage, setAudioLanguage] = useState("auto");

  /**
   * Per-file audio duration in seconds, keyed by a stable file id
   * (name + size + lastModified). Populated lazily once a file is added
   * by loading it into a hidden <audio> element.
   *
   * `undefined` → still probing
   * `null`      → probe failed (treat as 0 in totals)
   */
  const [durations, setDurations] = useState<
    Record<string, number | null>
  >({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitNotice, setSubmitNotice] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Hosted users (default) don't need a Gemini key — platform-paid. Only
  // BYO mode (code-license users) needs a personal key on file.
  const needsKey = !!me?.byoMode;
  const hasKey = !!me?.geminiKeyMask;
  const remainingMinutes = !me
    ? 0
    : me.unlimited
      ? Number.POSITIVE_INFINITY
      : Math.max(0, me.minutesLimit - me.minutesUsed) + (me.topUpMinutesRemaining || 0);
  const overLimit = !!me && !me.unlimited && remainingMinutes <= 0;

  // Pull the user's recent jobs every POLL_MS while there's anything active.
  // Once nothing is active we slow down to once every 6s so resting isn't
  // burning Mongo reads.
  const refreshJobs = useCallback(async () => {
    if (!ready) return;
    try {
      const res = await apiClient.listJobs({ limit: 50 });
      setJobs(res.items);
    } catch {
      // ignore — auth may be in flux
    }
  }, [ready]);

  useEffect(() => {
    refreshJobs();
  }, [refreshJobs]);

  useEffect(() => {
    const anyActive = jobs.some(
      (j) => j.status === "queued" || j.status === "running",
    );
    const interval = anyActive ? POLL_MS : 6000;
    const id = setInterval(refreshJobs, interval);
    return () => clearInterval(id);
  }, [jobs, refreshJobs]);

  // Hosted users never need a personal key — only BYO plans do.
  const missingByoKey = needsKey && !hasKey;
  const disabledControls =
    submitting || files.length === 0 || missingByoKey;

  // Aggregate estimate across all picked files. `probing` flags the
  // panel as "still calculating" so we don't flash a wrong total before
  // metadata loads. `unknownCount` files contribute 0 to the totals.
  const estimate = (() => {
    let totalSec = 0;
    let totalScenes = 0;
    let totalPlanChunks = 0;
    let totalCost = 0;
    let probingCount = 0;
    let unknownCount = 0;
    for (const f of files) {
      const d = durations[fileKey(f)];
      if (d === undefined) {
        probingCount += 1;
        continue;
      }
      if (d === null) {
        unknownCount += 1;
        continue;
      }
      totalSec += d;
      // Auto-pacing uses Gemini-decided per-scene duration. For the
      // pre-submit estimate we use ~3s/scene as a sensible average.
      const segForEstimate =
        segmentSeconds === "auto" ? 3.0 : segmentSeconds;
      const e = estimateForDuration(d, segForEstimate);
      totalScenes += e.scenes;
      totalPlanChunks += e.planChunks;
      totalCost += e.cost;
    }
    return {
      totalSec,
      totalScenes,
      totalPlanChunks,
      totalCost,
      probingCount,
      unknownCount,
      knownCount: files.length - probingCount - unknownCount,
    };
  })();

  function pickFiles(picked: FileList | null) {
    if (!picked) return;
    const arr = Array.from(picked).slice(0, MAX_FILES);
    setFiles(arr);
    setSubmitError(null);
    setSubmitNotice(null);
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  // Probe duration for any newly-added file. We use a hidden Audio
  // element to read `duration` from the metadata — no server round-trip
  // needed. Object URLs revoked after read so memory doesn't leak.
  useEffect(() => {
    let cancelled = false;
    files.forEach((f) => {
      const id = fileKey(f);
      if (durations[id] !== undefined) return; // already probed (success or fail)
      const url = URL.createObjectURL(f);
      const a = new Audio();
      a.preload = "metadata";
      a.src = url;
      const finalize = (val: number | null) => {
        URL.revokeObjectURL(url);
        if (cancelled) return;
        setDurations((prev) => ({ ...prev, [id]: val }));
      };
      a.onloadedmetadata = () => {
        const d = Number.isFinite(a.duration) ? a.duration : null;
        finalize(d);
      };
      a.onerror = () => finalize(null);
    });
    return () => {
      cancelled = true;
    };
  }, [files, durations]);


  async function submit() {
    if (files.length === 0) return;
    setSubmitting(true);
    setSubmitError(null);
    setSubmitNotice(null);
    try {
      const res = await apiClient.submitAudioToVideo(files, {
        label: label.trim(),
        size,
        stylePreset,
        segmentSeconds,
        animationStyle,
        audioLanguage,
      });
      setFiles([]);
      if (inputRef.current) inputRef.current.value = "";
      const parts: string[] = [];
      if (res.summary.queued > 0) parts.push(`${res.summary.queued} queued`);
      if (res.summary.blocked > 0)
        parts.push(`${res.summary.blocked} need an upgrade to render`);
      if (res.summary.rejected > 0)
        parts.push(`${res.summary.rejected} rejected`);
      setSubmitNotice(parts.join(" · ") || "Submitted.");
      await refreshJobs();
      await refresh();
    } catch (e) {
      setSubmitError(
        e instanceof ApiError ? e.message : "Submission failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  // Captions jobs are follow-ups on a parent video — render them inline
  // on the parent's card, not as separate top-level cards.
  const audioToVideoJobs = jobs.filter((j) => j.tool === "audio-to-video");
  const captionsJobs = jobs.filter((j) => j.tool === "captions");

  // Map parent-video job id → most recent captions job for that parent.
  const captionsByParent = new Map<string, Job>();
  for (const c of captionsJobs) {
    const parentId =
      typeof c.params?.parentJobId === "string"
        ? (c.params.parentJobId as string)
        : null;
    if (!parentId) continue;
    const existing = captionsByParent.get(parentId);
    // Most recent wins (jobs come back newest-first from the API).
    if (!existing) captionsByParent.set(parentId, c);
  }

  const queuedOrRunning = audioToVideoJobs.filter(
    (j) => j.status === "queued" || j.status === "running",
  );
  const blocked = audioToVideoJobs.filter((j) => j.status === "blocked");
  const finished = audioToVideoJobs.filter(
    (j) =>
      j.status === "done" ||
      j.status === "failed" ||
      j.status === "cancelled",
  );

  return (
    <div className="px-6 md:px-10 py-10 md:py-14 max-w-[1320px] mx-auto">
      <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
        Tool
      </div>
      <h1 className="mt-3 font-display text-[28px] md:text-[36px] tracking-[-0.035em] leading-[1.05]">
        Audio to Video
      </h1>
      <p className="mt-4 text-[15px] leading-[1.7] text-[var(--muted)] max-w-[640px]">
        Upload up to {MAX_FILES} audio files at once. We render each one in
        parallel. Settings below apply to every file in this batch.
      </p>

      {state.status === "unauthenticated" && (
        <Banner kind="warn">
          You aren&apos;t signed in. Pick a dev user from the ⚡ menu in the topbar.
        </Banner>
      )}
      {state.status === "ready" && needsKey && !hasKey && (
        <Banner kind="warn">
          You&apos;re on a self-hosted / BYO-key plan and haven&apos;t saved a
          Gemini API key yet.{" "}
          <Link
            href="/settings/api-keys"
            className="text-[var(--accent)] underline underline-offset-2"
          >
            Add one in Settings
          </Link>{" "}
          before rendering.
        </Banner>
      )}
      {state.status === "ready" && overLimit && (
        <Banner kind="warn">
          You&apos;ve used all your minutes ({me!.minutesUsed.toFixed(1)} /{" "}
          {me!.minutesLimit.toFixed(0)} min). Files you upload below will be
          saved but won&apos;t start rendering until you{" "}
          <Link
            href="/pricing"
            className="text-[var(--accent)] underline underline-offset-2"
          >
            upgrade or buy a top-up
          </Link>
          .
        </Banner>
      )}

      <div className="mt-10 grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6">
        {/* LEFT: upload + options */}
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6 md:p-8">
          <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
            Step 1
          </div>
          <h2 className="mt-2 font-display text-[20px] tracking-tight text-white">
            Pick audio files
          </h2>

          <label
            htmlFor="audio-input"
            className={`mt-5 flex flex-col items-center justify-center gap-2 px-6 py-10 rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
              files.length
                ? "border-[var(--accent)]/50 bg-[var(--accent)]/5"
                : "border-[var(--line)] hover:border-[var(--accent)]/40 bg-[var(--bg)]"
            }`}
          >
            <span className="text-[14px] text-white">
              {files.length
                ? `${files.length} file${files.length === 1 ? "" : "s"} selected`
                : "Click to pick audio files"}
            </span>
            <span className="text-[11.5px] text-[var(--muted)] font-mono text-center">
              mp3, m4a, wav, aac, ogg, flac · 50 MB each · up to {MAX_FILES} at once
            </span>
            <input
              ref={inputRef}
              id="audio-input"
              type="file"
              accept="audio/*"
              multiple
              className="hidden"
              onChange={(e) => pickFiles(e.target.files)}
              disabled={submitting}
            />
          </label>

          {files.length > 0 && (
            <ul className="mt-3 max-h-[240px] overflow-y-auto rounded-lg border border-[var(--line)] divide-y divide-[var(--line)]">
              {files.map((f, i) => (
                <li
                  key={`${f.name}-${i}`}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-[13px]"
                >
                  <span className="truncate text-white">{f.name}</span>
                  <span className="flex items-center gap-3 shrink-0">
                    <span className="text-[11px] font-mono text-[var(--muted)]">
                      {(f.size / 1024 / 1024).toFixed(2)} MB
                    </span>
                    <button
                      type="button"
                      onClick={() => removeFile(i)}
                      disabled={submitting}
                      className="text-[var(--muted)] hover:text-red-400 text-[14px]"
                      aria-label={`Remove ${f.name}`}
                    >
                      ×
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}

          {/* Style picker */}
          <div className="mt-6">
            <div className="flex items-baseline justify-between mb-3">
              <span className="block text-[11px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono">
                Style
              </span>
              <span className="text-[11px] font-mono text-[var(--muted)]">
                {STYLE_OPTIONS.find((s) => s.v === stylePreset)?.label}
              </span>
            </div>
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-2.5">
              {STYLE_OPTIONS.map((s) => {
                const active = stylePreset === s.v;
                return (
                  <button
                    key={s.v}
                    type="button"
                    onClick={() => !submitting && setStylePreset(s.v)}
                    disabled={submitting}
                    aria-pressed={active}
                    title={s.label}
                    className={`group relative aspect-square rounded-lg overflow-hidden border-2 transition-all ${
                      active
                        ? "border-[var(--accent)] ring-2 ring-[var(--accent)]/30"
                        : "border-[var(--line)] hover:border-[var(--line-2)]"
                    } ${submitting ? "opacity-60 cursor-not-allowed" : ""}`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={`/style-previews/${s.v}.jpg`}
                      alt={s.label}
                      loading="lazy"
                      className="absolute inset-0 w-full h-full object-cover"
                    />
                    <div className="absolute inset-x-0 bottom-0 px-2 py-1.5 bg-gradient-to-t from-black/85 to-transparent">
                      <div className="text-[10.5px] font-medium text-white truncate">
                        {s.label}
                      </div>
                    </div>
                    {active && <CheckBadge />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Animation picker */}
          <div className="mt-6">
            <div className="flex items-baseline justify-between mb-3">
              <span className="block text-[11px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono">
                Animation
              </span>
              <span className="text-[11px] font-mono text-[var(--muted)]">
                {ANIMATION_OPTIONS.find((a) => a.v === animationStyle)?.label}
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5">
              {ANIMATION_OPTIONS.map((a) => {
                const active = animationStyle === a.v;
                return (
                  <button
                    key={a.v}
                    type="button"
                    onClick={() => !submitting && setAnimationStyle(a.v)}
                    disabled={submitting}
                    aria-pressed={active}
                    title={a.desc}
                    className={`group relative aspect-[4/5] rounded-lg overflow-hidden border-2 transition-all bg-black ${
                      active
                        ? "border-[var(--accent)] ring-2 ring-[var(--accent)]/30"
                        : "border-[var(--line)] hover:border-[var(--line-2)]"
                    } ${submitting ? "opacity-60 cursor-not-allowed" : ""}`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src="/style-previews/photoreal.jpg"
                      alt={a.label}
                      loading="lazy"
                      className={`absolute inset-0 ${a.cls ? "anim-preview-img " + a.cls : "w-full h-full object-cover"}`}
                    />
                    <div className="absolute inset-x-0 bottom-0 px-2 py-1.5 bg-gradient-to-t from-black/90 via-black/60 to-transparent">
                      <div className="text-[10.5px] font-medium text-white truncate">
                        {a.label}
                      </div>
                      <div className="text-[9px] font-mono text-white/60 truncate">
                        {a.desc}
                      </div>
                    </div>
                    {active && <CheckBadge />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Other options */}
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="Aspect ratio">
              <select
                value={size}
                onChange={(e) => setSize(e.target.value)}
                disabled={submitting}
                className="tool-input"
              >
                {SIZE_OPTIONS.map((o) => (
                  <option key={o.v} value={o.v}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label="Audio language"
              hint="Helps Gemini understand non-English speech. Image prompts stay in English."
            >
              <select
                value={audioLanguage}
                onChange={(e) => setAudioLanguage(e.target.value)}
                disabled={submitting}
                className="tool-input"
              >
                {AUDIO_LANGUAGE_OPTIONS.map((o) => (
                  <option key={o.v} value={o.v}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label={
                segmentSeconds === "auto"
                  ? "Scene pacing · Auto (match audio)"
                  : `Seconds per scene · ${segmentSeconds.toFixed(1)}s`
              }
              hint={
                segmentSeconds === "auto"
                  ? "Gemini decides scene length from the audio rhythm (1.5s–6s)."
                  : "Lower = more scenes = more API spend"
              }
            >
              {segmentSeconds === "auto" ? (
                <div className="flex items-center justify-between gap-2 rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm">
                  <span className="text-white font-mono">Auto</span>
                  <button
                    type="button"
                    onClick={() => setSegmentSeconds(2.5)}
                    disabled={submitting}
                    className="text-xs text-[var(--accent)] hover:underline disabled:opacity-50"
                  >
                    Advanced…
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  <input
                    type="range"
                    min={1.5}
                    max={6}
                    step={0.5}
                    value={segmentSeconds}
                    onChange={(e) =>
                      setSegmentSeconds(Number(e.target.value))
                    }
                    disabled={submitting}
                    className="w-full h-11 accent-[var(--accent)]"
                  />
                  <button
                    type="button"
                    onClick={() => setSegmentSeconds("auto")}
                    disabled={submitting}
                    className="text-xs text-[var(--muted)] hover:text-[var(--accent)]"
                  >
                    ← Back to Auto
                  </button>
                </div>
              )}
            </Field>
            <div className="md:col-span-2">
              <Field
                label="Label (optional)"
                hint="Applied to every file in this batch"
              >
                <input
                  type="text"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="e.g. episode 12"
                  maxLength={80}
                  className="tool-input"
                  disabled={submitting}
                />
              </Field>
            </div>
          </div>

          {/* Estimate panel — appears as soon as files are picked. Shows
              total scenes + cost so the user sees what their Gemini bill
              will look like BEFORE hitting render. */}
          {files.length > 0 && (
            <EstimatePanel
              files={files}
              estimate={estimate}
              segmentSeconds={segmentSeconds}
            />
          )}

          <div className="mt-4 flex items-center gap-3 flex-wrap">
            <button
              type="button"
              onClick={submit}
              disabled={disabledControls}
              className="inline-flex h-11 items-center px-5 rounded-full bg-[var(--accent)] text-black text-[13px] font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting
                ? "Submitting…"
                : files.length === 0
                  ? "Pick at least 1 file"
                  : `Render ${files.length} video${files.length === 1 ? "" : "s"} →`}
            </button>
            {submitNotice && !submitError && (
              <span className="text-[12.5px] text-[var(--accent)] font-mono">
                {submitNotice}
              </span>
            )}
            {submitError && (
              <span className="text-[12.5px] text-red-300 font-mono">
                ✕ {submitError}
              </span>
            )}
          </div>
        </div>

        {/* RIGHT: live worker status */}
        <div className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <WorkerStatus jobs={queuedOrRunning} />
        </div>
      </div>

      {/* Job lists */}
      {(queuedOrRunning.length > 0 ||
        blocked.length > 0 ||
        finished.length > 0) && (
        <div className="mt-10 space-y-8">
          {queuedOrRunning.length > 0 && (
            <Section title="In progress" count={queuedOrRunning.length}>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {queuedOrRunning.map((j) => (
                  <JobCard
                    key={j.id}
                    job={j}
                    captionsJob={captionsByParent.get(j.id)}
                    onRefresh={refreshJobs}
                  />
                ))}
              </div>
            </Section>
          )}
          {blocked.length > 0 && (
            <Section title="Waiting on upgrade" count={blocked.length}>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {blocked.map((j) => (
                  <JobCard
                    key={j.id}
                    job={j}
                    captionsJob={captionsByParent.get(j.id)}
                    onRefresh={refreshJobs}
                  />
                ))}
              </div>
            </Section>
          )}
          {finished.length > 0 && (
            <RecentRenders
              jobs={finished}
              captionsByParent={captionsByParent}
              onRefresh={refreshJobs}
            />
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- Helper components ---------- */

function CheckBadge() {
  return (
    <div className="absolute top-1.5 right-1.5 h-5 w-5 rounded-full bg-[var(--accent)] flex items-center justify-center">
      <svg
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="black"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <polyline points="20 6 9 17 4 12" />
      </svg>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-[11px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono mb-1.5">
        {label}
      </span>
      {children}
      {hint && (
        <span className="mt-1 block text-[11px] text-[var(--muted)]">{hint}</span>
      )}
    </label>
  );
}

function Banner({
  kind,
  children,
}: {
  kind: "warn" | "info";
  children: React.ReactNode;
}) {
  const tone =
    kind === "warn"
      ? "border-yellow-500/40 bg-yellow-500/5 text-yellow-100"
      : "border-[var(--accent)]/40 bg-[var(--accent)]/5 text-white";
  return (
    <div className={`mt-6 rounded-xl border p-4 text-[13.5px] leading-[1.6] ${tone}`}>
      {children}
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
          {title}
        </span>
        <span className="h-px flex-1 bg-[var(--line)]" />
        <span className="text-[11px] font-mono text-[var(--muted)]">
          {count} {count === 1 ? "job" : "jobs"}
        </span>
      </div>
      {children}
    </div>
  );
}

function WorkerStatus({ jobs }: { jobs: Job[] }) {
  const running = jobs.filter((j) => j.status === "running");
  const queued = jobs.filter((j) => j.status === "queued");

  if (jobs.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6">
        <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
          Worker pool
        </div>
        <p className="mt-3 text-[13px] text-[var(--muted)] leading-[1.65]">
          Idle. Submit a batch to start rendering.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--accent)]/40 bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--accent)] font-mono">
          Worker pool
        </span>
        <span className="text-[11px] font-mono text-[var(--muted)]">
          {running.length} running · {queued.length} queued
        </span>
      </div>
      <ul className="mt-4 space-y-3">
        {running.map((j) => (
          <li key={j.id}>
            <div className="flex items-center justify-between gap-2 text-[12px] mb-1">
              <span className="truncate text-white">
                {j.audioFilename ?? j.id.slice(0, 8)}
              </span>
              <span className="text-[10px] font-mono text-[var(--muted)] shrink-0">
                {j.progress}%
              </span>
            </div>
            <div className="h-1 w-full rounded-full bg-[var(--bg)] overflow-hidden">
              <div
                className="h-full bg-[var(--accent)] transition-all"
                style={{ width: `${j.progress}%` }}
              />
            </div>
            <div className="mt-1 text-[10.5px] font-mono text-[var(--muted)] truncate">
              {j.message ?? ""} {j.workerName ? `· ${j.workerName}` : ""}
            </div>
          </li>
        ))}
        {queued.length > 0 && (
          <li className="text-[11px] font-mono text-[var(--muted)] pt-2 border-t border-[var(--line)]">
            +{queued.length} waiting in queue
          </li>
        )}
      </ul>
    </div>
  );
}

/* ---------- Recent renders (compact grid + filter chips) ---------- */

type RecentFilter = "all" | "done" | "failed" | "cancelled";

const RECENT_PAGE_SIZE = 10;  // 2 rows × 5 columns

function RecentRenders({
  jobs,
  captionsByParent,
  onRefresh,
}: {
  jobs: Job[];
  captionsByParent: Map<string, Job>;
  onRefresh?: () => Promise<void> | void;
}) {
  const [filter, setFilter] = useState<RecentFilter>("done");
  const [page, setPage] = useState(0);
  const [captionsOpenId, setCaptionsOpenId] = useState<string | null>(null);

  const counts = {
    all: jobs.length,
    done: jobs.filter((j) => j.status === "done").length,
    failed: jobs.filter((j) => j.status === "failed").length,
    cancelled: jobs.filter((j) => j.status === "cancelled").length,
  };

  const visible = useMemo(
    () => (filter === "all" ? jobs : jobs.filter((j) => j.status === filter)),
    [jobs, filter],
  );

  // Reset to page 0 when filter changes or list shrinks below current page.
  const totalPages = Math.max(1, Math.ceil(visible.length / RECENT_PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  if (safePage !== page) {
    // Defer to avoid setState-during-render warning. setTimeout = next tick.
    setTimeout(() => setPage(safePage), 0);
  }

  const start = safePage * RECENT_PAGE_SIZE;
  const pageItems = visible.slice(start, start + RECENT_PAGE_SIZE);

  return (
    <div>
      {/* Header + filter chips */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
          Recent renders
        </span>
        <span className="h-px flex-1 bg-[var(--line)] min-w-[20px]" />
        <div className="flex items-center gap-1">
          {(
            [
              { v: "all", label: "All" },
              { v: "done", label: "Done" },
              { v: "failed", label: "Failed" },
              { v: "cancelled", label: "Cancelled" },
            ] as Array<{ v: RecentFilter; label: string }>
          ).map((c) => {
            const active = filter === c.v;
            const n = counts[c.v];
            const disabled = n === 0 && c.v !== "all";
            return (
              <button
                key={c.v}
                type="button"
                onClick={() => {
                  setFilter(c.v);
                  setPage(0);
                }}
                disabled={disabled}
                className={`inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full text-[11.5px] font-mono transition-colors ${
                  active
                    ? "bg-[var(--accent)] text-black"
                    : "border border-[var(--line)] text-[var(--muted)] hover:text-white hover:border-[var(--line-2)]"
                } ${disabled ? "opacity-40 cursor-not-allowed" : ""}`}
              >
                {c.label}
                <span
                  className={`text-[10px] ${active ? "text-black/70" : "text-[var(--muted)]"}`}
                >
                  {n}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Thumbnail grid — 5 cols at lg+, fewer at smaller breakpoints */}
      {visible.length === 0 ? (
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-8 text-center text-[13px] text-[var(--muted)]">
          No renders match this filter.
        </div>
      ) : (
        <>
          <ul className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {pageItems.map((j) => (
              <li key={j.id}>
                <RecentRenderCard
                  job={j}
                  captionsJob={captionsByParent.get(j.id)}
                  captionsOpen={captionsOpenId === j.id}
                  onToggleCaptions={() =>
                    setCaptionsOpenId((cur) => (cur === j.id ? null : j.id))
                  }
                  onRefresh={onRefresh}
                />
              </li>
            ))}
          </ul>

          {/* Pagination */}
          {totalPages > 1 && (
            <Pagination
              page={safePage}
              totalPages={totalPages}
              total={visible.length}
              pageSize={RECENT_PAGE_SIZE}
              onPage={(p) => {
                setPage(p);
                setCaptionsOpenId(null);
              }}
            />
          )}
        </>
      )}

    </div>
  );
}

/**
 * Compact card: thumbnail on top, then filename, status, and a row of
 * three small buttons — Play, Download, Captions. The captions UI lives
 * in a collapsible drawer that opens below the card on click.
 */
function RecentRenderCard({
  job,
  captionsJob,
  captionsOpen,
  onToggleCaptions,
  onRefresh,
}: {
  job: Job;
  captionsJob?: Job;
  captionsOpen: boolean;
  onToggleCaptions: () => void;
  onRefresh?: () => Promise<void> | void;
}) {
  const opts = (job.params?.options ?? {}) as Record<string, unknown>;
  const sizeKey = typeof opts.size === "string" ? (opts.size as string) : "9:16";
  const aspectCls = aspectClassFor(sizeKey);
  // Cache-bust whenever the active-captions pointer changes so the
  // browser actually refetches when the user swaps style or removes.
  const cacheKey = job.activeCaptionsJobId ?? "orig";
  const url = apiClient.jobOutputUrl(job.id, { cacheKey });
  const name = job.audioFilename ?? `Job ${job.id.slice(0, 8)}`;

  const isDone = job.status === "done";
  const isFailed = job.status === "failed";
  const isCancelled = job.status === "cancelled";
  const captionsActive = !!job.activeCaptionsJobId;

  // When `playing`, the thumb swaps from "muted hover-preview" to a real
  // <video controls> player so the user can scrub, fullscreen, etc.
  const [playing, setPlaying] = useState(false);
  const playerRef = useRef<HTMLVideoElement | null>(null);

  // Live preview state pushed up by CaptionsPanel — null when the user
  // isn't actively editing (panel closed, or a captions render is in
  // progress / done). Drives the on-thumb overlay.
  const [captionPreview, setCaptionPreview] =
    useState<CaptionPreviewSpec | null>(null);
  // Drag-set fractional position (lifted up here so the modal's video
  // overlay and CaptionsPanel's submit() can both read it).
  const [captionPosX, setCaptionPosX] = useState<number | null>(null);
  const [captionPosY, setCaptionPosY] = useState<number | null>(null);

  // Drawer closed → drop any stale preview so the overlay disappears
  // even if CaptionsPanel was unmounted before its cleanup ran. Also
  // reset the drag position so reopening starts fresh.
  useEffect(() => {
    if (!captionsOpen) {
      setCaptionPreview(null);
      setCaptionPosX(null);
      setCaptionPosY(null);
    }
  }, [captionsOpen]);

  // Captions tab can show "(N done)" hint when there's an active job.
  const captionsBadge = captionsJob
    ? captionsJob.status === "done"
      ? "✓"
      : captionsJob.status === "running" || captionsJob.status === "queued"
        ? "…"
        : null
    : null;

  return (
    <div
      className={`rounded-lg overflow-hidden border bg-[var(--surface)] ${
        captionsOpen
          ? "border-[var(--accent)]/50"
          : playing
            ? "border-[var(--accent)]/40"
            : isFailed
              ? "border-red-500/30"
              : "border-[var(--line)]"
      }`}
    >
      {/* Thumb — click to play. While playing it becomes a real <video controls>
          player. Otherwise it's a hover-preview muted loop with a center ▶
          overlay so the play affordance is obvious. */}
      <div
        className={`relative ${aspectCls} bg-black overflow-hidden`}
      >
        {isDone ? (
          playing ? (
            <video
              ref={playerRef}
              src={url}
              controls
              autoPlay
              loop
              playsInline
              className="absolute inset-0 w-full h-full object-contain"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <button
              type="button"
              onClick={() => setPlaying(true)}
              className="group absolute inset-0 w-full h-full block"
              aria-label="Play"
            >
              <video
                src={url}
                muted
                loop
                playsInline
                preload="metadata"
                className="absolute inset-0 w-full h-full object-cover"
                onMouseEnter={(e) => {
                  const v = e.currentTarget;
                  v.currentTime = 0;
                  v.play().catch(() => {});
                }}
                onMouseLeave={(e) => {
                  const v = e.currentTarget;
                  v.pause();
                  v.currentTime = 0;
                }}
              />
              {/* Center play overlay so it's obvious the thumb is clickable */}
              <span className="absolute inset-0 flex items-center justify-center opacity-80 group-hover:opacity-100 transition-opacity">
                <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-black/55 backdrop-blur-sm text-white">
                  <PlayIcon />
                </span>
              </span>
            </button>
          )
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-[28px] opacity-30">
            {isFailed ? "✕" : isCancelled ? "⊘" : "·"}
          </div>
        )}

        {/* Caption-style live preview, only when the captions drawer is
            open and the user is editing. Sits on top of everything except
            the actual <video controls> player. */}
        {/* (Captions demo overlay used to live here. It now lives only
            on the bigger video inside CaptionsModal so the small thumb
            doesn't get visually noisy when the modal is open.) */}

        {/* Stop button while playing — small chip in top-left corner so
            the user can collapse back to thumb without losing the cell. */}
        {playing && (
          <button
            type="button"
            onClick={() => {
              if (playerRef.current) {
                try {
                  playerRef.current.pause();
                } catch {
                  /* ignore */
                }
              }
              setPlaying(false);
            }}
            aria-label="Stop"
            className="absolute top-1.5 left-1.5 inline-flex h-6 items-center gap-1 px-1.5 rounded bg-black/60 text-[10px] font-mono uppercase tracking-[0.18em] text-white hover:bg-black/80"
          >
            <StopIcon />
            Stop
          </button>
        )}

        {/* Status pill (top-right) — hidden while playing so it doesn't
            sit on top of the controls. */}
        {!playing && (
          <div className="absolute top-1.5 right-1.5 flex items-center gap-1">
            {isDone && captionsActive && (
              <span
                className="text-[9px] font-mono uppercase tracking-[0.18em] bg-[var(--accent)] text-black px-1.5 py-0.5 rounded"
                title={`Captions: ${job.activeCaptionsStyle ?? "on"}`}
              >
                CC
              </span>
            )}
            {isDone && (
              <span className="text-[9px] font-mono uppercase tracking-[0.18em] bg-black/60 text-[var(--accent)] px-1.5 py-0.5 rounded">
                done
              </span>
            )}
            {isFailed && (
              <span className="text-[9px] font-mono uppercase tracking-[0.18em] bg-black/60 text-red-300 px-1.5 py-0.5 rounded">
                failed
              </span>
            )}
            {isCancelled && (
              <span className="text-[9px] font-mono uppercase tracking-[0.18em] bg-black/60 text-[var(--muted)] px-1.5 py-0.5 rounded">
                cancelled
              </span>
            )}
          </div>
        )}
      </div>

      {/* Meta + buttons */}
      <div className="p-2.5">
        <div className="text-[11.5px] text-white truncate" title={name}>
          {name}
        </div>
        {!isDone && isFailed && (
          <>
            {job.errorDetail && (
              <p className="mt-1 text-[10px] font-mono text-red-300 line-clamp-2 leading-[1.4]">
                {job.errorDetail.split("\n")[0]}
              </p>
            )}
            <div className="mt-1.5">
              <RetryButton jobId={job.id} onDone={onRefresh} compact />
            </div>
          </>
        )}

        {isDone && job.frameQuality && (
          <FrameQualityBadge quality={job.frameQuality} />
        )}

        {isDone && (
          <div className="mt-2 flex items-center gap-1.5">
            <a
              href={url}
              download
              title="Download mp4"
              className="flex-1 inline-flex h-7 items-center justify-center gap-1 px-2 rounded-md border border-[var(--line)] text-[11px] text-white hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
            >
              <DownloadIcon /> Download
            </a>
            <button
              type="button"
              onClick={onToggleCaptions}
              title="Captions"
              className={`inline-flex h-7 items-center justify-center gap-1 px-2 rounded-md text-[11px] transition-colors ${
                captionsOpen
                  ? "bg-[var(--accent)]/15 border border-[var(--accent)]/50 text-[var(--accent)]"
                  : "border border-[var(--line)] text-white hover:border-[var(--accent)] hover:text-[var(--accent)]"
              }`}
            >
              <CaptionsIcon />
              {captionsBadge && (
                <span className="text-[10px] font-mono">{captionsBadge}</span>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Captions modal — 2-column popup with the video preview on the
          left and the picker on the right. Floats over the page so the
          grid stays put. */}
      {isDone && captionsOpen && (
        <CaptionsModal
          parentJob={job}
          captionsJob={captionsJob}
          aspectCls={aspectCls}
          onClose={onToggleCaptions}
          onRefresh={onRefresh}
          captionPreview={captionPreview}
          onPreviewChange={setCaptionPreview}
          posXFrac={captionPosX}
          posYFrac={captionPosY}
          onPositionChange={(x, y) => {
            setCaptionPosX(x);
            setCaptionPosY(y);
          }}
        />
      )}
    </div>
  );
}

function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPage: (p: number) => void;
}) {
  const start = page * pageSize + 1;
  const end = Math.min(total, (page + 1) * pageSize);
  return (
    <div className="mt-5 flex items-center justify-between gap-3 flex-wrap">
      <span className="text-[11px] font-mono text-[var(--muted)]">
        {start}–{end} of {total}
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPage(Math.max(0, page - 1))}
          disabled={page === 0}
          className="inline-flex h-8 items-center px-3 rounded-md border border-[var(--line)] text-[12px] text-white hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ← Prev
        </button>
        {/* Numbered buttons — show up to 7 with ellipses if more */}
        {pageNumbers(page, totalPages).map((p, i) =>
          p === "…" ? (
            <span
              key={`gap-${i}`}
              className="px-2 text-[12px] text-[var(--muted)] font-mono"
            >
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              onClick={() => onPage(p)}
              className={`inline-flex h-8 min-w-8 items-center justify-center px-2 rounded-md text-[12px] font-mono transition-colors ${
                p === page
                  ? "bg-[var(--accent)] text-black"
                  : "border border-[var(--line)] text-[var(--muted)] hover:text-white"
              }`}
            >
              {p + 1}
            </button>
          ),
        )}
        <button
          type="button"
          onClick={() => onPage(Math.min(totalPages - 1, page + 1))}
          disabled={page >= totalPages - 1}
          className="inline-flex h-8 items-center px-3 rounded-md border border-[var(--line)] text-[12px] text-white hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Next →
        </button>
      </div>
    </div>
  );
}

/**
 * Compute a list of page indices to render in the pagination strip.
 * Always shows first + last; collapses long runs in the middle with "…".
 */
function pageNumbers(page: number, total: number): (number | "…")[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i);
  }
  const out: (number | "…")[] = [0];
  const lo = Math.max(1, page - 1);
  const hi = Math.min(total - 2, page + 1);
  if (lo > 1) out.push("…");
  for (let i = lo; i <= hi; i++) out.push(i);
  if (hi < total - 2) out.push("…");
  out.push(total - 1);
  return out;
}

function PlayIcon() {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
    >
      <polygon points="6,4 20,12 6,20" />
    </svg>
  );
}

/**
 * Pre-submit estimate. Updates as the user picks files or tweaks the
 * scene-length slider. Conservative ballpark — invoice may be slightly
 * lower (free quotas, cache hits, fallback frames cost ₹0) but we'd
 * rather under-promise than under-bill.
 */
function EstimatePanel({
  files,
  estimate,
  segmentSeconds,
}: {
  files: File[];
  estimate: {
    totalSec: number;
    totalScenes: number;
    totalPlanChunks: number;
    totalCost: number;
    probingCount: number;
    unknownCount: number;
    knownCount: number;
  };
  segmentSeconds: number | "auto";
}) {
  const {
    totalSec,
    totalScenes,
    totalCost,
    probingCount,
    unknownCount,
    knownCount,
  } = estimate;

  const probing = probingCount > 0 && knownCount === 0;
  const partial = probingCount > 0 && knownCount > 0;
  const tooManyUnknowns = unknownCount > 0;

  return (
    <div className="mt-6 rounded-xl border border-[var(--accent)]/30 bg-[var(--accent)]/5 p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-blink" />
          <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--accent)] font-mono">
            Estimate
          </span>
        </div>
        <span className="text-[10.5px] font-mono text-[var(--muted)]">
          {files.length} file{files.length === 1 ? "" : "s"} ·{" "}
          {segmentSeconds === "auto"
            ? "auto pacing"
            : `${segmentSeconds.toFixed(1)}s per scene`}
        </span>
      </div>

      {probing ? (
        <div className="text-[12.5px] text-[var(--muted)] font-mono">
          Reading audio metadata…
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat
            label="Total audio"
            value={formatDuration(totalSec)}
            hint={partial ? `+${probingCount} probing` : undefined}
          />
          <Stat
            label="Scenes"
            value={String(totalScenes)}
            hint={`≈ ${totalScenes} images`}
          />
          <Stat
            label="Est. cost"
            value={`≈ ₹${totalCost.toFixed(0)}`}
            hint="Gemini Flash + image"
          />
          <Stat
            label="Cost per video"
            value={
              files.length > 0
                ? `≈ ₹${(totalCost / Math.max(1, knownCount || files.length)).toFixed(0)}`
                : "—"
            }
            hint="rough average"
          />
        </div>
      )}

      <div className="mt-3 text-[11px] text-[var(--muted)] leading-[1.55]">
        Approximate Gemini cost based on{" "}
        <span className="font-mono text-[var(--muted)]">
          ₹{COST_PER_IMAGE_INR.toFixed(2)}
        </span>{" "}
        per image. Free-tier quota and Pollinations fallbacks bring the
        actual bill lower in practice.
        {tooManyUnknowns && (
          <span className="block mt-2 text-yellow-200">
            ⚠ {unknownCount} file{unknownCount === 1 ? "" : "s"} couldn&apos;t
            be probed in the browser. Server will read duration on submit.
          </span>
        )}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono">
        {label}
      </div>
      <div className="mt-0.5 font-display text-[18px] tracking-tight text-white">
        {value}
      </div>
      {hint && (
        <div className="text-[10.5px] font-mono text-[var(--muted)]">
          {hint}
        </div>
      )}
    </div>
  );
}

/**
 * Show how many frames came from Gemini, Pollinations (free fallback),
 * and pure placeholder. Quietly hidden if all frames came from Gemini —
 * only surfaces when something needs disclosing.
 */
/**
 * One-click retry for a failed/cancelled job. Calls /me/jobs/{id}/retry
 * which re-queues the same job doc (no re-upload needed). After kicking
 * off, calls `onDone` so the parent grid refreshes and the user sees
 * the job flip from "failed" to "queued".
 */
function RetryButton({
  jobId,
  onDone,
  compact = false,
}: {
  jobId: string;
  onDone?: () => void | Promise<void>;
  compact?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function go() {
    setBusy(true);
    setErr(null);
    try {
      await apiClient.retryJob(jobId);
      if (onDone) await onDone();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Retry failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={go}
        disabled={busy}
        className={
          compact
            ? "inline-flex h-7 items-center px-2.5 rounded-full bg-[var(--accent)] text-black text-[10.5px] font-semibold disabled:opacity-50"
            : "inline-flex h-8 items-center px-3 rounded-full bg-[var(--accent)] text-black text-[11.5px] font-semibold disabled:opacity-50"
        }
      >
        {busy ? "Retrying…" : "↻ Retry"}
      </button>
      {err && (
        <p
          className={`font-mono text-red-300 ${
            compact ? "text-[10px]" : "text-[11px]"
          }`}
        >
          {err}
        </p>
      )}
    </div>
  );
}

function FrameQualityBadge({
  quality,
}: {
  quality: NonNullable<Job["frameQuality"]>;
}) {
  const { totalFrames, geminiFrames, pollinationsFrames, placeholderFrames } =
    quality;
  // Nothing to surface — all primary. Hide.
  if (pollinationsFrames === 0 && placeholderFrames === 0) return null;

  const parts: string[] = [];
  if (placeholderFrames > 0) {
    parts.push(`${placeholderFrames} placeholder`);
  }
  if (pollinationsFrames > 0) {
    parts.push(`${pollinationsFrames} fallback`);
  }
  const tone = placeholderFrames > 0 ? "warn" : "info";
  const toneClass =
    tone === "warn"
      ? "border-yellow-500/40 bg-yellow-500/10 text-yellow-200"
      : "border-[var(--accent)]/30 bg-[var(--accent)]/10 text-[var(--accent)]";
  const tip =
    `${geminiFrames}/${totalFrames} frames from Gemini` +
    (pollinationsFrames > 0
      ? ` · ${pollinationsFrames} via Pollinations (free fallback)`
      : "") +
    (placeholderFrames > 0
      ? ` · ${placeholderFrames} placeholder (image gen failed)`
      : "");

  return (
    <div
      title={tip}
      className={`mt-1.5 inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded text-[9.5px] font-mono uppercase tracking-[0.12em] border ${toneClass}`}
    >
      <span className="h-1 w-1 rounded-full bg-current opacity-80" />
      {parts.join(" · ")}
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 4v12" />
      <path d="m6 12 6 6 6-6" />
      <path d="M5 20h14" />
    </svg>
  );
}

function CaptionsIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M7 13c.5 1 1.5 1.5 2.5 1.5s2-.5 2.5-1.5" />
      <path d="M14 13c.5 1 1.5 1.5 2.5 1.5s2-.5 2.5-1.5" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
    >
      <rect x="6" y="6" width="12" height="12" rx="1" />
    </svg>
  );
}


/* ---------- Captions ---------- */

// 18 styles matching backend STYLE_PRESETS. Each gets a category for
// the tab filter UI and a label.
type CaptionStyle =
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

type CaptionCategory =
  | "all"
  | "trendy"
  | "bold"
  | "classic"
  | "minimal"
  | "decorative";

const CAPTION_STYLES: Array<{
  v: CaptionStyle;
  label: string;
  category: Exclude<CaptionCategory, "all">;
}> = [
  // Trendy first
  { v: "mrbeast",   label: "MrBeast",   category: "trendy" },
  { v: "reels",     label: "Reels",     category: "trendy" },
  { v: "tiktok",    label: "TikTok",    category: "trendy" },
  { v: "neon",      label: "Neon",      category: "trendy" },
  { v: "highlight", label: "Highlight", category: "trendy" },
  // Bold
  { v: "bold",      label: "Bold",      category: "bold" },
  { v: "karaoke",   label: "Karaoke",   category: "bold" },
  { v: "outline",   label: "Outline",   category: "bold" },
  { v: "gradient",  label: "Gradient",  category: "bold" },
  // Classic
  { v: "news",      label: "News",      category: "classic" },
  { v: "cinema",    label: "Cinema",    category: "classic" },
  { v: "plain",     label: "Plain",     category: "classic" },
  // Minimal
  { v: "whisper",     label: "Whisper",    category: "minimal" },
  { v: "underline",   label: "Underline",  category: "minimal" },
  { v: "typewriter",  label: "Typewriter", category: "minimal" },
  // Decorative
  { v: "sticker",  label: "Sticker", category: "decorative" },
  { v: "comic",    label: "Comic",   category: "decorative" },
  { v: "retro",    label: "Retro",   category: "decorative" },
];

const CAPTION_CATEGORIES: Array<{ v: CaptionCategory; label: string }> = [
  { v: "all",        label: "All" },
  { v: "trendy",     label: "Trending" },
  { v: "bold",       label: "Bold" },
  { v: "classic",    label: "Classic" },
  { v: "minimal",    label: "Minimal" },
  { v: "decorative", label: "Decorative" },
];

const CAPTION_POSITIONS: Array<{
  v: "top" | "middle" | "bottom";
  label: string;
}> = [
  { v: "top", label: "Top" },
  { v: "middle", label: "Middle" },
  { v: "bottom", label: "Bottom" },
];

/** Available font choices in Customize tab. Same as captions tool. */
const A2V_FONT_OPTIONS: Array<{ v: string; label: string }> = [
  { v: "Inter",         label: "Inter (default)" },
  { v: "Bangers",       label: "Bangers (comic)" },
  { v: "Courier New",   label: "Courier New (mono)" },
  { v: "Impact",        label: "Impact" },
  { v: "Arial Black",   label: "Arial Black" },
  { v: "Georgia",       label: "Georgia (serif)" },
];

const A2V_COLOR_SWATCHES: string[] = [
  "#FFFFFF", "#000000", "#FFE04A", "#00F0FF", "#FF3D9C", "#FF3D3D",
  "#FF8A2B", "#32D74B", "#B6FF3C", "#3B82F6", "#A855F7", "#FF1493",
];

/**
 * Big 2-column captions popup. Left column = the actual video at a
 * comfortable size with a live caption overlay. Right column = the
 * settings panel (style / position / words-per-line / generate). Stacks
 * vertically on mobile.
 */
function CaptionsModal({
  parentJob,
  captionsJob,
  aspectCls,
  onClose,
  onRefresh,
  captionPreview,
  onPreviewChange,
  posXFrac,
  posYFrac,
  onPositionChange,
}: {
  parentJob: Job;
  captionsJob?: Job;
  aspectCls: string;
  onClose: () => void;
  onRefresh?: () => Promise<void> | void;
  captionPreview: CaptionPreviewSpec | null;
  onPreviewChange: (spec: CaptionPreviewSpec | null) => void;
  /** Current drag-set position (null = use discrete `position` anchor). */
  posXFrac: number | null;
  posYFrac: number | null;
  onPositionChange: (xFrac: number, yFrac: number) => void;
}) {
  // Stage ref so the draggable overlay can clamp pointer-deltas to the
  // visible video frame.
  const stageRef = useRef<HTMLDivElement>(null);
  // When a captioned render is active on the parent, default to showing
  // the BURNED mp4 so the user actually sees their finished captions —
  // not a demo overlay sitting on the original. They can flip back to
  // original (with drag-preview overlay) for restyling via the toggle.
  const captionsActive = !!parentJob.activeCaptionsJobId;
  const [showOriginal, setShowOriginal] = useState(false);
  const showingBurned = captionsActive && !showOriginal;
  const url = showingBurned
    ? apiClient.jobOutputUrl(parentJob.id, {
        variant: "active",
        cacheKey: parentJob.activeCaptionsJobId ?? "burned",
      })
    : apiClient.jobOutputUrl(parentJob.id, { variant: "original" });
  const name = parentJob.audioFilename ?? `Job ${parentJob.id.slice(0, 8)}`;

  // Close on Escape.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Lock body scroll while the modal is open.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 md:p-6 overflow-y-auto"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-[1080px] max-h-[92vh] rounded-xl border border-[var(--line)] bg-[var(--surface)] shadow-2xl overflow-hidden flex flex-col md:flex-row"
      >
        {/* Close button (top-right of the modal) */}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute top-2 right-2 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full bg-black/60 text-white hover:bg-black/80"
        >
          ×
        </button>

        {/* LEFT — video preview with live caption overlay */}
        <div className="md:flex-1 md:min-w-0 bg-black flex items-center justify-center p-4 md:p-6">
          <div
            ref={stageRef}
            className={`relative ${aspectCls} w-full max-h-[80vh] mx-auto bg-black rounded-lg overflow-hidden`}
            style={{
              maxWidth: "min(100%, calc(80vh * 9 / 16))",
              // containerType on the STAGE so the caption's cqh/cqw
              // font + width units resolve against the video frame.
              containerType: "size",
            }}
          >
            <video
              src={url}
              controls
              autoPlay
              loop
              playsInline
              className="absolute inset-0 w-full h-full object-contain"
            />
            {/* Demo overlay only when we're showing the ORIGINAL frame —
                stacking it on the burned mp4 would double the captions.
                Wrapped in DraggableCaptionFrame so the user can drag the
                caption to any position on the video (matches the
                Captions tool's drag UX). */}
            {captionPreview && !showingBurned && (
              <DraggableCaptionFrame
                stageRef={stageRef}
                position={captionPreview.position}
                posXFrac={posXFrac}
                posYFrac={posYFrac}
                onMove={onPositionChange}
              >
                <CaptionOverlay
                  style={captionPreview.style}
                  position={captionPreview.position}
                  wordsPerLine={captionPreview.wordsPerLine}
                  primaryColor={captionPreview.primaryColor ?? null}
                  outlineColor={captionPreview.outlineColor ?? null}
                  outlineWidth={captionPreview.outlineWidth ?? null}
                  bgColor={captionPreview.bgColor ?? null}
                  bgAlpha={captionPreview.bgAlpha ?? null}
                  fontSize={captionPreview.fontSize ?? null}
                  fontFamily={captionPreview.fontFamily ?? null}
                  shadow={captionPreview.shadow ?? null}
                  embedded
                />
              </DraggableCaptionFrame>
            )}
            {/* One-click toggle between burned mp4 and original.
                Only meaningful once a captioned render exists. */}
            {captionsActive && (
              <button
                type="button"
                onClick={() => setShowOriginal((v) => !v)}
                className="absolute top-2 left-2 z-10 text-[10px] uppercase tracking-[0.18em] font-mono px-2 py-1 rounded-full bg-black/60 text-white hover:bg-black/80 backdrop-blur"
              >
                {showingBurned
                  ? "Captioned · show original"
                  : "Original · show captioned"}
              </button>
            )}
          </div>
        </div>

        {/* RIGHT — settings panel */}
        <div className="md:w-[360px] md:shrink-0 border-t md:border-t-0 md:border-l border-[var(--line)] flex flex-col">
          <div className="px-5 py-4 border-b border-[var(--line)] flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--accent)] font-mono">
                Captions
              </div>
              <div className="mt-0.5 text-[12.5px] text-white truncate" title={name}>
                {name}
              </div>
            </div>
          </div>

          <div className="px-5 py-4 overflow-y-auto">
            {/* Reuse the existing panel — same logic, lives in the right column */}
            <CaptionsPanel
              parentJob={parentJob}
              captionsJob={captionsJob}
              aspectCls={aspectCls}
              onRefresh={onRefresh}
              onPreviewChange={onPreviewChange}
              posXFrac={posXFrac}
              posYFrac={posYFrac}
              onPositionChange={onPositionChange}
              hideHeader
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Wraps the caption preview in a drag-handle. When the user drags the
 * caption around the video, we report new fractional coords back up so
 * the next render burns at that exact position.
 *
 * Falls back to the discrete `position` ("top" / "middle" / "bottom")
 * anchor if no drag has happened yet (posXFrac / posYFrac null).
 */
function DraggableCaptionFrame({
  stageRef,
  position,
  posXFrac,
  posYFrac,
  onMove,
  children,
}: {
  stageRef: React.RefObject<HTMLDivElement | null>;
  position: "top" | "middle" | "bottom";
  posXFrac: number | null;
  posYFrac: number | null;
  onMove: (xFrac: number, yFrac: number) => void;
  children: React.ReactNode;
}) {
  const [dragging, setDragging] = useState(false);
  const [hovered, setHovered] = useState(false);

  // Default anchor (no drag yet): centered horizontally, V from preset.
  const xFrac = posXFrac ?? 0.5;
  const yFrac =
    posYFrac ??
    (position === "top" ? 0.1 : position === "middle" ? 0.5 : 0.9);

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    const stage = stageRef.current;
    if (!stage) return;
    e.preventDefault();
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDragging(true);
    const rect = stage.getBoundingClientRect();
    const initX = e.clientX;
    const initY = e.clientY;
    const initXFrac = xFrac;
    const initYFrac = yFrac;

    function clamp(v: number) {
      return Math.max(0.02, Math.min(0.98, v));
    }
    function move(ev: PointerEvent) {
      const dx = (ev.clientX - initX) / rect.width;
      const dy = (ev.clientY - initY) / rect.height;
      onMove(clamp(initXFrac + dx), clamp(initYFrac + dy));
    }
    function up() {
      setDragging(false);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  }

  return (
    <div
      aria-hidden
      onPointerDown={onPointerDown}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      className="absolute z-10 select-none"
      style={{
        left: `${xFrac * 100}%`,
        top: `${yFrac * 100}%`,
        transform: "translate(-50%, -50%)",
        cursor: dragging ? "grabbing" : "grab",
        outline:
          hovered || dragging
            ? "1.5px dashed var(--accent)"
            : "1.5px dashed transparent",
        outlineOffset: "6px",
        borderRadius: "4px",
        transition: dragging ? "none" : "outline-color 120ms",
        touchAction: "none",
      }}
    >
      {/* nowrap so the caption stays on one line same as backend ASS
          render (WrapStyle 2). */}
      <div className="inline-block text-center" style={{ whiteSpace: "nowrap" }}>
        {children}
      </div>
    </div>
  );
}

/**
 * Caption overlay drawn on top of an existing video. Mirrors the ASS
 * presets in api/tools/captions.py so the on-screen preview matches
 * what the actual ffmpeg burn-in will produce.
 *
 * The overlay cycles through 4 sample phrases (~1.6s each) so the
 * preview *feels* like real captions flowing across the video, not a
 * static label. When the user clicks a different style card, the
 * overlay fades + scales in so the change is visually obvious.
 *
 * `compact=true` switches to thumb-sized text (used on the small grid
 * card thumbnails). `compact=false` (default) is sized for the bigger
 * modal player.
 * `embedded=true` skips the overlay's own absolute positioning so a
 * parent wrapper (e.g. DraggableCaptionFrame) can place it instead.
 */
function CaptionOverlay({
  style,
  position,
  wordsPerLine = 2,
  compact = false,
  embedded = false,
  // Optional Customize overrides. When any is set the overlay
  // switches to an "effective values" render that matches what the
  // backend will burn into the final mp4.
  primaryColor = null,
  outlineColor = null,
  outlineWidth = null,
  bgColor = null,
  bgAlpha = null,
  fontSize = null,
  fontFamily = null,
  shadow = null,
}: {
  style: CaptionStyle;
  position: "top" | "middle" | "bottom";
  /** Drives how many words per phrase the demo cycles through, mirroring
   *  the real backend grouping. So sliding from 1→5 visibly changes the
   *  phrase length on the live preview. */
  wordsPerLine?: number;
  compact?: boolean;
  /** When true, skip the overlay's own absolute positioning so a parent
   *  wrapper (DraggableCaptionFrame) can place it. */
  embedded?: boolean;
  primaryColor?: string | null;
  outlineColor?: string | null;
  outlineWidth?: number | null;
  bgColor?: string | null;
  bgAlpha?: number | null;
  fontSize?: number | null;
  fontFamily?: string | null;
  shadow?: number | null;
}) {
  // Master sample sentence. We chunk it into N-word phrases so the live
  // preview matches whatever the user has the wordsPerLine slider set to.
  const SAMPLE_WORDS = useMemo(
    () =>
      "this is how your captions will look on a real video".split(" "),
    [],
  );

  // Group words into phrases of `wordsPerLine`. Effectively the same as
  // _group_words_into_lines() in api/tools/captions.py.
  const phrases = useMemo(() => {
    const n = Math.max(1, Math.min(8, Math.round(wordsPerLine)));
    const out: string[] = [];
    for (let i = 0; i < SAMPLE_WORDS.length; i += n) {
      out.push(SAMPLE_WORDS.slice(i, i + n).join(" "));
    }
    return out;
  }, [wordsPerLine, SAMPLE_WORDS]);

  // Cycle through phrases.
  const [phraseIdx, setPhraseIdx] = useState(0);
  useEffect(() => {
    setPhraseIdx(0); // Reset when the phrase list changes (e.g. slider).
    const id = setInterval(() => {
      setPhraseIdx((i) => (i + 1) % phrases.length);
    }, 1600);
    return () => clearInterval(id);
  }, [phrases]);

  const safeIdx = Math.min(phraseIdx, phrases.length - 1);
  const currentWords = phrases[safeIdx]?.split(" ") ?? [];

  // Karaoke walks word-by-word inside the current phrase; reset on
  // phrase change so the active word is always at index 0 first.
  const [karaokeIdx, setKaraokeIdx] = useState(0);
  useEffect(() => {
    setKaraokeIdx(0);
    if (style !== "karaoke") return;
    const id = setInterval(() => {
      setKaraokeIdx((i) => (i + 1) % Math.max(1, currentWords.length));
    }, 380);
    return () => clearInterval(id);
  }, [style, safeIdx, currentWords.length]);

  // Sizing — bigger in modal, smaller on the grid thumb.
  const sizePx = compact
    ? "clamp(10px, 4cqh, 16px)"
    : "clamp(16px, 5cqh, 36px)";
  const heavyOutline = compact ? "1.6px" : "3px";
  const lightOutline = compact ? "1.2px" : "2px";

  // Style-specific spacing. Heavily outlined / boxed styles need a bit
  // more breathing room; tight styles like Bold sit close to the frame.
  type StyleSpacing = {
    padX: string;
    padY: string;
    marginX: string; // outer margin around the whole pill
  };
  const SPACING: Record<CaptionStyle, StyleSpacing> = {
    plain:      { padX: compact ? "0.45em" : "0.6em", padY: compact ? "0.15em" : "0.22em", marginX: "0" },
    bold:       { padX: "0",                          padY: "0",                            marginX: compact ? "0.2em" : "0.4em" },
    highlight:  { padX: compact ? "0.45em" : "0.7em", padY: compact ? "0.18em" : "0.28em", marginX: "0" },
    karaoke:    { padX: "0",                          padY: "0",                            marginX: "0" },
    outline:    { padX: "0",                          padY: "0",                            marginX: compact ? "0.3em" : "0.5em" },
    neon:       { padX: "0",                          padY: "0",                            marginX: compact ? "0.4em" : "0.7em" },
    gradient:   { padX: "0",                          padY: "0",                            marginX: compact ? "0.3em" : "0.5em" },
    typewriter: { padX: compact ? "0.4em" : "0.6em",  padY: compact ? "0.16em" : "0.24em", marginX: "0" },
    // 10 new styles — most use the bg-pill or stroke approach, so
    // spacing mirrors a similar existing entry.
    news:       { padX: compact ? "0.45em" : "0.7em", padY: compact ? "0.18em" : "0.28em", marginX: "0" },
    cinema:     { padX: "0",                          padY: "0",                            marginX: compact ? "0.2em" : "0.4em" },
    mrbeast:    { padX: "0",                          padY: "0",                            marginX: compact ? "0.4em" : "0.7em" },
    reels:      { padX: "0",                          padY: "0",                            marginX: compact ? "0.3em" : "0.6em" },
    tiktok:     { padX: "0",                          padY: "0",                            marginX: compact ? "0.4em" : "0.7em" },
    whisper:    { padX: "0",                          padY: "0",                            marginX: compact ? "0.2em" : "0.4em" },
    underline:  { padX: compact ? "0.4em" : "0.6em",  padY: compact ? "0.16em" : "0.24em", marginX: "0" },
    sticker:    { padX: compact ? "0.5em" : "0.85em", padY: compact ? "0.22em" : "0.3em",  marginX: "0" },
    comic:      { padX: "0",                          padY: "0",                            marginX: compact ? "0.4em" : "0.7em" },
    retro:      { padX: "0",                          padY: "0",                            marginX: compact ? "0.3em" : "0.6em" },
  };
  const spacing = SPACING[style];

  // Per-style monospace override (typewriter). Renamed from
  // `fontFamily` to avoid shadowing the new prop of the same name.
  const presetFontFamily =
    style === "typewriter"
      ? '"JetBrains Mono", "Courier New", ui-monospace, monospace'
      : "inherit";

  const baseText = phrases[safeIdx] ?? "";
  const text = style === "bold" ? baseText.toUpperCase() : baseText;

  // If the user touched ANY Customize knob, render the phrase with
  // those effective values directly — matches what the backend burn
  // will produce. Otherwise fall through to the per-style branches.
  const hasOverride =
    primaryColor !== null ||
    outlineColor !== null ||
    outlineWidth !== null ||
    bgColor !== null ||
    bgAlpha !== null ||
    fontSize !== null ||
    fontFamily !== null ||
    shadow !== null;

  let captionEl: React.ReactNode;
  if (hasOverride) {
    const color = primaryColor ?? "#FFFFFF";
    const outCol = outlineColor ?? "#000000";
    const outW = outlineWidth ?? 2;
    const bg = bgColor ?? "#000000";
    const bgAlphaCss = bgAlpha === null ? 0 : 1 - bgAlpha / 255;
    const fSize = fontSize !== null ? `${fontSize}px` : sizePx;
    const fFam = fontFamily ?? presetFontFamily;
    const sh = shadow ?? 0;
    const textShadow =
      sh > 0
        ? `0 0 ${sh * 1.2}px ${outCol}, 0 0 ${sh * 2}px ${outCol}`
        : undefined;
    captionEl = (
      <span
        className="inline-block font-bold leading-tight"
        style={{
          color,
          fontFamily: fFam,
          fontSize: fSize,
          paintOrder: "stroke fill",
          WebkitTextStroke: outW > 0 ? `${outW}px ${outCol}` : undefined,
          background:
            bgAlphaCss > 0
              ? `${bg}${a2vBgAlphaToHex(bgAlphaCss)}`
              : undefined,
          padding: bgAlphaCss > 0 ? "0.22em 0.7em" : undefined,
          borderRadius: bgAlphaCss > 0 ? "4px" : undefined,
          textShadow,
        }}
      >
        {text}
      </span>
    );
  } else if (style === "plain") {
    captionEl = (
      <span
        className="inline-block rounded font-semibold leading-tight"
        style={{
          background: "rgba(0,0,0,0.7)",
          color: "#FFFFFF",
          fontSize: sizePx,
          padding: `${spacing.padY} ${spacing.padX}`,
          fontFamily: presetFontFamily,
        }}
      >
        {text}
      </span>
    );
  } else if (style === "bold") {
    captionEl = (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#FFFFFF",
          fontSize: sizePx,
          margin: `0 ${spacing.marginX}`,
          paintOrder: "stroke fill",
          WebkitTextStroke: `${heavyOutline} #000`,
          textShadow:
            "0 1px 0 #000, 0 -1px 0 #000, 1px 0 0 #000, -1px 0 0 #000",
        }}
      >
        {text}
      </span>
    );
  } else if (style === "highlight") {
    captionEl = (
      <span
        className="inline-block rounded font-semibold leading-tight"
        style={{
          background: "var(--accent)",
          color: "#0a0a0a",
          fontSize: sizePx,
          padding: `${spacing.padY} ${spacing.padX}`,
          fontFamily: presetFontFamily,
        }}
      >
        {text}
      </span>
    );
  } else if (style === "outline") {
    // Hollow letters — cyan fill on a thick black stroke. Reads as
    // outlined typography.
    captionEl = (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#00F0FF",
          fontSize: sizePx,
          margin: `0 ${spacing.marginX}`,
          paintOrder: "stroke fill",
          WebkitTextStroke: `${compact ? "2px" : "4px"} #000`,
        }}
      >
        {text}
      </span>
    );
  } else if (style === "neon") {
    // Glowing tubes — white core wrapped in a cyan halo of multiple soft
    // shadows. Mimics the libass shadow we set in the ASS preset.
    captionEl = (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#FFFFFF",
          fontSize: sizePx,
          margin: `0 ${spacing.marginX}`,
          paintOrder: "stroke fill",
          WebkitTextStroke: `${compact ? "1.4px" : "2px"} #00F0FF`,
          textShadow: [
            "0 0 4px #00F0FF",
            "0 0 8px #00F0FF",
            "0 0 16px rgba(0,240,255,0.7)",
            "0 0 32px rgba(0,240,255,0.45)",
          ].join(", "),
        }}
      >
        {text}
      </span>
    );
  } else if (style === "gradient") {
    // Cyan fill on a thick navy stroke + a subtle white drop highlight
    // so it reads as two-tone even without per-glyph linear gradient.
    captionEl = (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#00F0FF",
          fontSize: sizePx,
          margin: `0 ${spacing.marginX}`,
          paintOrder: "stroke fill",
          WebkitTextStroke: `${compact ? "2px" : "4px"} #0B2A4A`,
          textShadow:
            "0 1px 0 rgba(255,255,255,0.4), 0 -1px 0 rgba(0,0,0,0.6)",
        }}
      >
        {text}
      </span>
    );
  } else if (style === "typewriter") {
    captionEl = (
      <span
        className="inline-block font-medium leading-tight"
        style={{
          background: "#000",
          color: "#FFFFFF",
          fontSize: sizePx,
          padding: `${spacing.padY} ${spacing.padX}`,
          fontFamily: presetFontFamily,
          letterSpacing: "0.02em",
        }}
      >
        {text}
      </span>
    );
  } else if (style === "news") {
    captionEl = (
      <span
        className="inline-block font-bold leading-tight"
        style={{
          background: "#B30000",
          color: "#FFFFFF",
          fontSize: sizePx,
          padding: "0.22em 0.8em",
          letterSpacing: "0.02em",
        }}
      >
        {text}
      </span>
    );
  } else if (style === "cinema") {
    captionEl = (
      <span
        className="inline-block leading-tight"
        style={{
          color: "#FFFFFF",
          fontSize: sizePx,
          fontWeight: 500,
          fontStyle: "italic",
          textShadow:
            "0 1px 3px rgba(0,0,0,0.95), 0 0 6px rgba(0,0,0,0.7)",
        }}
      >
        {text}
      </span>
    );
  } else if (style === "mrbeast") {
    captionEl = (
      <span
        className="inline-block leading-none tracking-tight"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          color: "#FFE04A",
          fontSize: sizePx,
          fontWeight: 400,
          margin: `0 ${spacing.marginX}`,
          paintOrder: "stroke fill",
          WebkitTextStroke: `${compact ? "2.4px" : "5px"} #000`,
          textShadow:
            "0 3px 0 #000, 0 5px 8px rgba(0,0,0,0.7)",
        }}
      >
        {text.toUpperCase()}
      </span>
    );
  } else if (style === "reels") {
    captionEl = (
      <span
        className="inline-block leading-tight tracking-wide"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          color: "#B6FF3C",
          fontSize: sizePx,
          fontWeight: 400,
          margin: `0 ${spacing.marginX}`,
          paintOrder: "stroke fill",
          WebkitTextStroke: `${compact ? "2px" : "4px"} #000`,
          textShadow:
            "0 1px 0 #000, 0 -1px 0 #000, 1px 0 0 #000, -1px 0 0 #000",
        }}
      >
        {text.toUpperCase()}
      </span>
    );
  } else if (style === "tiktok") {
    captionEl = (
      <span
        className="inline-block leading-tight"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          color: "#FFFFFF",
          fontSize: sizePx,
          fontWeight: 400,
          margin: `0 ${spacing.marginX}`,
          paintOrder: "stroke fill",
          WebkitTextStroke: `${compact ? "2px" : "4px"} #FF1493`,
          textShadow:
            "0 0 10px rgba(255,20,147,0.7), 0 0 20px rgba(255,20,147,0.4)",
        }}
      >
        {text}
      </span>
    );
  } else if (style === "whisper") {
    captionEl = (
      <span
        className="inline-block leading-tight"
        style={{
          color: "#C0C0C0",
          fontSize: sizePx,
          fontWeight: 400,
          letterSpacing: "0.04em",
        }}
      >
        {text.toLowerCase()}
      </span>
    );
  } else if (style === "underline") {
    captionEl = (
      <span
        className="inline-block font-semibold leading-tight"
        style={{
          color: "#FFFFFF",
          fontSize: sizePx,
          padding: "0.12em 0.55em",
          background:
            "linear-gradient(to top, rgba(0,240,255,0.65) 0%, rgba(0,240,255,0.65) 22%, transparent 22%)",
        }}
      >
        {text}
      </span>
    );
  } else if (style === "sticker") {
    captionEl = (
      <span
        className="inline-block font-bold leading-tight"
        style={{
          background: "#000",
          color: "#FFF1D0",
          fontSize: sizePx,
          padding: "0.25em 0.85em",
          border: "3px solid #FFF",
          borderRadius: "999px",
          boxShadow: "0 3px 0 rgba(0,0,0,0.45), 0 6px 14px rgba(0,0,0,0.4)",
        }}
      >
        {text}
      </span>
    );
  } else if (style === "comic") {
    captionEl = (
      <span
        className="inline-block leading-none tracking-tight"
        style={{
          fontFamily: 'var(--font-bangers), "Bangers", "Impact", system-ui',
          color: "#FFE04A",
          fontSize: sizePx,
          fontWeight: 400,
          margin: `0 ${spacing.marginX}`,
          paintOrder: "stroke fill",
          WebkitTextStroke: `${compact ? "1.6px" : "3px"} #000`,
          textShadow:
            "1px 1px 0 #000, 2px 2px 0 #000, 3px 3px 0 rgba(0,0,0,0.6)",
        }}
      >
        {text.toUpperCase()}
      </span>
    );
  } else if (style === "retro") {
    captionEl = (
      <span
        className="inline-block leading-tight tracking-wide"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          color: "#FFC107",
          fontSize: sizePx,
          fontWeight: 400,
          margin: `0 ${spacing.marginX}`,
          paintOrder: "stroke fill",
          WebkitTextStroke: `${compact ? "1.6px" : "3px"} #B30000`,
          textShadow:
            "0 0 10px rgba(255,193,7,0.65), 0 0 18px rgba(179,0,0,0.5)",
          letterSpacing: "0.06em",
        }}
      >
        {text.toUpperCase()}
      </span>
    );
  } else {
    // karaoke
    captionEl = (
      <span
        className="inline-block font-extrabold leading-tight"
        style={{ fontSize: sizePx }}
      >
        {currentWords.map((w, i) => {
          const isActive = i === karaokeIdx;
          return (
            <span
              key={`${safeIdx}-${i}`}
              className="inline-block transition-colors duration-150"
              style={{
                marginRight: i === currentWords.length - 1 ? 0 : "0.2em",
                color: isActive ? "#FFE04A" : "#FFFFFF",
                paintOrder: "stroke fill",
                WebkitTextStroke: `${lightOutline} #000`,
                textShadow:
                  "0 1px 0 #000, 0 -1px 0 #000, 1px 0 0 #000, -1px 0 0 #000",
              }}
            >
              {w}
            </span>
          );
        })}
      </span>
    );
  }

  // Vertical placement matches the ASS Alignment numpad.
  const verticalPos = compact
    ? position === "top"
      ? "top-1.5"
      : position === "middle"
        ? "top-1/2 -translate-y-1/2"
        : "bottom-1.5"
    : position === "top"
      ? "top-[6%]"
      : position === "middle"
        ? "top-1/2 -translate-y-1/2"
        : "bottom-[8%]";

  // The animation key forces the inner span to remount whenever style
  // OR phrase changes, so CSS keyframes re-run and the overlay visibly
  // pops in (fade + slight scale). Keeps user in the loop on what they
  // just clicked.
  const animKey = `${style}-${wordsPerLine}-${safeIdx}`;

  // Embedded mode: parent (DraggableCaptionFrame) handles positioning,
  // so just emit the inner phrase. Standalone mode: do the absolute
  // positioning ourselves like before.
  if (embedded) {
    return (
      <span key={animKey} className="caption-pop inline-block">
        {captionEl}
      </span>
    );
  }

  return (
    <div
      aria-hidden
      className={`pointer-events-none absolute inset-x-0 ${verticalPos} z-10 flex justify-center px-2`}
      style={{ containerType: "size" }}
    >
      <span key={animKey} className="caption-pop inline-block">
        {captionEl}
      </span>
    </div>
  );
}


type CaptionPreviewSpec = {
  style: CaptionStyle;
  position: "top" | "middle" | "bottom";
  wordsPerLine: number;
  // Optional Customize-tab overrides for the live preview. When any of
  // these are set the modal's CaptionOverlay switches to an
  // "effective values" render that matches what the backend will burn.
  primaryColor?: string | null;
  outlineColor?: string | null;
  outlineWidth?: number | null;
  bgColor?: string | null;
  bgAlpha?: number | null;
  fontSize?: number | null;
  fontFamily?: string | null;
  shadow?: number | null;
};

function CaptionsPanel({
  parentJob,
  captionsJob,
  aspectCls,
  onRefresh,
  onPreviewChange,
  posXFrac = null,
  posYFrac = null,
  onPositionChange,
  hideHeader = false,
}: {
  parentJob: Job;
  captionsJob?: Job;
  aspectCls: string;
  onRefresh?: () => Promise<void> | void;
  /** Drag-set position (null = use discrete anchor). Owned by JobCard so
   *  CaptionsModal's video overlay + this panel's submit stay in sync. */
  posXFrac?: number | null;
  posYFrac?: number | null;
  onPositionChange?: (xFrac: number, yFrac: number) => void;
  /** Fires whenever the user picks a different style/position so the
   *  parent can render a live overlay on the video thumb. Receives null
   *  when the user is no longer actively editing. */
  onPreviewChange?: (spec: CaptionPreviewSpec | null) => void;
  /** When mounted inside a host that already shows its own header (e.g.
   *  the modal), drop the panel's own borders / paddings / "+ Add captions"
   *  button so the form sits flush. Also defaults the picker open so the
   *  user doesn't have to click twice. */
  hideHeader?: boolean;
}) {
  // Captions are "active" on the parent when the backend has stamped a
  // captioned variant — that's the live state of "this video has captions
  // burned in right now". Independent of whether a fresh captions job
  // happens to be queued.
  const captionsActiveOnParent = !!parentJob.activeCaptionsJobId;
  const activeStyle = parentJob.activeCaptionsStyle as
    | "plain"
    | "bold"
    | "highlight"
    | "karaoke"
    | null;
  // In modal mode, default the picker to open so we don't double-gate.
  const [open, setOpen] = useState(hideHeader);
  const [style, setStyle] = useState<CaptionStyle>("bold");
  const [position, setPosition] = useState<"top" | "middle" | "bottom">("bottom");
  const [wordsPerLine, setWordsPerLine] = useState(2);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Style picker tabs — Style | Customize. Style is the default since
  // most users just pick a preset and submit.
  const [activeTab, setActiveTab] = useState<"style" | "customize">("style");
  // Category filter for the 18-style grid.
  const [styleCategory, setStyleCategory] = useState<CaptionCategory>("trendy");
  const visibleStyles = useMemo(
    () =>
      styleCategory === "all"
        ? CAPTION_STYLES
        : CAPTION_STYLES.filter((s) => s.category === styleCategory),
    [styleCategory],
  );
  // Customize overrides — all null means "use the preset". Backend
  // only receives keys the user explicitly set.
  const [primaryColor, setPrimaryColor] = useState<string | null>(null);
  const [outlineColor, setOutlineColor] = useState<string | null>(null);
  const [outlineWidth, setOutlineWidth] = useState<number | null>(null);
  const [bgColor, setBgColor] = useState<string | null>(null);
  const [bgAlpha, setBgAlpha] = useState<number | null>(null);
  const [fontSize, setFontSize] = useState<number | null>(null);
  const [fontFamily, setFontFamily] = useState<string | null>(null);
  const [shadow, setShadow] = useState<number | null>(null);
  const [uppercase, setUppercase] = useState(false);

  // Local optimistic copy of the captionsJob — used to swap to the new
  // job id immediately on submit, before the next list-jobs poll lands.
  const [localCaptions, setLocalCaptions] = useState<Job | null>(null);
  const activeCaptions = captionsJob ?? localCaptions;

  // Surface the current style/position upward so the host (the modal)
  // can render a live demo overlay on its big video. We fire in TWO
  // cases:
  //   1) The picker is open — preview reflects what the user is editing.
  //   2) Captions are already active on the parent (summary mode) — show
  //      the SAVED style + bottom position so the user can still see
  //      what their video has, even before clicking "Change".
  // Clear when a fresh captions job is in flight (we don't want a stale
  // preview while ffmpeg is mid-burn).
  const showingProgress =
    !!activeCaptions &&
    (activeCaptions.status === "queued" ||
      activeCaptions.status === "running");
  useEffect(() => {
    if (!onPreviewChange) return;
    if (showingProgress) {
      onPreviewChange(null);
    } else if (open) {
      onPreviewChange({
        style,
        position,
        wordsPerLine,
        primaryColor,
        outlineColor,
        outlineWidth,
        bgColor,
        bgAlpha,
        fontSize,
        fontFamily,
        shadow,
      });
    } else if (captionsActiveOnParent && activeStyle) {
      onPreviewChange({
        style: activeStyle as CaptionStyle,
        position: "bottom",
        wordsPerLine: 2,
      });
    } else {
      onPreviewChange(null);
    }
    return () => {
      if (onPreviewChange) onPreviewChange(null);
    };
  }, [
    open,
    style,
    position,
    wordsPerLine,
    primaryColor,
    outlineColor,
    outlineWidth,
    bgColor,
    bgAlpha,
    fontSize,
    fontFamily,
    shadow,
    showingProgress,
    captionsActiveOnParent,
    activeStyle,
    onPreviewChange,
  ]);

  const isCaptionsActive =
    !!activeCaptions &&
    (activeCaptions.status === "queued" ||
      activeCaptions.status === "running");
  const isCaptionsFailed = activeCaptions?.status === "failed";

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      // Build payload — Customize overrides only included when the
      // user actually set them, so backend falls back to the preset
      // for untouched fields.
      const payload: Parameters<typeof apiClient.submitCaptions>[1] = {
        style,
        position,
        wordsPerLine,
        uppercase,
      };
      // Drag position wins over the discrete anchor when set.
      if (posXFrac !== null) payload.posXFrac = posXFrac;
      if (posYFrac !== null) payload.posYFrac = posYFrac;
      if (primaryColor) payload.primaryColor = primaryColor;
      if (outlineColor) payload.outlineColor = outlineColor;
      if (outlineWidth !== null) payload.outlineWidth = outlineWidth;
      if (bgColor) payload.bgColor = bgColor;
      if (bgAlpha !== null) payload.bgAlpha = bgAlpha;
      if (fontSize !== null) payload.fontSize = fontSize;
      if (fontFamily) payload.fontFamily = fontFamily;
      if (shadow !== null) payload.shadow = shadow;
      const job = await apiClient.submitCaptions(parentJob.id, payload);
      setLocalCaptions(job);
      if (onRefresh) await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't start captions job.");
    } finally {
      setSubmitting(false);
    }
  }

  async function removeCaptions() {
    setError(null);
    try {
      await apiClient.clearCaptions(parentJob.id);
      // Drop any local captions job state so we go back to the picker.
      setLocalCaptions(null);
      setOpen(false);
      if (onRefresh) await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't remove captions.");
    }
  }

  // ---- Render branching ----
  // 1. A captions job is queued or running → show progress
  // 2. Captions job failed → show the error + retry CTA
  // 3. Captions are active on the parent (currently burned in) → show
  //    a slim summary with Change / Remove. If the user clicks Change
  //    we open the picker.
  // 4. Otherwise → show "+ Add captions" → picker

  if (isCaptionsActive) {
    return (
      <CaptionsProgress
        job={activeCaptions!}
        hideHeader={hideHeader}
        onCancel={async () => {
          try {
            await apiClient.cancelJob(activeCaptions!.id);
          } catch {
            /* ignore */
          }
        }}
      />
    );
  }

  if (isCaptionsFailed) {
    return (
      <div className={hideHeader ? "" : "mt-4 border-t border-[var(--line)] pt-4"}>
        <div className="text-[11.5px] font-mono text-red-300">
          ✕{" "}
          {activeCaptions?.errorDetail?.split("\n")[0] ??
            "Caption render failed."}
        </div>
        <button
          type="button"
          onClick={() => {
            setLocalCaptions(null);
            setOpen(true);
          }}
          className="mt-2 inline-flex h-8 items-center px-3 rounded-full bg-[var(--accent)] text-black text-[11.5px] font-semibold"
        >
          Try again
        </button>
      </div>
    );
  }

  if (captionsActiveOnParent && !open) {
    return (
      <div className={hideHeader ? "" : "mt-4 border-t border-[var(--line)] pt-4"}>
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--accent)] font-mono">
            Captions on · {activeStyle ?? "active"}
          </span>
          <a
            href={apiClient.jobSrtUrl(parentJob.activeCaptionsJobId!)}
            download
            className="text-[10.5px] font-mono text-[var(--muted)] hover:text-[var(--accent)] underline underline-offset-2"
          >
            .srt
          </a>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => {
              if (activeStyle) setStyle(activeStyle);
              setLocalCaptions(null);
              setOpen(true);
            }}
            className="inline-flex h-8 items-center px-3 rounded-md border border-[var(--line)] text-[11.5px] text-white hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors flex-1 justify-center"
          >
            Change style
          </button>
          <button
            type="button"
            onClick={removeCaptions}
            className="inline-flex h-8 items-center px-3 rounded-md border border-[var(--line)] text-[11.5px] text-[var(--muted)] hover:border-red-500/60 hover:text-red-400 transition-colors"
          >
            Remove
          </button>
        </div>
        {error && (
          <p className="mt-2 text-[11px] font-mono text-red-300">✕ {error}</p>
        )}
      </div>
    );
  }

  return (
    <div className={hideHeader ? "" : "mt-4 border-t border-[var(--line)] pt-4"}>
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex h-8 items-center gap-1.5 px-3 rounded-full border border-[var(--line)] text-[12px] text-white hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
        >
          + Add captions
        </button>
      ) : (
        <div className="space-y-4">
          {!hideHeader && (
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
                Captions
              </span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-[11px] text-[var(--muted)] hover:text-white"
                disabled={submitting}
              >
                Cancel
              </button>
            </div>
          )}

          {/* Style / Customize tab strip */}
          <div className="flex items-end gap-0 border-b border-[var(--line)]">
            {(
              [
                { id: "style", label: "Style" },
                { id: "customize", label: "Customize" },
              ] as const
            ).map((t) => {
              const isActive = activeTab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setActiveTab(t.id)}
                  className={`relative px-3 h-9 text-[11px] font-mono uppercase tracking-[0.14em] transition-colors ${
                    isActive
                      ? "text-white"
                      : "text-[var(--muted)] hover:text-white"
                  }`}
                >
                  {t.label}
                  {isActive && (
                    <span
                      aria-hidden
                      className="absolute left-2 right-2 -bottom-px h-0.5 bg-[var(--accent)] rounded-full"
                    />
                  )}
                </button>
              );
            })}
          </div>

          {activeTab === "style" && (
            <>
              {/* Category filter */}
              <div className="flex gap-1.5 overflow-x-auto scrollbar-hide -mx-1 px-1">
                {CAPTION_CATEGORIES.map((c) => {
                  const isActive = styleCategory === c.v;
                  const count =
                    c.v === "all"
                      ? CAPTION_STYLES.length
                      : CAPTION_STYLES.filter((s) => s.category === c.v).length;
                  return (
                    <button
                      key={c.v}
                      type="button"
                      onClick={() => setStyleCategory(c.v)}
                      className={`whitespace-nowrap rounded-full px-3 py-1 text-[11px] font-medium transition-colors ${
                        isActive
                          ? "bg-[var(--accent)] text-black"
                          : "bg-[var(--bg)] text-[var(--muted)] hover:text-white border border-[var(--line)]"
                      }`}
                    >
                      {c.label}
                      <span
                        className={`ml-1.5 text-[10px] font-mono ${
                          isActive ? "opacity-70" : "opacity-60"
                        }`}
                      >
                        {count}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* 3-per-row tile grid, scrollable */}
              <div className="grid grid-cols-3 gap-2 max-h-[360px] overflow-y-auto scrollbar-hide pr-1">
                {visibleStyles.map((s) => {
                  const isActive = style === s.v;
                  return (
                    <button
                      key={s.v}
                      type="button"
                      onClick={() => setStyle(s.v)}
                      disabled={submitting}
                      title={s.label}
                      aria-label={s.label}
                      className={`relative overflow-hidden rounded-md border-2 transition-colors ${
                        isActive
                          ? "border-[var(--accent)] ring-1 ring-[var(--accent)]/40"
                          : "border-[var(--line)] hover:border-[var(--line-2)]"
                      }`}
                    >
                      <CaptionStyleTile style={s.v} />
                      {isActive && (
                        <div className="absolute top-1.5 right-1.5 h-5 w-5 rounded-full bg-[var(--accent)] text-black flex items-center justify-center shadow-lg">
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Position */}
              <div>
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono">
                    Position
                  </span>
                  {(posXFrac !== null || posYFrac !== null) && (
                    <span className="text-[10px] text-[var(--accent)] font-mono">
                      dragged
                    </span>
                  )}
                </div>
                <div className="flex gap-1.5">
                  {CAPTION_POSITIONS.map((p) => {
                    const isActive = position === p.v;
                    return (
                      <button
                        key={p.v}
                        type="button"
                        onClick={() => setPosition(p.v)}
                        disabled={submitting}
                        className={`flex-1 px-2 py-1.5 rounded-md border text-[11.5px] transition-colors ${
                          isActive
                            ? "border-[var(--accent)] bg-[var(--accent)]/5 text-white"
                            : "border-[var(--line)] text-[var(--muted)] hover:text-white"
                        }`}
                      >
                        {p.label}
                      </button>
                    );
                  })}
                </div>
                <p className="mt-1.5 text-[10.5px] text-[var(--muted)]">
                  Or drag the caption directly on the video.
                </p>
              </div>

              {/* Words per line */}
              <div>
                <span className="block text-[10px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono mb-1.5">
                  Words per line · {wordsPerLine}
                </span>
                <input
                  type="range"
                  min={1}
                  max={5}
                  step={1}
                  value={wordsPerLine}
                  onChange={(e) => setWordsPerLine(Number(e.target.value))}
                  disabled={submitting}
                  className="w-full accent-[var(--accent)]"
                />
              </div>

              {/* Uppercase toggle */}
              <label className="flex items-center gap-2 text-[12px] text-white cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={uppercase}
                  onChange={(e) => setUppercase(e.target.checked)}
                  disabled={submitting}
                  className="accent-[var(--accent)] h-4 w-4"
                />
                Force ALL CAPS
              </label>
            </>
          )}

          {activeTab === "customize" && (
            <div className="space-y-4 max-h-[420px] overflow-y-auto scrollbar-hide pr-1">
              <p className="text-[11px] text-[var(--muted)] leading-[1.55]">
                Tweak colors and sizing on top of the picked style. Leave a
                field on default to use the preset value.
              </p>

              <A2VColorRow
                label="Text color"
                value={primaryColor}
                onChange={setPrimaryColor}
              />
              <A2VColorRow
                label="Outline color"
                value={outlineColor}
                onChange={setOutlineColor}
              />
              <A2VSliderRow
                label="Outline thickness"
                value={outlineWidth ?? 0}
                min={0}
                max={12}
                step={1}
                unit="px"
                isOverridden={outlineWidth !== null}
                onChange={setOutlineWidth}
                onReset={() => setOutlineWidth(null)}
              />

              <A2VColorRow
                label="Background color"
                value={bgColor}
                onChange={setBgColor}
              />
              <A2VSliderRow
                label="Background opacity"
                value={
                  bgAlpha === null
                    ? 0
                    : Math.round(((255 - bgAlpha) / 255) * 100)
                }
                min={0}
                max={100}
                step={5}
                unit="%"
                isOverridden={bgAlpha !== null}
                onChange={(v) => setBgAlpha(Math.round(255 - (v / 100) * 255))}
                onReset={() => setBgAlpha(null)}
              />

              <A2VSliderRow
                label="Font size"
                value={fontSize ?? 48}
                min={16}
                max={140}
                step={2}
                unit="px"
                isOverridden={fontSize !== null}
                onChange={setFontSize}
                onReset={() => setFontSize(null)}
              />

              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] uppercase tracking-[0.16em] text-[var(--muted)] font-mono">
                    Font family
                  </span>
                  {fontFamily && (
                    <button
                      type="button"
                      onClick={() => setFontFamily(null)}
                      className="text-[10px] text-[var(--muted)] hover:text-[var(--accent)] font-mono"
                    >
                      reset
                    </button>
                  )}
                </div>
                <select
                  value={fontFamily ?? ""}
                  onChange={(e) =>
                    setFontFamily(e.target.value || null)
                  }
                  className="w-full rounded-md border border-[var(--line)] bg-[var(--bg)] px-2 py-1.5 text-[12px]"
                >
                  <option value="">Style default</option>
                  {A2V_FONT_OPTIONS.map((f) => (
                    <option key={f.v} value={f.v}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </div>

              <A2VSliderRow
                label="Shadow / glow"
                value={shadow ?? 0}
                min={0}
                max={12}
                step={1}
                unit="px"
                isOverridden={shadow !== null}
                onChange={setShadow}
                onReset={() => setShadow(null)}
              />

              <button
                type="button"
                onClick={() => {
                  setPrimaryColor(null);
                  setOutlineColor(null);
                  setOutlineWidth(null);
                  setBgColor(null);
                  setBgAlpha(null);
                  setFontSize(null);
                  setFontFamily(null);
                  setShadow(null);
                }}
                className="inline-flex h-8 items-center px-3 rounded-full border border-[var(--line)] text-[11px] text-[var(--muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
              >
                Reset all to preset
              </button>
            </div>
          )}

          <div className="flex items-center gap-2 pt-2 border-t border-[var(--line)]">
            <button
              type="button"
              onClick={submit}
              disabled={submitting}
              className="inline-flex h-9 items-center px-4 rounded-full bg-[var(--accent)] text-black text-[12px] font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting
                ? "Starting…"
                : captionsActiveOnParent
                  ? "Apply style change →"
                  : "Generate captions →"}
            </button>
            {error && (
              <span className="text-[11px] text-red-300 font-mono">
                ✕ {error}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Color picker row for the a2v modal's Customize tab. Mirrors the
 *  ColorRow helper in /captions. */
function A2VColorRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] uppercase tracking-[0.16em] text-[var(--muted)] font-mono">
          {label}
        </span>
        {value !== null && (
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-[10px] text-[var(--muted)] hover:text-[var(--accent)] font-mono"
          >
            reset
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {A2V_COLOR_SWATCHES.map((c) => {
          const isActive = (value ?? "").toLowerCase() === c.toLowerCase();
          return (
            <button
              key={c}
              type="button"
              onClick={() => onChange(c)}
              title={c}
              className={`h-6 w-6 rounded-md border-2 transition-transform ${
                isActive
                  ? "border-[var(--accent)] scale-110"
                  : "border-[var(--line)] hover:scale-105"
              }`}
              style={{ background: c }}
            />
          );
        })}
        <input
          type="color"
          value={value ?? "#FFFFFF"}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="h-6 w-10 rounded-md border-2 border-[var(--line)] cursor-pointer bg-transparent"
          title="Custom hex"
        />
      </div>
    </div>
  );
}

function A2VSliderRow({
  label,
  value,
  min,
  max,
  step,
  unit,
  isOverridden,
  onChange,
  onReset,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  isOverridden: boolean;
  onChange: (v: number) => void;
  onReset: () => void;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] uppercase tracking-[0.16em] text-[var(--muted)] font-mono">
          {label}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-white">
            {value}
            {unit ?? ""}
          </span>
          {isOverridden && (
            <button
              type="button"
              onClick={onReset}
              className="text-[10px] text-[var(--muted)] hover:text-[var(--accent)] font-mono"
            >
              reset
            </button>
          )}
        </div>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-7 accent-[var(--accent)]"
      />
    </div>
  );
}

/** Alpha 0..1 → 2-char hex for #RRGGBBAA shorthand. */
function a2vBgAlphaToHex(a: number): string {
  const clamped = Math.max(0, Math.min(1, a));
  return Math.round(clamped * 255)
    .toString(16)
    .padStart(2, "0")
    .toUpperCase();
}

function CaptionsProgress({
  job,
  onCancel,
  hideHeader = false,
}: {
  job: Job;
  onCancel: () => Promise<void> | void;
  hideHeader?: boolean;
}) {
  const isRunning = job.status === "running";
  return (
    <div className={hideHeader ? "" : "mt-4 border-t border-[var(--line)] pt-4"}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--accent)] font-mono">
          Burning captions…
        </span>
        <span className="text-[10px] font-mono text-[var(--muted)]">
          {job.status} · {job.progress}%
        </span>
      </div>
      <div className="h-1 w-full rounded-full bg-[var(--bg)] overflow-hidden mb-2">
        <div
          className="h-full bg-[var(--accent)] transition-all"
          style={{ width: `${isRunning ? job.progress : 4}%` }}
        />
      </div>
      <p className="text-[11.5px] font-mono text-[var(--muted)] line-clamp-2 leading-[1.45]">
        {job.message ?? "Working…"}
      </p>
      <button
        type="button"
        onClick={() => onCancel()}
        className="mt-2 inline-flex h-7 items-center px-2.5 rounded-full border border-[var(--line)] text-[11px] text-[var(--muted)] hover:border-red-500/60 hover:text-red-400 transition-colors"
      >
        Cancel
      </button>
    </div>
  );
}

function aspectClassFor(size: string | undefined): string {
  // Tailwind v4 supports arbitrary aspect ratios, but the obvious ones
  // compile slightly faster as named utilities.
  switch (size) {
    case "16:9":
      return "aspect-[16/9]";
    case "1:1":
      return "aspect-square";
    case "4:5":
      return "aspect-[4/5]";
    case "9:16":
    default:
      return "aspect-[9/16]";
  }
}

function JobCard({
  job,
  captionsJob,
  onRefresh,
}: {
  job: Job;
  captionsJob?: Job;
  onRefresh?: () => Promise<void> | void;
}) {
  const name = job.audioFilename ?? `Job ${job.id.slice(0, 8)}`;
  const isDone = job.status === "done";
  const isFailed = job.status === "failed";
  const isBlocked = job.status === "blocked";
  const isRunning = job.status === "running";
  const isQueued = job.status === "queued";
  const isCancelled = job.status === "cancelled";

  const [cancelLocal, setCancelLocal] = useState(false);
  const cancelInFlight = cancelLocal || job.cancelRequested;

  async function onCancel() {
    if (cancelInFlight) return;
    setCancelLocal(true);
    try {
      await apiClient.cancelJob(job.id);
    } catch {
      // If it failed, drop the optimistic flag so the user can retry.
      setCancelLocal(false);
    }
  }

  // Surface the size that was picked at submit time so the inline player
  // can use the right aspect ratio (no horrible 16:9 letterboxing on a
  // 9:16 video).
  const opts = (job.params?.options ?? {}) as Record<string, unknown>;
  const sizeKey =
    typeof opts.size === "string" ? (opts.size as string) : "9:16";
  const aspectCls = aspectClassFor(sizeKey);
  const url = apiClient.jobOutputUrl(job.id);

  const borderClass = isDone
    ? "border-[var(--accent)]/40"
    : isFailed
      ? "border-red-500/40"
      : isBlocked
        ? "border-yellow-500/40"
        : isCancelled
          ? "border-[var(--line-2)]"
          : isRunning
            ? "border-[var(--accent)]/30"
            : "border-[var(--line)]";

  const statusLabel = isDone
    ? "Done"
    : isFailed
      ? "Failed"
      : isBlocked
        ? "Locked"
        : isCancelled
          ? "Cancelled"
          : cancelInFlight
            ? "Cancelling…"
            : isRunning
              ? `${job.progress}%`
              : "Queued";

  const statusColor = isDone
    ? "text-[var(--accent)]"
    : isFailed
      ? "text-red-300"
      : isBlocked
        ? "text-yellow-300"
        : isCancelled || cancelInFlight
          ? "text-[var(--muted)]"
          : "text-[var(--muted)]";

  return (
    <div
      className={`rounded-xl border bg-[var(--surface)] overflow-hidden ${borderClass}`}
    >
      {/* Inline player — only on done jobs. Autoplay+loop+muted so it
          starts the moment the card is on screen, just like a feed. */}
      {isDone && (
        <div
          className={`relative ${aspectCls} max-h-[520px] mx-auto w-full bg-black`}
        >
          <video
            src={url}
            controls
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
            className="absolute inset-0 w-full h-full object-contain"
          />
        </div>
      )}

      <div className="p-4">
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="truncate text-[13px] text-white" title={name}>
            {name}
          </span>
          <span
            className={`text-[10px] font-mono uppercase tracking-[0.18em] shrink-0 ${statusColor}`}
          >
            {statusLabel}
          </span>
        </div>

        {(isRunning || isQueued) && (
          <div className="h-1 w-full rounded-full bg-[var(--bg)] overflow-hidden mt-1 mb-2">
            <div
              className="h-full bg-[var(--accent)] transition-all"
              style={{ width: `${isRunning ? job.progress : 4}%` }}
            />
          </div>
        )}

        <p className="text-[11.5px] font-mono text-[var(--muted)] line-clamp-2 leading-[1.45] min-h-[1.45em]">
          {job.message ??
            (isQueued
              ? "Waiting for a worker slot…"
              : isBlocked
                ? "Free tier limit. Subscribe to render this."
                : isCancelled
                  ? "Cancelled by user"
                  : "")}
        </p>

        {(isRunning || isQueued) && (
          <div className="mt-3">
            <button
              type="button"
              onClick={onCancel}
              disabled={cancelInFlight}
              className="inline-flex h-8 items-center px-3 rounded-full border border-[var(--line)] text-[11.5px] text-[var(--muted)] hover:border-red-500/60 hover:text-red-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {cancelInFlight ? "Cancelling…" : "Cancel"}
            </button>
          </div>
        )}

        {isFailed && (
          <div className="mt-2 space-y-2">
            {job.errorDetail && (
              <p className="text-[11.5px] font-mono text-red-300 line-clamp-3">
                {job.errorDetail.split("\n")[0]}
              </p>
            )}
            <RetryButton jobId={job.id} onDone={onRefresh} />
          </div>
        )}

        {isDone && (
          <>
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              <a
                href={url}
                download
                className="inline-flex h-9 items-center px-4 rounded-full bg-[var(--accent)] text-black text-[12px] font-semibold hover:shadow-[0_0_18px_var(--accent-glow)] transition-shadow"
              >
                Download mp4
              </a>
            </div>

            <CaptionsPanel
              parentJob={job}
              captionsJob={captionsJob}
              aspectCls={aspectCls}
              onRefresh={onRefresh}
            />
          </>
        )}

        {isBlocked && (
          <Link
            href="/settings/billing"
            className="mt-3 inline-flex h-8 items-center px-3 rounded-full bg-[var(--accent)] text-black text-[11.5px] font-semibold"
          >
            Upgrade →
          </Link>
        )}
      </div>
    </div>
  );
}
