import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MentorPage from "@/app/mentor/page";
import { api, type S } from "@/lib/api";
import { clearSession, setSession } from "@/lib/auth";

vi.mock("next/link", () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));

const reply: S["MentorReply"] = {
  session_id: "s1",
  user_message_id: "m1",
  mentor_message_id: "m2",
  intent: "explain",
  answer: "Here is what the knowledge base says:\n- RAG retrieves documents. [1]",
  answer_source: "demo_rules",
  citations: [{ index: 1, title: "RAG intro", source: null, heading: null, document_id: "d1", chunk_id: "c1", score: 0.8 }],
  missing_context: ["You have no recorded level for RAG."],
  actions: [],
  assessment: null,
};

beforeEach(() => {
  setSession({ token: "t", user: { id: "u1", email: "u1@example.com", display_name: null, is_admin: false } });
  vi.spyOn(api, "listMentorSessions").mockResolvedValue([]);
  vi.spyOn(api, "createMentorSession").mockResolvedValue({
    id: "s1",
    user_id: "u1",
    title: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    message_count: 0,
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  clearSession();
});

describe("Mentor page", () => {
  it("sends a message and shows citations and missing context from the reply", async () => {
    const send = vi.spyOn(api, "sendMentorMessage").mockResolvedValue(reply);
    render(<MentorPage />);
    await userEvent.type(await screen.findByLabelText("Message"), "Explain RAG");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/RAG retrieves documents/)).toBeInTheDocument();
    expect(send).toHaveBeenCalledWith("s1", "u1", "Explain RAG");
    expect(screen.getByRole("list", { name: "Sources" })).toHaveTextContent("RAG intro");
    expect(screen.getByRole("note")).toHaveTextContent("You have no recorded level for RAG.");
  });

  it("shows the API error and keeps the input when sending fails", async () => {
    vi.spyOn(api, "sendMentorMessage").mockRejectedValue(new (await import("@/lib/api")).ApiError(422, "Message too long"));
    render(<MentorPage />);
    await userEvent.type(await screen.findByLabelText("Message"), "hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Message too long");
    expect(screen.getByLabelText("Message")).toHaveValue("hello");
  });
});
