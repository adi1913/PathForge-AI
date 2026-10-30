import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SESSION_KEY, clearSession, getSession, getToken, setSession, type Session } from "./auth";
import { useSession, useUserId } from "./user";

const session: Session = { token: "tok-1", user: { id: "u-1", email: "a@example.com", display_name: null, is_admin: false } };

afterEach(() => {
  vi.restoreAllMocks();
  clearSession();
  window.sessionStorage.clear();
});

describe("session storage", () => {
  it("round-trips through sessionStorage (never localStorage)", () => {
    setSession(session);
    expect(getToken()).toBe("tok-1");
    expect(JSON.parse(window.sessionStorage.getItem(SESSION_KEY) ?? "{}").user.id).toBe("u-1");
    expect(window.localStorage.length).toBe(0);
    clearSession();
    expect(getSession()).toBeNull();
    expect(window.sessionStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it("ignores corrupt stored data", () => {
    window.sessionStorage.setItem(SESSION_KEY, "{not json");
    expect(getSession()).toBeNull();
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({ token: 5 }));
    expect(getSession()).toBeNull();
  });

  it("does not throw when storage is blocked, and keeps the session for the page", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => setSession(session)).not.toThrow();
    expect(getToken()).toBe("tok-1");
    expect(() => clearSession()).not.toThrow();
  });
});

describe("hooks", () => {
  it("useUserId follows sign-in and sign-out", () => {
    const { result } = renderHook(() => useUserId());
    expect(result.current).toEqual(["", true]);
    act(() => setSession(session));
    expect(result.current).toEqual(["u-1", true]);
    act(() => clearSession());
    expect(result.current[0]).toBe("");
  });

  it("useSession exposes the user", () => {
    setSession(session);
    const { result } = renderHook(() => useSession());
    expect(result.current[0]?.user.email).toBe("a@example.com");
  });
});
