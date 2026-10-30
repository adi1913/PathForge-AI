import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";
import { clearSession, getSession, setSession } from "@/lib/auth";

const replace = vi.fn();
let pathname = "/";
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => pathname }));
vi.mock("next/link", () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));

beforeEach(() => {
  replace.mockReset();
  pathname = "/";
  vi.spyOn(api, "health").mockResolvedValue({ status: "ok", demo_mode: true });
});
afterEach(() => {
  vi.restoreAllMocks();
  clearSession();
  window.sessionStorage.clear();
});

const user = { id: "u1", email: "a@example.com", display_name: "Asha", is_admin: false };

describe("AppShell", () => {
  it("redirects to /login and hides the app when signed out", async () => {
    render(<AppShell>secret page</AppShell>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("secret page")).toBeNull();
  });

  it("shows the signed-in user and no manual user-id input", async () => {
    setSession({ token: "t", user });
    vi.spyOn(api, "me").mockResolvedValue(user);
    render(<AppShell>dashboard</AppShell>);
    expect(await screen.findByText("dashboard")).toBeInTheDocument();
    expect(screen.getByText("Asha")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Active user id/i)).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it("signs out: discards the session and goes to /login", async () => {
    setSession({ token: "t", user });
    vi.spyOn(api, "me").mockResolvedValue(user);
    render(<AppShell>dashboard</AppShell>);
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(getSession()).toBeNull();
    expect(replace).toHaveBeenCalledWith("/login");
  });

  it("an expired token (401 from /auth/me) sends the user back to /login", async () => {
    setSession({ token: "old", user });
    vi.spyOn(api, "me").mockImplementation(async () => {
      const { expireSession } = await import("@/lib/auth");
      expireSession();
      throw new Error("401");
    });
    render(<AppShell>dashboard</AppShell>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("renders the login page without the app chrome or a redirect loop", () => {
    pathname = "/login";
    render(<AppShell>login form</AppShell>);
    expect(screen.getByText("login form")).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });
});
