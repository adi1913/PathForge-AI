"use client";

import { useEffect, useState } from "react";
import { SESSION_EVENT, getSession, type Session } from "./auth";

/** The signed-in session, kept in sync across components and tabs. `ready` is false until the first client read. */
export function useSession(): [Session | null, boolean] {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const sync = () => setSession(getSession());
    sync();
    setReady(true);
    window.addEventListener(SESSION_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(SESSION_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return [session, ready];
}

/** The authenticated user's id (from the server's /auth responses, never typed in by hand). */
export function useUserId(): [string, boolean] {
  const [session, ready] = useSession();
  return [session?.user.id ?? "", ready];
}
