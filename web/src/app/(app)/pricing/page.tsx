"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ApiError,
  apiClient,
  type Plan,
  type PlansResponse,
  type TopUp,
} from "@/lib/api";
import { useMe } from "@/components/MeProvider";

export default function PricingPage() {
  const { state, refresh } = useMe();
  const [data, setData] = useState<PlansResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [mode, setMode] = useState<"hosted" | "byo">("hosted");

  useEffect(() => {
    apiClient
      .plans()
      .then((d) => {
        setData(d);
        // Preselect the toggle to match the user's current plan mode
        // so they land on the right tier when they open the page.
        if (state.status === "ready") {
          const cur = d.plans.find((p) => p.id === state.me.plan);
          if (cur?.mode === "byo") setMode("byo");
        }
      })
      .catch((e) => {
        setError(e instanceof ApiError ? e.message : "Couldn't load plans");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status]);

  const currentPlan =
    state.status === "ready" ? state.me.plan : null;

  async function handleCheckout(
    kind: "subscription" | "topup",
    id: string,
  ) {
    if (state.status !== "ready") {
      setError("Sign in first to subscribe.");
      return;
    }
    setError(null);
    setPendingId(`${kind}:${id}`);
    try {
      const res = await apiClient.createCheckout(kind, id);
      if (res.stub) {
        // Razorpay not configured yet — surface the dev message so
        // the operator knows what's missing.
        setError(
          `Razorpay not configured. ${res.message} (dev: amount ₹${res.amountPaise / 100})`,
        );
      } else {
        // Real Razorpay Checkout JS would open here. We'll wire that
        // up once live keys exist.
        setError(
          `Razorpay order ${res.orderId} created. Checkout JS wiring is pending.`,
        );
      }
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Checkout failed");
    } finally {
      setPendingId(null);
    }
  }

  if (error && !data) {
    return (
      <div className="max-w-5xl mx-auto p-10">
        <h1 className="text-2xl font-bold mb-4">Pricing</h1>
        <p className="text-red-400">{error}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="max-w-5xl mx-auto p-10 text-[var(--muted)]">
        Loading plans…
      </div>
    );
  }

  // Audio-to-video plans split by hosted/BYO toggle.
  const a2vPlans = data.plans
    .filter((p) => p.tool === "audio-to-video" && p.mode === mode)
    .sort((a, b) => a.priceInr - b.priceInr);
  // Caption tool plans are a separate section (no mode toggle).
  const captionPlans = data.plans
    .filter((p) => p.tool === "captions")
    .sort((a, b) => a.priceInr - b.priceInr);
  const currentCaptionPlan =
    state.status === "ready" ? state.me.captionPlan : null;

  return (
    <div className="max-w-6xl mx-auto p-6 md:p-10">
      <header className="mb-8 text-center">
        <h1 className="text-3xl md:text-4xl font-bold mb-3">
          Simple, minute-based pricing
        </h1>
        <p className="text-[var(--muted)] max-w-2xl mx-auto">
          Pick a plan that matches how much video you create each month.
          You pay only for the minutes you render. {data.gstNote}
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <section className="mb-16">
        <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono mb-2">
          Tool 1
        </div>
        <h2 className="text-2xl font-bold mb-1">Audio → Video</h2>
        <p className="text-[var(--muted)] text-sm mb-4">
          Audio uploads turn into Ken-Burns-styled videos with captions
          included free on every render.
        </p>

        <div className="flex items-center gap-3 mb-6 flex-wrap">
          <div className="inline-flex rounded-full border border-[var(--line)] bg-[var(--panel)] p-1">
            <button
              type="button"
              onClick={() => setMode("hosted")}
              className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${
                mode === "hosted"
                  ? "bg-[var(--accent)] text-black"
                  : "text-[var(--muted)] hover:text-white"
              }`}
            >
              Hosted
            </button>
            <button
              type="button"
              onClick={() => setMode("byo")}
              className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${
                mode === "byo"
                  ? "bg-[var(--accent)] text-black"
                  : "text-[var(--muted)] hover:text-white"
              }`}
            >
              Bring your own key
            </button>
          </div>
          <span className="text-xs text-[var(--muted)]">
            {mode === "hosted"
              ? "All-inclusive — we provide Gemini."
              : "Cheaper — you provide your own Gemini key."}
          </span>
        </div>

        <div
          className={`grid gap-5 sm:grid-cols-2 ${
            a2vPlans.length === 4 ? "lg:grid-cols-4" : "lg:grid-cols-5"
          }`}
        >
          {a2vPlans.map((p) => (
            <PlanCard
              key={p.id}
              plan={p}
              isCurrent={p.id === currentPlan}
              popular={p.id === "creator" || p.id === "byo_standard"}
              pending={pendingId === `subscription:${p.id}`}
              onPick={() => handleCheckout("subscription", p.id)}
            />
          ))}
        </div>
      </section>

      <section className="mb-16">
        <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono mb-2">
          Tool 2
        </div>
        <h2 className="text-2xl font-bold mb-1">Caption Your Videos</h2>
        <p className="text-[var(--muted)] text-sm mb-6">
          Upload any finished video and we&apos;ll transcribe + burn
          captions. Separate plan, separate quota.
        </p>
        <div className="grid gap-5 sm:grid-cols-2 max-w-2xl">
          {captionPlans.map((p) => (
            <PlanCard
              key={p.id}
              plan={p}
              isCurrent={p.id === currentCaptionPlan}
              popular={p.id === "caption_pro"}
              pending={pendingId === `subscription:${p.id}`}
              onPick={() => handleCheckout("subscription", p.id)}
            />
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xl font-bold mb-4">Need more minutes?</h2>
        <p className="text-[var(--muted)] mb-5 text-sm">
          One-time top-ups never expire. Cycle minutes drain first; top-up
          minutes kick in when your monthly bucket runs out.
        </p>
        <div className="grid gap-4 sm:grid-cols-3">
          {data.topups.map((t) => (
            <TopUpCard
              key={t.id}
              topup={t}
              pending={pendingId === `topup:${t.id}`}
              onPick={() => handleCheckout("topup", t.id)}
            />
          ))}
        </div>
      </section>

      <footer className="mt-14 text-center text-[var(--muted)] text-xs">
        Prices in INR. GST {data.gstPercent}% extra at checkout. Cancel anytime.
      </footer>
    </div>
  );
}

function PlanCard({
  plan,
  isCurrent,
  popular,
  pending,
  onPick,
}: {
  plan: Plan;
  isCurrent: boolean;
  popular: boolean;
  pending: boolean;
  onPick: () => void;
}) {
  const isFree = plan.priceInr === 0;
  return (
    <div
      className={`relative rounded-xl border p-5 flex flex-col ${
        popular
          ? "border-[var(--accent)] bg-[var(--accent)]/5"
          : "border-[var(--border)] bg-[var(--panel)]"
      }`}
    >
      {popular && (
        <span className="absolute -top-2 right-3 rounded-full bg-[var(--accent)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-black">
          Popular
        </span>
      )}
      <h3 className="text-lg font-bold">{plan.name}</h3>
      <p className="text-[var(--muted)] text-xs mt-1 min-h-[2.5rem]">
        {plan.description}
      </p>

      <div className="mt-4 mb-5">
        <div className="text-3xl font-bold">
          {isFree ? "Free" : <>₹{plan.priceInr}</>}
          {!isFree && (
            <span className="text-sm text-[var(--muted)] font-normal">
              /mo
            </span>
          )}
        </div>
        {!isFree && (
          <div className="text-xs text-[var(--muted)] mt-1">+ GST 18%</div>
        )}
      </div>

      <ul className="space-y-2 text-sm flex-1 mb-5">
        <Feature>
          <strong>{plan.minutesPerMonth} min</strong> of video / month
        </Feature>
        <Feature>
          Up to {plan.maxConcurrentJobs} concurrent render
          {plan.maxConcurrentJobs > 1 ? "s" : ""}
        </Feature>
        {plan.expressRenderMinutes > 0 && (
          <Feature>
            {plan.expressRenderMinutes >= 9999
              ? "Unlimited express render"
              : `${plan.expressRenderMinutes} min express render`}
          </Feature>
        )}
        <Feature on={plan.priorityQueue}>Priority queue</Feature>
        <Feature on={plan.commercialUse}>Commercial use</Feature>
        <Feature on={plan.apiAccess}>API access</Feature>
      </ul>

      <button
        onClick={onPick}
        disabled={isCurrent || pending || isFree}
        className={`w-full rounded-md py-2 text-sm font-medium transition ${
          isCurrent
            ? "bg-[var(--border)] text-[var(--muted)] cursor-default"
            : isFree
            ? "bg-[var(--border)] text-[var(--muted)] cursor-not-allowed"
            : "bg-[var(--accent)] text-black hover:opacity-90"
        }`}
      >
        {isCurrent
          ? "Current plan"
          : isFree
          ? "Default"
          : pending
          ? "Opening checkout…"
          : "Upgrade"}
      </button>
    </div>
  );
}

function TopUpCard({
  topup,
  pending,
  onPick,
}: {
  topup: TopUp;
  pending: boolean;
  onPick: () => void;
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--panel)] p-5 flex flex-col">
      <h3 className="text-lg font-bold">{topup.label}</h3>
      <p className="text-[var(--muted)] text-xs mt-1">
        Adds {topup.minutes} minutes to your top-up pool.
      </p>
      <div className="mt-4 mb-5 text-2xl font-bold">
        ₹{topup.priceInr}
        <span className="text-xs text-[var(--muted)] font-normal"> + GST</span>
      </div>
      <button
        onClick={onPick}
        disabled={pending}
        className="w-full rounded-md py-2 text-sm font-medium bg-[var(--accent)] text-black hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Opening checkout…" : "Buy"}
      </button>
    </div>
  );
}

function Feature({
  children,
  on = true,
}: {
  children: React.ReactNode;
  on?: boolean;
}) {
  return (
    <li
      className={`flex items-start gap-2 ${
        on ? "text-[var(--fg)]" : "text-[var(--muted)] line-through"
      }`}
    >
      <span className="mt-0.5 text-[var(--accent)]">
        {on ? "✓" : "·"}
      </span>
      <span>{children}</span>
    </li>
  );
}

// Backlink to docs (placeholder for now).
export function PricingFooterLink() {
  return (
    <Link href="/" className="text-sm text-[var(--accent)] hover:underline">
      ← Back to workspace
    </Link>
  );
}
