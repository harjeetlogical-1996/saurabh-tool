"use client";

import { useState } from "react";
import Link from "next/link";
import { ApiError, apiClient } from "@/lib/api";
import { useMe } from "@/components/MeProvider";

type Status =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "testing" }
  | { kind: "test-ok"; sampleModel: string }
  | { kind: "error"; message: string };

export default function ApiKeysPage() {
  const { state, refresh } = useMe();
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  const ready = state.status === "ready";
  const me = ready ? state.me : null;
  const hasKey = !!me?.geminiKeyMask;

  async function save() {
    if (draft.trim().length < 20) {
      setStatus({
        kind: "error",
        message: "That doesn't look like a Gemini key (too short).",
      });
      return;
    }
    setStatus({ kind: "saving" });
    try {
      await apiClient.saveApiKey(draft.trim());
      setDraft("");
      await refresh();
      setStatus({ kind: "saved" });
    } catch (e) {
      setStatus({
        kind: "error",
        message: e instanceof ApiError ? e.message : "Couldn't save the key.",
      });
    }
  }

  async function test() {
    setStatus({ kind: "testing" });
    try {
      const res = await apiClient.testApiKey();
      setStatus({ kind: "test-ok", sampleModel: res.sampleModel });
    } catch (e) {
      setStatus({
        kind: "error",
        message: e instanceof ApiError ? e.message : "Test failed.",
      });
    }
  }

  async function remove() {
    setStatus({ kind: "saving" });
    try {
      await apiClient.deleteApiKey();
      await refresh();
      setStatus({ kind: "idle" });
    } catch (e) {
      setStatus({
        kind: "error",
        message: e instanceof ApiError ? e.message : "Couldn't delete the key.",
      });
    }
  }

  const platformPaid = ready && !me!.byoMode;

  if (platformPaid) {
    return (
      <div className="max-w-[820px]">
        <h2 className="font-display text-[20px] tracking-tight text-white">
          Not applicable on your plan
        </h2>
        <p className="mt-2 text-[14px] leading-[1.65] text-[var(--muted)]">
          You&apos;re on a hosted plan — we handle everything for you, and
          render minutes are tracked on your subscription. No API keys to
          manage.
        </p>
        <div className="mt-6">
          <Link
            href="/pricing"
            className="inline-flex h-10 items-center px-4 rounded-full bg-[var(--accent)] text-black text-[13px] font-semibold"
          >
            View plans &rarr;
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[820px]">
      <h2 className="font-display text-[20px] tracking-tight text-white">
        API keys
      </h2>
      <p className="mt-2 text-[14px] leading-[1.65] text-[var(--muted)]">
        Bring-your-own-key plan. Paste your Gemini key here and every render
        bills your Google Cloud account directly.
      </p>

      {state.status === "unauthenticated" && (
        <div className="mt-6 rounded-xl border border-yellow-500/40 bg-yellow-500/5 p-5 text-[13.5px] text-yellow-100">
          You aren&apos;t signed in.{" "}
          {state.reason ? <span className="text-yellow-200/80">({state.reason})</span> : null}
          <div className="mt-2 text-[12.5px] text-yellow-200/70">
            In dev: pick a user from the ⚡ menu in the top bar. In prod:
            sign in at saurabhbhayana.com first.
          </div>
        </div>
      )}

      <div className="mt-8 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6 space-y-4">
        <label className="block">
          <span className="block text-[11px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono mb-1.5">
            Gemini API key
          </span>
          {hasKey && !draft && (
            <div className="flex items-center justify-between gap-3 rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 h-11 text-[14px] font-mono text-white">
              <span>{me!.geminiKeyMask}</span>
              <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--accent)] font-mono">
                saved
              </span>
            </div>
          )}
          {(!hasKey || draft) && (
            <input
              type="password"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={hasKey ? "Paste a new key to replace…" : "AIzaSy…"}
              className="tool-input"
              disabled={!ready}
              autoComplete="off"
              spellCheck={false}
            />
          )}
          <span className="mt-2 block text-[11.5px] text-[var(--muted)] leading-[1.55]">
            Encrypted at rest with AES-256-GCM. Only decrypted in-memory at
            request time. Never logged, never displayed back after save.
          </span>
        </label>

        <div className="flex flex-wrap items-center gap-3 pt-1">
          {(!hasKey || draft) && (
            <button
              type="button"
              onClick={save}
              disabled={!ready || status.kind === "saving" || draft.length < 20}
              className="inline-flex h-10 items-center px-4 rounded-full bg-[var(--accent)] text-black text-[13px] font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {status.kind === "saving" ? "Saving…" : "Save key"}
            </button>
          )}
          {hasKey && !draft && (
            <>
              <button
                type="button"
                onClick={test}
                disabled={status.kind === "testing"}
                className="inline-flex h-10 items-center px-4 rounded-full bg-[var(--accent)] text-black text-[13px] font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {status.kind === "testing" ? "Testing…" : "Test key"}
              </button>
              <button
                type="button"
                onClick={() => setDraft(" ")}
                className="inline-flex h-10 items-center px-4 rounded-full border border-[var(--line)] text-[13px] text-white hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
              >
                Replace
              </button>
              <button
                type="button"
                onClick={remove}
                className="inline-flex h-10 items-center px-4 rounded-full border border-[var(--line)] text-[13px] text-[var(--muted)] hover:border-red-500/60 hover:text-red-400 transition-colors"
              >
                Delete
              </button>
            </>
          )}
          {draft && hasKey && (
            <button
              type="button"
              onClick={() => {
                setDraft("");
                setStatus({ kind: "idle" });
              }}
              className="inline-flex h-10 items-center px-4 rounded-full border border-[var(--line)] text-[13px] text-[var(--muted)] hover:text-white"
            >
              Cancel
            </button>
          )}
        </div>

        {status.kind === "saved" && (
          <p className="text-[12.5px] text-[var(--accent)] font-mono">
            ✓ Saved. Hit “Test key” to confirm it works.
          </p>
        )}
        {status.kind === "test-ok" && (
          <p className="text-[12.5px] text-[var(--accent)] font-mono">
            ✓ Key works — Gemini returned model {status.sampleModel}.
          </p>
        )}
        {status.kind === "error" && (
          <p className="text-[12.5px] text-red-300 font-mono">
            ✕ {status.message}
          </p>
        )}
      </div>

      <div className="mt-6 rounded-xl border border-[var(--line)] bg-[var(--bg)] p-5 text-[13px] text-[var(--muted)] leading-[1.7]">
        <div className="text-white text-[13.5px]">How to get a Gemini key</div>
        <ol className="mt-2 list-decimal list-inside space-y-1">
          <li>Go to <span className="font-mono text-white">aistudio.google.com</span> and sign in.</li>
          <li>Open the API keys page from the left rail.</li>
          <li>Click <span className="text-white">Create API key</span>, pick or create a project.</li>
          <li>Paste it above and hit Save.</li>
        </ol>
      </div>
    </div>
  );
}
