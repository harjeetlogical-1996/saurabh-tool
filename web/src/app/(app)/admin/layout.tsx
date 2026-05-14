"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMe } from "@/components/MeProvider";

const TABS = [
  { href: "/admin/keys", label: "API keys & config" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/invites", label: "Invites" },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { state } = useMe();
  const pathname = usePathname();

  if (state.status === "loading") {
    return (
      <div className="p-10 text-[var(--muted)]">Loading…</div>
    );
  }
  if (state.status !== "ready") {
    return (
      <div className="p-10 text-[var(--muted)]">
        Sign in required.
      </div>
    );
  }
  if (state.me.plan !== "owner") {
    return (
      <div className="max-w-xl mx-auto p-10 text-center">
        <h1 className="text-2xl font-bold mb-3">Forbidden</h1>
        <p className="text-[var(--muted)]">
          This area is for the platform owner only.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6 md:p-10">
      <header className="mb-8">
        <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono mb-1">
          Admin
        </div>
        <h1 className="text-2xl md:text-3xl font-bold">
          Platform controls
        </h1>
      </header>

      <nav className="flex gap-2 border-b border-[var(--line)] mb-8">
        {TABS.map((t) => {
          const active =
            pathname === t.href || pathname.startsWith(t.href + "/");
          return (
            <Link
              key={t.href}
              href={t.href}
              className={`px-3 py-2 text-sm border-b-2 -mb-px transition-colors ${
                active
                  ? "border-[var(--accent)] text-white"
                  : "border-transparent text-[var(--muted)] hover:text-white"
              }`}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
