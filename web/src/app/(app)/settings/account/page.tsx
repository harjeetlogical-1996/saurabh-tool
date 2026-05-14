"use client";

import { useMe } from "@/components/MeProvider";

export default function AccountPage() {
  const { state } = useMe();
  const me = state.status === "ready" ? state.me : null;

  return (
    <div className="max-w-[820px]">
      <h2 className="font-display text-[20px] tracking-tight text-white">
        Account
      </h2>
      <p className="mt-2 text-[14px] leading-[1.65] text-[var(--muted)]">
        Account profile lives on the main site. Sign in, sign out, and
        password changes happen at saurabhbhayana.com.
      </p>

      <div className="mt-6 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6 space-y-4">
        <Row label="Email" value={me?.email ?? "—"} />
        <Row label="Name" value={me?.name ?? "—"} />
        <Row label="Role" value={me?.role ?? "—"} />
        <Row label="Plan" value={me?.plan ?? "—"} />
        <Row
          label="Renders used"
          value={
            me
              ? me.unlimited
                ? "∞ unlimited"
                : `${me.rendersUsed} / ${me.renderLimit || "∞"}`
              : "—"
          }
        />
        <Row
          label="API key"
          value={me?.geminiKeyMask ?? "Not set"}
        />
      </div>

      <div className="mt-6 flex items-center gap-3">
        <a
          href="https://saurabhbhayana.com/sb-console/account"
          className="inline-flex h-10 items-center px-4 rounded-full border border-[var(--line)] text-[13px] text-white hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
        >
          Edit on main site →
        </a>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 text-[14px]">
      <span className="text-[11px] uppercase tracking-[0.18em] text-[var(--muted)] font-mono">
        {label}
      </span>
      <span className="text-white font-mono">{value}</span>
    </div>
  );
}
