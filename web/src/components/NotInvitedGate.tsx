"use client";

import { useMe } from "@/components/MeProvider";

/**
 * Renders a clean "early access" screen for signed-in users whose email
 * isn't on the invite whitelist. All other states fall through to the
 * regular page content.
 *
 * Sits inside the (app) layout below MeProvider so every authenticated
 * route gets gated without each page having to handle 403s manually.
 */
export function NotInvitedGate({
  children,
}: {
  children: React.ReactNode;
}) {
  const { state } = useMe();

  if (state.status !== "not-invited") {
    return <>{children}</>;
  }

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-6 py-16">
      <div className="max-w-md text-center space-y-5">
        <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--accent)] font-mono">
          Early access
        </div>
        <h1 className="font-display text-[26px] md:text-[32px] tracking-[-0.025em] leading-tight">
          You&apos;re on the list… almost.
        </h1>
        <p className="text-[14.5px] leading-[1.65] text-[var(--muted)]">
          {state.reason ||
            "These tools are invite-only right now. Drop a line to request access."}
        </p>
        <div className="pt-2">
          <a
            href="mailto:saurabhbhayana1996@gmail.com?subject=Tool%20access%20request"
            className="inline-flex h-11 items-center px-5 rounded-full bg-[var(--accent)] text-black text-[13px] font-semibold hover:shadow-[0_0_18px_var(--accent-glow)] transition-shadow"
          >
            Request access →
          </a>
        </div>
        <p className="text-[11.5px] text-[var(--muted)] pt-2">
          Already invited? Make sure you&apos;re signed in with the same
          email you shared with us.
        </p>
      </div>
    </div>
  );
}
