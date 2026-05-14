"use client";

import { useEffect, useState } from "react";
import { ApiError, apiClient, type AdminInvite } from "@/lib/api";

export default function AdminInvitesPage() {
  const [items, setItems] = useState<AdminInvite[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [adding, setAdding] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const res = await apiClient.adminListInvites();
      setItems(res.items);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load invites.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function add() {
    const e = email.trim().toLowerCase();
    if (!e || !e.includes("@")) {
      setError("Enter a valid email.");
      return;
    }
    setAdding(true);
    setError(null);
    try {
      await apiClient.adminAddInvite(e, note.trim() || undefined);
      setEmail("");
      setNote("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add invite.");
    } finally {
      setAdding(false);
    }
  }

  async function remove(em: string) {
    if (!confirm(`Revoke access for ${em}? They can be re-added later.`)) {
      return;
    }
    try {
      await apiClient.adminRemoveInvite(em);
      await load();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Couldn't remove invite.");
    }
  }

  const active = items.filter((i) => i.active);
  const revoked = items.filter((i) => !i.active);

  return (
    <div className="space-y-8">
      {/* Quick stats */}
      <section className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <Stat label="Active invites" value={String(active.length)} tone="ok" />
        <Stat label="Revoked" value={String(revoked.length)} tone="neutral" />
        <Stat
          label="Total ever invited"
          value={String(items.length)}
          tone="neutral"
        />
      </section>

      {/* Add form */}
      <section className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6 space-y-4">
        <div>
          <h2 className="text-lg font-bold mb-1">Invite someone</h2>
          <p className="text-sm text-[var(--muted)]">
            Only whitelisted emails can use the tools while early-access is
            on. They sign in normally on saurabhbhayana.com first, then this
            email gate lets them through to tool.saurabhbhayana.com.
          </p>
        </div>
        <div className="flex flex-col md:flex-row gap-2.5">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@example.com"
            className="flex-1 rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm"
            onKeyDown={(e) => e.key === "Enter" && add()}
          />
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (e.g. friend, beta tester) — optional"
            className="flex-1 rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm"
            maxLength={200}
            onKeyDown={(e) => e.key === "Enter" && add()}
          />
          <button
            type="button"
            onClick={add}
            disabled={adding || !email.trim()}
            className="px-4 py-2 rounded-md bg-[var(--accent)] text-black text-sm font-semibold disabled:opacity-40"
          >
            {adding ? "Adding…" : "Add"}
          </button>
        </div>
        {error && (
          <p className="text-[12.5px] font-mono text-red-300">✕ {error}</p>
        )}
      </section>

      {/* Active table */}
      <section>
        <h2 className="text-lg font-bold mb-3">
          Active ({active.length})
        </h2>
        {active.length === 0 && (
          <p className="text-sm text-[var(--muted)]">
            No active invites yet. Add the first email above.
          </p>
        )}
        {active.length > 0 && (
          <div className="rounded-xl border border-[var(--line)] overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface)] text-left text-[var(--muted)]">
                <tr>
                  <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider">
                    Email
                  </th>
                  <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider">
                    Note
                  </th>
                  <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider">
                    Added
                  </th>
                  <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {active.map((inv) => (
                  <tr
                    key={inv.email}
                    className="border-t border-[var(--line)] bg-[var(--panel)] hover:bg-[var(--surface)]"
                  >
                    <td className="px-3 py-2.5 font-mono text-white">
                      {inv.email}
                    </td>
                    <td className="px-3 py-2.5 text-[var(--muted)] text-xs">
                      {inv.note || "—"}
                    </td>
                    <td className="px-3 py-2.5 text-[var(--muted)] text-xs font-mono">
                      {inv.createdAt
                        ? new Date(inv.createdAt).toLocaleDateString()
                        : "—"}
                    </td>
                    <td className="px-3 py-2.5">
                      <button
                        type="button"
                        onClick={() => remove(inv.email)}
                        className="px-2 py-1 rounded-md border border-[var(--line)] text-xs text-[var(--muted)] hover:border-red-500/60 hover:text-red-400"
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Revoked — collapsed by default since rare */}
      {revoked.length > 0 && (
        <section>
          <h2 className="text-lg font-bold mb-3 text-[var(--muted)]">
            Revoked ({revoked.length})
          </h2>
          <div className="rounded-xl border border-[var(--line)] overflow-hidden">
            <table className="w-full text-sm">
              <tbody>
                {revoked.map((inv) => (
                  <tr
                    key={inv.email}
                    className="border-t border-[var(--line)] bg-[var(--panel)]"
                  >
                    <td className="px-3 py-2.5 font-mono text-[var(--muted)] line-through">
                      {inv.email}
                    </td>
                    <td className="px-3 py-2.5">
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            await apiClient.adminAddInvite(
                              inv.email,
                              inv.note,
                            );
                            await load();
                          } catch (e) {
                            alert(
                              e instanceof ApiError
                                ? e.message
                                : "Couldn't restore",
                            );
                          }
                        }}
                        className="px-2 py-1 rounded-md border border-[var(--line)] text-xs text-[var(--accent)] hover:border-[var(--accent)]"
                      >
                        Restore
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {loading && (
        <p className="text-[var(--muted)] text-sm">Loading…</p>
      )}
    </div>
  );
}

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
