"use client";

/**
 * Voice Pair tool — MVP.
 *
 * Two file inputs side-by-side: Media (images / videos) and Voice (audio).
 * Files pair by upload order — 1st media + 1st voice, 2nd + 2nd, etc.
 * Each pair becomes one rendered mp4: image+voice stays still or Ken-Burns
 * pans; video+voice loops the video until the voice ends.
 *
 * No billing — completely free. Captions baad me add hongi.
 */

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { ApiError, apiClient, type Job } from "@/lib/api";

type Animation = "static" | "ken_burns";
type Mode = "single" | "slideshow";

type MediaRow = {
  id: string;
  file: File;
  isVideo: boolean;
  animation: Animation;
  /** Object URL for inline preview (image / video poster). Created on
   *  add, revoked on remove so we don't leak memory. */
  previewUrl: string;
  /** When the user drops a FOLDER (webkitdirectory), every file in
   *  that folder shares the same groupKey (the folder name). In
   *  slideshow mode, files sharing a groupKey are grouped into one
   *  "pair" with a single voice. In single mode, each file is its own
   *  pair regardless of groupKey. Loose file drops get a unique key. */
  groupKey: string;
};

type VoiceRow = {
  id: string;
  file: File;
  /** Object URL for the <audio> player so user can scrub the voice. */
  previewUrl: string;
};

// Match what the API accepts. Mirrors ALLOWED_IMAGE_EXTS / ALLOWED_VIDEO_EXTS
// in api/app.py so we can show a friendly error before the upload starts.
const IMAGE_EXTS = new Set([".jpg", ".jpeg", ".png", ".webp"]);
const VIDEO_EXTS = new Set([".mp4", ".mov", ".webm", ".mkv", ".m4v"]);
const AUDIO_EXTS = new Set([".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"]);

function fileExt(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

function isImage(file: File): boolean {
  return IMAGE_EXTS.has(fileExt(file.name));
}
function isVideo(file: File): boolean {
  return VIDEO_EXTS.has(fileExt(file.name));
}
function isAudio(file: File): boolean {
  return AUDIO_EXTS.has(fileExt(file.name));
}

function genId(): string {
  return Math.random().toString(36).slice(2, 10);
}

/** Pull the folder name out of a File picked via webkitdirectory.
 *  webkitRelativePath looks like "myfolder/sub/file.jpg"; the first
 *  segment is what the user named their folder. Single-file picks
 *  have an empty webkitRelativePath, so we get "". */
function folderNameOf(f: File): string {
  // `webkitRelativePath` is on File but not in the standard TS lib type.
  const rel = (f as unknown as { webkitRelativePath?: string }).webkitRelativePath || "";
  if (!rel) return "";
  const slash = rel.indexOf("/");
  return slash > 0 ? rel.slice(0, slash) : "";
}

export default function VoicePairPage() {
  const [media, setMedia] = useState<MediaRow[]>([]);
  const [voices, setVoices] = useState<VoiceRow[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitNotice, setSubmitNotice] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  /** Project name the user types for THIS submit. Cleared on success. */
  const [projectName, setProjectName] = useState("");

  /** Refresh the recent jobs list so users see progress on this tool. */
  const refresh = useCallback(async () => {
    try {
      const res = await apiClient.listJobs({ limit: 30 });
      setJobs(res.items.filter((j) => j.tool === "voice-pair"));
    } catch {
      // non-fatal; the page is still usable for uploads.
    }
  }, []);

  useEffect(() => {
    refresh();
    // Poll every 2s while any job is still running so progress bars move.
    const id = setInterval(() => refresh(), 2000);
    return () => clearInterval(id);
  }, [refresh]);

  /** Single unified pairing model:
   *  - Folder upload → one slideshow pair (all items inside play
   *    back-to-back with one voice).
   *  - Loose file upload → one per-file pair (one media + one voice).
   *
   *  `mediaGroups` are visual groupings (folder card or loose row).
   *  `pairUnits` is what the submit endpoint receives: one entry per
   *  pair. A folder group becomes one slideshow pair-unit; a loose
   *  file group (size 1, no webkitRelativePath) becomes one per-file
   *  pair-unit. Same shape either way. */
  const mediaGroups = useMemo(() => {
    const order: string[] = [];
    const buckets = new Map<string, MediaRow[]>();
    for (const m of media) {
      if (!buckets.has(m.groupKey)) {
        order.push(m.groupKey);
        buckets.set(m.groupKey, []);
      }
      buckets.get(m.groupKey)!.push(m);
    }
    return order.map((key) => ({ key, items: buckets.get(key)! }));
  }, [media]);

  // Each visual group is one pair-unit. Folder groups carry N items
  // (slideshow); loose-file groups carry 1.
  const pairUnits = mediaGroups;

  const pairCount = Math.min(pairUnits.length, voices.length);
  const canSubmit = pairCount > 0 && !submitting;

  function addMediaFiles(files: FileList | null) {
    if (!files) return;
    const rows: MediaRow[] = [];
    const rejected: string[] = [];
    // Folder uploads arrive in arbitrary OS order. Sort by filename so
    // image_01.jpg comes before image_02.jpg.
    const sorted = Array.from(files).sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }),
    );
    // Files from the same folder share one groupKey so slideshow mode
    // can collapse them into a single pair. Loose files get fresh keys.
    const folderKeys = new Map<string, string>();  // folderName → key
    for (const f of sorted) {
      if (!(isImage(f) || isVideo(f))) {
        rejected.push(f.name);
        continue;
      }
      const folder = folderNameOf(f);
      let groupKey: string;
      if (folder) {
        let k = folderKeys.get(folder);
        if (!k) {
          k = `folder-${folder}-${genId()}`;
          folderKeys.set(folder, k);
        }
        groupKey = k;
      } else {
        groupKey = `file-${genId()}`;
      }
      rows.push({
        id: genId(),
        file: f,
        isVideo: isVideo(f),
        animation: "static",
        previewUrl: URL.createObjectURL(f),
        groupKey,
      });
    }
    setMedia((prev) => [...prev, ...rows]);
    if (rejected.length) {
      setSubmitError(
        `${rejected.length} skipped: not image or video — ${rejected.slice(0, 3).join(", ")}${rejected.length > 3 ? "…" : ""}`,
      );
    } else {
      setSubmitError(null);
    }
  }

  function addVoiceFiles(files: FileList | null) {
    if (!files) return;
    const rows: VoiceRow[] = [];
    const rejected: string[] = [];
    // Same alphabetical sort as media, so voice_01.mp3 pairs with
    // image_01.jpg etc. when both are loaded from folders.
    const sorted = Array.from(files).sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }),
    );
    for (const f of sorted) {
      if (isAudio(f)) {
        rows.push({
          id: genId(),
          file: f,
          previewUrl: URL.createObjectURL(f),
        });
      } else {
        rejected.push(f.name);
      }
    }
    setVoices((prev) => [...prev, ...rows]);
    if (rejected.length) {
      setSubmitError(
        `${rejected.length} skipped: not audio — ${rejected.slice(0, 3).join(", ")}${rejected.length > 3 ? "…" : ""}`,
      );
    } else {
      setSubmitError(null);
    }
  }

  function moveMedia(from: number, to: number) {
    setMedia((prev) => {
      if (to < 0 || to >= prev.length) return prev;
      const next = [...prev];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  }
  function moveVoice(from: number, to: number) {
    setVoices((prev) => {
      if (to < 0 || to >= prev.length) return prev;
      const next = [...prev];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  }
  function removeMedia(id: string) {
    setMedia((prev) => {
      const dropped = prev.find((m) => m.id === id);
      if (dropped) URL.revokeObjectURL(dropped.previewUrl);
      return prev.filter((m) => m.id !== id);
    });
  }
  function removeVoice(id: string) {
    setVoices((prev) => {
      const dropped = prev.find((v) => v.id === id);
      if (dropped) URL.revokeObjectURL(dropped.previewUrl);
      return prev.filter((v) => v.id !== id);
    });
  }
  function setAnim(id: string, anim: Animation) {
    setMedia((prev) => prev.map((m) => (m.id === id ? { ...m, animation: anim } : m)));
  }

  async function submit() {
    if (!pairCount) return;
    setSubmitting(true);
    setSubmitError(null);
    setSubmitNotice(null);
    try {
      // Each pair = one pair-unit's media files + one voice. In
      // single mode the unit holds 1 file; in slideshow it holds N.
      const pairs = Array.from({ length: pairCount }, (_, i) => ({
        media: pairUnits[i].items.map((m) => m.file),
        voice: voices[i].file,
        animation: pairUnits[i].items[0].animation,
      }));
      // Backend auto-routes per-pair: pair_media size > 1 becomes a
      // slideshow render; size = 1 uses the per-file path (so the
      // image's animation choice still applies).
      const res = await apiClient.submitVoicePair(pairs, {
        mode: "single",
        projectName: projectName.trim() || undefined,
      });
      const parts = [`${res.summary.queued} queued in “${res.projectName}”`];
      if (res.summary.rejected) parts.push(`${res.summary.rejected} rejected`);
      setSubmitNotice(parts.join(" · "));
      // Clear the queues so the user sees only fresh items. Revoke
      // every preview URL so we don't leak blob memory in the browser.
      for (const m of media) URL.revokeObjectURL(m.previewUrl);
      for (const v of voices) URL.revokeObjectURL(v.previewUrl);
      setMedia([]);
      setVoices([]);
      setProjectName("");
      refresh();
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e.message : "Submit failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <header className="mb-8">
        <Link
          href="/"
          className="text-[12px] uppercase tracking-[0.18em] font-mono text-[var(--muted)] hover:text-white"
        >
          ← Tools
        </Link>
        <h1 className="mt-2 text-3xl font-semibold font-display">
          Voice Pair
        </h1>
        <p className="text-[var(--muted)] mt-1 text-sm leading-relaxed">
          Pair media with a voice. Each pair renders one mp4. Pairs match
          by list order — 1st with 1st, 2nd with 2nd.
        </p>
        <p className="text-[11px] text-[var(--muted)] mt-2 leading-relaxed">
          Upload a <strong>file</strong> to get a 1-file pair, or a{" "}
          <strong>folder</strong> to bundle all its items into one
          slideshow video. Mix freely — each pair (file or folder) needs
          one voice on the right.
        </p>
        <p className="text-[11px] text-[var(--muted)] mt-1 leading-relaxed">
          <span className="text-[var(--accent)]">Duration:</span> output
          length = voice length. In a slideshow each item gets an equal
          share of the voice duration. Short videos loop to fill their
          slice; long videos get trimmed.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Media column */}
        <section className="rounded-lg border border-[var(--line)] bg-[var(--surface)] p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-mono uppercase tracking-[0.18em] text-[var(--muted)]">
              Media · {media.length}
            </h2>
            <div className="flex gap-2">
              <label className="text-[11px] font-mono uppercase tracking-[0.18em] px-3 py-1.5 rounded-full border border-[var(--line)] hover:border-[var(--accent)] cursor-pointer">
                + Files
                <input
                  type="file"
                  multiple
                  accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.mkv,.m4v"
                  className="hidden"
                  onChange={(e) => {
                    addMediaFiles(e.target.files);
                    e.currentTarget.value = "";
                  }}
                />
              </label>
              <label className="text-[11px] font-mono uppercase tracking-[0.18em] px-3 py-1.5 rounded-full border border-[var(--line)] hover:border-[var(--accent)] cursor-pointer">
                + Folder
                {/* webkitdirectory is non-standard but supported in every
                    modern browser. React types don't know about it so we
                    splat it via dangerous spread. */}
                <input
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    addMediaFiles(e.target.files);
                    e.currentTarget.value = "";
                  }}
                  {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
                />
              </label>
            </div>
          </div>

          {media.length === 0 ? (
            <MediaDropZone
              onFiles={addMediaFiles}
              accept={[
                ".jpg", ".jpeg", ".png", ".webp",
                ".mp4", ".mov", ".webm", ".mkv", ".m4v",
              ]}
              hint="Drop images, videos, or a folder here"
              subHint="jpg, png, webp, mp4, mov, webm"
            />
          ) : (
            // Always render by groups so a folder upload shows as one
            // folder card no matter which mode is active. Folder cards
            // expand on click; loose-file groups render as flat rows.
            <ul className="space-y-2">
              {mediaGroups.map((g, gi) => (
                <MediaGroupRow
                  key={g.key}
                  index={gi}
                  group={g}
                  onRemove={() => {
                    for (const m of g.items) removeMedia(m.id);
                  }}
                  onRemoveOne={(mediaId) => removeMedia(mediaId)}
                  onSetAnim={(mediaId, anim) => setAnim(mediaId, anim)}
                />
              ))}
            </ul>
          )}
        </section>

        {/* Voice column */}
        <section className="rounded-lg border border-[var(--line)] bg-[var(--surface)] p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-mono uppercase tracking-[0.18em] text-[var(--muted)]">
              Voice · {voices.length}
            </h2>
            <div className="flex gap-2">
              <label className="text-[11px] font-mono uppercase tracking-[0.18em] px-3 py-1.5 rounded-full border border-[var(--line)] hover:border-[var(--accent)] cursor-pointer">
                + Files
                <input
                  type="file"
                  multiple
                  accept=".mp3,.m4a,.wav,.aac,.ogg,.flac"
                  className="hidden"
                  onChange={(e) => {
                    addVoiceFiles(e.target.files);
                    e.currentTarget.value = "";
                  }}
                />
              </label>
              <label className="text-[11px] font-mono uppercase tracking-[0.18em] px-3 py-1.5 rounded-full border border-[var(--line)] hover:border-[var(--accent)] cursor-pointer">
                + Folder
                <input
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    addVoiceFiles(e.target.files);
                    e.currentTarget.value = "";
                  }}
                  {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
                />
              </label>
            </div>
          </div>

          {voices.length === 0 ? (
            <MediaDropZone
              onFiles={addVoiceFiles}
              accept={[".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"]}
              hint="Drop voice audio here"
              subHint="mp3, m4a, wav, aac, ogg, flac"
            />
          ) : (
            <ul className="space-y-2">
              {voices.map((v, i) => (
                <li
                  key={v.id}
                  className="flex items-center gap-3 rounded border border-[var(--line)] bg-black/30 px-3 py-2"
                >
                  <span className="text-[11px] font-mono text-[var(--muted)] w-6">
                    {i + 1}
                  </span>
                  {/* Inline audio scrubber so the user can confirm the
                      voice file is the one they meant before rendering. */}
                  <audio
                    src={v.previewUrl}
                    controls
                    preload="metadata"
                    className="h-8 max-w-[160px]"
                  />
                  <span className="flex-1 truncate text-[13px]">
                    {v.file.name}
                  </span>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={() => moveVoice(i, i - 1)}
                      disabled={i === 0}
                      className="text-[11px] w-6 h-6 rounded border border-[var(--line)] disabled:opacity-30 hover:border-[var(--accent)]"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => moveVoice(i, i + 1)}
                      disabled={i === voices.length - 1}
                      className="text-[11px] w-6 h-6 rounded border border-[var(--line)] disabled:opacity-30 hover:border-[var(--accent)]"
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      onClick={() => removeVoice(v.id)}
                      className="text-[11px] w-6 h-6 rounded border border-[var(--line)] hover:border-red-500 hover:text-red-400"
                    >
                      ×
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* Submit bar — project name + render button + per-pair preview.
          Project name is OPTIONAL and inline so it doesn't dominate the
          empty page; backend defaults to a timestamp if blank. */}
      <div className="mt-6 rounded-lg border border-[var(--line)] bg-[var(--surface)] p-4">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="Project name (optional)"
            maxLength={80}
            className="flex-1 bg-black/30 border border-[var(--line)] rounded px-3 py-2 text-[13px] placeholder:text-[var(--muted)]/60 focus:outline-none focus:border-[var(--accent)]"
          />
          <div className="flex items-center gap-3 justify-between sm:justify-end">
            <div className="text-[12px] font-mono text-[var(--muted)]">
              {pairCount > 0
                ? `${pairCount} pair${pairCount === 1 ? "" : "s"}`
                : "Add files + voice"}
            </div>
            <button
              type="button"
              onClick={submit}
              disabled={!canSubmit}
              className="text-[12px] uppercase tracking-[0.18em] font-mono px-4 py-2 rounded-full bg-[var(--accent)] text-black hover:bg-[var(--accent-deep)] disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
            >
              {submitting ? "Submitting…" : `Render ${pairCount || ""}`}
            </button>
          </div>
        </div>
        {pairCount > 0 && (
          <div className="mt-3 pt-3 border-t border-[var(--line)] space-y-1 text-[12px] font-mono text-[var(--muted)]">
            {Array.from({ length: pairCount }, (_, i) => {
              const u = pairUnits[i];
              const v = voices[i];
              const first = u.items[0];
              const folderName = folderNameOf(first.file);
              const isSlideshow = u.items.length > 1;
              const mediaLabel = isSlideshow
                ? `${folderName || "folder"} (${u.items.length} items, slideshow)`
                : first.file.name;
              return (
                <div key={u.key} className="flex items-center gap-2 truncate">
                  <span className="text-[var(--accent)]">{i + 1}.</span>
                  <span className="truncate">{mediaLabel}</span>
                  <span>+</span>
                  <span className="truncate">{v.file.name}</span>
                </div>
              );
            })}
            {(pairUnits.length !== pairCount || voices.length !== pairCount) && (
              <div className="text-[11px] text-orange-400 pt-1">
                ⚠ {Math.abs(pairUnits.length - voices.length)} extra{" "}
                {pairUnits.length > voices.length ? "media" : "voice"} will be ignored.
              </div>
            )}
          </div>
        )}
      </div>

      {submitError && (
        <div className="mt-3 text-[12px] text-red-400 font-mono">{submitError}</div>
      )}
      {submitNotice && (
        <div className="mt-3 text-[12px] text-[var(--accent)] font-mono">{submitNotice}</div>
      )}

      {/* Recent jobs, grouped by project. Each project = one collapsible
          card with bulk actions (rename, delete, zip). */}
      <section className="mt-8">
        <h2 className="text-sm font-mono uppercase tracking-[0.18em] text-[var(--muted)] mb-3">
          Recent renders
        </h2>
        {jobs.length === 0 ? (
          <p className="text-[12px] text-[var(--muted)]">Nothing yet.</p>
        ) : (
          <ul className="space-y-3">
            {groupJobsByProject(jobs).map((proj) => (
              <ProjectCard
                key={proj.projectId ?? "unfiled"}
                project={proj}
                onChanged={refresh}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/** Group jobs by projectId, preserving the newest-first order from
 *  the API. Jobs without a projectId fall into a single "(Unfiled)"
 *  bucket so legacy renders are still visible. */
function groupJobsByProject(jobs: Job[]): {
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
      const name =
        j.projectName || (pid ? "Untitled project" : "(Unfiled)");
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

function ProjectCard({
  project,
  onChanged,
}: {
  project: { projectId: string | null; projectName: string; jobs: Job[] };
  onChanged: () => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState(project.projectName);
  const [busy, setBusy] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const doneCount = project.jobs.filter((j) => j.status === "done").length;
  const runningCount = project.jobs.filter(
    (j) => j.status === "running" || j.status === "queued",
  ).length;
  const failedCount = project.jobs.filter(
    (j) => j.status === "failed" || j.status === "cancelled",
  ).length;

  const canManage = !!project.projectId;
  const zipUrl = canManage && doneCount > 0
    ? apiClient.projectZipUrl(project.projectId!)
    : null;

  async function handleRename() {
    if (!project.projectId) return;
    const n = newName.trim();
    if (!n || n === project.projectName) {
      setRenaming(false);
      return;
    }
    setBusy(true);
    try {
      await apiClient.renameProject(project.projectId, n);
      onChanged();
    } catch {
      // refresh anyway — server is source of truth.
      onChanged();
    } finally {
      setBusy(false);
      setRenaming(false);
    }
  }

  async function handleDelete() {
    if (!project.projectId) return;
    setConfirmingDelete(false);
    setBusy(true);
    try {
      await apiClient.deleteProject(project.projectId);
      onChanged();
    } catch {
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-lg border border-[var(--line)] bg-[var(--surface)] overflow-hidden">
      {/* Header: name + counts + action buttons */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--line)] bg-black/20">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-[var(--muted)] hover:text-white"
          aria-label={expanded ? "Collapse" : "Expand"}
        >
          <span
            className={`inline-block transition-transform ${expanded ? "rotate-90" : ""}`}
          >
            ▶
          </span>
        </button>
        <div className="flex-1 min-w-0">
          {renaming ? (
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onBlur={handleRename}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleRename();
                if (e.key === "Escape") { setRenaming(false); setNewName(project.projectName); }
              }}
              maxLength={80}
              autoFocus
              className="bg-black/30 border border-[var(--accent)] rounded px-2 py-1 text-[13px] font-medium w-full max-w-md"
            />
          ) : (
            <div
              className="text-[13px] font-medium truncate cursor-pointer hover:text-[var(--accent)]"
              onClick={() => canManage && setRenaming(true)}
              title={canManage ? "Click to rename" : ""}
            >
              {project.projectName}
            </div>
          )}
          <div className="text-[11px] font-mono text-[var(--muted)] mt-0.5">
            {project.jobs.length} job{project.jobs.length === 1 ? "" : "s"}
            {doneCount > 0 && ` · ${doneCount} done`}
            {runningCount > 0 && ` · ${runningCount} running`}
            {failedCount > 0 && ` · ${failedCount} failed`}
          </div>
        </div>
        {zipUrl && (
          <a
            href={zipUrl}
            download
            className="text-[11px] font-mono uppercase tracking-[0.18em] px-3 py-1.5 rounded-full bg-[var(--accent)] text-black hover:bg-[var(--accent-deep)]"
          >
            ZIP
          </a>
        )}
        {canManage && (
          <button
            type="button"
            onClick={() => setConfirmingDelete(true)}
            disabled={busy}
            className="text-[11px] font-mono uppercase tracking-[0.18em] px-3 py-1.5 rounded-full border border-[var(--line)] hover:border-red-500 hover:text-red-400 disabled:opacity-40"
          >
            {busy ? "…" : "Delete"}
          </button>
        )}
      </div>
      {expanded && (
        <ul className="divide-y divide-[var(--line)]">
          {project.jobs.map((j) => (
            <li key={j.id} className="px-2 py-2">
              <VoicePairJobRow job={j} onChanged={onChanged} />
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={confirmingDelete}
        title={`Delete “${project.projectName}”?`}
        message={
          <>
            This will permanently remove the project and{" "}
            <strong className="text-white">
              all {project.jobs.length} render{project.jobs.length === 1 ? "" : "s"}
            </strong>{" "}
            inside it, including the rendered mp4 files. This can't be undone.
          </>
        }
        confirmLabel="Delete project"
        destructive
        onConfirm={handleDelete}
        onCancel={() => setConfirmingDelete(false)}
      />
    </li>
  );
}

/** Drag-and-drop upload area shown when a column is empty. Accepts a
 *  drop OR a click (opens a file picker via a hidden <input>). Filters
 *  by extension client-side before handing to the parent's add* fn so
 *  audio dropped on the media column gets rejected with feedback. */
function MediaDropZone({
  onFiles,
  accept,
  hint,
  subHint,
}: {
  onFiles: (files: FileList | null) => void;
  accept: string[];
  hint: string;
  subHint: string;
}) {
  const [hover, setHover] = useState(false);
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setHover(true);
      }}
      onDragLeave={() => setHover(false)}
      onDrop={(e) => {
        e.preventDefault();
        setHover(false);
        onFiles(e.dataTransfer.files);
      }}
      className={`flex flex-col items-center justify-center gap-1 py-10 px-4 rounded border-2 border-dashed text-center cursor-pointer transition-colors ${
        hover
          ? "border-[var(--accent)] bg-[var(--accent)]/5"
          : "border-[var(--line)] hover:border-[var(--accent)]/60"
      }`}
    >
      <div className="text-2xl" aria-hidden>
        ⬆
      </div>
      <div className="text-[13px] font-medium">{hint}</div>
      <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[var(--muted)]">
        {subHint}
      </div>
      <input
        type="file"
        multiple
        accept={accept.join(",")}
        className="hidden"
        onChange={(e) => {
          onFiles(e.target.files);
          e.currentTarget.value = "";
        }}
      />
    </label>
  );
}


/** One row in the media list. Folder uploads render as a collapsed
 *  card (📁 name · N items); click to expand the contents. Loose
 *  single files render as a flat row with an animation selector. */
function MediaGroupRow({
  index,
  group,
  onRemove,
  onRemoveOne,
  onSetAnim,
}: {
  index: number;
  group: { key: string; items: MediaRow[] };
  onRemove: () => void;
  onRemoveOne: (mediaId: string) => void;
  onSetAnim: (mediaId: string, anim: Animation) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const first = group.items[0];
  const folder = folderNameOf(first.file);
  // webkitRelativePath = folder upload; render as folder card. No
  // relativePath = loose file; render flat (no expand affordance).
  const isFolder = !!folder;

  if (!isFolder) {
    return (
      <li className="flex items-center gap-3 rounded border border-[var(--line)] bg-black/30 px-3 py-2">
        <span className="text-[11px] font-mono text-[var(--muted)] w-6">
          {index + 1}
        </span>
        <div className="h-12 w-12 flex-shrink-0 rounded overflow-hidden bg-black/40 border border-white/5">
          {first.isVideo ? (
            <video src={first.previewUrl} className="h-full w-full object-cover" muted preload="metadata" />
          ) : (
            <img src={first.previewUrl} alt={first.file.name} className="h-full w-full object-cover" />
          )}
        </div>
        <span className="flex-1 truncate text-[13px]">{first.file.name}</span>
        <span className="text-[10px] font-mono uppercase text-[var(--muted)]">
          {first.isVideo ? "video" : "image"}
        </span>
        {!first.isVideo && (
          <select
            value={first.animation}
            onChange={(e) => onSetAnim(first.id, e.target.value as Animation)}
            className="text-[11px] font-mono bg-black/40 border border-[var(--line)] rounded px-2 py-1"
          >
            <option value="static">Static</option>
            <option value="ken_burns">Ken Burns</option>
          </select>
        )}
        <button
          type="button"
          onClick={onRemove}
          className="text-[11px] w-6 h-6 rounded border border-[var(--line)] hover:border-red-500 hover:text-red-400"
        >
          ×
        </button>
      </li>
    );
  }

  // Folder card. Folder always means "one slideshow video" — single
  // unified flow, no mode toggle. Output length = voice length; each
  // item gets an equal share (voice_dur / N) and short videos auto-loop
  // to fill their slice if needed.
  const subLabel = `${group.items.length} ${group.items.length === 1 ? "item" : "items"} · slideshow · equal split to voice length`;

  return (
    <li className="rounded border border-[var(--line)] bg-black/30 px-3 py-2">
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
        className="w-full flex items-center gap-3 cursor-pointer hover:bg-white/5 rounded -mx-1 px-1 py-0.5 transition-colors"
      >
        <span className="text-[11px] font-mono text-[var(--muted)] w-6">
          {index + 1}
        </span>
        <div className="h-12 w-12 flex-shrink-0 rounded overflow-hidden bg-black/40 border border-white/5">
          {first.isVideo ? (
            <video src={first.previewUrl} className="h-full w-full object-cover" muted preload="metadata" />
          ) : (
            <img src={first.previewUrl} alt={first.file.name} className="h-full w-full object-cover" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="truncate text-[13px] font-medium">📁 {folder}</div>
          <div className="text-[11px] font-mono text-[var(--muted)]">{subLabel}</div>
        </div>
        <span
          className={`text-[var(--muted)] transition-transform ${expanded ? "rotate-90" : ""}`}
          aria-hidden
        >
          ▶
        </span>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="text-[11px] w-6 h-6 rounded border border-[var(--line)] hover:border-red-500 hover:text-red-400 inline-flex items-center justify-center"
        >
          ×
        </button>
      </div>
      {expanded && (
        <ul className="mt-2 pl-9 space-y-1.5">
          {group.items.map((m) => (
            <li
              key={m.id}
              className="flex items-center gap-2 text-[12px]"
              title={m.file.name}
            >
              <div className="h-10 w-10 flex-shrink-0 rounded overflow-hidden bg-black/40 border border-white/5">
                {m.isVideo ? (
                  <video src={m.previewUrl} className="h-full w-full object-cover" muted preload="metadata" />
                ) : (
                  <img src={m.previewUrl} alt={m.file.name} className="h-full w-full object-cover" />
                )}
              </div>
              <span className="flex-1 truncate">{m.file.name}</span>
              {/* Folder items don't carry an animation choice — the
                  slideshow renderer concatenates them at equal-split
                  durations. Per-image animation only applies to loose
                  files (rendered in the non-folder branch above). */}
              <button
                type="button"
                onClick={() => onRemoveOne(m.id)}
                className="text-[10px] w-5 h-5 rounded border border-[var(--line)] hover:border-red-500 hover:text-red-400"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}


function VoicePairJobRow({
  job,
  onChanged,
}: {
  job: Job;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<"cancel" | "remove" | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [confirmingRemove, setConfirmingRemove] = useState(false);
  const status = job.status;
  const params = (job.params || {}) as Record<string, unknown>;
  // Slideshow jobs carry mediaFilenames[] instead of mediaFilename.
  const mediaName = String(
    params.mediaFilename ??
      (Array.isArray(params.mediaFilenames)
        ? `Slideshow · ${(params.mediaFilenames as unknown[]).length} items`
        : "?"),
  );
  const voiceName = String(params.voiceFilename ?? "?");
  const pct = typeof job.progress === "number" ? job.progress : 0;
  const isDone = status === "done";
  const isFailed = status === "failed";
  const isCancelled = status === "cancelled";
  const isRunning = status === "running" || status === "queued";

  const outputUrl = isDone
    ? apiClient.jobOutputUrl(job.id, {
        cacheKey: job.updatedAt ?? job.id,
      })
    : null;

  async function handleCancel() {
    setBusy("cancel");
    try {
      await apiClient.cancelJob(job.id);
      onChanged();
    } catch {
      // refresh anyway so the user sees the latest state.
      onChanged();
    } finally {
      setBusy(null);
    }
  }

  async function handleRemove() {
    setConfirmingRemove(false);
    setBusy("remove");
    try {
      await apiClient.deleteJob(job.id);
      onChanged();
    } catch {
      onChanged();
    } finally {
      setBusy(null);
    }
  }

  return (
    // Wrapper is a <div> not <li> because this component is rendered
    // INSIDE a project-card's <li>, and nested <li> is invalid HTML.
    // The parent project-card supplies the <li> container.
    <div className="rounded border border-[var(--line)] bg-[var(--surface)] px-3 py-3">
      {/* Header row: filename + status (left) | actions (right). On
          mobile actions wrap to a new line below the filename. */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-[13px] truncate">
            <span className="font-medium">{mediaName}</span>
            <span className="text-[var(--muted)] mx-2">+</span>
            <span>{voiceName}</span>
          </div>
          <div className="text-[11px] font-mono text-[var(--muted)] mt-1">
            {status} · {job.message ?? ""}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
        {isRunning && (
          <div className="text-[11px] font-mono text-[var(--accent)]">{pct}%</div>
        )}
        {/* Done → inline preview toggle. Click expands a video player
            below the row so the user doesn't have to download. */}
        {outputUrl && (
          <button
            type="button"
            onClick={() => setShowPreview((v) => !v)}
            className="text-[11px] font-mono uppercase tracking-[0.18em] px-3 py-1.5 rounded-full border border-[var(--line)] hover:border-[var(--accent)]"
          >
            {showPreview ? "Hide" : "Preview"}
          </button>
        )}
        {outputUrl && (
          <a
            href={outputUrl}
            download
            className="text-[11px] font-mono uppercase tracking-[0.18em] px-3 py-1.5 rounded-full bg-[var(--accent)] text-black hover:bg-[var(--accent-deep)]"
          >
            Download
          </a>
        )}
        {isFailed && (
          <span className="text-[11px] font-mono text-red-400">Failed</span>
        )}
        {isCancelled && (
          <span className="text-[11px] font-mono text-[var(--muted)]">Cancelled</span>
        )}
        {/* Cancel for in-flight; Remove for terminal state. */}
        {isRunning ? (
          <button
            type="button"
            onClick={handleCancel}
            disabled={busy !== null}
            className="text-[11px] font-mono uppercase tracking-[0.18em] px-3 py-1.5 rounded-full border border-[var(--line)] hover:border-red-500 hover:text-red-400 disabled:opacity-40"
          >
            {busy === "cancel" ? "…" : "Cancel"}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmingRemove(true)}
            disabled={busy !== null}
            className="text-[11px] font-mono uppercase tracking-[0.18em] px-3 py-1.5 rounded-full border border-[var(--line)] hover:border-red-500 hover:text-red-400 disabled:opacity-40"
          >
            {busy === "remove" ? "…" : "Remove"}
          </button>
        )}
        </div>
      </div>
      {isRunning && (
        <div className="mt-2 h-1 rounded bg-black/40 overflow-hidden">
          <div
            className="h-full bg-[var(--accent)] transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
      {showPreview && outputUrl && (
        <div className="mt-3">
          {/* Inline preview. autoPlay + muted so the browser fetches +
              decodes the first frame immediately and the user gets
              instant feedback (most modern browsers gate autoPlay on
              muted=true). They can unmute via controls. */}
          <video
            src={outputUrl}
            controls
            autoPlay
            muted
            playsInline
            preload="auto"
            className="w-full max-h-[480px] rounded bg-black"
          />
        </div>
      )}
      <ConfirmDialog
        open={confirmingRemove}
        title={`Remove this render?`}
        message={
          <>
            This deletes the rendered mp4 for{" "}
            <strong className="text-white">“{mediaName}”</strong> and removes
            it from your history. The original source files will be cleaned
            up too. This can't be undone.
          </>
        }
        confirmLabel="Remove"
        destructive
        onConfirm={handleRemove}
        onCancel={() => setConfirmingRemove(false)}
      />
    </div>
  );
}


/** Brand-styled replacement for the browser's native confirm() dialog.
 *  Renders a centered modal with a configurable title, message, and
 *  destructive/neutral confirm button. Closing on backdrop click or
 *  Escape cancels. Use via state: setDialog({open, ...}) → render. */
function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  destructive = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        className="relative w-full max-w-md mx-4 rounded-xl border border-[var(--line)] bg-[var(--surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal
      >
        <div className="px-5 pt-5 pb-3 border-b border-[var(--line)]">
          <div className="text-[10px] uppercase tracking-[0.22em] font-mono text-[var(--muted)] mb-1">
            {destructive ? "Confirm delete" : "Confirm"}
          </div>
          <h3 className="text-lg font-semibold font-display">{title}</h3>
        </div>
        <div className="px-5 py-4 text-[13px] text-white/85 leading-relaxed">
          {message}
        </div>
        <div className="flex items-center justify-end gap-2 px-5 pb-5">
          <button
            type="button"
            onClick={onCancel}
            className="text-[11px] uppercase tracking-[0.18em] font-mono px-4 py-2 rounded-full border border-[var(--line)] hover:border-white text-[var(--muted)] hover:text-white"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            autoFocus
            className={
              destructive
                ? "text-[11px] uppercase tracking-[0.18em] font-mono px-4 py-2 rounded-full bg-red-500 text-white hover:bg-red-600"
                : "text-[11px] uppercase tracking-[0.18em] font-mono px-4 py-2 rounded-full bg-[var(--accent)] text-black hover:bg-[var(--accent-deep)]"
            }
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
