import Link from "next/link";

export default function WorkspaceHome() {
  return (
    <div className="px-6 md:px-10 py-10 md:py-14 max-w-[1100px] mx-auto">
      {/* Header — staggered fade-rise on mount */}
      <div
        className="animate-fade-rise-delay text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono inline-flex items-center gap-2"
        style={{ ["--reveal-delay" as string]: "0ms" }}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-blink" />
        Workspace
      </div>

      <h1
        className="animate-fade-rise-delay mt-3 font-display text-[30px] md:text-[42px] tracking-[-0.035em] leading-[1.05]"
        style={{ ["--reveal-delay" as string]: "80ms" }}
      >
        Welcome back<span className="text-[var(--accent)]">.</span>
      </h1>

      <p
        className="animate-fade-rise-delay mt-4 text-[15px] leading-[1.7] text-[var(--muted)] max-w-[640px]"
        style={{ ["--reveal-delay" as string]: "160ms" }}
      >
        Pick a tool below. Each runs on your own Gemini API key, so you
        control your costs — we charge for the workflow, not the compute.
      </p>

      {/* Tool cards */}
      <div
        className="animate-fade-rise-delay mt-10 grid grid-cols-1 md:grid-cols-2 gap-4"
        style={{ ["--reveal-delay" as string]: "240ms" }}
      >
        <ToolCard
          href="/audio-to-video"
          eyebrow="Audio · Video"
          title="Audio to Video"
          blurb="Upload an MP3, get a Ken Burns video with AI-generated images per audio segment. Powered by your Gemini key."
          status="ready"
        />
        <ToolCard
          href="/captions"
          eyebrow="Video · Captions"
          title="Caption your videos"
          blurb="Bulk-upload finished videos and burn captions in. Eight styles, position control, transcript cached so style swaps are free."
          status="ready"
        />
      </div>

      {/* Get-started panel */}
      <div
        className="animate-fade-rise-delay mt-12 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6 hover:border-[var(--accent)]/40 transition-colors"
        style={{ ["--reveal-delay" as string]: "340ms" }}
      >
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-[var(--accent)] font-mono">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-blink" />
          Get started
        </div>
        <ol className="mt-4 space-y-3 text-[14px] text-white/85">
          <li className="flex items-start gap-3">
            <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-[11px] font-mono font-semibold">
              1
            </span>
            <span>
              Open{" "}
              <Link
                href="/settings/api-keys"
                className="text-[var(--accent)] underline underline-offset-2 hover:text-[var(--accent-deep)]"
              >
                Settings → API keys
              </Link>{" "}
              and paste your Gemini API key.
            </span>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-[11px] font-mono font-semibold">
              2
            </span>
            <span>Open the Audio to Video tool, upload an MP3, hit render.</span>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-[11px] font-mono font-semibold">
              3
            </span>
            <span className="text-[var(--muted)]">
              Free tier: 1 lifetime render. After that, ₹100/month for unlimited.
            </span>
          </li>
        </ol>
      </div>
    </div>
  );
}

function ToolCard({
  href,
  eyebrow,
  title,
  blurb,
  status,
}: {
  href: string;
  eyebrow: string;
  title: string;
  blurb: string;
  status: "ready" | "soon";
}) {
  const ready = status === "ready";
  const inner = (
    <div
      className={`group h-full rounded-xl border bg-[var(--surface)] p-6 card-spring ${
        ready
          ? "border-[var(--line)] hover:border-[var(--accent)]"
          : "border-[var(--line)] opacity-60"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
          {eyebrow}
        </span>
        {ready && (
          <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--accent)] font-mono inline-flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-blink" />
            Ready
          </span>
        )}
      </div>
      <h2 className="mt-4 font-display text-[22px] tracking-tight text-white">
        {title}
      </h2>
      <p className="mt-2 text-[13.5px] leading-[1.65] text-[var(--muted)]">
        {blurb}
      </p>
      {ready && (
        <div className="mt-5 inline-flex items-center gap-1.5 text-[13px] font-medium text-[var(--accent)]">
          Open the tool
          <span className="transition-transform duration-200 group-hover:translate-x-1">
            →
          </span>
        </div>
      )}
    </div>
  );
  return ready ? <Link href={href}>{inner}</Link> : <div>{inner}</div>;
}
