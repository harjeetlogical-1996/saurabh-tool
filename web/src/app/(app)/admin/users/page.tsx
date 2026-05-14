"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  apiClient,
  type AdminUser,
  type Plan,
  type TopUp,
  type PlansResponse,
} from "@/lib/api";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [plans, setPlans] = useState<PlansResponse | null>(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actingFor, setActingFor] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [u, p] = await Promise.all([
        apiClient.adminListUsers(q || undefined, 200),
        apiClient.plans(),
      ]);
      setUsers(u.items);
      setPlans(p);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function grantPlan(userId: string, planId: string) {
    setActingFor(userId);
    try {
      await apiClient.adminGrantPlan(userId, planId);
      await load();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : "Grant failed");
    } finally {
      setActingFor(null);
    }
  }

  async function grantTopup(userId: string, topupId: string) {
    setActingFor(userId);
    try {
      await apiClient.adminGrantTopup(userId, topupId);
      await load();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : "Top-up failed");
    } finally {
      setActingFor(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-3 items-center">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") load();
          }}
          placeholder="Search email or name…"
          className="flex-1 max-w-md rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm"
        />
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="px-4 py-2 rounded-md border border-[var(--line)] text-sm hover:border-[var(--accent)] disabled:opacity-50"
        >
          {loading ? "Loading…" : "Search"}
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="rounded-xl border border-[var(--line)] overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[var(--surface)] text-left text-[var(--muted)]">
            <tr>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider">
                Email
              </th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider">
                Plan
              </th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider">
                Minutes
              </th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider">
                Top-up
              </th>
              <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr
                key={u.id}
                className="border-t border-[var(--line)] bg-[var(--panel)] hover:bg-[var(--surface)]"
              >
                <td className="px-3 py-2.5">
                  <div className="text-white">{u.name ?? u.email}</div>
                  <div className="text-[var(--muted)] text-xs font-mono">
                    {u.email}
                  </div>
                  <div className="text-[var(--muted)] text-[10px] font-mono mt-0.5">
                    {u.id}
                  </div>
                </td>
                <td className="px-3 py-2.5 font-mono text-xs">
                  {u.planName}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs">
                  {u.minutesUsed.toFixed(1)} / {u.minutesLimit.toFixed(0)}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs">
                  {u.topUpMinutesRemaining.toFixed(1)}
                </td>
                <td className="px-3 py-2.5">
                  <UserActions
                    userId={u.id}
                    currentPlan={u.plan}
                    plans={plans?.plans ?? []}
                    topups={plans?.topups ?? []}
                    pending={actingFor === u.id}
                    onGrantPlan={(pid) => grantPlan(u.id, pid)}
                    onGrantTopup={(tid) => grantTopup(u.id, tid)}
                  />
                </td>
              </tr>
            ))}
            {!loading && users.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-8 text-center text-[var(--muted)]"
                >
                  No users.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function UserActions({
  userId,
  currentPlan,
  plans,
  topups,
  pending,
  onGrantPlan,
  onGrantTopup,
}: {
  userId: string;
  currentPlan: string;
  plans: Plan[];
  topups: TopUp[];
  pending: boolean;
  onGrantPlan: (id: string) => void;
  onGrantTopup: (id: string) => void;
}) {
  const [planChoice, setPlanChoice] = useState(currentPlan);
  const [topupChoice, setTopupChoice] = useState(topups[0]?.id ?? "");

  return (
    <div className="flex flex-wrap gap-2 items-center">
      <select
        value={planChoice}
        onChange={(e) => setPlanChoice(e.target.value)}
        className="rounded-md border border-[var(--line)] bg-[var(--bg)] px-2 py-1 text-xs"
      >
        <option value="owner">owner</option>
        {plans.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={pending || planChoice === currentPlan}
        onClick={() => onGrantPlan(planChoice)}
        className="px-2 py-1 rounded-md bg-[var(--accent)] text-black text-xs font-semibold disabled:opacity-40"
      >
        Grant
      </button>

      <span className="text-[var(--muted)] text-xs">·</span>

      <select
        value={topupChoice}
        onChange={(e) => setTopupChoice(e.target.value)}
        className="rounded-md border border-[var(--line)] bg-[var(--bg)] px-2 py-1 text-xs"
      >
        {topups.map((t) => (
          <option key={t.id} value={t.id}>
            {t.label}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={pending || !topupChoice}
        onClick={() => onGrantTopup(topupChoice)}
        className="px-2 py-1 rounded-md border border-[var(--line)] text-xs hover:border-[var(--accent)] disabled:opacity-40"
      >
        Add
      </button>
    </div>
  );
}
