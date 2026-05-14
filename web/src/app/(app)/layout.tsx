import { MeProvider } from "@/components/MeProvider";
import { NotInvitedGate } from "@/components/NotInvitedGate";
import { TopBar } from "@/components/TopBar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <MeProvider>
      <div className="min-h-screen flex flex-col bg-[var(--bg)] text-[var(--fg)]">
        <TopBar />
        <main className="flex-1 min-w-0 bg-[var(--canvas)]">
          <NotInvitedGate>{children}</NotInvitedGate>
        </main>
      </div>
    </MeProvider>
  );
}
