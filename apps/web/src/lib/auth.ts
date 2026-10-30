/**
 * Browser-side session. The access token lives in sessionStorage (cleared when the tab closes). It is readable by
 * any script on this origin, which is the documented trade-off versus httpOnly cookies (those would need CSRF
 * handling). Sign-out only discards the token here: the API issues stateless tokens that expire on their own.
 */
export const SESSION_KEY = "pathforge.session";
export const SESSION_EVENT = "pathforge:session";
export const EXPIRED_FLAG = "pathforge.expired";

export interface SessionUser {
  id: string;
  email: string;
  display_name: string | null;
  is_admin: boolean;
}
export interface Session {
  token: string;
  user: SessionUser;
}

function notify(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SESSION_EVENT));
}

/** Storage can throw (private mode, blocked storage); the app must still work without it for the current page. */
let memory: Session | null = null;

export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    if (!raw) return memory;
    const parsed = JSON.parse(raw) as Partial<Session>;
    if (parsed && typeof parsed.token === "string" && parsed.user && typeof parsed.user.id === "string") {
      return parsed as Session;
    }
    return null;
  } catch {
    return memory;
  }
}

export function getToken(): string | null {
  return getSession()?.token ?? null;
}

export function setSession(session: Session): void {
  memory = session;
  try {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    window.sessionStorage.removeItem(EXPIRED_FLAG);
  } catch {
    /* keep the in-memory session only */
  }
  notify();
}

export function clearSession(): void {
  memory = null;
  try {
    window.sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* nothing to clear */
  }
  notify();
}

/** A request came back 401 while we held a token: the session is over. The shell redirects to /login. */
export function expireSession(): void {
  try {
    window.sessionStorage.setItem(EXPIRED_FLAG, "1");
  } catch {
    /* the redirect still happens; only the message is lost */
  }
  clearSession();
}

export function consumeExpiredFlag(): boolean {
  try {
    const flagged = window.sessionStorage.getItem(EXPIRED_FLAG) === "1";
    window.sessionStorage.removeItem(EXPIRED_FLAG);
    return flagged;
  } catch {
    return false;
  }
}
