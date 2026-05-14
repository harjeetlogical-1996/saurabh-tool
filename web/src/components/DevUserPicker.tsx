"use client";

import { useEffect, useState } from "react";
import { apiClient, getDevUserId, setDevUserId, type DevUser } from "@/lib/api";

/**
 * Tiny dev-only widget. Lets you pick which Mongo user to act as while
 * running locally, since cross-subdomain cookies don't work between
 * `localhost:3007` and `localhost:3010`.
 *
 * Disappears entirely if /_dev/users 404s (i.e. ALLOW_DEV_AUTH != 1).
 */
export function DevUserPicker() {
  const [users, setUsers] = useState<DevUser[] | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setActive(getDevUserId());
    apiClient.devUsers().then(setUsers).catch(() => setUsers(null));
  }, []);

  if (users === null) return null;
  if (users.length === 0) {
    return (
      <span className="text-[11px] font-mono text-yellow-300/80">
        No users in DB
      </span>
    );
  }

  const activeUser = users.find((u) => u.id === active) ?? null;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 px-2 h-7 rounded-md border border-yellow-500/30 bg-yellow-500/5 text-[11px] font-mono text-yellow-200 hover:border-yellow-400/60"
        title="Dev-only: pick the Mongo user this tab acts as."
      >
        <span aria-hidden>⚡</span>
        <span>{activeUser ? activeUser.email : "pick dev user"}</span>
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-20 w-[260px] rounded-lg border border-yellow-500/30 bg-[var(--surface)] shadow-xl p-1.5">
          <div className="px-2 py-1.5 text-[10px] uppercase tracking-[0.18em] text-yellow-300/80 font-mono">
            Dev — act as user
          </div>
          {users.map((u) => (
            <button
              key={u.id}
              type="button"
              onClick={() => {
                setDevUserId(u.id);
                setActive(u.id);
                setOpen(false);
                window.location.reload();
              }}
              className={`w-full text-left px-2 py-2 rounded-md text-[12.5px] hover:bg-[var(--bg)] ${
                u.id === active ? "text-white" : "text-[var(--muted)]"
              }`}
            >
              <div className="truncate">{u.email}</div>
              <div className="text-[10px] font-mono text-[var(--muted)]">
                {u.role} · {u.plan}
              </div>
            </button>
          ))}
          {active && (
            <button
              type="button"
              onClick={() => {
                setDevUserId(null);
                setActive(null);
                setOpen(false);
                window.location.reload();
              }}
              className="w-full text-left px-2 py-1.5 mt-1 border-t border-[var(--line)] text-[11px] text-[var(--muted)] hover:text-red-400"
            >
              Sign out (clear dev id)
            </button>
          )}
        </div>
      )}
    </div>
  );
}
