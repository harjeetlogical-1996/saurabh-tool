"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMe } from "@/components/MeProvider";

type Tab = { href: string; label: string; byoOnly?: boolean };

const TABS: Tab[] = [
  { href: "/settings/api-keys", label: "API keys", byoOnly: true },
  { href: "/settings/billing", label: "Billing" },
  { href: "/settings/account", label: "Account" },
];

export function SettingsTabs() {
  const pathname = usePathname();
  const { state } = useMe();
  const isByo = state.status === "ready" && state.me.byoMode;
  const visible = TABS.filter((t) => !t.byoOnly || isByo);

  return (
    <nav
      aria-label="Settings sections"
      className="border-b border-[var(--line)] flex gap-1 -mb-px"
    >
      {visible.map((t) => {
        const active = pathname === t.href;
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`relative px-3 py-2 text-[13px] transition-colors ${
              active
                ? "text-white"
                : "text-[var(--muted)] hover:text-white"
            }`}
          >
            {t.label}
            {active && (
              <span
                aria-hidden
                className="absolute left-2 right-2 -bottom-px h-px bg-[var(--accent)]"
              />
            )}
          </Link>
        );
      })}
    </nav>
  );
}
