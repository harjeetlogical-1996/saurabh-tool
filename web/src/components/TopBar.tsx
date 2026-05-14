"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useMe } from "@/components/MeProvider";
import { DevUserPicker } from "@/components/DevUserPicker";
import { setDevUserId } from "@/lib/api";

/**
 * TopBar replaces the old left sidebar. Layout:
 *   [logo] [tool switcher ▾]              [dev picker] [main site] [user ▾]
 *
 * On mobile (<sm) the tool switcher collapses to just the active tool
 * label; the right rail collapses to user avatar + a hamburger menu that
 * opens the tool switcher.
 */

type Tool = {
  href: string;
  label: string;
  status: "live" | "soon";
};

const TOOLS: Tool[] = [
  { href: "/audio-to-video", label: "Audio to Video", status: "live" },
  { href: "/captions", label: "Caption your videos", status: "live" },
];

type SettingsItem = { href: string; label: string; byoOnly?: boolean };

const SETTINGS: SettingsItem[] = [
  { href: "/pricing", label: "Pricing & plans" },
  { href: "/settings/api-keys", label: "API keys", byoOnly: true },
  { href: "/settings/billing", label: "Billing" },
  { href: "/settings/account", label: "Account" },
];

export function TopBar() {
  const pathname = usePathname();

  // Pick the active tool by URL. If we're on the workspace root or a
  // settings page, fall back to the first tool's label so the dropdown
  // says something sensible.
  const activeTool =
    TOOLS.find((t) => pathname === t.href || pathname.startsWith(t.href + "/")) ??
    null;
  const inSettings = pathname.startsWith("/settings");
  const onWorkspaceRoot = pathname === "/";

  return (
    <header className="h-14 shrink-0 sticky top-0 z-30 border-b border-[var(--line)] bg-[var(--surface)]/95 backdrop-blur supports-[backdrop-filter]:bg-[var(--surface)]/80 px-4 md:px-6 flex items-center justify-between gap-3">
      <div className="flex items-center gap-3 min-w-0">
        <Link
          href="/"
          className="flex items-center gap-2.5 shrink-0"
          aria-label="Workspace home"
        >
          <span className="relative inline-flex h-8 w-8 items-center justify-center rounded-md bg-[var(--accent)] text-black">
            <span className="font-display text-[14px] leading-none">sb</span>
          </span>
          <span className="hidden sm:flex flex-col leading-tight">
            <span className="font-display text-[14px] tracking-tight">
              Tools<span className="text-[var(--accent)]">.</span>
            </span>
            <span className="text-[9px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
              saurabhbhayana
            </span>
          </span>
        </Link>

        <span aria-hidden className="h-5 w-px bg-[var(--line)] shrink-0" />

        <ToolSwitcher
          activeLabel={
            activeTool?.label ??
            (inSettings ? "Settings" : onWorkspaceRoot ? "Workspace" : "Tools")
          }
        />
      </div>

      <div className="flex items-center gap-2 md:gap-3 shrink-0">
        <div className="hidden md:block">
          <DevUserPicker />
        </div>
        <Link
          href="https://saurabhbhayana.com"
          className="hidden md:inline text-[12.5px] text-[var(--muted)] hover:text-[var(--accent)] transition-colors"
        >
          Main site →
        </Link>
        <UserMenu />
      </div>
    </header>
  );
}

/* ---------- Tool switcher ---------- */

function ToolSwitcher({ activeLabel }: { activeLabel: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useClickOutside(ref, () => setOpen(false));

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 px-2.5 h-8 rounded-md border border-[var(--line)] bg-[var(--bg)] text-[13px] text-white hover:border-[var(--accent)]/50 transition-colors max-w-[180px] sm:max-w-none"
      >
        <span className="truncate">{activeLabel}</span>
        <Chevron open={open} />
      </button>
      {open && (
        <div className="absolute left-0 top-10 z-40 w-[260px] rounded-lg border border-[var(--line)] bg-[var(--surface)] shadow-2xl p-1.5">
          <div className="px-2 py-1.5 text-[10px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono">
            Tools
          </div>
          {TOOLS.map((t) => (
            <button
              key={t.href}
              type="button"
              onClick={() => {
                setOpen(false);
                router.push(t.href);
              }}
              className="w-full flex items-center justify-between gap-3 text-left px-2 py-2 rounded-md text-[13px] text-white hover:bg-[var(--bg)]"
            >
              <span className="truncate">{t.label}</span>
              <span className="text-[9px] font-mono uppercase tracking-[0.18em] text-[var(--accent)] border border-[var(--accent)]/40 px-1.5 py-0.5 rounded-full">
                live
              </span>
            </button>
          ))}
          <div className="px-2 py-1.5 mt-1 border-t border-[var(--line)] text-[10px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono">
            Coming soon
          </div>
          {[
            "Image upscaler",
            "Transcript to shorts",
            "AI thumbnail studio",
          ].map((label) => (
            <div
              key={label}
              className="px-2 py-2 rounded-md text-[13px] text-[var(--muted)] cursor-not-allowed"
            >
              {label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- User menu ---------- */

function UserMenu() {
  const { state } = useMe();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useClickOutside(ref, () => setOpen(false));

  if (state.status === "loading") {
    return (
      <div className="flex items-center gap-2.5">
        <span className="h-7 w-7 rounded-full bg-[var(--line)] animate-pulse" />
      </div>
    );
  }

  if (state.status === "unauthenticated") {
    return (
      <a
        href="https://saurabhbhayana.com/login"
        className="text-[12.5px] text-[var(--accent)] hover:underline whitespace-nowrap"
      >
        Sign in →
      </a>
    );
  }

  const me = state.me;
  const initial = (me.name?.[0] ?? me.email[0] ?? "?").toUpperCase();
  const planLabel = me.unlimited
    ? `${me.planName} · unlimited`
    : `${me.planName} · ${me.minutesUsed.toFixed(1)} / ${me.minutesLimit.toFixed(0)} min`;
  const usagePct =
    me.minutesLimit > 0
      ? Math.min(100, Math.round((me.minutesUsed / me.minutesLimit) * 100))
      : 0;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 pl-1 pr-2 h-9 rounded-full hover:bg-[var(--bg)] transition-colors"
        aria-label="Account menu"
      >
        <span className="h-7 w-7 rounded-full bg-[var(--accent)] text-black font-display text-[12px] flex items-center justify-center">
          {initial}
        </span>
        <span className="hidden md:inline text-[13px] text-white max-w-[140px] truncate">
          {me.name ?? me.email}
        </span>
        <span className="hidden md:block">
          <Chevron open={open} />
        </span>
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-40 w-[260px] rounded-lg border border-[var(--line)] bg-[var(--surface)] shadow-2xl p-1.5">
          <div className="px-3 py-2.5">
            <div className="text-[13px] text-white truncate">
              {me.name ?? me.email}
            </div>
            <div className="text-[11px] text-[var(--muted)] truncate font-mono mt-0.5">
              {me.email}
            </div>
            <div className="mt-2 inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.18em]">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  me.unlimited ? "bg-[var(--accent)]" : "bg-[var(--muted)]"
                }`}
              />
              <span
                className={
                  me.unlimited ? "text-[var(--accent)]" : "text-[var(--muted)]"
                }
              >
                {planLabel}
              </span>
            </div>
            {!me.unlimited && me.minutesLimit > 0 && (
              <div className="mt-2.5">
                <div className="h-1.5 w-full rounded-full bg-[var(--bg)] overflow-hidden">
                  <div
                    className={`h-full transition-all ${
                      usagePct > 85
                        ? "bg-red-400"
                        : usagePct > 60
                          ? "bg-yellow-400"
                          : "bg-[var(--accent)]"
                    }`}
                    style={{ width: `${usagePct}%` }}
                  />
                </div>
                {me.topUpMinutesRemaining > 0 && (
                  <div className="text-[10px] text-[var(--muted)] mt-1.5">
                    + {me.topUpMinutesRemaining.toFixed(1)} min top-up
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="border-t border-[var(--line)] py-1">
            {SETTINGS.filter((s) => !s.byoOnly || me.byoMode).map((s) => (
              <button
                key={s.href}
                type="button"
                onClick={() => {
                  setOpen(false);
                  router.push(s.href);
                }}
                className="w-full text-left px-3 py-2 rounded-md text-[13px] text-white hover:bg-[var(--bg)]"
              >
                {s.label}
              </button>
            ))}
            {me.plan === "owner" && (
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  router.push("/admin/keys");
                }}
                className="w-full text-left px-3 py-2 rounded-md text-[13px] text-[var(--accent)] hover:bg-[var(--bg)]"
              >
                Admin →
              </button>
            )}
          </div>
          {!me.unlimited && (
            <div className="border-t border-[var(--line)] p-2">
              <Link
                href="/pricing"
                onClick={() => setOpen(false)}
                className="block w-full text-center px-3 py-2 rounded-md bg-[var(--accent)] text-black text-[12.5px] font-semibold hover:shadow-[0_0_18px_var(--accent-glow)] transition-shadow"
              >
                Upgrade plan →
              </Link>
            </div>
          )}
          <div className="border-t border-[var(--line)] py-1">
            <a
              href="https://saurabhbhayana.com"
              className="block px-3 py-2 rounded-md text-[12.5px] text-[var(--muted)] hover:bg-[var(--bg)] hover:text-white"
            >
              Open main site
            </a>
            <button
              type="button"
              onClick={() => {
                setDevUserId(null);
                setOpen(false);
                window.location.reload();
              }}
              className="w-full text-left px-3 py-2 rounded-md text-[12.5px] text-[var(--muted)] hover:bg-[var(--bg)] hover:text-red-400"
            >
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- Helpers ---------- */

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`text-[var(--muted)] transition-transform ${open ? "rotate-180" : ""}`}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function useClickOutside(
  ref: React.RefObject<HTMLElement | null>,
  onOutside: () => void,
) {
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) onOutside();
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [ref, onOutside]);
}
