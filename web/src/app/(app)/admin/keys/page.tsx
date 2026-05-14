"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  apiClient,
  type AdminConfig,
  type AdminSecretField,
  type AdminPublicField,
} from "@/lib/api";

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "error"; message: string };

export default function AdminKeysPage() {
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Editable drafts. Empty string = "no change". To clear a field, the
  // user toggles the clear button (sets draft to the sentinel "").
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [save, setSave] = useState<SaveState>({ kind: "idle" });

  async function load() {
    try {
      const c = await apiClient.adminGetConfig();
      setConfig(c);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Couldn't load config");
    }
  }

  useEffect(() => {
    load();
  }, []);

  function setDraft(field: string, value: string) {
    setDrafts((d) => ({ ...d, [field]: value }));
  }

  async function saveAll() {
    setSave({ kind: "saving" });
    try {
      const c = await apiClient.adminSetConfig(drafts);
      setConfig(c);
      setDrafts({});
      setSave({ kind: "saved" });
      setTimeout(() => setSave({ kind: "idle" }), 2500);
    } catch (e) {
      setSave({
        kind: "error",
        message: e instanceof ApiError ? e.message : "Save failed",
      });
    }
  }

  async function resetCycles() {
    if (!confirm("Force-reset all subscription cycles to start of this month?"))
      return;
    try {
      const r = await apiClient.adminResetCycles();
      alert(`Reset ${r.reset} subscription cycle(s).`);
    } catch (e) {
      alert(e instanceof ApiError ? e.message : "Reset failed");
    }
  }

  if (loadError) {
    return <p className="text-red-400">{loadError}</p>;
  }
  if (!config) {
    return <p className="text-[var(--muted)]">Loading config…</p>;
  }

  const hasDrafts = Object.values(drafts).some((v) => v !== undefined);

  return (
    <div className="space-y-10">
      {/* Status summary */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Stat
          label="Gemini keys loaded"
          value={String(config.resolved.geminiKeyCount)}
          tone={config.resolved.geminiKeyCount > 0 ? "ok" : "warn"}
        />
        <Stat
          label="Razorpay"
          value={config.resolved.razorpayConfigured ? "Configured" : "Not set"}
          tone={config.resolved.razorpayConfigured ? "ok" : "warn"}
        />
        <Stat
          label="BYO-key users"
          value={String(config.resolved.byoUserCount)}
          tone="neutral"
        />
      </section>

      {/* Gemini keys */}
      <section className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6">
        <h2 className="text-lg font-bold mb-1">Gemini API keys</h2>
        <p className="text-sm text-[var(--muted)] mb-4">
          Comma-separated list. Each key gets its own rate-limit bucket
          on Google&apos;s side — more keys = higher parallel throughput.
          Cost is the same regardless of key count.
        </p>
        <SecretEditor
          field="geminiApiKeys"
          value={config.geminiApiKeys}
          draft={drafts.geminiApiKeys}
          onChange={(v) => setDraft("geminiApiKeys", v)}
          placeholder="AIzaSy...key1, AIzaSy...key2"
          multiline
        />
      </section>

      {/* Cheap FLUX image providers */}
      <section className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6 space-y-5">
        <div>
          <h2 className="text-lg font-bold mb-1">Image providers (FLUX schnell)</h2>
          <p className="text-sm text-[var(--muted)]">
            Cost-ascending fallback chain used before Gemini for image
            generation. Each is ~10× cheaper than Gemini Image with
            indistinguishable quality. Skip a provider by leaving its
            key blank.
          </p>
          <div className="mt-3 flex gap-2 text-[10px] font-mono uppercase tracking-wider">
            <ProviderBadge label="Together" ok={config.resolved.togetherReady} />
            <ProviderBadge label="Replicate" ok={config.resolved.replicateReady} />
            <ProviderBadge label="Fireworks" ok={config.resolved.fireworksReady} />
          </div>
        </div>
        <SecretEditor
          field="togetherApiKey"
          label="Together AI key  · ₹0.23 / image"
          value={config.togetherApiKey}
          draft={drafts.togetherApiKey}
          onChange={(v) => setDraft("togetherApiKey", v)}
          placeholder="tgp_•••"
        />
        <SecretEditor
          field="replicateApiKey"
          label="Replicate token  · ₹0.25 / image"
          value={config.replicateApiKey}
          draft={drafts.replicateApiKey}
          onChange={(v) => setDraft("replicateApiKey", v)}
          placeholder="r8_•••"
        />
        <SecretEditor
          field="fireworksApiKey"
          label="Fireworks AI key  · ₹0.30 / image"
          value={config.fireworksApiKey}
          draft={drafts.fireworksApiKey}
          onChange={(v) => setDraft("fireworksApiKey", v)}
          placeholder="fw_•••"
        />
        <PublicEditor
          field="imageProviderOrder"
          value={config.imageProviderOrder}
          draft={drafts.imageProviderOrder}
          onChange={(v) => setDraft("imageProviderOrder", v)}
          placeholder="together,replicate,fireworks"
        />
        <p className="text-[11px] text-[var(--muted)]">
          Order is comma-separated provider names. Default:
          <code className="ml-1 font-mono text-white">together,replicate,fireworks</code>.
          Demote a flaky one by moving it to the end.
        </p>
      </section>

      {/* Razorpay */}
      <section className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6 space-y-5">
        <div>
          <h2 className="text-lg font-bold mb-1">Razorpay</h2>
          <p className="text-sm text-[var(--muted)]">
            Required for live subscription checkout. Until these are set
            the pricing page returns a stub response.
          </p>
        </div>
        <SecretEditor
          field="razorpayKeyId"
          label="Key ID"
          value={config.razorpayKeyId}
          draft={drafts.razorpayKeyId}
          onChange={(v) => setDraft("razorpayKeyId", v)}
          placeholder="rzp_live_xxxxxxxxxx"
        />
        <SecretEditor
          field="razorpayKeySecret"
          label="Key Secret"
          value={config.razorpayKeySecret}
          draft={drafts.razorpayKeySecret}
          onChange={(v) => setDraft("razorpayKeySecret", v)}
          placeholder="•••"
        />
        <SecretEditor
          field="razorpayWebhookSecret"
          label="Webhook Secret"
          value={config.razorpayWebhookSecret}
          draft={drafts.razorpayWebhookSecret}
          onChange={(v) => setDraft("razorpayWebhookSecret", v)}
          placeholder="•••"
        />
      </section>

      {/* BYO user ids */}
      <section className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6">
        <h2 className="text-lg font-bold mb-1">BYO-key users</h2>
        <p className="text-sm text-[var(--muted)] mb-4">
          Comma-separated user IDs. These users will be forced to bring
          their own Gemini key (for code-license / self-hosted buyers).
          Most users should NOT be on this list.
        </p>
        <PublicEditor
          field="byoKeyUserIds"
          value={config.byoKeyUserIds}
          draft={drafts.byoKeyUserIds}
          onChange={(v) => setDraft("byoKeyUserIds", v)}
          placeholder="user_id_1, user_id_2"
        />
      </section>

      {/* Save bar */}
      <div className="sticky bottom-4 flex items-center justify-between gap-4 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 shadow-xl">
        <div className="text-sm">
          {save.kind === "saving" && <span className="text-[var(--muted)]">Saving…</span>}
          {save.kind === "saved" && <span className="text-[var(--accent)]">Saved.</span>}
          {save.kind === "error" && (
            <span className="text-red-400">{save.message}</span>
          )}
          {save.kind === "idle" && !hasDrafts && (
            <span className="text-[var(--muted)]">No unsaved changes.</span>
          )}
          {save.kind === "idle" && hasDrafts && (
            <span className="text-yellow-300">
              {Object.keys(drafts).length} unsaved change(s).
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={resetCycles}
            className="px-4 py-2 rounded-md border border-[var(--line)] text-sm hover:border-[var(--accent)]"
          >
            Reset cycles
          </button>
          <button
            type="button"
            onClick={saveAll}
            disabled={!hasDrafts || save.kind === "saving"}
            className="px-4 py-2 rounded-md bg-[var(--accent)] text-black text-sm font-semibold disabled:opacity-40"
          >
            Save changes
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Bits ---------- */

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "ok" | "warn" | "neutral";
}) {
  const color =
    tone === "ok"
      ? "text-[var(--accent)]"
      : tone === "warn"
        ? "text-yellow-300"
        : "text-white";
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono mb-1">
        {label}
      </div>
      <div className={`text-xl font-bold ${color}`}>{value}</div>
    </div>
  );
}

function ProviderBadge({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span
      className={`px-2 py-0.5 rounded-full border ${
        ok
          ? "border-[var(--accent)] text-[var(--accent)]"
          : "border-[var(--line)] text-[var(--muted)]"
      }`}
    >
      {label} {ok ? "✓" : "·"}
    </span>
  );
}

function SecretEditor({
  field,
  label,
  value,
  draft,
  onChange,
  placeholder,
  multiline = false,
}: {
  field: string;
  label?: string;
  value: AdminSecretField;
  draft: string | undefined;
  onChange: (v: string) => void;
  placeholder?: string;
  multiline?: boolean;
}) {
  const editing = draft !== undefined;
  return (
    <div>
      {label && (
        <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono mb-1.5">
          {label}
        </div>
      )}
      {!editing ? (
        <div className="flex items-center justify-between gap-3 rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm">
          <span className="font-mono">
            {value.set ? value.mask : <span className="text-[var(--muted)]">not set</span>}
          </span>
          <div className="flex gap-2 items-center">
            {value.source && (
              <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-[var(--muted)]">
                {value.source}
              </span>
            )}
            <button
              type="button"
              onClick={() => onChange("")}
              className="text-xs text-[var(--accent)] hover:underline"
            >
              {value.set ? "Replace" : "Set"}
            </button>
            {value.set && value.source === "db" && (
              <button
                type="button"
                onClick={() => onChange("")}
                className="text-xs text-red-400 hover:underline"
                title="Save with empty value to clear and fall back to env"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      ) : multiline ? (
        <textarea
          value={draft}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={3}
          className="w-full rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm font-mono"
          spellCheck={false}
        />
      ) : (
        <input
          type="password"
          value={draft}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm font-mono"
          spellCheck={false}
          autoComplete="off"
        />
      )}
    </div>
  );
}

function PublicEditor({
  field,
  value,
  draft,
  onChange,
  placeholder,
}: {
  field: string;
  value: AdminPublicField;
  draft: string | undefined;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const editing = draft !== undefined;
  return (
    <div>
      {!editing ? (
        <div className="flex items-center justify-between gap-3 rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm">
          <span className="font-mono truncate">
            {value.set ? value.value : <span className="text-[var(--muted)]">empty</span>}
          </span>
          <button
            type="button"
            onClick={() => onChange(value.value)}
            className="text-xs text-[var(--accent)] hover:underline"
          >
            Edit
          </button>
        </div>
      ) : (
        <input
          type="text"
          value={draft}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm font-mono"
          spellCheck={false}
        />
      )}
    </div>
  );
}
