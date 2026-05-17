/**
 * API client for the Python backend.
 *
 * In production cookies cross subdomains automatically, so every fetch just
 * needs `credentials: "include"`. In local dev the SSO cookie can't reach
 * us across `localhost:3007` <-> `localhost:3010`, so we read a chosen
 * `dev_user_id` out of localStorage and append it as a query param. The
 * backend gates this bypass behind ALLOW_DEV_AUTH=1.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

const DEV_USER_KEY = "saurabh-tools.dev_user_id";

export function getDevUserId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(DEV_USER_KEY);
}

export function setDevUserId(id: string | null) {
  if (typeof window === "undefined") return;
  if (id) window.localStorage.setItem(DEV_USER_KEY, id);
  else window.localStorage.removeItem(DEV_USER_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

type Init = Omit<RequestInit, "body"> & {
  body?: unknown;
};

export async function api<T = unknown>(
  path: string,
  init: Init = {},
): Promise<T> {
  const url = new URL(BASE + path);
  const devId = getDevUserId();
  if (devId) url.searchParams.set("dev_user_id", devId);

  const headers = new Headers(init.headers);
  let body: BodyInit | undefined;
  if (init.body !== undefined) {
    if (init.body instanceof FormData) {
      body = init.body;
    } else {
      headers.set("content-type", "application/json");
      body = JSON.stringify(init.body);
    }
  }

  const res = await fetch(url.toString(), {
    method: init.method ?? "GET",
    headers,
    body,
    credentials: "include",
  });

  const isJson = (res.headers.get("content-type") ?? "").includes("application/json");
  const data = isJson ? await res.json().catch(() => null) : await res.text();

  if (!res.ok) {
    const message =
      (isJson && data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : null) ||
      (typeof data === "string" && data) ||
      `Request failed (${res.status})`;
    throw new ApiError(message, res.status);
  }

  return data as T;
}

/* ---------- Typed endpoints ---------- */

export type DevUser = {
  id: string;
  email: string;
  name?: string;
  role: string;
  plan: string;
};

export type Me = {
  id: string;
  email: string;
  name?: string;
  role: string;
  // ---- audio-to-video tool subscription ----
  plan: string;
  planName: string;
  /** "hosted" or "byo" — drives whether API-key UI is shown. */
  planMode: "hosted" | "byo";
  minutesUsed: number;
  minutesLimit: number;
  topUpMinutesRemaining: number;
  cycleStartAt: string | null;
  cycleEndAt: string | null;
  subscriptionStatus: string;
  unlimited: boolean;
  // ---- captions tool subscription ----
  captionPlan: string;
  captionPlanName: string;
  captionMinutesUsed: number;
  captionMinutesLimit: number;
  captionTopUpMinutesRemaining: number;
  captionCycleEndAt: string | null;
  // ---- BYO key ----
  geminiKeyMask: string | null;
  /** True when this user must supply their own Gemini key (BYO-mode plan
   *  or admin-flagged self-host user). */
  byoMode: boolean;
};

export type Plan = {
  id: string;
  name: string;
  priceInr: number;
  minutesPerMonth: number;
  maxConcurrentJobs: number;
  priorityQueue: boolean;
  expressRenderMinutes: number;
  commercialUse: boolean;
  apiAccess: boolean;
  /** Which tool this plan belongs to. */
  tool: "audio-to-video" | "captions";
  /** "hosted" = we pay Gemini; "byo" = user supplies key */
  mode: "hosted" | "byo";
  description: string;
};

export type TopUp = {
  id: string;
  minutes: number;
  priceInr: number;
  label: string;
};

export type PlansResponse = {
  plans: Plan[];
  topups: TopUp[];
  currency: string;
  gstPercent: number;
  gstNote: string;
};

export type Subscription = {
  plan: string;
  planName: string;
  tool: "audio-to-video" | "captions";
  minutesUsed: number;
  minutesLimit: number;
  topUpMinutesRemaining: number;
  cycleStartAt: string | null;
  cycleEndAt: string | null;
  status: string;
  unlimited: boolean;
};

export type MySubscriptions = {
  audioToVideo: Subscription;
  captions: Subscription;
};

export type CheckoutResponse =
  | {
      stub: true;
      amountPaise: number;
      description: string;
      kind: "subscription" | "topup";
      itemId: string;
      message: string;
    }
  | {
      stub: false;
      orderId: string;
      amountPaise: number;
      description: string;
      kind: "subscription" | "topup";
      itemId: string;
      keyId: string;
    };

export type JobStatus =
  | "queued"
  | "running"
  | "done"
  | "failed"
  | "blocked"
  | "cancelled";

export type Job = {
  id: string;
  tool: string;
  status: JobStatus;
  progress: number;
  message: string | null;
  params: Record<string, unknown>;
  audioFilename: string | null;
  label: string | null;
  hasOutput: boolean;
  errorDetail: string | null;
  workerName: string | null;
  cancelRequested: boolean;
  /** Captions variant currently active on this video (only on
   *  audio-to-video jobs). When set, /output streams the captioned mp4. */
  activeCaptionsJobId: string | null;
  activeCaptionsStyle: string | null;
  /** Source-video metadata, present on bulk-captions transcribe jobs. */
  videoWidth: number | null;
  videoHeight: number | null;
  videoDuration: number | null;
  /** Per-frame quality breakdown for audio-to-video jobs. Tells the UI
   *  how many frames came from Gemini vs Pollinations vs placeholder. */
  frameQuality: {
    totalFrames: number;
    geminiFrames: number;
    pollinationsFrames: number;
    placeholderFrames: number;
    pollinationsIndices: number[];
    placeholderIndices: number[];
  } | null;
  /** Project grouping. New jobs always have these; legacy jobs may not. */
  projectId: string | null;
  projectName: string | null;
  /** Voice-pair → captions auto-chain pointers. Set on the parent
   *  voice-pair job once its render finishes and the transcribe is
   *  queued. The reverse pointer lives on the transcribe job. */
  chainedCaptionsJobId?: string | null;
  fromVoicePairJobId?: string | null;
  createdAt: string | null;
  updatedAt: string | null;
};

/**
 * What the captions tool sends to the backend on render. The base
 * fields (style / position / wordsPerLine / uppercase / posXFrac /
 * posYFrac) are required by the picker; the override fields below are
 * optional and only sent when the user touched them in the Customize
 * tab. Backend falls back to the picked style's preset for anything
 * the user didn't override.
 */
export type CaptionRenderOpts = {
  style: string;
  position: "top" | "middle" | "bottom";
  wordsPerLine: number;
  uppercase?: boolean;
  posXFrac?: number;
  posYFrac?: number;
  // ---- Customize-tab overrides (all optional) ----
  /** Hex like "#FFE04A" or one of the named colors backend knows. */
  primaryColor?: string;
  outlineColor?: string;
  /** 0..20 px outline thickness. */
  outlineWidth?: number;
  bgColor?: string;
  /** 0=opaque, 255=transparent. */
  bgAlpha?: number;
  /** Absolute font size in pixels. */
  fontSize?: number;
  /** Any font name installed in the backend fonts dir. */
  fontFamily?: string;
  /** 0..20 px drop-shadow / glow radius. */
  shadow?: number;
};

export type TranscriptResponse = {
  words: Array<{ word: string; start: number; end: number }>;
  videoWidth: number;
  videoHeight: number;
  videoDuration: number;
};

export type SubmitResult = {
  queued: Job[];
  blocked: Job[];
  rejected: Array<{ filename: string; reason: string }>;
  summary: {
    uploaded: number;
    queued: number;
    blocked: number;
    rejected: number;
  };
};

export const apiClient = {
  health: () => api<{ ok: boolean; service: string; ts: string }>("/health"),
  me: () => api<Me>("/me"),
  plans: () => api<PlansResponse>("/plans"),
  mySubscription: () => api<MySubscriptions>("/me/subscription"),
  createCheckout: (kind: "subscription" | "topup", id: string) =>
    api<CheckoutResponse>("/me/billing/checkout", {
      method: "POST",
      body: { kind, id },
    }),
  saveApiKey: (key: string) =>
    api<{ ok: boolean; geminiKeyMask: string }>("/me/api-key", {
      method: "POST",
      body: { key },
    }),
  deleteApiKey: () => api<{ ok: boolean }>("/me/api-key", { method: "DELETE" }),
  testApiKey: () =>
    api<{ ok: boolean; sampleModel: string }>("/me/api-key/test", {
      method: "POST",
    }),
  submitAudioToVideo: (
    files: File[],
    opts: {
      label?: string;
      size?: string;
      stylePreset?: string;
      /** Number = fixed-length scenes. "auto" = let Gemini pace it. */
      segmentSeconds?: number | "auto";
      animationStyle?: string;
      /** Spoken language of the audio. Helps Gemini comprehend non-English
       *  speech correctly when planning visual scenes. Defaults to "auto"
       *  (Gemini detects). Image prompts are still emitted in English. */
      audioLanguage?: string;
    } = {},
  ) => {
    const fd = new FormData();
    for (const f of files) fd.append("audio", f);
    if (opts.label) fd.append("label", opts.label);
    if (opts.size) fd.append("size", opts.size);
    if (opts.stylePreset) fd.append("style_preset", opts.stylePreset);
    if (opts.segmentSeconds !== undefined)
      fd.append("segment_seconds", String(opts.segmentSeconds));
    if (opts.animationStyle) fd.append("animation_style", opts.animationStyle);
    if (opts.audioLanguage) fd.append("audio_language", opts.audioLanguage);
    return api<SubmitResult>("/me/jobs/audio-to-video", {
      method: "POST",
      body: fd,
    });
  },
  /** Voice Pair. Two modes:
   *  - "single": each pair has 1 media + 1 voice
   *  - "slideshow": each pair has N media files + 1 voice; the media
   *    play back-to-back filling the voice's duration in equal slices.
   *  Pair shape is the same in both modes — caller passes media as an
   *  array of files per pair. */
  submitVoicePair: (
    pairs: {
      media: File[];
      voice: File;
      animation: "static" | "ken_burns";
    }[],
    opts: {
      label?: string;
      mode?: "single" | "slideshow";
      projectName?: string;
      projectId?: string;
      /** Language hint for the auto-chained captions transcribe.
       *  "auto" lets Whisper detect; "hi"/"ur"/etc. routes to the
       *  medium model that handles Devanagari/Nastaliq correctly. */
      language?: string;
    } = {},
  ) => {
    const fd = new FormData();
    const counts: number[] = [];
    for (const p of pairs) {
      counts.push(p.media.length);
      for (const m of p.media) fd.append("media", m);
      fd.append("voice", p.voice);
      fd.append("animations", p.animation);
    }
    for (const c of counts) fd.append("mediaCounts", String(c));
    fd.append("mode", opts.mode ?? "single");
    if (opts.label) fd.append("label", opts.label);
    if (opts.projectName) fd.append("projectName", opts.projectName);
    if (opts.projectId) fd.append("projectId", opts.projectId);
    if (opts.language) fd.append("language", opts.language);
    return api<{
      queued: {
        id: string;
        filename: string;
        voiceFilename: string;
        voiceDurationSec: number;
        animation: string;
        mode: string;
      }[];
      rejected: { filename: string; reason: string }[];
      summary: { queued: number; rejected: number };
      projectId: string;
      projectName: string;
    }>("/me/jobs/voice-pair", { method: "POST", body: fd });
  },
  listJobs: (params?: { status?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api<{ items: Job[] }>(`/me/jobs${suffix}`);
  },
  requeueBlocked: () =>
    api<{ requeued: number }>("/me/jobs/requeue-blocked", { method: "POST" }),
  cancelJob: (jobId: string) =>
    api<{
      ok: boolean;
      alreadyFinal?: boolean;
      killed?: number;
      wasStatus?: string;
      reason?: string;
      status?: string;
    }>(`/me/jobs/${jobId}/cancel`, { method: "POST" }),
  deleteJob: (jobId: string) =>
    api<{ ok: boolean; filesRemoved?: number }>(`/me/jobs/${jobId}`, {
      method: "DELETE",
    }),
  // Projects: a (projectId, projectName) pair stamped on each job at
  // submit time. The frontend uses these to fold related renders into
  // a single collapsible card with bulk actions.
  listProjects: (params?: { limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api<{
      items: {
        projectId: string | null;
        projectName: string;
        jobCount: number;
        doneCount: number;
        runningCount: number;
        failedCount: number;
        tools: string[];
        createdAt: string | null;
        updatedAt: string | null;
      }[];
    }>(`/me/projects${suffix}`);
  },
  listProjectJobs: (projectId: string) =>
    api<{ items: Job[] }>(`/me/projects/${projectId}/jobs`),
  renameProject: (projectId: string, name: string) =>
    api<{ ok: boolean; renamed: number; name: string }>(
      `/me/projects/${projectId}/rename`,
      { method: "POST", body: { name } },
    ),
  deleteProject: (projectId: string) =>
    api<{ ok: boolean; jobsRemoved: number; filesRemoved: number }>(
      `/me/projects/${projectId}`,
      { method: "DELETE" },
    ),
  projectZipUrl: (projectId: string) => {
    const url = new URL(BASE + `/me/projects/${projectId}/zip`);
    const devId = getDevUserId();
    if (devId) url.searchParams.set("dev_user_id", devId);
    return url.toString();
  },
  retryJob: (jobId: string) =>
    api<{ ok: boolean; wasStatus: string }>(`/me/jobs/${jobId}/retry`, {
      method: "POST",
    }),
  submitCaptions: (
    parentJobId: string,
    opts: CaptionRenderOpts,
  ) =>
    api<Job>("/me/jobs/captions", {
      method: "POST",
      body: { parentJobId, ...opts },
    }),
  clearCaptions: (parentJobId: string) =>
    api<{ ok: boolean }>(`/me/jobs/${parentJobId}/captions/clear`, {
      method: "POST",
    }),
  /**
   * Stage 1 of the bulk caption tool. Uploads videos and queues
   * transcribe-only jobs. The user then opens each transcribed clip in
   * the editor to choose a style and trigger `submitCaptionsRender`.
   */
  submitBulkCaptions: (
    files: File[],
    opts: { projectName?: string; projectId?: string; language?: string } = {},
  ) => {
    const fd = new FormData();
    for (const f of files) fd.append("video", f);
    if (opts.projectName) fd.append("projectName", opts.projectName);
    if (opts.projectId) fd.append("projectId", opts.projectId);
    if (opts.language) fd.append("language", opts.language);
    return api<SubmitResult & { projectId?: string; projectName?: string }>(
      "/me/jobs/captions-bulk",
      { method: "POST", body: fd },
    );
  },
  /** Stage 2: burn captions onto a transcribed video. */
  submitCaptionsRender: (
    parentJobId: string,
    opts: CaptionRenderOpts,
  ) =>
    api<Job>("/me/jobs/captions-render", {
      method: "POST",
      body: { parentJobId, ...opts },
    }),
  /**
   * Stage 2 — BULK. Same style + customize opts applied to many
   * transcribed videos at once. Backend pre-checks the combined cost
   * against the user's captions plan and 402s if the whole batch
   * doesn't fit (friendlier than failing half-way).
   */
  submitCaptionsRenderBulk: (
    parentJobIds: string[],
    opts: CaptionRenderOpts,
  ) =>
    api<{
      queued: Job[];
      rejected: Array<{ parentJobId: string; reason: string }>;
      summary: {
        uploaded: number;
        queued: number;
        rejected: number;
        totalSeconds: number;
      };
    }>("/me/jobs/captions-render-bulk", {
      method: "POST",
      body: { parentJobIds, ...opts },
    }),
  /** Build a one-shot ZIP download URL for an arbitrary set of finished
   *  bulk-captions-render jobs. Dev-mode appends dev_user_id. */
  captionsBulkZipUrl: (renderJobIds: string[]) => {
    const url = new URL(BASE + "/me/jobs/captions-bulk-zip");
    url.searchParams.set("ids", renderJobIds.join(","));
    const devId = getDevUserId();
    if (devId) url.searchParams.set("dev_user_id", devId);
    return url.toString();
  },
  /** Fetch the cached word-level transcript + video metadata for the editor. */
  getTranscript: (jobId: string) =>
    api<TranscriptResponse>(`/me/jobs/${jobId}/transcript`),
  jobSrtUrl: (jobId: string) => {
    const url = new URL(BASE + `/me/jobs/${jobId}/srt`);
    const devId = getDevUserId();
    if (devId) url.searchParams.set("dev_user_id", devId);
    return url.toString();
  },
  getJob: (jobId: string) => api<Job>(`/me/jobs/${jobId}`),
  /**
   * Build the URL that streams the rendered mp4. By default returns the
   * "active" variant — captioned if a captions job is currently set on
   * the parent, otherwise the original. Pass `variant: "original"` to
   * always get the source video. The optional `cacheKey` ends up in the
   * query string only as a cache-buster — useful when the active
   * captions variant changes and the same job id needs a fresh fetch.
   */
  jobOutputUrl: (
    jobId: string,
    opts: { variant?: "active" | "original"; cacheKey?: string } = {},
  ) => {
    const url = new URL(BASE + `/me/jobs/${jobId}/output`);
    const devId = getDevUserId();
    if (devId) url.searchParams.set("dev_user_id", devId);
    if (opts.variant && opts.variant !== "active")
      url.searchParams.set("variant", opts.variant);
    if (opts.cacheKey) url.searchParams.set("v", opts.cacheKey);
    return url.toString();
  },
  /**
   * Turn a relative API path (e.g. the `imageUrl` returned by the
   * preview endpoint) into a fully-qualified URL with the dev_user_id
   * appended where applicable.
   */
  absoluteUrl: (relativePath: string) => {
    const url = new URL(
      relativePath.startsWith("/") ? BASE + relativePath : relativePath,
    );
    const devId = getDevUserId();
    if (devId) url.searchParams.set("dev_user_id", devId);
    return url.toString();
  },
  devUsers: () => api<DevUser[]>("/_dev/users"),

  // ---- Admin (owner-only on the backend) ----
  adminGetConfig: () => api<AdminConfig>("/_admin/config"),
  adminSetConfig: (updates: Record<string, string>) =>
    api<AdminConfig>("/_admin/config", {
      method: "POST",
      body: updates,
    }),
  adminListUsers: (q?: string, limit = 100) => {
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    qs.set("limit", String(limit));
    return api<{ items: AdminUser[] }>(`/_admin/users?${qs.toString()}`);
  },
  adminGrantPlan: (userId: string, planId: string) =>
    api<Subscription>("/_admin/billing/grant", {
      method: "POST",
      body: { userId, kind: "subscription", id: planId },
    }),
  adminGrantTopup: (userId: string, topupId: string) =>
    api<Subscription>("/_admin/billing/grant", {
      method: "POST",
      body: { userId, kind: "topup", id: topupId },
    }),
  adminResetCycles: () =>
    api<{ reset: number }>("/_admin/billing/reset-cycles", { method: "POST" }),

  // ---- Invite whitelist ----
  adminListInvites: () =>
    api<{ items: AdminInvite[] }>("/_admin/invites"),
  adminAddInvite: (email: string, note?: string) =>
    api<AdminInvite>("/_admin/invites", {
      method: "POST",
      body: { email, note },
    }),
  adminRemoveInvite: (email: string) =>
    api<{ ok: boolean }>(
      `/_admin/invites/${encodeURIComponent(email)}`,
      { method: "DELETE" },
    ),
};

export type AdminInvite = {
  email: string;
  active: boolean;
  note: string;
  addedBy: string;
  createdAt: string | null;
  updatedAt: string | null;
};

export type AdminSecretField = {
  source: "db" | "env" | null;
  mask: string | null;
  set: boolean;
};

export type AdminPublicField = {
  source: "db" | "env" | null;
  value: string;
  set: boolean;
};

export type AdminConfig = {
  geminiApiKeys: AdminSecretField;
  razorpayKeyId: AdminSecretField;
  razorpayKeySecret: AdminSecretField;
  razorpayWebhookSecret: AdminSecretField;
  togetherApiKey: AdminSecretField;
  replicateApiKey: AdminSecretField;
  fireworksApiKey: AdminSecretField;
  razorpayEnabled: AdminPublicField;
  byoKeyUserIds: AdminPublicField;
  imageProviderOrder: AdminPublicField;
  resolved: {
    geminiKeyCount: number;
    razorpayConfigured: boolean;
    byoUserCount: number;
    togetherReady: boolean;
    replicateReady: boolean;
    fireworksReady: boolean;
  };
};

export type AdminUser = {
  id: string;
  email: string;
  name?: string;
  role: string;
  plan: string;
  planName: string;
  minutesUsed: number;
  minutesLimit: number;
  topUpMinutesRemaining: number;
  cycleEndAt: string | null;
  status: string;
};
