"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ApiError,
  apiClient,
  type CaptionRenderOpts,
  type Job,
  type TranscriptResponse,
} from "@/lib/api";
import { useMe } from "@/components/MeProvider";
import { CaptionStyleTile } from "@/components/CaptionStyleTile";

const MAX_FILES = 50;
const POLL_MS = 1500;

type CaptionStyle =
  // Original 7 (Bold removed 2026-05)
  | "plain"
  | "highlight"
  | "karaoke"
  | "outline"
  | "neon"
  | "gradient"
  | "typewriter"
  // Classic / News
  | "news"
  | "cinema"
  // Social-media trendy
  | "mrbeast"
  | "reels"
  | "tiktok"
  // Minimal
  | "whisper"
  | "underline"
  // Decorative
  | "sticker"
  | "comic"
  | "retro";

type CaptionCategory =
  | "all"
  | "trendy"
  | "classic"
  | "bold"
  | "minimal"
  | "decorative";

const CAPTION_STYLES: Array<{
  v: CaptionStyle;
  label: string;
  category: Exclude<CaptionCategory, "all">;
}> = [
  // Trendy first — the most-picked block sits at the top.
  { v: "mrbeast", label: "MrBeast", category: "trendy" },
  { v: "reels", label: "Reels", category: "trendy" },
  { v: "tiktok", label: "TikTok", category: "trendy" },
  { v: "neon", label: "Neon", category: "trendy" },
  { v: "highlight", label: "Highlight", category: "trendy" },

  // Bold / impact (Bold style removed 2026-05; category name kept for grouping)
  { v: "karaoke", label: "Karaoke", category: "bold" },
  { v: "outline", label: "Outline", category: "bold" },
  { v: "gradient", label: "Gradient", category: "bold" },

  // Classic / news
  { v: "news", label: "News", category: "classic" },
  { v: "cinema", label: "Cinema", category: "classic" },
  { v: "plain", label: "Plain", category: "classic" },

  // Minimal
  { v: "whisper", label: "Whisper", category: "minimal" },
  { v: "underline", label: "Underline", category: "minimal" },
  { v: "typewriter", label: "Typewriter", category: "minimal" },

  // Decorative
  { v: "sticker", label: "Sticker", category: "decorative" },
  { v: "comic", label: "Comic", category: "decorative" },
  { v: "retro", label: "Retro", category: "decorative" },
];

const CAPTION_CATEGORIES: Array<{
  v: CaptionCategory;
  label: string;
}> = [
  { v: "all", label: "All" },
  { v: "trendy", label: "Trending" },
  { v: "bold", label: "Bold" },
  { v: "classic", label: "Classic" },
  { v: "minimal", label: "Minimal" },
  { v: "decorative", label: "Decorative" },
];

const POSITIONS: Array<{ v: "top" | "middle" | "bottom"; label: string }> = [
  { v: "top", label: "Top" },
  { v: "middle", label: "Middle" },
  { v: "bottom", label: "Bottom" },
];

type Word = { word: string; start: number; end: number };

export default function BulkCaptionsPage() {
  const { state, refresh } = useMe();
  const me = state.status === "ready" ? state.me : null;
  const ready = state.status === "ready";

  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitNotice, setSubmitNotice] = useState<string | null>(null);
  // Optional project name for grouped Recent renders. Cleared on success.
  const [projectName, setProjectName] = useState("");
  // When set, new uploads merge into that existing project instead of
  // creating a new one. Empty string = "New project" (use projectName).
  const [pickedProjectId, setPickedProjectId] = useState("");
  // Existing projects available to add to — populated from listProjects.
  const [existingProjects, setExistingProjects] = useState<
    { projectId: string; projectName: string; jobCount: number }[]
  >([]);
  // Language hint for the transcriber. "auto" = let it detect, but
  // Hindi/Urdu users will want to pin to avoid script flips.
  const [language, setLanguage] = useState<"auto" | "hi" | "en" | "ur">("auto");
  const inputRef = useRef<HTMLInputElement>(null);

  // All this user's bulk-captions transcribe jobs + their render children.
  const [transcribeJobs, setTranscribeJobs] = useState<Job[]>([]);
  const [renderJobs, setRenderJobs] = useState<Job[]>([]);

  // Which transcribed video the user has open in the editor.
  const [editingId, setEditingId] = useState<string | null>(null);
  // Remember the last opts the user rendered with — drives the "Apply
  // to all other videos" bulk button on the Library. We only track
  // values from a successful submit, so a half-tweaked unsaved state
  // doesn't accidentally get applied to 50 videos.
  const [lastUsedOpts, setLastUsedOpts] = useState<RenderOpts | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkNotice, setBulkNotice] = useState<string | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);

  // Hosted users don't need a personal key. Only BYO plans gate on hasKey.
  const needsKey = !!me?.byoMode;
  const hasKey = !!me?.geminiKeyMask;
  const missingByoKey = needsKey && !hasKey;

  const refreshJobs = useCallback(async () => {
    if (!ready) return;
    try {
      const res = await apiClient.listJobs({ limit: 200 });
      setTranscribeJobs(res.items.filter((j) => j.tool === "bulk-captions"));
      setRenderJobs(res.items.filter((j) => j.tool === "bulk-captions-render"));
    } catch {
      /* ignore — auth in flux */
    }
  }, [ready]);

  // Project list for the "Add to existing project" picker. Refreshed
  // on mount + whenever a submit succeeds (since a new project may
  // have appeared). Filtered to projects that already contain
  // bulk-captions jobs so the dropdown isn't polluted with voice-pair
  // or audio-to-video projects.
  const refreshProjects = useCallback(async () => {
    if (!ready) return;
    try {
      const res = await apiClient.listProjects({ limit: 50 });
      setExistingProjects(
        res.items
          .filter((p) => p.projectId && p.tools.includes("bulk-captions"))
          .map((p) => ({
            projectId: p.projectId!,
            projectName: p.projectName,
            jobCount: p.jobCount,
          })),
      );
    } catch {
      /* ignore — auth in flux */
    }
  }, [ready]);

  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  useEffect(() => {
    refreshJobs();
  }, [refreshJobs]);

  // Deep-link support: ?open=<jobId> opens that transcribe in the
  // editor as soon as it appears in the jobs list. Used by the voice-
  // pair tool to bounce the user from their finished render straight
  // into the captions editor. We wait for the job to be present AND
  // done (transcribe finished) before flipping editingId on so the
  // editor doesn't open against an empty transcript.
  const [pendingOpenId, setPendingOpenId] = useState<string | null>(null);
  // Embed mode: this page is rendered inside an iframe by the
  // voice-pair tool. We hide the library/upload chrome and postMessage
  // up to the parent when the editor closes so the modal dismisses.
  const [isEmbed, setIsEmbed] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const id = params.get("open");
    const embed = params.get("embed") === "1";
    if (embed) setIsEmbed(true);
    if (id) {
      setPendingOpenId(id);
      // Strip params so a refresh doesn't keep re-triggering the open
      // (we keep embed=1 because it's load-time only too).
      const u = new URL(window.location.href);
      u.searchParams.delete("open");
      u.searchParams.delete("embed");
      window.history.replaceState({}, "", u.toString());
    }
  }, []);
  useEffect(() => {
    if (!pendingOpenId) return;
    const job = transcribeJobs.find((j) => j.id === pendingOpenId);
    if (job && job.status === "done") {
      setEditingId(pendingOpenId);
      setPendingOpenId(null);
    }
  }, [pendingOpenId, transcribeJobs]);

  // Poll faster while anything is in flight.
  useEffect(() => {
    const anyActive =
      transcribeJobs.some((j) => j.status === "queued" || j.status === "running") ||
      renderJobs.some((j) => j.status === "queued" || j.status === "running");
    const interval = anyActive ? POLL_MS : 6000;
    const id = setInterval(refreshJobs, interval);
    return () => clearInterval(id);
  }, [transcribeJobs, renderJobs, refreshJobs]);

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

  async function submit() {
    if (files.length === 0) return;
    setSubmitting(true);
    setSubmitError(null);
    setSubmitNotice(null);
    // Chunk size = 1. Cloud Run HTTP/1.1 caps the request body at
    // 32MB; reel videos routinely hit 20-30MB each, so even 2 files
    // in one POST blows the limit and the proxy 502s before FastAPI
    // sees the request. One file per request keeps every upload
    // safely under the cap regardless of how many videos the user
    // selected — they all still merge into the same project via
    // projectId passthrough.
    const CHUNK_SIZE = 1;
    try {
      // First chunk creates the project (server generates an id when
      // none is supplied). Subsequent chunks reuse that id so all the
      // uploads end up grouped under the same project card.
      let projectIdForBatch = pickedProjectId || undefined;
      let totalQueued = 0;
      let totalRejected = 0;
      let resolvedProjectName: string | undefined;

      const chunks: File[][] = [];
      for (let i = 0; i < files.length; i += CHUNK_SIZE) {
        chunks.push(files.slice(i, i + CHUNK_SIZE));
      }
      for (let i = 0; i < chunks.length; i++) {
        setSubmitNotice(
          `Uploading batch ${i + 1} of ${chunks.length}…`,
        );
        const res = await apiClient.submitBulkCaptions(chunks[i], {
          projectName:
            i === 0 && !projectIdForBatch
              ? projectName.trim() || undefined
              : undefined,
          projectId: projectIdForBatch,
          language: language === "auto" ? undefined : language,
        });
        if (!projectIdForBatch && res.projectId) {
          projectIdForBatch = res.projectId;
        }
        if (res.projectName) resolvedProjectName = res.projectName;
        totalQueued += res.summary.queued;
        totalRejected += res.summary.rejected;
      }

      setFiles([]);
      if (inputRef.current) inputRef.current.value = "";
      const parts: string[] = [];
      if (totalQueued > 0) {
        const proj = resolvedProjectName ? ` in "${resolvedProjectName}"` : "";
        parts.push(`${totalQueued} transcribing${proj}`);
      }
      if (totalRejected > 0) parts.push(`${totalRejected} rejected`);
      setSubmitNotice(parts.join(" · ") || "Submitted.");
      setProjectName("");
      setPickedProjectId("");
      await refreshProjects();
      await refreshJobs();
      await refresh();
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e.message : "Submission failed.");
    } finally {
      setSubmitting(false);
    }
  }

  // Group renders by their parent transcribe job so each row knows
  // whether a render is in flight / complete.
  const rendersByParent = useMemo(() => {
    const m = new Map<string, Job[]>();
    for (const r of renderJobs) {
      const params = (r.params ?? {}) as Record<string, unknown>;
      const pid = (params.parentJobId as string | undefined) ?? "";
      if (!pid) continue;
      const arr = m.get(pid) ?? [];
      arr.push(r);
      m.set(pid, arr);
    }
    return m;
  }, [renderJobs]);

  const editingJob =
    editingId ? transcribeJobs.find((j) => j.id === editingId) ?? null : null;

  /** Shared bulk-render handler. Library's group button passes the
   *  stored `lastUsedOpts`; the Editor passes the live `opts` it has
   *  RIGHT NOW so the user can apply unsaved tweaks. */
  const runBulkApply = useCallback(
    async (parentIds: string[], opts: RenderOpts) => {
      setBulkBusy(true);
      setBulkNotice(null);
      setBulkError(null);
      try {
        const payload: CaptionRenderOpts = {
          style: opts.style,
          position: opts.position,
          wordsPerLine: opts.wordsPerLine,
          uppercase: opts.uppercase,
        };
        if (opts.posXFrac !== null) payload.posXFrac = opts.posXFrac;
        if (opts.posYFrac !== null) payload.posYFrac = opts.posYFrac;
        if (opts.primaryColor) payload.primaryColor = opts.primaryColor;
        if (opts.outlineColor) payload.outlineColor = opts.outlineColor;
        if (opts.outlineWidth !== null)
          payload.outlineWidth = opts.outlineWidth;
        if (opts.bgColor) payload.bgColor = opts.bgColor;
        if (opts.bgAlpha !== null) payload.bgAlpha = opts.bgAlpha;
        if (opts.fontSize !== null) payload.fontSize = opts.fontSize;
        if (opts.fontFamily) payload.fontFamily = opts.fontFamily;
        if (opts.shadow !== null) payload.shadow = opts.shadow;
        const res = await apiClient.submitCaptionsRenderBulk(
          parentIds,
          payload,
        );
        const parts = [`${res.summary.queued} queued`];
        if (res.summary.rejected > 0)
          parts.push(`${res.summary.rejected} rejected`);
        setBulkNotice(parts.join(" · "));
        await refreshJobs();
        await refresh();
      } catch (e) {
        setBulkError(
          e instanceof ApiError ? e.message : "Bulk render failed.",
        );
      } finally {
        setBulkBusy(false);
      }
    },
    [refresh, refreshJobs],
  );

  // Other transcribed videos in the same project as the one being
  // edited. Used to show an "Apply to all N other videos" button INSIDE
  // the editor once the user has rendered once. Same-project means same
  // projectId; unfiled (null) videos don't get sibling suggestions.
  const projectSiblings = useMemo(() => {
    if (!editingJob || !editingJob.projectId) return [];
    return transcribeJobs.filter(
      (j) =>
        j.id !== editingJob.id &&
        j.projectId === editingJob.projectId &&
        j.status === "done",
    );
  }, [editingJob, transcribeJobs]);

  return (
    <div className={isEmbed ? "" : "px-6 md:px-10 py-10 md:py-14 max-w-[1400px] mx-auto"}>
      {/* Page header / intro — hidden in embed mode where only the
          editor modal matters. The wrapping voice-pair page provides
          its own context (close button, page chrome). */}
      {!isEmbed && (
        <>
          <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
            Tool
          </div>
          <h1 className="mt-3 font-display text-[28px] md:text-[36px] tracking-[-0.035em] leading-[1.05]">
            Caption your videos
          </h1>
          <p className="mt-4 text-[15px] leading-[1.7] text-[var(--muted)] max-w-[680px]">
            Upload finished videos. We transcribe them with your Gemini key, then
            you tune the caption style on top of the actual video before rendering.
            Re-render with a different style anytime — transcription is cached so
            only the burn-in costs.
          </p>
        </>
      )}

      {state.status === "unauthenticated" && (
        <Banner kind="warn">
          You aren&apos;t signed in. Pick a dev user from the ⚡ menu in the topbar.
        </Banner>
      )}
      {state.status === "ready" && missingByoKey && (
        <Banner kind="warn">
          You&apos;re on a bring-your-own-key plan and haven&apos;t saved a
          Gemini API key yet.{" "}
          <Link href="/settings/api-keys" className="text-[var(--accent)] underline underline-offset-2">
            Add one in Settings
          </Link>{" "}
          before captioning.
        </Banner>
      )}

      {/* Editor — opens above the picker so it's the focus when active. */}
      {editingJob && (
        <Editor
          job={editingJob}
          renders={rendersByParent.get(editingJob.id) ?? []}
          onClose={() => {
            setEditingId(null);
            // In embed mode we don't show the rest of the page, so
            // closing the editor should dismiss the wrapping modal
            // instead of leaving the user staring at a blank iframe.
            if (isEmbed && typeof window !== "undefined") {
              window.parent?.postMessage(
                { type: "captions-editor-closed" },
                "*",
              );
            }
          }}
          onRendered={async (opts) => {
            // Remember this render's settings for the "Apply to all"
            // bulk action on the library. Only fires on successful
            // submit, so unsaved tweaks don't leak into the batch.
            if (opts) setLastUsedOpts(opts);
            await refreshJobs();
            await refresh();
          }}
          projectSiblings={projectSiblings}
          onApplyToProject={runBulkApply}
          bulkBusy={bulkBusy}
          bulkNotice={bulkNotice}
          bulkError={bulkError}
        />
      )}

      {!editingJob && !isEmbed && (
        <div className="mt-10 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6 md:p-8">
          <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
            Step 1
          </div>
          <h2 className="mt-2 font-display text-[20px] tracking-tight text-white">
            Pick videos to transcribe
          </h2>

          <label
            htmlFor="video-input"
            className={`mt-5 flex flex-col items-center justify-center gap-2 px-6 py-10 rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
              files.length
                ? "border-[var(--accent)]/50 bg-[var(--accent)]/5"
                : "border-[var(--line)] hover:border-[var(--accent)]/40 bg-[var(--bg)]"
            }`}
          >
            <span className="text-[14px] text-white">
              {files.length
                ? `${files.length} file${files.length === 1 ? "" : "s"} selected`
                : "Click to pick video files"}
            </span>
            <span className="text-[11.5px] text-[var(--muted)] font-mono text-center">
              mp4, mov, webm, mkv, m4v · 200 MB each · up to {MAX_FILES} at once
            </span>
            <input
              ref={inputRef}
              id="video-input"
              type="file"
              accept="video/*"
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

          {/* Project selector + language picker inline above submit.
              Two-row layout: top row is the project picker (add to an
              existing project OR start a new one); the project-name
              input only renders when "New project" is selected. */}
          <div className="mt-5 grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3">
            <select
              value={pickedProjectId}
              onChange={(e) => {
                setPickedProjectId(e.target.value);
                // Clear typed name when switching to an existing
                // project — that name would otherwise be ignored.
                if (e.target.value) setProjectName("");
              }}
              className="bg-black/30 border border-[var(--line)] rounded px-3 py-2 text-[13px] focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="">+ New project</option>
              {existingProjects.map((p) => (
                <option key={p.projectId} value={p.projectId}>
                  {p.projectName} ({p.jobCount})
                </option>
              ))}
            </select>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as typeof language)}
              className="bg-black/30 border border-[var(--line)] rounded px-3 py-2 text-[13px] focus:outline-none focus:border-[var(--accent)]"
              title="Force transcription language. Auto works for most clips."
            >
              <option value="auto">Language: Auto-detect</option>
              <option value="hi">Hindi</option>
              <option value="en">English</option>
              <option value="ur">Urdu</option>
            </select>
          </div>
          {!pickedProjectId && (
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="New project name (optional — defaults to timestamp)"
              maxLength={80}
              className="mt-3 w-full bg-black/30 border border-[var(--line)] rounded px-3 py-2 text-[13px] placeholder:text-[var(--muted)]/60 focus:outline-none focus:border-[var(--accent)]"
            />
          )}

          <div className="mt-4 flex items-center gap-3 flex-wrap">
            <button
              type="button"
              onClick={submit}
              disabled={!files.length || missingByoKey || submitting}
              className="inline-flex h-11 items-center px-5 rounded-full bg-[var(--accent)] text-black text-[13px] font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting
                ? "Uploading…"
                : files.length === 0
                  ? "Pick at least 1 video"
                  : `Transcribe ${files.length} video${files.length === 1 ? "" : "s"} →`}
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
      )}

      {/* Library — every transcribed video, with status & open-editor
          button. Skipped entirely in embed mode (voice-pair has its
          own library; showing another one inside the iframe would be
          confusing and duplicate-fetch jobs the user already sees). */}
      {!isEmbed && (
        <Library
          jobs={transcribeJobs}
          rendersByParent={rendersByParent}
          editingId={editingId}
          onEdit={setEditingId}
          lastUsedOpts={lastUsedOpts}
          bulkBusy={bulkBusy}
          bulkNotice={bulkNotice}
          bulkError={bulkError}
          onApplyToAll={async (parentIds) => {
            if (!lastUsedOpts) return;
            await runBulkApply(parentIds, lastUsedOpts);
          }}
          onApplyOptsToParents={runBulkApply}
        />
      )}
    </div>
  );
}

/* ---------- Editor ---------- */

/**
 * Canonical editor state. The caption position is stored as a fraction
 * (0..1) of the source frame — the drag handle on the stage updates
 * these values, and we send them to the backend as `posXFrac`/`posYFrac`
 * so libass `\pos()` can place the burnt-in caption at the same spot.
 *
 * `position` (top/middle/bottom) is kept only for the case where the
 * user opens the editor and never drags — we then send the discrete
 * anchor instead and let the backend pick the default margin.
 */
type RenderOpts = {
  style: CaptionStyle;
  position: "top" | "middle" | "bottom";
  wordsPerLine: number;
  uppercase: boolean;
  /** Caption center as a fraction of frame width.  null = not yet dragged. */
  posXFrac: number | null;
  /** Caption center as a fraction of frame height. null = not yet dragged. */
  posYFrac: number | null;
  // ---- Customize overrides (all null = use picked style's preset) ----
  primaryColor: string | null;
  outlineColor: string | null;
  outlineWidth: number | null;
  bgColor: string | null;
  /** 0=opaque, 255=transparent. */
  bgAlpha: number | null;
  fontSize: number | null;
  fontFamily: string | null;
  shadow: number | null;
};

const DEFAULT_OPTS: RenderOpts = {
  style: "plain",
  position: "bottom",
  wordsPerLine: 3,
  uppercase: false,
  posXFrac: null,
  posYFrac: null,
  primaryColor: null,
  outlineColor: null,
  outlineWidth: null,
  bgColor: null,
  bgAlpha: null,
  fontSize: null,
  fontFamily: null,
  shadow: null,
};

type EditorTab = "style" | "layout" | "text";

/** Backend named-colour palette mirrored here so the Customize tab can
 *  show the real preset colours in the swatch picker — without this the
 *  pickers default to empty/black even when the preset says "yellow". */
const NAMED_COLOR_HEX: Record<string, string> = {
  white: "#FFFFFF",
  black: "#000000",
  yellow: "#FFE04A",
  cyan: "#00F0FF",
  navy: "#0B2A4A",
  magenta: "#FF3D9C",
  red: "#FF3D3D",
  darkred: "#B30000",
  orange: "#FF8A2B",
  amber: "#FFC107",
  green: "#32D74B",
  lime: "#B6FF3C",
  blue: "#3B82F6",
  purple: "#A855F7",
  pink: "#FF6FCB",
  hotpink: "#FF1493",
  gold: "#F5C518",
  silver: "#C0C0C0",
  cream: "#FFF1D0",
  paper: "#F4ECD8",
  gray: "#8E8E93",
  darkgray: "#333333",
};

/** A subset of every backend STYLE_PRESETS field the Customize tab
 *  needs. Kept in sync by hand with api/tools/captions.py.
 *  - outlineWidth / shadow: percentages of font size (NOT abs px)
 *  - bgAlpha: 0=opaque, 255=transparent
 *  - useBack: when false, the preset has NO background pill — UI hides
 *    bg-color + bg-opacity controls so users don't fiddle with values
 *    that don't apply to this style. */
const STYLE_PRESET_DEFAULTS: Record<string, {
  primaryColor: string;
  outlineColor: string;
  outlineWidth: number;
  bgColor: string;
  bgAlpha: number;
  fontSizeRatio: number;
  shadow: number;
  fontFamily: string;
  useBack: boolean;
}> = {
  plain:      { primaryColor: "white",  outlineColor: "black",   outlineWidth: 9,  bgColor: "black",   bgAlpha: 80,  fontSizeRatio: 0.045, shadow: 0, fontFamily: "Inter",       useBack: true  },
  highlight:  { primaryColor: "white",  outlineColor: "black",   outlineWidth: 5,  bgColor: "cyan",    bgAlpha: 0,   fontSizeRatio: 0.045, shadow: 0, fontFamily: "Inter",       useBack: true  },
  karaoke:    { primaryColor: "yellow", outlineColor: "black",   outlineWidth: 7,  bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.05,  shadow: 0, fontFamily: "Inter",       useBack: false },
  outline:    { primaryColor: "cyan",   outlineColor: "black",   outlineWidth: 13, bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.05,  shadow: 0, fontFamily: "Inter",       useBack: false },
  neon:       { primaryColor: "white",  outlineColor: "cyan",    outlineWidth: 16, bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.05,  shadow: 7, fontFamily: "Inter",       useBack: false },
  gradient:   { primaryColor: "cyan",   outlineColor: "navy",    outlineWidth: 11, bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.052, shadow: 0, fontFamily: "Inter",       useBack: false },
  typewriter: { primaryColor: "white",  outlineColor: "black",   outlineWidth: 5,  bgColor: "black",   bgAlpha: 0,   fontSizeRatio: 0.04,  shadow: 0, fontFamily: "Courier New", useBack: true  },
  news:       { primaryColor: "white",  outlineColor: "darkred", outlineWidth: 10, bgColor: "darkred", bgAlpha: 0,   fontSizeRatio: 0.044, shadow: 0, fontFamily: "Inter",       useBack: true  },
  cinema:     { primaryColor: "white",  outlineColor: "black",   outlineWidth: 9,  bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.038, shadow: 0, fontFamily: "Inter",       useBack: false },
  mrbeast:    { primaryColor: "yellow", outlineColor: "black",   outlineWidth: 12, bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.058, shadow: 4, fontFamily: "Anton",       useBack: false },
  reels:      { primaryColor: "lime",   outlineColor: "black",   outlineWidth: 10, bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.055, shadow: 0, fontFamily: "Anton",       useBack: false },
  tiktok:     { primaryColor: "white",  outlineColor: "hotpink", outlineWidth: 10, bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.053, shadow: 3, fontFamily: "Anton",       useBack: false },
  whisper:    { primaryColor: "silver", outlineColor: "black",   outlineWidth: 6,  bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.036, shadow: 0, fontFamily: "Inter",       useBack: false },
  underline:  { primaryColor: "white",  outlineColor: "cyan",    outlineWidth: 12, bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.046, shadow: 0, fontFamily: "Inter",       useBack: false },
  sticker:    { primaryColor: "cream",  outlineColor: "white",   outlineWidth: 9,  bgColor: "black",   bgAlpha: 0,   fontSizeRatio: 0.046, shadow: 0, fontFamily: "Inter",       useBack: true  },
  comic:      { primaryColor: "yellow", outlineColor: "black",   outlineWidth: 11, bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.054, shadow: 3, fontFamily: "Bangers",     useBack: false },
  retro:      { primaryColor: "amber",  outlineColor: "darkred", outlineWidth: 9,  bgColor: "black",   bgAlpha: 255, fontSizeRatio: 0.05,  shadow: 5, fontFamily: "Anton",       useBack: false },
};

/** Resolve a colour value — either an explicit hex from a customize
 *  override, or the named hex from the preset palette. Used by colour
 *  pickers to show the right swatch when no override is set. */
function resolveColor(value: string | null | undefined, fallbackName: string): string {
  if (value && value.startsWith("#")) return value;
  if (value && NAMED_COLOR_HEX[value]) return NAMED_COLOR_HEX[value];
  return NAMED_COLOR_HEX[fallbackName] ?? "#FFFFFF";
}

/** Available font choices in Customize tab. These must match families
 *  available to libass on the backend (assets/fonts dir + system). */
const FONT_OPTIONS: Array<{ v: string; label: string }> = [
  { v: "Inter", label: "Inter (default)" },
  { v: "Bangers", label: "Bangers (comic)" },
  { v: "Courier New", label: "Courier New (mono)" },
  { v: "Impact", label: "Impact" },
  { v: "Arial Black", label: "Arial Black" },
  { v: "Georgia", label: "Georgia (serif)" },
];

/** Color swatches used by all color pickers. Hex sent to backend
 *  as-is — backend's _ass_color handles both names and hex. */
const COLOR_SWATCHES: string[] = [
  "#FFFFFF", "#000000", "#FFE04A", "#00F0FF", "#FF3D9C", "#FF3D3D",
  "#FF8A2B", "#32D74B", "#B6FF3C", "#3B82F6", "#A855F7", "#FF1493",
];

function Editor({
  job,
  renders,
  onClose,
  onRendered,
  projectSiblings,
  onApplyToProject,
  bulkBusy,
  bulkNotice,
  bulkError,
}: {
  job: Job;
  renders: Job[];
  onClose: () => void;
  /** Called after a successful submit. `opts` lets the parent remember
   *  the last-used render settings for the bulk "Apply to all" action. */
  onRendered: (opts?: RenderOpts) => Promise<void> | void;
  /** Other transcribed videos in the SAME project as `job`. Empty when
   *  this video is the only one in its project (or unfiled). */
  projectSiblings: Job[];
  /** Fire the bulk-render with the current editor opts onto every
   *  sibling parent id. Parent's `onApplyToAll` already exists; we
   *  just delegate. */
  onApplyToProject: (parentIds: string[], opts: RenderOpts) => Promise<void> | void;
  bulkBusy: boolean;
  bulkNotice: string | null;
  bulkError: string | null;
}) {
  const [opts, setOpts] = useState<RenderOpts>(DEFAULT_OPTS);
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Category tab for the style grid. Default to "Trending" so users hit
  // the most-picked styles first.
  const [styleCategory, setStyleCategory] = useState<CaptionCategory>("trendy");
  const visibleStyles = useMemo(
    () =>
      styleCategory === "all"
        ? CAPTION_STYLES
        : CAPTION_STYLES.filter((s) => s.category === styleCategory),
    [styleCategory],
  );
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [tab, setTab] = useState<EditorTab>("style");
  const videoRef = useRef<HTMLVideoElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);

  // Default = the original uploaded video. Once a render finishes we
  // swap the player to the burned-in mp4 so the user sees REAL captions,
  // not just the dragging preview overlay.
  const originalUrl = useMemo(
    () => apiClient.jobOutputUrl(job.id, { variant: "original" }),
    [job.id],
  );

  // Lock page scroll + listen for Escape while the full-page editor
  // is open. Restores both on unmount so the underlying library page
  // scrolls normally again.
  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  // Pull transcript once.
  useEffect(() => {
    let cancelled = false;
    setTranscript(null);
    setTranscriptError(null);
    apiClient
      .getTranscript(job.id)
      .then((t) => {
        if (!cancelled) {
          setTranscript(t);
          // When running inside the voice-pair iframe modal, the parent
          // page is showing a "Loading editor…" overlay. Once the
          // transcript lands the editor is actually usable, so signal
          // ready up so the overlay can fade out.
          if (typeof window !== "undefined" && window.parent !== window) {
            window.parent.postMessage(
              { type: "captions-editor-ready" },
              "*",
            );
          }
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setTranscriptError(
            e instanceof ApiError ? e.message : "Failed to load transcript.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [job.id]);

  // Track playhead + play/pause state for the custom toolbar.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onTime = () => setCurrentTime(v.currentTime);
    const onMeta = () => setDuration(v.duration || 0);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("seeked", onTime);
    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("seeked", onTime);
      v.removeEventListener("loadedmetadata", onMeta);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
    };
  }, [transcript]);

  const activeRender = renders.find(
    (r) => r.status === "queued" || r.status === "running",
  );
  const lastDoneRender = [...renders]
    .filter((r) => r.status === "done")
    .sort(
      (a, b) =>
        new Date(b.updatedAt ?? 0).getTime() - new Date(a.updatedAt ?? 0).getTime(),
    )[0];

  // When a captioned render exists, default the player to it (so the
  // user sees REAL burned-in captions, not the drag-preview overlay).
  // The "Show original" toggle lets them flip back when restyling.
  const [showOriginal, setShowOriginal] = useState(false);

  // Auto-flip back to the original when the user starts editing (changes
  // style, position, slider, or any Customize knob). Otherwise they see
  // the burned mp4 with no drag handle and think the editor is broken.
  // We watch the same opts the render endpoint cares about.
  const optsFingerprint = JSON.stringify({
    s: opts.style,
    p: opts.position,
    w: opts.wordsPerLine,
    u: opts.uppercase,
    pc: opts.primaryColor,
    oc: opts.outlineColor,
    ow: opts.outlineWidth,
    bc: opts.bgColor,
    ba: opts.bgAlpha,
    fs: opts.fontSize,
    ff: opts.fontFamily,
    sh: opts.shadow,
  });
  const firstFingerprintRef = useRef(optsFingerprint);
  useEffect(() => {
    if (optsFingerprint !== firstFingerprintRef.current) {
      firstFingerprintRef.current = optsFingerprint;
      setShowOriginal(true);
    }
  }, [optsFingerprint]);

  const showingBurned = !!lastDoneRender && !activeRender && !showOriginal;
  const playerSrc = showingBurned
    ? apiClient.jobOutputUrl(lastDoneRender.id, {
        variant: "active",
        cacheKey: lastDoneRender.updatedAt ?? lastDoneRender.id,
      })
    : originalUrl;

  async function submit() {
    setSubmitting(true);
    setSubmitError(null);
    try {
      // Resolve which position to send: drag wins over discrete anchor.
      // Customize-tab overrides are only included when the user actually
      // touched them — backend treats `null` as "use preset value".
      const payload: Parameters<typeof apiClient.submitCaptionsRender>[1] = {
        style: opts.style,
        position: opts.position,
        wordsPerLine: opts.wordsPerLine,
        uppercase: opts.uppercase,
      };
      if (opts.posXFrac !== null) payload.posXFrac = opts.posXFrac;
      if (opts.posYFrac !== null) payload.posYFrac = opts.posYFrac;
      if (opts.primaryColor) payload.primaryColor = opts.primaryColor;
      if (opts.outlineColor) payload.outlineColor = opts.outlineColor;
      if (opts.outlineWidth !== null)
        payload.outlineWidth = opts.outlineWidth;
      if (opts.bgColor) payload.bgColor = opts.bgColor;
      if (opts.bgAlpha !== null) payload.bgAlpha = opts.bgAlpha;
      if (opts.fontSize !== null) payload.fontSize = opts.fontSize;
      if (opts.fontFamily) payload.fontFamily = opts.fontFamily;
      if (opts.shadow !== null) payload.shadow = opts.shadow;
      // Flip to original while the new render is in flight so the user
      // can drag/restyle without an outdated burned video flashing.
      setShowOriginal(true);
      await apiClient.submitCaptionsRender(job.id, payload);
      // Once render kicks off, queue an auto-flip back to the burned
      // variant the moment a new completion lands.
      setShowOriginal(false);
      // Surface the resolved opts back to the page so it can power the
      // "Apply this style to all other videos" library button.
      await onRendered(opts);
    } catch (e) {
      console.error("[captions submit] failed:", e);
      const msg =
        e instanceof ApiError
          ? `${e.message} (HTTP ${e.status})`
          : e instanceof Error
            ? `Render failed: ${e.message}`
            : "Render failed to start.";
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  function togglePlay() {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) v.play();
    else v.pause();
  }
  function seekTo(t: number) {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Math.max(0, Math.min(t, duration || t));
  }

  // Aspect for the stage. We compute a max-width formula so the video
  // never overflows the column AND never gets too tall.
  const ar =
    job.videoWidth && job.videoHeight ? job.videoWidth / job.videoHeight : 9 / 16;

  return (
    <div
      className="fixed inset-0 z-50 bg-[var(--bg)] flex flex-col"
      role="dialog"
      aria-modal="true"
      aria-label="Caption editor"
    >
      {/* Top breadcrumb header — fixed, never scrolls. ESC / Library button
          closes the overlay. */}
      <div className="shrink-0 flex items-center gap-3 px-5 md:px-6 h-14 border-b border-[var(--line)] bg-[var(--surface)]">
        <button
          type="button"
          onClick={onClose}
          className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--muted)] hover:text-white font-mono"
        >
          ← Library
        </button>
        <span aria-hidden className="h-4 w-px bg-[var(--line)]" />
        <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--accent)] font-mono">
          Editor
        </span>
        <span className="text-[13px] text-white truncate flex-1 min-w-0">
          {job.label || "Video"}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close editor"
          className="ml-auto h-9 w-9 rounded-full hover:bg-[var(--bg)] text-[var(--muted)] hover:text-white flex items-center justify-center text-[18px]"
        >
          ×
        </button>
      </div>

      {/* 2-column body — flex-1 fills remaining viewport height. Each
          column scrolls independently (Canva-style). Below `lg` it
          collapses to stacked vertical so phone-size still reads cleanly. */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[1fr_380px]">

      {/* LEFT: theatre stage + custom video toolbar. Independent scroll
          so a tall video doesn't push the right sidebar off-screen. */}
      <div className="overflow-y-auto bg-[#08090c] px-4 md:px-6 py-5 md:py-7 border-b lg:border-b-0 lg:border-r border-[var(--line)] flex flex-col items-center">
        <div
          ref={stageRef}
          className="relative mx-auto bg-black rounded-md overflow-hidden shadow-2xl"
          style={{
            aspectRatio: `${ar}`,
            // Use almost the whole canvas height (full-page editor gives
            // us the room). 80vh leaves space for the video toolbar + a
            // little breathing.
            maxHeight: "calc(100vh - 180px)",
            maxWidth: `calc((100vh - 180px) * ${ar})`,
            width: "100%",
            // containerType lives HERE (on the stage) so the caption's
            // cqh/cqw font + width units resolve against the actual video
            // frame size, not the 0-width draggable wrapper.
            containerType: "size",
          }}
        >
          <video
            ref={videoRef}
            src={playerSrc}
            autoPlay
            loop
            muted={false}
            playsInline
            className="absolute inset-0 w-full h-full object-contain"
            onClick={togglePlay}
          />
          {/* Drag-preview overlay only shows on the ORIGINAL video — when
              we're playing the burned mp4 the captions are already baked in
              and a second overlay would double them up. */}
          {transcript && !showingBurned && (
            <DraggableCaption
              words={transcript.words}
              currentTime={currentTime}
              opts={opts}
              stageRef={stageRef}
              onMove={(x, y) =>
                setOpts((o) => ({ ...o, posXFrac: x, posYFrac: y }))
              }
            />
          )}
          {/* Toggle + hint. On burned view we explicitly tell the user to
              flip back to original if they want to drag/restyle, since the
              drag overlay is intentionally hidden over the burned mp4. */}
          {lastDoneRender && !activeRender && (
            <button
              type="button"
              onClick={() => setShowOriginal((v) => !v)}
              className="absolute top-3 right-3 z-10 text-[11px] uppercase tracking-[0.18em] font-mono px-3 py-1.5 rounded-full bg-black/70 text-white hover:bg-[var(--accent)] hover:text-black backdrop-blur border border-white/20"
              title={showingBurned ? "Switch to original video to drag captions or edit style" : "View the captioned render"}
            >
              {showingBurned ? "Captioned · edit original" : "Original · show captioned"}
            </button>
          )}
        </div>

        {/* Custom video toolbar */}
        <div className="mx-auto mt-3 flex items-center gap-3 max-w-[640px] text-[var(--muted)]">
          <button
            type="button"
            onClick={togglePlay}
            className="h-9 w-9 rounded-full bg-[var(--surface)] border border-[var(--line)] hover:border-[var(--accent)] hover:text-white flex items-center justify-center"
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="5" width="4" height="14" rx="1" />
                <rect x="14" y="5" width="4" height="14" rx="1" />
              </svg>
            ) : (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                <path d="M7 5v14l12-7z" />
              </svg>
            )}
          </button>
          <input
            type="range"
            min={0}
            max={Math.max(duration, 0.1)}
            step={0.05}
            value={currentTime}
            onChange={(e) => seekTo(Number(e.target.value))}
            className="flex-1 h-1.5 accent-[var(--accent)]"
          />
          <span className="text-[11px] font-mono whitespace-nowrap">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>
        </div>
      </div>
      {/* end LEFT */}

      {/* RIGHT: sidebar with tabs + sticky action bar at bottom.
          h-full + min-h-0 so the inner scroll region honors the grid
          row's height (full editor viewport minus the breadcrumb). */}
      <div className="flex flex-col h-full min-h-0 bg-[var(--surface)]">
      {/* Tabbed settings panel */}
      <div className="flex-1 min-h-0 flex flex-col">
        {/* Tabs strip — 4 tabs need to fit a 380px sidebar without the
            last label kissing the close button. Reduced padding +
            tighter tracking + space-around layout gives each label
            equal breathing room. */}
        <div className="px-2 flex items-end justify-around gap-0 border-b border-[var(--line)]">
          {(
            [
              { id: "style", label: "Style" },
              { id: "layout", label: "Layout" },
              { id: "text", label: "Text" },
            ] as const
          ).map((t) => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`relative px-2 h-11 text-[11.5px] font-mono uppercase tracking-[0.12em] transition-colors ${
                  active
                    ? "text-white"
                    : "text-[var(--muted)] hover:text-white"
                }`}
              >
                {t.label}
                {active && (
                  <span
                    aria-hidden
                    className="absolute left-1.5 right-1.5 -bottom-px h-0.5 bg-[var(--accent)] rounded-full"
                  />
                )}
              </button>
            );
          })}
        </div>

        <div className="px-4 md:px-5 py-4 flex-1 overflow-y-auto">
          {transcriptError && (
            <div className="mb-4 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-[12px] text-red-200">
              {transcriptError}
            </div>
          )}

          {tab === "style" && (
            <div className="space-y-3">
              {/* Category filter — sticky just above the grid */}
              <div className="flex gap-1.5 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1">
                {CAPTION_CATEGORIES.map((c) => {
                  const active = styleCategory === c.v;
                  const count =
                    c.v === "all"
                      ? CAPTION_STYLES.length
                      : CAPTION_STYLES.filter((s) => s.category === c.v).length;
                  return (
                    <button
                      key={c.v}
                      type="button"
                      onClick={() => setStyleCategory(c.v)}
                      className={`whitespace-nowrap rounded-full px-3 py-1 text-[11.5px] font-medium transition-colors ${
                        active
                          ? "bg-[var(--accent)] text-black"
                          : "bg-[var(--bg)] text-[var(--muted)] hover:text-white border border-[var(--line)]"
                      }`}
                    >
                      {c.label}
                      <span
                        className={`ml-1.5 text-[10px] font-mono ${
                          active ? "opacity-70" : "opacity-60"
                        }`}
                      >
                        {count}
                      </span>
                    </button>
                  );
                })}
              </div>
              <div className="grid grid-cols-3 gap-2 max-h-[420px] overflow-y-auto pr-1">
                {visibleStyles.map((s) => {
                  const active = opts.style === s.v;
                  return (
                    <button
                      key={s.v}
                      type="button"
                      onClick={() => setOpts((o) => ({ ...o, style: s.v }))}
                      title={s.label}
                      aria-label={s.label}
                      className={`relative overflow-hidden rounded-md border-2 transition-colors ${
                        active
                          ? "border-[var(--accent)] ring-1 ring-[var(--accent)]/40"
                          : "border-[var(--line)] hover:border-[var(--line-2)]"
                      }`}
                    >
                      <CaptionStyleTile style={s.v} />
                      {active && (
                        <div className="absolute top-1.5 right-1.5 h-5 w-5 rounded-full bg-[var(--accent)] flex items-center justify-center shadow-lg">
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="black" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {tab === "layout" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 max-w-[720px]">
              <Field label="Anchor (one-tap presets)">
                <div className="flex gap-1.5">
                  {POSITIONS.map((p) => {
                    const active =
                      opts.posXFrac === null && opts.position === p.v;
                    return (
                      <button
                        key={p.v}
                        type="button"
                        onClick={() =>
                          setOpts((o) => ({
                            ...o,
                            position: p.v,
                            // Clear drag override when picking a preset
                            posXFrac: null,
                            posYFrac: null,
                          }))
                        }
                        className={`flex-1 px-2 py-1.5 rounded-md border text-[11.5px] transition-colors ${
                          active
                            ? "border-[var(--accent)] bg-[var(--accent)]/5 text-white"
                            : "border-[var(--line)] text-[var(--muted)] hover:text-white"
                        }`}
                      >
                        {p.label}
                      </button>
                    );
                  })}
                </div>
                <p className="mt-1.5 text-[10.5px] text-[var(--muted)] font-mono">
                  {opts.posXFrac !== null && opts.posYFrac !== null
                    ? `Custom · ${(opts.posXFrac * 100).toFixed(0)}% × ${(opts.posYFrac * 100).toFixed(0)}% — drag the caption on the video to adjust`
                    : "Or drag the caption directly on the video"}
                </p>
              </Field>

              <Field label={`Words per line · ${opts.wordsPerLine}`}>
                <input
                  type="range"
                  min={1}
                  max={5}
                  step={1}
                  value={opts.wordsPerLine}
                  onChange={(e) =>
                    setOpts((o) => ({
                      ...o,
                      wordsPerLine: Number(e.target.value),
                    }))
                  }
                  className="w-full h-9 accent-[var(--accent)]"
                />
              </Field>
            </div>
          )}

          {tab === "text" && (
            <div className="max-w-[420px] space-y-4">
              <label className="flex items-center gap-2.5 text-[13px] text-white cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={opts.uppercase}
                  onChange={(e) =>
                    setOpts((o) => ({ ...o, uppercase: e.target.checked }))
                  }
                  className="accent-[var(--accent)] h-4 w-4"
                />
                Force ALL CAPS
              </label>
              <p className="text-[11.5px] text-[var(--muted)] leading-[1.55]">
                Bold style is always uppercase regardless. More text controls
                (font size, color) coming soon.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Sticky action bar at bottom of right sidebar */}
      <div className="border-t border-[var(--line)] bg-[var(--surface)] px-4 md:px-5 py-3.5 space-y-2.5">
        {activeRender ? (
          <div className="flex items-center gap-3">
            <div className="h-1.5 flex-1 bg-[var(--bg)] rounded-full overflow-hidden">
              <div
                className="h-full bg-[var(--accent)] transition-all"
                style={{ width: `${activeRender.progress}%` }}
              />
            </div>
            <span className="text-[11.5px] font-mono text-[var(--accent)] truncate">
              {activeRender.progress}%
            </span>
          </div>
        ) : lastDoneRender ? (
          <a
            href={apiClient.jobOutputUrl(lastDoneRender.id, { variant: "active" })}
            className="block text-[12px] text-[var(--accent)] hover:underline font-mono"
          >
            Download last render ↓
          </a>
        ) : (
          <span className="block text-[11.5px] font-mono text-[var(--muted)]">
            Drag the caption on the video. Hit render when ready.
          </span>
        )}
        {submitError && (
          <p className="text-[11.5px] text-red-300 font-mono">✕ {submitError}</p>
        )}

        <button
          type="button"
          onClick={submit}
          disabled={submitting || !!activeRender || !transcript}
          className="w-full inline-flex h-11 items-center justify-center px-6 rounded-full bg-[var(--accent)] text-black text-[13px] font-semibold disabled:opacity-40 disabled:cursor-not-allowed shadow-[0_0_18px_var(--accent-glow)]"
        >
          {submitting
            ? "Submitting…"
            : activeRender
              ? "Rendering…"
              : lastDoneRender
                ? "Apply style change →"
                : "Render captioned video →"}
        </button>

        {/* Apply current style to every other video in the same project.
            Only meaningful once THIS video has rendered successfully —
            otherwise the user is bulk-applying a style they haven't
            previewed. Shows project sibling count and queue status. */}
        {lastDoneRender && projectSiblings.length > 0 && (
          <div className="space-y-2">
            <button
              type="button"
              onClick={() =>
                onApplyToProject(
                  projectSiblings.map((j) => j.id),
                  opts,
                )
              }
              disabled={bulkBusy}
              className="w-full inline-flex h-10 items-center justify-center px-5 rounded-full border border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--accent)] text-[12px] font-semibold uppercase tracking-[0.14em] hover:bg-[var(--accent)]/20 disabled:opacity-40 disabled:cursor-not-allowed"
              title={`Render the other ${projectSiblings.length} videos in this project with the same style`}
            >
              {bulkBusy
                ? "Submitting…"
                : `Apply this style to ${projectSiblings.length} other video${
                    projectSiblings.length === 1 ? "" : "s"
                  } in project`}
            </button>
            {bulkNotice && (
              <p className="text-[11.5px] text-[var(--accent)] font-mono">
                {bulkNotice}
              </p>
            )}
            {bulkError && (
              <p className="text-[11.5px] text-red-300 font-mono">✕ {bulkError}</p>
            )}
          </div>
        )}

        {/* Remove captions — only visible once a captioned render exists.
            Wipes the burned mp4 + clears the activeCaptionsJobId pointer
            on the parent. Original video + transcript are kept so the
            user can re-render with a different style. */}
        {lastDoneRender && !activeRender && (
          <RemoveCaptionsButton
            parentJobId={job.id}
            onCleared={async () => {
              setOpts((o) => ({ ...o, posXFrac: null, posYFrac: null }));
              setShowOriginal(true);
              await onRendered();
            }}
          />
        )}
      </div>
      </div>
      </div>
    </div>
  );
}

/**
 * One-click "Remove captions" — wipes the burned mp4 + clears the
 * activeCaptionsJobId pointer on the parent. Keeps original + transcript.
 */
function RemoveCaptionsButton({
  parentJobId,
  onCleared,
}: {
  parentJobId: string;
  onCleared: () => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function go() {
    if (busy) return;
    if (
      !confirm(
        "Remove the burned captions? The original video and transcript will be kept so you can apply a different style.",
      )
    ) {
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await apiClient.clearCaptions(parentJobId);
      await onCleared();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't remove captions.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={go}
        disabled={busy}
        className="w-full inline-flex h-9 items-center justify-center px-4 rounded-full border border-[var(--line)] text-[12px] text-[var(--muted)] hover:border-red-500/60 hover:text-red-300 transition-colors disabled:opacity-50"
      >
        {busy ? "Removing…" : "Remove captions"}
      </button>
      {err && <p className="text-[11px] text-red-300 font-mono">{err}</p>}
    </>
  );
}

/** CSS alpha 0..1 → 2-char hex appended to a #RRGGBB color, giving
 *  the #RRGGBBAA shorthand modern browsers accept. */
function bgAlphaToHex(a: number): string {
  const clamped = Math.max(0, Math.min(1, a));
  return Math.round(clamped * 255)
    .toString(16)
    .padStart(2, "0")
    .toUpperCase();
}

function formatTime(t: number): string {
  if (!Number.isFinite(t) || t < 0) return "0:00";
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/* ---------- Caption overlay (transcript-driven, draggable) ---------- */

function DraggableCaption({
  words,
  currentTime,
  opts,
  stageRef,
  onMove,
}: {
  words: Word[];
  currentTime: number;
  opts: RenderOpts;
  /** Ref to the stage element so we can compute fractional coords from
   *  raw pointer positions during a drag. */
  stageRef: React.RefObject<HTMLDivElement | null>;
  /** Called with new (xFrac, yFrac) on every drag move. */
  onMove: (xFrac: number, yFrac: number) => void;
}) {
  // Group words into N-word lines, mirroring backend `_group_words_into_lines`.
  const lines = useMemo(() => {
    const out: Array<{ start: number; end: number; words: Word[] }> = [];
    const n = Math.max(1, Math.min(8, Math.round(opts.wordsPerLine)));
    for (let i = 0; i < words.length; i += n) {
      const chunk = words.slice(i, i + n);
      if (!chunk.length) continue;
      out.push({
        start: chunk[0].start,
        end: chunk[chunk.length - 1].end,
        words: chunk,
      });
    }
    return out;
  }, [words, opts.wordsPerLine]);

  // Find the line whose [start,end] covers currentTime. If none, find the
  // most recent past line and hold it for ~0.4s, otherwise nothing.
  const currentLine = useMemo(() => {
    const t = currentTime;
    const exact = lines.find((l) => t >= l.start && t <= l.end);
    if (exact) return exact;
    return null;
  }, [lines, currentTime]);

  // Hooks for drag state must run on every render — Rules of Hooks. We
  // gate the rendered output further down by hiding the overlay when
  // there's no active caption line.
  const [hovered, setHovered] = useState(false);
  const [dragging, setDragging] = useState(false);

  // Hide the overlay between caption lines (small silent gaps).
  if (!currentLine) return null;

  // Karaoke: which word inside the current line is active right now?
  let activeWordIdx = -1;
  for (let i = 0; i < currentLine.words.length; i++) {
    const w = currentLine.words[i];
    if (currentTime >= w.start && currentTime <= w.end) {
      activeWordIdx = i;
      break;
    }
  }
  if (activeWordIdx === -1) {
    // Fall back to last past word so the highlight doesn't blink off.
    for (let i = currentLine.words.length - 1; i >= 0; i--) {
      if (currentTime >= currentLine.words[i].start) {
        activeWordIdx = i;
        break;
      }
    }
  }

  const baseText = currentLine.words.map((w) => w.word).join(" ");
  const text = opts.uppercase ? baseText.toUpperCase() : baseText;

  // If the user has touched ANY Customize-tab knob, switch the preview
  // to a generic "effective values" render so they see their tweaks
  // reflected directly. The per-style branches below still run for the
  // out-of-the-box preview when no overrides are active.
  const hasOverride =
    opts.primaryColor !== null ||
    opts.outlineColor !== null ||
    opts.outlineWidth !== null ||
    opts.bgColor !== null ||
    opts.bgAlpha !== null ||
    opts.fontSize !== null ||
    opts.fontFamily !== null ||
    opts.shadow !== null;

  // Same style branches as CaptionStyleTile / CaptionOverlay.
  let captionEl: React.ReactNode;
  if (hasOverride) {
    // Build a preview that honors every override the user set. Falls
    // back to sensible defaults that read on top of any video.
    const primary = opts.primaryColor ?? "#FFFFFF";
    const outline = opts.outlineColor ?? "#000000";
    const outlineW = opts.outlineWidth ?? 2;
    const bg = opts.bgColor ?? "#000000";
    // bgAlpha = 0=opaque, 255=transparent. Convert to CSS rgba alpha 0..1.
    const bgAlphaCss =
      opts.bgAlpha === null ? 0 : 1 - opts.bgAlpha / 255;
    const fontSizePx = opts.fontSize ?? null;
    const fontFamily = opts.fontFamily ?? "Inter";
    const shadow = opts.shadow ?? 0;

    const textShadow =
      shadow > 0
        ? `0 0 ${shadow * 1.2}px ${outline}, 0 0 ${shadow * 2}px ${outline}`
        : undefined;

    captionEl = (
      <span
        className="inline-block font-bold leading-tight"
        style={{
          color: primary,
          fontFamily,
          fontSize: fontSizePx
            ? `${fontSizePx}px`
            : "clamp(12px, 3.6cqh, 26px)",
          paintOrder: "stroke fill",
          WebkitTextStroke: outlineW > 0 ? `${outlineW}px ${outline}` : undefined,
          background:
            bgAlphaCss > 0
              ? `${bg}${bgAlphaToHex(bgAlphaCss)}`
              : undefined,
          padding: bgAlphaCss > 0 ? "0.22em 0.7em" : undefined,
          borderRadius: bgAlphaCss > 0 ? "4px" : undefined,
          textShadow,
        }}
      >
        {text}
      </span>
    );
  } else
  if (opts.style === "plain") {
    captionEl = (
      <span
        className="inline-block rounded font-semibold leading-tight"
        style={{
          background: "rgba(0,0,0,0.7)",
          color: "#FFFFFF",
          fontSize: "clamp(12px, 3.6cqh, 26px)",
          padding: "0.22em 0.7em",
        }}
      >
        {text}
      </span>
    );
  } else if (opts.style === "highlight") {
    captionEl = (
      <span
        className="inline-block rounded font-bold leading-tight"
        style={{
          background: "#00F0FF",
          color: "#FFFFFF",
          paintOrder: "stroke fill",
          WebkitTextStroke: "1px #000",
          fontSize: "clamp(12px, 3.6cqh, 26px)",
          padding: "0.24em 0.8em",
        }}
      >
        {text}
      </span>
    );
  } else if (opts.style === "outline") {
    captionEl = (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#00F0FF",
          fontSize: "clamp(12px, 3.6cqh, 26px)",
          paintOrder: "stroke fill",
          WebkitTextStroke: "4px #000",
        }}
      >
        {text}
      </span>
    );
  } else if (opts.style === "neon") {
    captionEl = (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#FFFFFF",
          fontSize: "clamp(12px, 3.6cqh, 26px)",
          paintOrder: "stroke fill",
          WebkitTextStroke: "2px #00F0FF",
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
  } else if (opts.style === "gradient") {
    captionEl = (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#00F0FF",
          fontSize: "clamp(12px, 3.6cqh, 26px)",
          paintOrder: "stroke fill",
          WebkitTextStroke: "4px #0B2A4A",
          textShadow:
            "0 1px 0 rgba(255,255,255,0.4), 0 -1px 0 rgba(0,0,0,0.6)",
        }}
      >
        {text}
      </span>
    );
  } else if (opts.style === "typewriter") {
    captionEl = (
      <span
        className="inline-block font-medium leading-tight"
        style={{
          background: "#000",
          color: "#FFFFFF",
          fontSize: "clamp(11px, 3.2cqh, 22px)",
          padding: "0.2em 0.7em",
          fontFamily:
            '"JetBrains Mono", "Courier New", ui-monospace, monospace',
          letterSpacing: "0.02em",
        }}
      >
        {text}
      </span>
    );
  } else if (opts.style === "news") {
    captionEl = (
      <span
        className="inline-block font-bold leading-tight"
        style={{
          background: "#B30000",
          color: "#FFFFFF",
          fontSize: "clamp(12px, 3.6cqh, 26px)",
          padding: "0.22em 0.8em",
          letterSpacing: "0.02em",
        }}
      >
        {text}
      </span>
    );
  } else if (opts.style === "cinema") {
    captionEl = (
      <span
        className="inline-block leading-tight"
        style={{
          color: "#FFFFFF",
          fontSize: "clamp(11px, 3.2cqh, 22px)",
          fontWeight: 500,
          fontStyle: "italic",
          textShadow:
            "0 1px 3px rgba(0,0,0,0.95), 0 0 6px rgba(0,0,0,0.7)",
        }}
      >
        {text}
      </span>
    );
  } else if (opts.style === "mrbeast") {
    captionEl = (
      <span
        className="inline-block leading-none tracking-tight"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          color: "#FFE04A",
          fontSize: "clamp(15px, 4.4cqh, 34px)",
          fontWeight: 400,
          paintOrder: "stroke fill",
          WebkitTextStroke: "5px #000",
          textShadow:
            "0 3px 0 #000, 0 5px 8px rgba(0,0,0,0.7)",
        }}
      >
        {text.toUpperCase()}
      </span>
    );
  } else if (opts.style === "reels") {
    captionEl = (
      <span
        className="inline-block leading-tight tracking-wide"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          color: "#B6FF3C",
          fontSize: "clamp(13px, 4cqh, 30px)",
          fontWeight: 400,
          paintOrder: "stroke fill",
          WebkitTextStroke: "4px #000",
          textShadow:
            "0 1px 0 #000, 0 -1px 0 #000, 1px 0 0 #000, -1px 0 0 #000",
        }}
      >
        {text.toUpperCase()}
      </span>
    );
  } else if (opts.style === "tiktok") {
    captionEl = (
      <span
        className="inline-block leading-tight"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          color: "#FFFFFF",
          fontSize: "clamp(12px, 3.6cqh, 26px)",
          fontWeight: 400,
          paintOrder: "stroke fill",
          WebkitTextStroke: "4px #FF1493",
          textShadow:
            "0 0 10px rgba(255,20,147,0.7), 0 0 20px rgba(255,20,147,0.4)",
        }}
      >
        {text}
      </span>
    );
  } else if (opts.style === "whisper") {
    captionEl = (
      <span
        className="inline-block leading-tight"
        style={{
          color: "#C0C0C0",
          fontSize: "clamp(10px, 3cqh, 20px)",
          fontWeight: 400,
          letterSpacing: "0.04em",
        }}
      >
        {text.toLowerCase()}
      </span>
    );
  } else if (opts.style === "underline") {
    captionEl = (
      <span
        className="inline-block font-extrabold leading-tight tracking-wide"
        style={{
          color: "#FFFFFF",
          fontSize: "clamp(12px, 3.6cqh, 26px)",
          paintOrder: "stroke fill",
          WebkitTextStroke: "2.5px #00F0FF",
        }}
      >
        {text}
      </span>
    );
  } else if (opts.style === "sticker") {
    captionEl = (
      <span
        className="inline-block font-bold leading-tight"
        style={{
          background: "#000",
          color: "#FFF1D0",
          fontSize: "clamp(11px, 3.3cqh, 22px)",
          padding: "0.25em 0.85em",
          // ASS has no rounded corners — keep this square to match.
          border: "3px solid #FFF",
        }}
      >
        {text}
      </span>
    );
  } else if (opts.style === "comic") {
    captionEl = (
      <span
        className="inline-block leading-none tracking-tight"
        style={{
          fontFamily: 'var(--font-bangers), "Bangers", "Impact", system-ui',
          color: "#FFE04A",
          fontSize: "clamp(16px, 4.6cqh, 36px)",
          fontWeight: 400,
          paintOrder: "stroke fill",
          WebkitTextStroke: "3px #000",
          textShadow:
            "1px 1px 0 #000, 2px 2px 0 #000, 3px 3px 0 rgba(0,0,0,0.6)",
        }}
      >
        {text.toUpperCase()}
      </span>
    );
  } else if (opts.style === "retro") {
    captionEl = (
      <span
        className="inline-block leading-tight tracking-wide"
        style={{
          fontFamily: 'var(--font-anton), "Anton", Impact, sans-serif',
          color: "#FFC107",
          fontSize: "clamp(12px, 3.6cqh, 26px)",
          fontWeight: 400,
          paintOrder: "stroke fill",
          WebkitTextStroke: "3px #B30000",
          textShadow:
            "3px 3px 0 rgba(179,0,0,0.7)",
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
        style={{ fontSize: "clamp(16px, 5cqh, 36px)" }}
      >
        {currentLine.words.map((w, i) => {
          const isActive = i === activeWordIdx;
          return (
            <span
              key={i}
              className="inline-block transition-colors duration-150"
              style={{
                marginRight: i === currentLine.words.length - 1 ? 0 : "0.2em",
                color: isActive ? "#FFE04A" : "#FFFFFF",
                paintOrder: "stroke fill",
                WebkitTextStroke: "2px #000",
                textShadow:
                  "0 1px 0 #000, 0 -1px 0 #000, 1px 0 0 #000, -1px 0 0 #000",
              }}
            >
              {opts.uppercase ? w.word.toUpperCase() : w.word}
            </span>
          );
        })}
      </span>
    );
  }

  // Resolve the anchor on the stage. If the user has dragged, use the
  // fractional coords directly. Otherwise fall back to the discrete
  // top/middle/bottom anchor (centered horizontally, default V padding).
  const xFrac =
    opts.posXFrac ?? 0.5;
  const yFrac =
    opts.posYFrac ??
    (opts.position === "top"
      ? 0.1
      : opts.position === "middle"
        ? 0.5
        : 0.9);

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    const stage = stageRef.current;
    if (!stage) return;
    e.preventDefault();
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDragging(true);
    const rect = stage.getBoundingClientRect();
    // Compute drag offset within the caption element so dragging starts
    // from where the user grabbed it, not from its center.
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
        // While hovered or dragging, surround the caption with a faint
        // accent ring so users see it's draggable. Fades on rest.
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
      {/* Force the caption phrase onto ONE line — same behavior as the
          backend ASS render which uses WrapStyle 2 (no auto-wrap). The
          containerType:size on this draggable wrapper has no width
          (it's positioned via translate from a single point), so `cqw`
          would resolve against 0 → every word wrapped. nowrap is the
          right fix for "stay on one line". */}
      <div
        className="caption-pop inline-block text-center"
        style={{ whiteSpace: "nowrap" }}
      >
        {captionEl}
      </div>
    </div>
  );
}

/* ---------- Library ---------- */

function Library({
  jobs,
  rendersByParent,
  editingId,
  onEdit,
  lastUsedOpts,
  bulkBusy,
  bulkNotice,
  bulkError,
  onApplyToAll,
  onApplyOptsToParents,
}: {
  jobs: Job[];
  rendersByParent: Map<string, Job[]>;
  editingId: string | null;
  onEdit: (id: string) => void;
  /** When non-null, "Apply this style to all other videos" appears. */
  lastUsedOpts: RenderOpts | null;
  bulkBusy: boolean;
  bulkNotice: string | null;
  bulkError: string | null;
  onApplyToAll: (parentIds: string[]) => Promise<void> | void;
  /** Variant used by the per-project "Apply style of 1st video" button:
   *  caller passes the opts pulled from the project's first done render
   *  + the sibling parent ids to apply them to. */
  onApplyOptsToParents: (
    parentIds: string[],
    opts: RenderOpts,
  ) => Promise<void> | void;
}) {
  // Show 4 projects per page in the "Ready" section. Anything older
  // collapses under a "Show more" button so the page doesn't grow
  // unbounded as the user accumulates batches.
  const READY_PROJECTS_PER_PAGE = 4;
  const [readyPage, setReadyPage] = useState(1);

  if (jobs.length === 0) return null;

  const transcribing = jobs.filter(
    (j) => j.status === "queued" || j.status === "running",
  );
  const ready = jobs.filter((j) => j.status === "done");
  const broken = jobs.filter(
    (j) => j.status === "failed" || j.status === "cancelled",
  );

  // Group ready by project, then slice for pagination.
  const readyGroups = groupTranscribesByProject(ready);
  const totalReadyPages = Math.max(
    1,
    Math.ceil(readyGroups.length / READY_PROJECTS_PER_PAGE),
  );
  const visibleReadyGroups = readyGroups.slice(
    0,
    readyPage * READY_PROJECTS_PER_PAGE,
  );
  const hasMoreReady = readyPage < totalReadyPages;

  // Which "ready" parents currently have NO completed render? Those are
  // the candidates for "Apply style to all". We also list parents that
  // have a render in-flight to disable the button cleanly.
  const renderedParentIds = new Set<string>();
  const inFlightParentIds = new Set<string>();
  for (const [pid, renders] of rendersByParent) {
    if (renders.some((r) => r.status === "done")) renderedParentIds.add(pid);
    if (
      renders.some((r) => r.status === "queued" || r.status === "running")
    ) {
      inFlightParentIds.add(pid);
    }
  }
  const applyableParents = ready.filter(
    (j) => !renderedParentIds.has(j.id) && !inFlightParentIds.has(j.id),
  );

  // Collect every COMPLETED render id across all parents for the
  // "Download all as ZIP" button.
  const doneRenderIds: string[] = [];
  for (const renders of rendersByParent.values()) {
    for (const r of renders) {
      if (r.status === "done") doneRenderIds.push(r.id);
    }
  }

  return (
    <div className="mt-12 space-y-8">
      {/* Bulk action bar — only meaningful when there's >1 ready video
          or 1+ finished renders. */}
      {(applyableParents.length > 0 || doneRenderIds.length >= 1) && (
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] px-5 py-4 flex flex-wrap items-center justify-between gap-3">
          <div className="text-[12.5px] text-[var(--muted)] flex-1 min-w-0">
            {lastUsedOpts ? (
              <span>
                Last render style:{" "}
                <span className="font-mono text-white">
                  {lastUsedOpts.style}
                </span>
                {applyableParents.length > 0 && (
                  <span>
                    {" "}
                    — apply to {applyableParents.length} more video
                    {applyableParents.length === 1 ? "" : "s"}?
                  </span>
                )}
              </span>
            ) : applyableParents.length > 0 ? (
              <span>
                Render one video first — then you can apply the same
                style to the remaining{" "}
                {applyableParents.length} in one click.
              </span>
            ) : (
              <span>
                {doneRenderIds.length} render
                {doneRenderIds.length === 1 ? "" : "s"} ready to download.
              </span>
            )}
            {bulkNotice && (
              <span className="ml-3 font-mono text-[var(--accent)]">
                · {bulkNotice}
              </span>
            )}
            {bulkError && (
              <span className="ml-3 font-mono text-red-300">
                · {bulkError}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {applyableParents.length > 0 && lastUsedOpts && (
              <button
                type="button"
                disabled={bulkBusy}
                onClick={() =>
                  onApplyToAll(applyableParents.map((j) => j.id))
                }
                className="inline-flex h-9 items-center px-4 rounded-full bg-[var(--accent)] text-black text-[12px] font-semibold disabled:opacity-50"
              >
                {bulkBusy
                  ? "Submitting…"
                  : `Apply to ${applyableParents.length} video${
                      applyableParents.length === 1 ? "" : "s"
                    } →`}
              </button>
            )}
            {doneRenderIds.length >= 1 && (
              <a
                href={apiClient.captionsBulkZipUrl(doneRenderIds)}
                download="captions-batch.zip"
                className="inline-flex h-9 items-center px-4 rounded-full border border-[var(--line)] text-[12px] font-semibold text-white hover:border-[var(--accent)] hover:text-[var(--accent)]"
              >
                Download {doneRenderIds.length} as ZIP ↓
              </a>
            )}
          </div>
        </div>
      )}

      {transcribing.length > 0 && (
        <Section title="Transcribing" count={transcribing.length}>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {transcribing.map((j) => (
              <ProgressCard key={j.id} job={j} />
            ))}
          </div>
        </Section>
      )}

      {ready.length > 0 && (
        <Section title="Ready to caption" count={ready.length}>
          {/* Project-grouped layout. Jobs without a projectId go into
              an "(Unfiled)" bucket so legacy uploads stay visible.
              Paginated so a user with 50 projects doesn't have to
              scroll forever — older projects load behind "Show more". */}
          <div className="space-y-4">
            {visibleReadyGroups.map((group) => {
              // Find this project's first parent that has at least one
              // completed render — its style/position/customize values
              // are what "Apply style of 1st video" will replay onto
              // every sibling. Walks the project's job order (newest
              // first, but we iterate naturally — first match wins).
              let firstRenderedParent: Job | null = null;
              let firstRender: Job | null = null;
              for (const j of group.jobs) {
                const r = (rendersByParent.get(j.id) ?? []).find(
                  (x) => x.status === "done",
                );
                if (r) {
                  firstRenderedParent = j;
                  firstRender = r;
                  break;
                }
              }
              const siblingsToApply = firstRenderedParent
                ? group.jobs
                    .filter((j) => j.id !== firstRenderedParent!.id)
                    .map((j) => j.id)
                : [];
              const renderedCount = group.jobs.filter((j) =>
                (rendersByParent.get(j.id) ?? []).some(
                  (r) => r.status === "done",
                ),
              ).length;
              // Count parents that have an in-flight render (queued or
              // running). Used to show a live progress bar + count on
              // the project header during bulk apply so the user can
              // see how many videos are still cooking.
              const renderingCount = group.jobs.filter((j) =>
                (rendersByParent.get(j.id) ?? []).some(
                  (r) => r.status === "queued" || r.status === "running",
                ),
              ).length;
              const failedRenderCount = group.jobs.filter((j) =>
                (rendersByParent.get(j.id) ?? []).some(
                  (r) => r.status === "failed",
                ),
              ).length;
              const totalForProgress = group.jobs.length;
              const progressPct = totalForProgress > 0
                ? Math.round((renderedCount / totalForProgress) * 100)
                : 0;
              const zipUrl = group.projectId && renderedCount > 0
                ? apiClient.projectZipUrl(group.projectId)
                : null;
              return (
                <ProjectGroupCard
                  key={group.projectId ?? "unfiled"}
                  group={group}
                  rendersByParent={rendersByParent}
                  editingId={editingId}
                  onEdit={onEdit}
                  renderedCount={renderedCount}
                  renderingCount={renderingCount}
                  failedRenderCount={failedRenderCount}
                  totalForProgress={totalForProgress}
                  progressPct={progressPct}
                  firstRender={firstRender}
                  siblingsToApply={siblingsToApply}
                  zipUrl={zipUrl}
                  bulkBusy={bulkBusy}
                  onApplyOpts={onApplyOptsToParents}
                />
              );
            })}
            {hasMoreReady && (
              <div className="flex items-center justify-center pt-2">
                <button
                  type="button"
                  onClick={() => setReadyPage((p) => p + 1)}
                  className="text-[11px] font-mono uppercase tracking-[0.18em] px-4 py-2 rounded-full border border-[var(--line)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
                >
                  Show more projects ({readyGroups.length - visibleReadyGroups.length} remaining)
                </button>
              </div>
            )}
          </div>
        </Section>
      )}

      {broken.length > 0 && (
        <Section title="Failed / cancelled" count={broken.length}>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {broken.map((j) => (
              <FailedCard key={j.id} job={j} />
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

function TranscribedCard({
  job,
  renders,
  isEditing,
  onEdit,
}: {
  job: Job;
  renders: Job[];
  isEditing: boolean;
  onEdit: () => void;
}) {
  const lastDone = [...renders]
    .filter((r) => r.status === "done")
    .sort(
      (a, b) =>
        new Date(b.updatedAt ?? 0).getTime() - new Date(a.updatedAt ?? 0).getTime(),
    )[0];
  const inFlight = renders.find(
    (r) => r.status === "queued" || r.status === "running",
  );
  const filename = job.label || "Video";

  return (
    <div
      className={`rounded-xl border bg-[var(--surface)] p-4 ${
        isEditing
          ? "border-[var(--accent)] ring-1 ring-[var(--accent)]/30"
          : "border-[var(--line)]"
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="truncate text-[13px] text-white" title={filename}>
          {filename}
        </span>
        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-[var(--accent)] shrink-0">
          {inFlight ? "Rendering" : lastDone ? "Rendered" : "Ready"}
        </span>
      </div>
      <div className="text-[11px] font-mono text-[var(--muted)] mb-3">
        {job.videoWidth}×{job.videoHeight}
        {job.videoDuration ? ` · ${job.videoDuration.toFixed(1)}s` : ""}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onEdit}
          className="flex-1 h-8 rounded-full bg-[var(--accent)] text-black text-[11.5px] font-semibold"
        >
          {lastDone ? "Edit & re-render" : "Open editor →"}
        </button>
        {lastDone && (
          <a
            href={apiClient.jobOutputUrl(lastDone.id, { variant: "active" })}
            download
            className="h-8 px-3 inline-flex items-center rounded-full border border-[var(--line)] text-[11.5px] font-mono uppercase tracking-[0.14em] text-white hover:border-[var(--accent)] hover:text-[var(--accent)]"
            title="Download latest captioned mp4"
          >
            Download
          </a>
        )}
      </div>
    </div>
  );
}

function ProgressCard({ job }: { job: Job }) {
  const filename = job.label || `Job ${job.id.slice(0, 8)}`;
  const isRunning = job.status === "running";

  async function onCancel() {
    try {
      await apiClient.cancelJob(job.id);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="truncate text-[13px] text-white" title={filename}>
          {filename}
        </span>
        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-[var(--muted)] shrink-0">
          {isRunning ? `${job.progress}%` : "Queued"}
        </span>
      </div>
      <div className="h-1 w-full rounded-full bg-[var(--bg)] overflow-hidden">
        <div
          className="h-full bg-[var(--accent)] transition-all"
          style={{ width: `${job.progress}%` }}
        />
      </div>
      <div className="mt-2 text-[11px] font-mono text-[var(--muted)] truncate">
        {job.message ?? ""}
      </div>
      {(isRunning || job.status === "queued") && (
        <button
          type="button"
          onClick={onCancel}
          disabled={job.cancelRequested}
          className="mt-3 text-[11px] text-[var(--muted)] hover:text-red-400 disabled:opacity-50"
        >
          {job.cancelRequested ? "Cancelling…" : "Cancel"}
        </button>
      )}
    </div>
  );
}

/** Pull the render options off a bulk-captions-render Job's `params`
 *  field so we can replay them as RenderOpts for a bulk-apply submit.
 *  Mirrors the backend shape — see api/tools/bulk_captions_render.py
 *  where the worker reads `params.options`. Returns null if the shape
 *  doesn't look like a render job (e.g. a transcribe-only parent). */
function optsFromRenderJob(job: Job): RenderOpts | null {
  const params = (job.params ?? {}) as Record<string, unknown>;
  const o = params.options as Record<string, unknown> | undefined;
  if (!o) return null;
  const num = (v: unknown) => (typeof v === "number" ? v : null);
  const str = (v: unknown) => (typeof v === "string" ? v : null);
  return {
    style: (o.style as CaptionStyle) ?? "plain",
    position: (o.position as "top" | "middle" | "bottom") ?? "bottom",
    wordsPerLine: typeof o.wordsPerLine === "number" ? o.wordsPerLine : 3,
    uppercase: !!o.uppercase,
    posXFrac: num(o.posXFrac),
    posYFrac: num(o.posYFrac),
    primaryColor: str(o.primaryColor),
    outlineColor: str(o.outlineColor),
    outlineWidth: num(o.outlineWidth),
    bgColor: str(o.bgColor),
    bgAlpha: num(o.bgAlpha),
    fontSize: num(o.fontSize),
    fontFamily: str(o.fontFamily),
    shadow: num(o.shadow),
  };
}


/** Group bulk-captions transcribe jobs by their projectId, preserving
 *  the input array's order (which is already newest-first). Jobs that
 *  pre-date the project feature have no projectId — they bucket into
 *  one "(Unfiled)" group so the user can still see them. */
function groupTranscribesByProject(jobs: Job[]): {
  projectId: string | null;
  projectName: string;
  jobs: Job[];
}[] {
  const order: (string | null)[] = [];
  const buckets = new Map<string | null, { projectName: string; jobs: Job[] }>();
  for (const j of jobs) {
    const pid = j.projectId ?? null;
    if (!buckets.has(pid)) {
      order.push(pid);
      const name = j.projectName || (pid ? "Untitled project" : "(Unfiled)");
      buckets.set(pid, { projectName: name, jobs: [] });
    }
    buckets.get(pid)!.jobs.push(j);
  }
  return order.map((pid) => ({
    projectId: pid,
    projectName: buckets.get(pid)!.projectName,
    jobs: buckets.get(pid)!.jobs,
  }));
}


/** A single project's card on the "Ready to caption" section. Owns
 *  its own collapse state so a 50-video project doesn't drown out the
 *  smaller projects on the page. Header surfaces the most relevant
 *  signal (progress when active, "all done" when done, video count
 *  otherwise) without piling up every counter. */
function ProjectGroupCard({
  group,
  rendersByParent,
  editingId,
  onEdit,
  renderedCount,
  renderingCount,
  failedRenderCount,
  totalForProgress,
  progressPct,
  firstRender,
  siblingsToApply,
  zipUrl,
  bulkBusy,
  onApplyOpts,
}: {
  group: { projectId: string | null; projectName: string; jobs: Job[] };
  rendersByParent: Map<string, Job[]>;
  editingId: string | null;
  onEdit: (id: string) => void;
  renderedCount: number;
  renderingCount: number;
  failedRenderCount: number;
  totalForProgress: number;
  progressPct: number;
  firstRender: Job | null;
  siblingsToApply: string[];
  zipUrl: string | null;
  bulkBusy: boolean;
  onApplyOpts: (parentIds: string[], opts: RenderOpts) => Promise<void> | void;
}) {
  // Collapsed-by-default once the project is fully captioned. Active
  // projects (with anything still rendering) stay expanded so the user
  // can see live status without an extra click. New project (no
  // renders yet) also starts expanded.
  const fullyDone = renderingCount === 0 && renderedCount === totalForProgress;
  const [expanded, setExpanded] = useState(!fullyDone);

  // Pick one status line for the header — only the most relevant.
  // Active > failed > done > idle. Keeps the row visually quiet.
  let statusEl: React.ReactNode = null;
  if (renderingCount > 0) {
    statusEl = (
      <span className="text-[11px] font-mono uppercase tracking-[0.16em] text-yellow-300 inline-flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-yellow-300 animate-pulse" />
        {renderingCount} rendering · {renderedCount}/{totalForProgress} done
      </span>
    );
  } else if (failedRenderCount > 0) {
    statusEl = (
      <span className="text-[11px] font-mono uppercase tracking-[0.16em] text-red-400">
        ✕ {failedRenderCount} failed · {renderedCount}/{totalForProgress} done
      </span>
    );
  } else if (renderedCount > 0) {
    statusEl = (
      <span className="text-[11px] font-mono uppercase tracking-[0.16em] text-[var(--accent)]">
        ✓ {renderedCount}/{totalForProgress} captioned
      </span>
    );
  } else {
    statusEl = (
      <span className="text-[11px] font-mono uppercase tracking-[0.16em] text-[var(--muted)]">
        {totalForProgress} video{totalForProgress === 1 ? "" : "s"}
      </span>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)]/40 overflow-hidden">
      {/* Header row — single line on desktop, wraps on mobile. */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/5 transition-colors"
        aria-expanded={expanded}
      >
        <span
          aria-hidden
          className={`text-[var(--muted)] text-[12px] transition-transform ${expanded ? "rotate-90" : ""}`}
        >
          ▶
        </span>
        <h3 className="flex-1 text-[14px] font-medium text-white truncate">
          {group.projectName}
        </h3>
        {statusEl}
      </button>

      {/* Progress bar — slim, always visible at the bottom of the
          header so the user can see overall state even when collapsed. */}
      {(renderingCount > 0 || renderedCount > 0) && (
        <div className="h-[3px] w-full bg-black/30">
          <div
            className={`h-full transition-all ${
              renderingCount > 0 ? "bg-yellow-300" : "bg-[var(--accent)]"
            }`}
            style={{ width: `${progressPct}%` }}
          />
        </div>
      )}

      {expanded && (
        <div className="px-4 py-4 border-t border-[var(--line)] space-y-4">
          {/* Action row — only renders when there's something to do.
              Cleaner than always-on buttons since most projects (no
              first render yet) skip the row entirely. */}
          {(firstRender && siblingsToApply.length > 0) || zipUrl ? (
            <div className="flex items-center gap-2 flex-wrap">
              {firstRender && siblingsToApply.length > 0 && (
                <button
                  type="button"
                  disabled={bulkBusy}
                  onClick={() => {
                    const opts = optsFromRenderJob(firstRender!);
                    if (opts) onApplyOpts(siblingsToApply, opts);
                  }}
                  className="text-[11px] font-mono uppercase tracking-[0.16em] px-3 py-1.5 rounded-full border border-[var(--line)] hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-50"
                  title="Apply the first captioned video's style to the rest of this project"
                >
                  {bulkBusy
                    ? "Submitting…"
                    : `Apply 1st style → ${siblingsToApply.length}`}
                </button>
              )}
              {zipUrl && (
                <a
                  href={zipUrl}
                  download
                  className="text-[11px] font-mono uppercase tracking-[0.16em] px-3 py-1.5 rounded-full bg-[var(--accent)] text-black hover:bg-[var(--accent-deep)]"
                >
                  Download all ({renderedCount})
                </a>
              )}
            </div>
          ) : null}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {group.jobs.map((j) => (
              <TranscribedCard
                key={j.id}
                job={j}
                renders={rendersByParent.get(j.id) ?? []}
                isEditing={editingId === j.id}
                onEdit={() => onEdit(j.id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


function FailedCard({ job }: { job: Job }) {
  const filename = job.label || `Job ${job.id.slice(0, 8)}`;
  return (
    <div className="rounded-xl border border-red-500/40 bg-[var(--surface)] p-4">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="truncate text-[13px] text-white" title={filename}>
          {filename}
        </span>
        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-red-300 shrink-0">
          {job.status}
        </span>
      </div>
      <div className="text-[11.5px] text-[var(--muted)]">
        {job.errorDetail ?? job.message ?? "Unknown error."}
      </div>
    </div>
  );
}

/* ---------- shared bits ---------- */

/**
 * Color picker row used in the Customize tab. Shows a swatch grid +
 * a native hex input. `value=null` means "use the style preset"; a
 * `reset` link clears the override.
 */
function ColorRow({
  label,
  value,
  defaultHex,
  onChange,
}: {
  label: string;
  value: string | null;
  /** Preset's color when the user hasn't overridden — resolved hex.
   *  Used to highlight the right swatch as the "default" state so the
   *  picker doesn't look empty just because no override is set yet. */
  defaultHex?: string;
  onChange: (v: string | null) => void;
}) {
  // What the swatches compare against: the user's override, or the
  // preset default if nothing has been changed yet.
  const effective = (value ?? defaultHex ?? "").toLowerCase();
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11.5px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono">
          {label}
        </span>
        {value !== null && (
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-[10.5px] text-[var(--muted)] hover:text-[var(--accent)] font-mono"
          >
            reset
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {COLOR_SWATCHES.map((c) => {
          const active = effective === c.toLowerCase();
          return (
            <button
              key={c}
              type="button"
              onClick={() => onChange(c)}
              title={c}
              className={`h-7 w-7 rounded-md border-2 transition-transform ${
                active
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
          className="h-7 w-12 rounded-md border-2 border-[var(--line)] cursor-pointer bg-transparent"
          title="Custom hex"
        />
      </div>
    </div>
  );
}

/**
 * Generic slider with a "reset to preset" button. `isOverridden` says
 * whether the value currently differs from the preset — when false the
 * reset link hides and the slider is just an indicator (no harm tweaking).
 */
function SliderRow({
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
        <span className="text-[11.5px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono">
          {label}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[11.5px] font-mono text-white">
            {value}
            {unit ?? ""}
          </span>
          {isOverridden && (
            <button
              type="button"
              onClick={onReset}
              className="text-[10.5px] text-[var(--muted)] hover:text-[var(--accent)] font-mono"
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
        className="w-full h-8 accent-[var(--accent)]"
      />
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
          {count} {count === 1 ? "video" : "videos"}
        </span>
      </div>
      {children}
    </div>
  );
}
