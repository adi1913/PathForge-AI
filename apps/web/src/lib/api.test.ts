import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, buildUrl, describeDetail, request } from "./api";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => new Response(body === undefined ? "" : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("buildUrl", () => {
  it("drops empty query values and encodes the rest", () => {
    const url = buildUrl("/assessments", { user_id: "u 1", skill: "", status: undefined, limit: 5 });
    expect(url).toMatch(/\/assessments\?user_id=u\+1&limit=5$/);
  });
  it("has no query string when nothing is set", () => {
    expect(buildUrl("/health")).toMatch(/\/health$/);
  });
});

describe("describeDetail", () => {
  it("reads string and validation-array details", () => {
    expect(describeDetail({ detail: "Not found" }, "x")).toBe("Not found");
    expect(describeDetail({ detail: [{ msg: "too short" }, { msg: "bad" }] }, "x")).toBe("too short; bad");
    expect(describeDetail(null, "fallback")).toBe("fallback");
  });
});

describe("request", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("sends JSON with a content type", async () => {
    const fn = mockFetch(200, { ok: true });
    await request("/x", { method: "POST", json: { a: 1 } });
    const [, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(init.body).toBe('{"a":1}');
  });

  it("sends multipart without forcing a content type", async () => {
    const fn = mockFetch(200, { status: "ok" });
    await api.analyzeResume("user-1", { text: "hello" });
    const [, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("user_id")).toBe("user-1");
    expect((init.body as FormData).get("text")).toBe("hello");
    expect(init.headers as Record<string, string>).not.toHaveProperty("Content-Type");
  });

  it("turns API errors into ApiError with the readable detail", async () => {
    mockFetch(404, { detail: "Assessment not found" });
    await expect(api.getAssessment("a", "u")).rejects.toMatchObject({ name: "ApiError", status: 404, detail: "Assessment not found" });
  });

  it("falls back to the status when the error body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>", { status: 502 })));
    await expect(request("/x")).rejects.toMatchObject({ status: 502, detail: "Request failed (502)" });
  });

  it("explains unreachable APIs", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fetch failed"))));
    const err = (await request("/x").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.detail).toMatch(/Cannot reach the API/);
  });

  it("passes the user id as a query parameter on reads", async () => {
    const fn = mockFetch(200, []);
    await api.assessmentEvidence("u-9");
    expect((fn.mock.calls[0] as unknown as [string])[0]).toMatch(/\/assessments\/evidence\?user_id=u-9$/);
  });
});

describe("authentication", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });
  afterEach(() => window.sessionStorage.clear());

  it("sends the bearer token on API calls", async () => {
    const { setSession } = await import("./auth");
    setSession({ token: "tok-abc", user: { id: "u1", email: "a@example.com", display_name: null, is_admin: false } });
    const fn = mockFetch(200, []);
    await api.listRoadmaps("u1");
    const [, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok-abc");
  });

  it("sends no Authorization header on login and register", async () => {
    const { setSession } = await import("./auth");
    setSession({ token: "tok-abc", user: { id: "u1", email: "a@example.com", display_name: null, is_admin: false } });
    const fn = mockFetch(401, { detail: "Invalid credentials" });
    await expect(api.login("a@example.com", "nope-nope-nope")).rejects.toMatchObject({ status: 401 });
    const [, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>)["Authorization"]).toBeUndefined();
    expect((await import("./auth")).getToken()).toBe("tok-abc"); // a failed login must not end an existing session
  });

  it("a 401 on an authenticated call ends the session and flags it as expired", async () => {
    const auth = await import("./auth");
    auth.setSession({ token: "tok-abc", user: { id: "u1", email: "a@example.com", display_name: null, is_admin: false } });
    mockFetch(401, { detail: "Invalid or expired token" });
    await expect(api.me()).rejects.toMatchObject({ status: 401 });
    expect(auth.getSession()).toBeNull();
    expect(auth.consumeExpiredFlag()).toBe(true);
    expect(auth.consumeExpiredFlag()).toBe(false);
  });

  it("403, 404, 422 and 429 keep the session and surface the safe message", async () => {
    const auth = await import("./auth");
    auth.setSession({ token: "tok-abc", user: { id: "u1", email: "a@example.com", display_name: null, is_admin: false } });
    for (const [status, detail] of [
      [403, "user_id does not match the authenticated user"],
      [404, "Not found"],
      [422, "bad"],
      [429, "Too many attempts. Try again later."],
    ] as const) {
      mockFetch(status, { detail });
      await expect(api.me()).rejects.toMatchObject({ status, detail });
    }
    expect(auth.getToken()).toBe("tok-abc");
  });
});
