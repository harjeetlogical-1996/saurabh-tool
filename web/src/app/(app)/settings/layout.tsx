import { SettingsTabs } from "@/components/SettingsTabs";

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="px-6 md:px-10 py-10 md:py-14 max-w-[1080px]">
      <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted)] font-mono">
        Settings
      </div>
      <h1 className="mt-3 font-display text-[28px] md:text-[34px] tracking-[-0.035em] leading-[1.05]">
        Account &amp; preferences
      </h1>
      <div className="mt-8">
        <SettingsTabs />
      </div>
      <div className="pt-8">{children}</div>
    </div>
  );
}
