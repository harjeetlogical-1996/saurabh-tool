export default function BillingPage() {
  return (
    <div className="max-w-[820px]">
      <h2 className="font-display text-[20px] tracking-tight text-white">
        Billing
      </h2>
      <p className="mt-2 text-[14px] leading-[1.65] text-[var(--muted)]">
        Free tier gives you 1 render lifetime. Subscribe at ₹100/month for
        unlimited renders. You still pay Google directly for the API compute.
      </p>

      <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
        <PlanCard
          name="Free"
          price="₹0"
          tagline="Try once"
          features={[
            "1 lifetime render",
            "BYO Gemini API key",
            "All tools available",
            "Output watermark",
          ]}
          ctaLabel="Current plan"
          disabled
        />
        <PlanCard
          name="Pro"
          price="₹100"
          tagline="per month"
          features={[
            "Unlimited renders",
            "BYO Gemini API key",
            "All tools available",
            "No watermark",
            "Priority job queue",
          ]}
          ctaLabel="Subscribe — coming soon"
          disabled
          highlighted
        />
      </div>
    </div>
  );
}

function PlanCard({
  name,
  price,
  tagline,
  features,
  ctaLabel,
  disabled,
  highlighted,
}: {
  name: string;
  price: string;
  tagline: string;
  features: string[];
  ctaLabel: string;
  disabled?: boolean;
  highlighted?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border bg-[var(--surface)] p-6 ${
        highlighted ? "border-[var(--accent)]/40" : "border-[var(--line)]"
      }`}
    >
      <div className="flex items-baseline gap-2">
        <span className="font-display text-[20px] tracking-tight text-white">
          {name}
        </span>
        {highlighted && (
          <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--accent)] font-mono">
            recommended
          </span>
        )}
      </div>
      <div className="mt-4 flex items-baseline gap-1.5">
        <span className="font-display text-[34px] tracking-[-0.03em] text-white">
          {price}
        </span>
        <span className="text-[13px] text-[var(--muted)]">{tagline}</span>
      </div>
      <ul className="mt-5 space-y-1.5 text-[13.5px] text-white/85">
        {features.map((f) => (
          <li key={f} className="flex gap-2">
            <span className="text-[var(--accent)]">+</span>
            {f}
          </li>
        ))}
      </ul>
      <button
        type="button"
        disabled={disabled}
        className={`mt-6 inline-flex h-10 items-center px-4 rounded-full text-[13px] font-semibold ${
          highlighted
            ? "bg-[var(--accent)] text-black"
            : "border border-[var(--line)] text-white"
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        {ctaLabel}
      </button>
    </div>
  );
}
