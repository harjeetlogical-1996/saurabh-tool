"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { ApiError, apiClient, type Me } from "@/lib/api";

type State =
  | { status: "loading" }
  | { status: "unauthenticated"; reason: string }
  | { status: "not-invited"; reason: string }
  | { status: "ready"; me: Me };

type Ctx = {
  state: State;
  refresh: () => Promise<void>;
};

const MeContext = createContext<Ctx | null>(null);

export function MeProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });

  const refresh = useCallback(async () => {
    try {
      const me = await apiClient.me();
      setState({ status: "ready", me });
    } catch (e) {
      // 403 from /me = the user is authenticated on Better Auth but
      // their email isn't on the early-access whitelist. Surface that
      // as a distinct state so the layout can show a friendlier
      // "request access" screen instead of the generic sign-in CTA.
      if (e instanceof ApiError && e.status === 403) {
        setState({ status: "not-invited", reason: e.message });
        return;
      }
      const reason = e instanceof ApiError ? e.message : "Couldn't reach the API";
      setState({ status: "unauthenticated", reason });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <MeContext.Provider value={{ state, refresh }}>
      {children}
    </MeContext.Provider>
  );
}

export function useMe(): Ctx {
  const ctx = useContext(MeContext);
  if (!ctx) {
    throw new Error("useMe must be used inside <MeProvider>");
  }
  return ctx;
}
