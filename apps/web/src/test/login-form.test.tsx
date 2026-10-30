import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm } from "@/components/login-form";
import { ApiError, api } from "@/lib/api";
import { EXPIRED_FLAG, clearSession, getSession } from "@/lib/auth";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => "/login" }));

const token = {
  access_token: "tok-1",
  token_type: "bearer",
  expires_in: 3600,
  user: { id: "u1", email: "a@example.com", display_name: "A", is_admin: false },
};

beforeEach(() => replace.mockReset());
afterEach(() => {
  vi.restoreAllMocks();
  clearSession();
  window.sessionStorage.clear();
});

describe("LoginForm", () => {
  it("signs in, stores the session and goes to the dashboard", async () => {
    const login = vi.spyOn(api, "login").mockResolvedValue(token);
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(login).toHaveBeenCalledWith("a@example.com", "correct horse battery");
    expect(getSession()?.user.id).toBe("u1");
    expect(window.localStorage.length).toBe(0);
  });

  it("shows the server's message on bad credentials and stays on the page", async () => {
    vi.spyOn(api, "login").mockRejectedValue(new ApiError(401, "Invalid credentials"));
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid credentials");
    expect(getSession()).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows the throttling message on 429", async () => {
    vi.spyOn(api, "login").mockRejectedValue(new ApiError(429, "Too many attempts. Try again later."));
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });

  it("registers a new account and signs in", async () => {
    const register = vi.spyOn(api, "register").mockResolvedValue(token);
    render(<LoginForm />);
    await userEvent.click(screen.getByRole("button", { name: /Create an account/ }));
    await userEvent.type(screen.getByLabelText(/Display name/), "A");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(register).toHaveBeenCalledWith({ email: "a@example.com", password: "correct horse battery", display_name: "A" });
  });

  it("tells the user when the session expired", async () => {
    window.sessionStorage.setItem(EXPIRED_FLAG, "1");
    render(<LoginForm />);
    expect(await screen.findByRole("status")).toHaveTextContent("session expired");
  });
});
